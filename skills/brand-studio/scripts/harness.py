#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

VALUE_FLAGS = {
    "--brand",
    "--theme",
    "--outputs-dir",
}
DEFAULT_MARKETING_ROOT = "marketing"
DEFAULT_SCRATCH_DIR = ".harness/out"
DEFAULT_APPROVED_DIR = "marketing/approved"
DEFAULT_RELEASE_STYLE = "launch-hero"
DEFAULT_RELEASE_DELIVERABLES = [
    ("release-card", (1200, 630)),
    ("release-square", (1080, 1080)),
    ("release-poster", (1080, 1920)),
]
SLUG_PART_RE = re.compile(r"[^a-z0-9]+")
CHANGELOG_VERSION_HEADING_RE = re.compile(
    r"^#{2,6}\s+(?:\[?[vV]?([0-9]+\.[0-9]+\.[0-9][0-9A-Za-z.+-]*)\]?)"
    r"(?:\s|$|-)"
)
CHANGELOG_LINK_DEF_RE = re.compile(r"^\[[^\]]+\]:\s")
IGNORED_SCAN_DIRS = {
    ".git",
    ".harness",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
}
RELEASE_VALUE_OPTIONS = {
    "--version",
    "--name",
    "--style",
    "--headline",
    "--changelog",
    "--campaign",
    "--copy",
}


def main() -> int:
    args, metadata_path = extract_option(sys.argv[1:], "--metadata")
    metadata = load_metadata(metadata_path) if metadata_path else {}

    if args[:1] == ["plan"]:
        print_plan(metadata)
        return 0

    if args[:1] == ["state"]:
        return print_state(args[1:], metadata, metadata_path)

    if args[:1] == ["check"]:
        return check_project(args[1:], metadata, metadata_path)

    if args[:1] == ["bootstrap"]:
        return bootstrap_project(args[1:], metadata, metadata_path)

    if args[:1] == ["release-campaign"]:
        return release_campaign(args[1:], metadata, metadata_path)

    if args[:1] == ["release-copy"]:
        return release_copy(args[1:], metadata, metadata_path)

    if args[:1] == ["release-render"]:
        return release_render(args[1:], metadata, metadata_path)

    if args[:1] == ["--resolve"]:
        resolution = bundled_cli_command()
        print(" ".join(shell_quote(part) for part in resolution))
        return 0

    command_args = apply_metadata_args(args, metadata)
    command = bundled_cli_command()
    completed = subprocess.run([*command, *command_args], check=False)
    return completed.returncode


def bundled_cli_command() -> list[str]:
    return [sys.executable, str(Path(__file__).resolve().parent / "cli.py")]


def apply_metadata_args(args: list[str], metadata: dict[str, Any]) -> list[str]:
    if not metadata or not args:
        return args

    command = args[0]
    project_root = project_root_for(metadata)
    next_args = list(args)

    if command in {"validate", "render"}:
        campaign = metadata_path(metadata, project_root, "campaign", "path")
        if campaign and not has_positional(next_args, start=1):
            next_args.insert(1, campaign)
        add_option(next_args, "--theme", theme_source_path(metadata, project_root))

    if command == "render":
        add_option(
            next_args,
            "--outputs-dir",
            metadata_path(metadata, project_root, "artifacts", "scratch"),
        )

    return next_args


def bootstrap_project(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    write = False
    with_example = False
    target = "."
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token == "--write":
            write = True
        elif token == "--with-example":
            with_example = True
        elif token in {"-h", "--help"}:
            print(
                "usage: harness.py bootstrap [--metadata FILE] "
                "[--write] [--with-example] [target-dir]"
            )
            return 0
        elif token.startswith("-"):
            raise SystemExit(f"unknown bootstrap option: {token}")
        else:
            target = token

    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    plan = project_paths(metadata, project_root)
    dirs = [
        plan["marketing_root"],
        plan["campaigns_dir"],
        plan["references_dir"],
        plan["plans_dir"],
        plan["asset_index"].parent,
        plan["scratch_dir"],
        plan["approved_dir"],
        plan["accepted_state"].parent,
    ]

    if write:
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
        if with_example:
            copy_example(plan["marketing_root"])

    print_kv(
        {
            "mode": "write" if write else "dry-run",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "marketing_root": plan["marketing_root"],
            "campaigns_dir": plan["campaigns_dir"],
            "references_dir": plan["references_dir"],
            "plans_dir": plan["plans_dir"],
            "asset_index": plan["asset_index"],
            "scratch_dir": plan["scratch_dir"],
            "approved_dir": plan["approved_dir"],
            "accepted_state": plan["accepted_state"],
            "created": " ".join(str(path) for path in dirs) if write else "",
            "copied_example": str(plan["marketing_root"] / "examples" / "codefox")
            if write and with_example
            else "",
        }
    )
    if not write:
        print(
            "dry_run_note=pass --write to create directories; "
            "no .gitignore or .gitattributes edits are made"
        )
    return 0


def release_campaign(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py release-campaign [--metadata FILE] "
        "[--write] [--force] [--version VERSION] [--name NAME] "
        "[--style STYLE] [--headline TEXT] [--changelog FILE] "
        "[--copy FILE] [--campaign FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=True,
        command_name="release-campaign",
    )
    plan = build_release_campaign_plan(metadata, options)
    if isinstance(plan, str):
        print(plan, file=sys.stderr)
        return 1

    if options["write"]:
        write_result = write_release_campaign_file(
            plan["campaign_path"],
            plan["campaign_yaml"],
            force=bool(options["force"]),
        )
        if write_result["error"]:
            print(write_result["error"], file=sys.stderr)
            return 1
    else:
        write_result = {"status": "dry-run", "error": ""}

    print_release_summary(
        plan,
        metadata_path=metadata_path,
        mode="write" if options["write"] else "dry-run",
        campaign_status=write_result["status"],
    )
    if not options["write"]:
        print("\n" + str(plan["campaign_yaml"]).rstrip())
    return 0


def release_copy(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py release-copy [--metadata FILE] "
        "[--write] [--force] [--version VERSION] [--name NAME] "
        "[--headline TEXT] [--changelog FILE] [--copy FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=True,
        command_name="release-copy",
    )
    plan = build_release_copy_plan(metadata, options)
    if isinstance(plan, str):
        print(plan, file=sys.stderr)
        return 1

    if options["write"]:
        write_result = write_text_asset(
            Path(str(plan["copy_path"])),
            str(plan["copy_yaml"]),
            force=bool(options["force"]),
        )
        if write_result["error"]:
            print(write_result["error"], file=sys.stderr)
            return 1
    else:
        write_result = {"status": "dry-run", "error": ""}

    print_release_copy_summary(
        plan,
        metadata_path=metadata_path,
        mode="write" if options["write"] else "dry-run",
        copy_status=write_result["status"],
    )
    if not options["write"]:
        print("\n" + str(plan["copy_yaml"]).rstrip())
    return 0


def release_render(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py release-render [--metadata FILE] "
        "[--force] [--version VERSION] [--name NAME] [--style STYLE] "
        "[--headline TEXT] [--changelog FILE] [--copy FILE] "
        "[--campaign FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=False,
        command_name="release-render",
    )
    plan = build_release_campaign_plan(metadata, options)
    if isinstance(plan, str):
        print(plan, file=sys.stderr)
        return 1

    if plan["copy_source"] == "file":
        copy_result = {"status": "existing", "error": ""}
    else:
        copy_result = write_text_asset(
            Path(str(plan["copy_path"])),
            str(plan["copy_yaml"]),
            force=bool(options["force"]),
        )
        if copy_result["error"]:
            print(copy_result["error"], file=sys.stderr)
            return 1

    write_result = write_release_campaign_file(
        plan["campaign_path"],
        plan["campaign_yaml"],
        force=bool(options["force"]),
    )
    if write_result["error"]:
        print(write_result["error"], file=sys.stderr)
        return 1

    render_args = apply_metadata_args(
        ["render", str(plan["campaign_path"]), "--dry-run"],
        metadata,
    )
    completed = subprocess.run([*bundled_cli_command(), *render_args], check=False)
    if completed.returncode != 0:
        return completed.returncode

    producer_context_result = write_release_producer_context(plan, metadata)
    if producer_context_result["error"]:
        print(producer_context_result["error"], file=sys.stderr)
        return 1

    print_release_summary(
        plan,
        metadata_path=metadata_path,
        mode="render",
        campaign_status=write_result["status"],
        copy_status=copy_result["status"],
        producer_context_path=Path(str(producer_context_result["path"])),
        producer_skill=str(producer_context_result["producer_skill"]),
    )
    return 0


def parse_release_options(
    args: list[str],
    *,
    usage: str,
    allow_write: bool,
    command_name: str,
) -> dict[str, object]:
    write = False
    force = False
    target = "."
    version: str | None = None
    name: str | None = None
    style: str | None = None
    headline: str | None = None
    changelog_value: str | None = None
    campaign_path_value: str | None = None
    copy_path_value: str | None = None
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token == "--write" and allow_write:
            write = True
        elif token == "--write":
            raise SystemExit(f"unknown {command_name} option: --write")
        elif token == "--force":
            force = True
        elif token in RELEASE_VALUE_OPTIONS:
            if not remaining:
                raise SystemExit(f"{token} requires a value")
            value = remaining.pop(0)
            if token == "--version":
                version = value
            elif token == "--name":
                name = value
            elif token == "--style":
                style = value
            elif token == "--headline":
                headline = value
            elif token == "--changelog":
                changelog_value = value
            elif token == "--campaign":
                campaign_path_value = value
            elif token == "--copy":
                copy_path_value = value
        elif token.startswith("--version="):
            version = token.split("=", 1)[1]
        elif token.startswith("--name="):
            name = token.split("=", 1)[1]
        elif token.startswith("--style="):
            style = token.split("=", 1)[1]
        elif token.startswith("--headline="):
            headline = token.split("=", 1)[1]
        elif token.startswith("--changelog="):
            changelog_value = token.split("=", 1)[1]
        elif token.startswith("--campaign="):
            campaign_path_value = token.split("=", 1)[1]
        elif token.startswith("--copy="):
            copy_path_value = token.split("=", 1)[1]
        elif token in {"-h", "--help"}:
            print(usage)
            raise SystemExit(0)
        elif token.startswith("-"):
            raise SystemExit(f"unknown {command_name} option: {token}")
        else:
            target = token

    return {
        "write": write,
        "force": force,
        "target": target,
        "version": version,
        "name": name,
        "style": style,
        "headline": headline,
        "changelog_value": changelog_value,
        "campaign_path_value": campaign_path_value,
        "copy_path_value": copy_path_value,
    }


def build_release_copy_plan(
    metadata: dict[str, Any],
    options: dict[str, object],
    *,
    prefer_existing_copy: bool = False,
) -> dict[str, object] | str:
    target = str(options["target"])
    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    paths = project_paths(metadata, project_root)
    explicit_copy_path = (
        Path(resolve_project_path(project_root, options["copy_path_value"]))
        if options["copy_path_value"]
        else None
    )

    if prefer_existing_copy and explicit_copy_path and explicit_copy_path.is_file():
        return build_existing_release_copy_plan(
            project_root=project_root,
            copy_path=explicit_copy_path,
            options=options,
            changelog_count=0,
        )

    changelog_entries, changelog_error = read_latest_changelog_entries(
        project_root,
        options["changelog_value"],
    )
    if changelog_error:
        return changelog_error
    if not changelog_entries:
        return f"{project_root}: no CHANGELOG.md release entries found"

    release_version = options["version"] or infer_changelog_version(changelog_entries)
    copy_asset = build_release_copy_asset(
        changelog_entries,
        version=str(release_version or ""),
        headline=str(options["headline"] or ""),
    )
    copy_yaml = build_release_copy_yaml(copy_asset)
    source_count = len(changelog_entries)

    campaign_name = slugify(
        str(options["name"] or release_campaign_name(release_version)),
        "release-update",
    )
    copy_path = explicit_copy_path or paths["scratch_dir"] / campaign_name / "copy.yaml"
    if prefer_existing_copy and copy_path.is_file():
        return build_existing_release_copy_plan(
            project_root=project_root,
            copy_path=copy_path,
            options=options,
            changelog_count=len(changelog_entries),
        )

    return {
        "project_root": project_root,
        "changelog_count": len(changelog_entries),
        "release_source": "changelog",
        "source_count": source_count,
        "copy_source": "generated",
        "campaign_name": campaign_name,
        "copy_path": copy_path,
        "copy_yaml": copy_yaml,
        "copy_asset": copy_asset,
        "version": release_version or "",
        "style": options["style"] or DEFAULT_RELEASE_STYLE,
    }


def build_release_campaign_plan(
    metadata: dict[str, Any],
    options: dict[str, object],
) -> dict[str, object] | str:
    copy_plan = build_release_copy_plan(metadata, options, prefer_existing_copy=True)
    if isinstance(copy_plan, str):
        return copy_plan

    target = str(options["target"])
    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    paths = project_paths(metadata, project_root)
    copy_asset = copy_plan["copy_asset"]
    if not isinstance(copy_asset, dict):
        return "release copy asset is invalid"

    campaign_path = (
        Path(resolve_project_path(project_root, options["campaign_path_value"]))
        if options["campaign_path_value"]
        else paths["campaigns_dir"] / f"{copy_plan['campaign_name']}.campaign.yaml"
    )
    campaign_yaml = build_release_campaign_yaml(
        name=str(copy_plan["campaign_name"]),
        brief=release_copy_brief(copy_asset),
        style=str(options["style"] or DEFAULT_RELEASE_STYLE),
        headline=str(copy_asset["headline"]),
        subject=release_copy_subject(copy_asset),
    )
    return {
        **copy_plan,
        "campaign_path": campaign_path,
        "campaign_yaml": campaign_yaml,
        "output_dir": paths["scratch_dir"] / str(copy_plan["campaign_name"]),
    }


def build_existing_release_copy_plan(
    *,
    project_root: Path,
    copy_path: Path,
    options: dict[str, object],
    changelog_count: int,
) -> dict[str, object] | str:
    copy_asset, copy_yaml, error = read_release_copy_asset(copy_path)
    if error:
        return error
    if copy_asset is None:
        return f"{copy_path}: release copy asset is empty"
    release_version = str(options["version"] or copy_asset.get("version") or "")
    campaign_name = slugify(
        str(options["name"] or release_campaign_name(release_version)),
        "release-update",
    )
    return {
        "project_root": project_root,
        "changelog_count": changelog_count,
        "release_source": "copy",
        "source_count": release_copy_source_count(copy_asset),
        "copy_source": "file",
        "campaign_name": campaign_name,
        "copy_path": copy_path,
        "copy_yaml": copy_yaml,
        "copy_asset": copy_asset,
        "version": release_version,
        "style": options["style"] or DEFAULT_RELEASE_STYLE,
    }


def read_release_copy_asset(path: Path) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "", f"{path}: unable to read release copy asset: {exc}"
    try:
        data = parse_yaml_document(raw)
    except Exception as exc:
        return None, raw, f"{path}: unable to parse release copy asset YAML: {exc}"
    if not isinstance(data, dict):
        return None, raw, f"{path}: release copy asset root must be an object"
    asset, error = normalize_release_copy_asset(data, path)
    return asset, raw, error


def normalize_release_copy_asset(
    data: dict[str, Any],
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if str(data.get("kind") or "") != "release_copy":
        return None, f"{path}: release copy asset kind must be release_copy"

    required = ["product", "release_theme", "headline", "subheadline"]
    for key in required:
        if not str(data.get(key) or "").strip():
            return None, f"{path}: release copy asset missing {key}"

    raw_points = data.get("key_points")
    if not isinstance(raw_points, list) or not raw_points:
        return None, f"{path}: release copy asset key_points must be a non-empty list"
    key_points: list[dict[str, str]] = []
    for index, raw_point in enumerate(raw_points, start=1):
        if not isinstance(raw_point, dict):
            return None, f"{path}: key_points[{index}] must be an object"
        title = str(raw_point.get("title") or "").strip()
        detail = str(raw_point.get("detail") or "").strip()
        if not title or not detail:
            return None, f"{path}: key_points[{index}] requires title and detail"
        key_points.append(
            {
                "title": title,
                "detail": detail,
                "source_package": str(raw_point.get("source_package") or "").strip(),
                "source_version": str(raw_point.get("source_version") or "").strip(),
            }
        )

    raw_visual = data.get("visual_direction")
    visual = raw_visual if isinstance(raw_visual, dict) else {}
    return {
        "schema_version": str(data.get("schema_version") or "1.0"),
        "kind": "release_copy",
        "product": str(data.get("product") or "").strip(),
        "version": str(data.get("version") or "").strip(),
        "release_theme": str(data.get("release_theme") or "").strip(),
        "headline": str(data.get("headline") or "").strip(),
        "subheadline": str(data.get("subheadline") or "").strip(),
        "key_points": key_points,
        "audience": release_copy_string_list(data.get("audience")),
        "visual_direction": {
            "mood": str(visual.get("mood") or "release marketing visual").strip(),
            "motifs": release_copy_string_list(visual.get("motifs")),
            "avoid": release_copy_string_list(visual.get("avoid")),
        },
        "sources": release_copy_sources(data.get("sources")),
    }, None


def release_copy_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def release_copy_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "package": str(item.get("package") or "").strip(),
                "version": str(item.get("version") or "").strip(),
                "path": str(item.get("path") or "").strip(),
            }
        )
    return sources


def release_copy_source_count(copy_asset: dict[str, Any]) -> int:
    sources = copy_asset.get("sources")
    if isinstance(sources, list) and sources:
        return len(sources)
    key_points = copy_asset.get("key_points")
    return len(key_points) if isinstance(key_points, list) else 0


def build_release_copy_asset(
    entries: list[dict[str, Any]],
    *,
    version: str,
    headline: str,
) -> dict[str, Any]:
    product = release_product_name(entries)
    key_points = release_key_points(entries)
    release_theme = infer_release_theme(key_points)
    return {
        "schema_version": "1.0",
        "kind": "release_copy",
        "product": product,
        "version": version,
        "release_theme": release_theme,
        "headline": headline or headline_from_theme(release_theme),
        "subheadline": subheadline_from_theme(product, version, release_theme),
        "key_points": key_points,
        "audience": [
            "terminal-first developers",
            "AI coding agent users",
            "multi-task workspace operators",
        ],
        "visual_direction": {
            "mood": "premium terminal workspace release",
            "motifs": [
                "dark terminal panes",
                "task rail",
                "tmux split layout",
                "orange kobe accent",
                "developer workflow board",
            ],
            "avoid": [
                "generic AI robot art",
                "fake app screenshots",
                "unreadable long changelog text",
                "busy abstract gradients",
            ],
        },
        "sources": [
            {
                "package": entry["package"],
                "version": entry["version"],
                "path": str(entry["path"]),
            }
            for entry in entries
        ],
    }


def release_product_name(entries: list[dict[str, Any]]) -> str:
    packages = [str(entry["package"]) for entry in entries if entry.get("package")]
    if not packages:
        return "release"
    if len(packages) == 1:
        return packages[0].split("/")[-1]
    names = [package.split("/")[-1] for package in packages]
    return names[0] if all(name == names[0] for name in names) else "release"


def release_key_points(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    for entry in entries:
        for summary in entry["summary"]:
            detail = shorten_sentence(str(summary), 180)
            points.append(
                {
                    "title": title_from_summary(detail),
                    "detail": detail,
                    "source_package": str(entry["package"]),
                    "source_version": str(entry["version"]),
                }
            )
    return points[:4]


def title_from_summary(summary: str) -> str:
    lower = summary.lower()
    if "task" in lower and ("engine" in lower or "prompt" in lower):
        return "Jump straight into the engine"
    if "tmux" in lower or "layout" in lower or "pane" in lower:
        return "Control layouts without losing work"
    if "board" in lower or "issue" in lower:
        return "Keep project work visible"
    if "web" in lower or "dashboard" in lower:
        return "Sharper web workspace"
    return shorten_sentence(summary, 54).rstrip(".")


def infer_release_theme(key_points: list[dict[str, str]]) -> str:
    joined = " ".join(
        point["title"].lower() + " " + point["detail"].lower() for point in key_points
    )
    if "tmux" in joined or "layout" in joined or "pane" in joined:
        return "Faster task starts, deeper workspace control"
    if "board" in joined or "issue" in joined:
        return "Cleaner project tracking for active work"
    if "web" in joined or "dashboard" in joined:
        return "A sharper browser workspace for coding agents"
    return "Release improvements for focused developer workflows"


def headline_from_theme(theme: str) -> str:
    return theme


def subheadline_from_theme(product: str, version: str, theme: str) -> str:
    prefix = f"{product} {version}" if version else product
    return f"{prefix} sharpens {theme.lower()}."


def shorten_sentence(text: str, limit: int) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    truncated = collapsed[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;: ")
    return f"{truncated}..."


def build_release_copy_yaml(copy_asset: dict[str, Any]) -> str:
    lines = [
        f"schema_version: {yaml_string(str(copy_asset['schema_version']))}",
        f"kind: {yaml_string(str(copy_asset['kind']))}",
        f"product: {yaml_string(str(copy_asset['product']))}",
        f"version: {yaml_string(str(copy_asset['version']))}",
        f"release_theme: {yaml_string(str(copy_asset['release_theme']))}",
        f"headline: {yaml_string(str(copy_asset['headline']))}",
        f"subheadline: {yaml_string(str(copy_asset['subheadline']))}",
        "key_points:",
    ]
    for point in copy_asset["key_points"]:
        lines.extend(
            [
                f"  - title: {yaml_string(str(point['title']))}",
                f"    detail: {yaml_string(str(point['detail']))}",
                f"    source_package: {yaml_string(str(point['source_package']))}",
                f"    source_version: {yaml_string(str(point['source_version']))}",
            ]
        )
    lines.append("audience:")
    for item in copy_asset["audience"]:
        lines.append(f"  - {yaml_string(str(item))}")
    visual = copy_asset["visual_direction"]
    lines.extend(
        [
            "visual_direction:",
            f"  mood: {yaml_string(str(visual['mood']))}",
            "  motifs:",
            *[f"    - {yaml_string(str(item))}" for item in visual["motifs"]],
            "  avoid:",
            *[f"    - {yaml_string(str(item))}" for item in visual["avoid"]],
            "sources:",
        ]
    )
    for source in copy_asset["sources"]:
        lines.extend(
            [
                f"  - package: {yaml_string(str(source['package']))}",
                f"    version: {yaml_string(str(source['version']))}",
                f"    path: {yaml_string(str(source['path']))}",
            ]
        )
    return "\n".join(lines) + "\n"


def release_copy_brief(copy_asset: dict[str, Any]) -> str:
    return (
        f"Release notes page for {copy_asset['product']} {copy_asset['version']}: "
        f"{copy_asset['release_theme']}"
    )


def release_copy_subject(copy_asset: dict[str, Any]) -> str:
    product = str(copy_asset["product"])
    version = str(copy_asset["version"])
    lines = [
        f"Render a release notes page for {product} {version}.",
        "The release notes are the main subject, not a decorative side panel.",
        "Composition: premium product changelog page with a header, metadata chips, "
        "and a chronological release list.",
        "Use the copy language from the headline and changelog summaries; do not translate it.",
        "",
        "Visible release notes structure:",
        f'- Page title/headline: "{copy_asset["headline"]}"',
        f'- Supporting copy: "{copy_asset["subheadline"]}"',
        f'- Metadata chip: "Latest {version}"',
        '- Source chip: "CHANGELOG.md"',
        '- Section label: "RELEASES"',
        f'- Version heading: "v{version}"',
        '- Change group label: "Patch Changes"',
        "",
        "Chronological release list rows from CHANGELOG.md:",
    ]
    for point in copy_asset["key_points"]:
        lines.append(
            f'- Row title: "{point["title"]}" | Row detail: "{point["detail"]}"'
        )
    visual = copy_asset["visual_direction"]
    lines.extend(
        [
            "",
            "The release notes page should occupy most of the image. "
            "Do not make the changelog a small side panel.",
            "Avoid terminal-app hero screenshots unless they are tiny supporting motifs.",
            f"Visual mood: {visual['mood']}",
            "Motifs: " + ", ".join(str(item) for item in visual["motifs"]),
            "Avoid: " + ", ".join(str(item) for item in visual["avoid"]),
        ]
    )
    return "\n".join(lines)


def write_release_campaign_file(
    campaign_path: Path,
    campaign_yaml: str,
    *,
    force: bool,
) -> dict[str, str]:
    if campaign_path.exists():
        existing = campaign_path.read_text(encoding="utf-8")
        if existing == campaign_yaml:
            return {"status": "unchanged", "error": ""}
        if not force:
            return {
                "status": "blocked",
                "error": f"{campaign_path}: already exists; pass --force to overwrite",
            }
        status = "overwritten"
    else:
        status = "created"
    campaign_path.parent.mkdir(parents=True, exist_ok=True)
    campaign_path.write_text(campaign_yaml, encoding="utf-8")
    return {"status": status, "error": ""}


def write_text_asset(path: Path, content: str, *, force: bool) -> dict[str, str]:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return {"status": "unchanged", "error": ""}
        if not force:
            return {
                "status": "blocked",
                "error": f"{path}: already exists; pass --force to overwrite",
            }
        status = "overwritten"
    else:
        status = "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"status": status, "error": ""}


def write_release_producer_context(
    plan: dict[str, object],
    metadata: dict[str, Any],
) -> dict[str, object]:
    output_dir = Path(str(plan["output_dir"]))
    run_lock_path = output_dir / "run.lock.json"
    context_path = output_dir / "producer-context.json"
    producer_skill = string_at(metadata, "skills", "image") or ""
    if not run_lock_path.is_file():
        return {
            "path": context_path,
            "producer_skill": producer_skill,
            "error": f"{run_lock_path}: dry-run run lock not found",
        }

    try:
        run_lock = json.loads(run_lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": context_path,
            "producer_skill": producer_skill,
            "error": f"{run_lock_path}: cannot read dry-run run lock: {exc}",
        }

    producer = run_lock.get("producer") if isinstance(run_lock, dict) else {}
    producer = producer if isinstance(producer, dict) else {}
    params = producer.get("params") if isinstance(producer.get("params"), dict) else {}
    output_format = str(params.get("output_format") or "png")

    assets: list[dict[str, Any]] = []
    raw_assets = run_lock.get("assets") if isinstance(run_lock, dict) else []
    if isinstance(raw_assets, list):
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, dict):
                continue
            asset_id = str(raw_asset.get("id") or "")
            if not asset_id:
                continue
            target_file = f"{asset_id}.{output_format}"
            size = raw_asset.get("size")
            assets.append(
                {
                    "id": asset_id,
                    "size": size if isinstance(size, list) else [],
                    "prompt": str(raw_asset.get("prompt") or ""),
                    "negative_prompt": str(raw_asset.get("negative_prompt") or ""),
                    "dry_run_file": str(raw_asset.get("file") or ""),
                    "target_file": target_file,
                    "target_path": str(output_dir / target_file),
                }
            )

    context = {
        "schema_version": "1.0",
        "kind": "producer_context",
        "capability": "image",
        "producer_skill": producer_skill,
        "project_root": str(plan["project_root"]),
        "copy": str(plan["copy_path"]),
        "campaign": str(plan["campaign_path"]),
        "run_lock": str(run_lock_path),
        "output_dir": str(output_dir),
        "producer": producer,
        "resolved_style": run_lock.get("resolved_style", {}) if isinstance(run_lock, dict) else {},
        "assets": assets,
    }
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"path": context_path, "producer_skill": producer_skill, "error": ""}


def print_release_summary(
    plan: dict[str, object],
    *,
    metadata_path: str | None,
    mode: str,
    campaign_status: str,
    copy_status: str | None = None,
    producer_context_path: Path | None = None,
    producer_skill: str | None = None,
) -> None:
    values = {
        "mode": mode,
        "metadata": metadata_path or "",
        "project_root": plan["project_root"],
        "release_source": plan["release_source"],
        "source_count": plan["source_count"],
        "changelog_count": plan["changelog_count"],
        "copy": plan["copy_path"],
        "campaign": plan["campaign_path"],
        "campaign_status": campaign_status,
        "campaign_name": plan["campaign_name"],
        "version": plan["version"],
        "style": plan["style"],
    }
    if copy_status is not None:
        values["copy_status"] = copy_status
    if producer_context_path is not None:
        values["producer_context"] = producer_context_path
    if producer_skill is not None:
        values["producer_skill"] = producer_skill
    print_kv(values)


def print_release_copy_summary(
    plan: dict[str, object],
    *,
    metadata_path: str | None,
    mode: str,
    copy_status: str,
) -> None:
    print_kv(
        {
            "mode": mode,
            "metadata": metadata_path or "",
            "project_root": plan["project_root"],
            "release_source": plan["release_source"],
            "source_count": plan["source_count"],
            "changelog_count": plan["changelog_count"],
            "copy": plan["copy_path"],
            "copy_status": copy_status,
            "campaign_name": plan["campaign_name"],
            "version": plan["version"],
        }
    )


def read_latest_changelog_entries(
    project_root: Path,
    changelog_value: object | None,
) -> tuple[list[dict[str, Any]], str | None]:
    changelog_files = discover_changelog_files(project_root, changelog_value)
    if changelog_value and not changelog_files:
        return [], f"{resolve_project_path(project_root, changelog_value)}: changelog not found"

    entries: list[dict[str, Any]] = []
    for path in changelog_files:
        entry = read_latest_changelog_entry(path)
        if entry:
            entries.append(entry)
    return entries, None


def discover_changelog_files(project_root: Path, changelog_value: object | None) -> list[Path]:
    if changelog_value:
        path = Path(resolve_project_path(project_root, changelog_value))
        return [path] if path.is_file() else []

    candidates: list[Path] = [project_root / "CHANGELOG.md"]
    for package_dir in discover_package_dirs(project_root):
        candidates.append(package_dir / "CHANGELOG.md")
    candidates.extend(walk_changelog_files(project_root))
    return [path for path in unique_paths(candidates) if path.is_file()]


def discover_package_dirs(project_root: Path) -> list[Path]:
    package_dirs = [project_root] if (project_root / "package.json").is_file() else []
    package_json = project_root / "package.json"
    workspace_patterns: list[str] = []
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        workspaces = data.get("workspaces") if isinstance(data, dict) else None
        if isinstance(workspaces, list):
            workspace_patterns.extend(str(item) for item in workspaces)
        elif isinstance(workspaces, dict) and isinstance(workspaces.get("packages"), list):
            workspace_patterns.extend(str(item) for item in workspaces["packages"])
    workspace_patterns.extend(["packages/*", "apps/*", "libs/*"])

    for pattern in workspace_patterns:
        for path in project_root.glob(pattern):
            if path.is_dir() and (path / "package.json").is_file():
                package_dirs.append(path)
    return unique_paths(package_dirs)


def walk_changelog_files(project_root: Path) -> list[Path]:
    matches: list[Path] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_SCAN_DIRS]
        if "CHANGELOG.md" in files:
            matches.append(Path(root) / "CHANGELOG.md")
    return matches


def read_latest_changelog_entry(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        version = changelog_version_from_heading(line)
        if not version:
            continue
        end = next_changelog_release_index(lines, index + 1)
        summary = summarize_changelog_body(lines[index + 1 : end], path)
        return {
            "path": path,
            "package": changelog_package_name(path, lines),
            "version": version,
            "summary": summary,
        }
    return None


def changelog_version_from_heading(line: str) -> str | None:
    match = CHANGELOG_VERSION_HEADING_RE.match(line.strip())
    return match.group(1) if match else None


def next_changelog_release_index(lines: list[str], start: int) -> int:
    for index in range(start, len(lines)):
        if changelog_version_from_heading(lines[index]):
            return index
    return len(lines)


def changelog_package_name(path: Path, lines: list[str]) -> str:
    package_json = path.parent / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        name = data.get("name") if isinstance(data, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()

    for line in lines:
        if not line.startswith("# "):
            continue
        title = line[2:].strip()
        if title and title.lower() not in {"changelog", "change log"}:
            return title
    return path.parent.name


def summarize_changelog_body(lines: list[str], path: Path) -> list[str]:
    summaries: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        if CHANGELOG_LINK_DEF_RE.match(stripped):
            continue
        line = clean_markdown_summary_line(stripped)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        if line:
            summaries.append(line)
        if len(summaries) >= 6:
            break
    return summaries or [f"Release notes from {path.name}"]


def infer_changelog_version(entries: list[dict[str, Any]]) -> str | None:
    versions = {str(entry["version"]) for entry in entries if entry.get("version")}
    if len(versions) == 1:
        return next(iter(versions))
    return None


def build_changelog_release_brief(entries: list[dict[str, Any]]) -> str:
    releases = ", ".join(
        f"{entry['package']} v{entry['version']}" for entry in entries[:6]
    )
    return f"Release marketing visual generated from CHANGELOG.md: {releases}"


def build_changelog_release_subject(entries: list[dict[str, Any]]) -> str:
    bullets: list[str] = []
    multiple = len(entries) > 1
    for entry in entries:
        prefix = f"{entry['package']} v{entry['version']}: " if multiple else ""
        for line in entry["summary"]:
            bullets.append(f"- {prefix}{line}")
    return "Product release notes from CHANGELOG.md:\n" + "\n".join(bullets[:12])


def clean_markdown_summary_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line or line.startswith("<!--"):
        return ""
    line = re.sub(r"^#{1,6}\s+", "", line)
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.)]\s+", "", line)
    return line.strip()


def release_campaign_name(version: str | None) -> str:
    if version:
        return f"release-v{version}"
    return "release-update"


def release_campaign_headline(version: str | None) -> str:
    if version:
        return f"v{version} Release"
    return "Release Update"


def build_release_campaign_yaml(
    *,
    name: str,
    brief: str,
    style: str,
    headline: str,
    subject: str,
) -> str:
    lines = [
        f"name: {yaml_string(name)}",
        f"brief: {yaml_string(brief)}",
        f"style: {yaml_string(style)}",
        "content:",
        f"  headline: {yaml_string(headline)}",
        "  subject: |-",
        *indent_block(subject, 4),
        "deliverables:",
    ]
    for asset_id, size in DEFAULT_RELEASE_DELIVERABLES:
        lines.extend(
            [
                f"  - id: {yaml_string(asset_id)}",
                f"    size: [{size[0]}, {size[1]}]",
            ]
        )
    return "\n".join(lines) + "\n"


def indent_block(value: str, spaces: int) -> list[str]:
    prefix = " " * spaces
    return [prefix + line if line else prefix for line in value.splitlines()]


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def slugify(value: str, default: str) -> str:
    slug = SLUG_PART_RE.sub("-", value.strip().lower()).strip("-")
    return slug or default


def check_project(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    target = args[0] if args else "."
    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    paths = project_paths(metadata, project_root)
    yaml_ready = python_module_available("yaml")

    print_kv(
        {
            "project_root": project_root,
            "metadata": metadata_path or "",
            "marketing_root": paths["marketing_root"],
            "marketing_root_exists": paths["marketing_root"].exists(),
            "theme": theme_source_path_value(metadata) or "",
            "theme_exists": Path(
                theme_source_path_value(metadata) or ""
            ).exists()
            if theme_source_path_value(metadata)
            else False,
            "campaign": metadata_path_value(metadata, "campaign", "path") or "",
            "campaign_exists": Path(
                metadata_path_value(metadata, "campaign", "path") or ""
            ).exists()
            if metadata_path_value(metadata, "campaign", "path")
            else False,
            "scratch_dir": paths["scratch_dir"],
            "approved_dir": paths["approved_dir"],
            "plans_dir": paths["plans_dir"],
            "asset_index": paths["asset_index"],
            "asset_index_exists": paths["asset_index"].exists(),
            "directory_state_file": paths["directory_state_file"],
            "accepted_state": paths["accepted_state"],
            "accepted_state_exists": paths["accepted_state"].exists(),
            "bundled_cli": Path(__file__).resolve().parent / "cli.py",
            "yaml_ready": yaml_ready,
            "live_render_ready": False,
            "live_render_note": "use an external producer skill with dry-run context",
            "launcher_ready": yaml_ready,
        }
    )
    return 0 if yaml_ready else 1


def print_plan(metadata: dict[str, Any]) -> None:
    project_root = project_root_for(metadata)
    paths = project_paths(metadata, project_root)
    print_kv(
        {
            "project_root": project_root,
            "marketing_root": paths["marketing_root"],
            "campaigns_dir": paths["campaigns_dir"],
            "references_dir": paths["references_dir"],
            "plans_dir": paths["plans_dir"],
            "asset_index": paths["asset_index"],
            "directory_state_file": paths["directory_state_file"],
            "scratch_dir": paths["scratch_dir"],
            "approved_dir": paths["approved_dir"],
            "accepted_state": paths["accepted_state"],
            "theme": theme_source_path_value(metadata) or "",
            "campaign": metadata_path_value(metadata, "campaign", "path") or "",
            "allow_root_workspace_bootstrap": bool_at(
                metadata, False, "policy", "allowRootWorkspaceBootstrap"
            ),
        }
    )


def print_state(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    target = "."
    pretty = True
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token == "--compact":
            pretty = False
        elif token in {"-h", "--help"}:
            print("usage: harness.py state [--metadata FILE] [--compact] [target-dir]")
            return 0
        elif token.startswith("-"):
            raise SystemExit(f"unknown state option: {token}")
        else:
            target = token

    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    snapshot = collect_state_snapshot(metadata, project_root, metadata_path)
    print(json.dumps(snapshot, indent=2 if pretty else None, sort_keys=True))
    return 1 if snapshot["errors"] else 0


def project_paths(metadata: dict[str, Any], project_root: Path) -> dict[str, Path]:
    marketing_root = path_at(
        metadata, project_root, DEFAULT_MARKETING_ROOT, "project", "marketingRoot"
    )
    scratch_dir = path_at(metadata, project_root, DEFAULT_SCRATCH_DIR, "artifacts", "scratch")
    approved_dir = path_at(metadata, project_root, DEFAULT_APPROVED_DIR, "artifacts", "approved")
    plans_dir = path_at(metadata, project_root, "marketing/plans", "state", "plans")
    asset_index = path_at(
        metadata,
        project_root,
        "marketing/asset-state.yaml",
        "state",
        "assetIndex",
    )
    accepted_state = path_at(
        metadata,
        project_root,
        "marketing/accepted.yaml",
        "state",
        "accepted",
    )
    directory_state_file = string_at(metadata, "state", "directoryStateFile") or "asset-state.yaml"
    campaigns_value = theme_metadata_path_value(metadata, "campaigns")
    references_value = theme_metadata_path_value(metadata, "references")
    campaigns_dir = (
        Path(resolve_project_path(project_root, campaigns_value))
        if campaigns_value
        else marketing_root / "campaigns"
    )
    references_dir = (
        Path(resolve_project_path(project_root, references_value))
        if references_value
        else marketing_root / "references"
    )
    return {
        "marketing_root": marketing_root,
        "scratch_dir": scratch_dir,
        "approved_dir": approved_dir,
        "plans_dir": plans_dir,
        "asset_index": asset_index,
        "directory_state_file": directory_state_file,
        "accepted_state": accepted_state,
        "campaigns_dir": campaigns_dir,
        "references_dir": references_dir,
    }


def collect_state_snapshot(
    metadata: dict[str, Any],
    project_root: Path,
    metadata_path: str | None,
) -> dict[str, Any]:
    paths = project_paths(metadata, project_root)
    errors: list[str] = []
    state_files = collect_state_files(metadata, project_root, paths, errors)
    asset_roots = collect_asset_roots(metadata, project_root, paths, errors)
    related_repos = collect_related_repos(metadata, project_root, errors)
    required_reads = [
        paths["asset_index"],
        paths["accepted_state"],
        *[entry["path"] for entry in state_files if entry["exists"]],
    ]
    return {
        "schema_version": "1.0",
        "metadata": metadata_path or "",
        "project": {
            "id": string_at(metadata, "project", "id") or "",
            "root": str(project_root),
            "marketing_root": str(paths["marketing_root"]),
        },
        "organization": mapping_summary(value_at(metadata, "organization")),
        "theme": {
            "path": theme_metadata_path_value(metadata, "path") or "",
            "campaigns": theme_metadata_path_value(metadata, "campaigns") or "",
            "references": theme_metadata_path_value(metadata, "references") or "",
        },
        "state": {
            "plans": str(paths["plans_dir"]),
            "asset_index": str(paths["asset_index"]),
            "accepted": str(paths["accepted_state"]),
            "directory_state_file": paths["directory_state_file"],
        },
        "asset_roots": asset_roots,
        "state_files": state_files,
        "related_repos": related_repos,
        "read_before_production": unique_strings(str(path) for path in required_reads),
        "errors": errors,
    }


def collect_state_files(
    metadata: dict[str, Any],
    project_root: Path,
    paths: dict[str, Any],
    errors: list[str],
) -> list[dict[str, Any]]:
    state_paths: list[tuple[str, Path]] = [
        ("asset_index", paths["asset_index"]),
        ("accepted", paths["accepted_state"]),
    ]
    for root in declared_asset_roots(metadata, project_root, paths):
        if root.is_dir():
            state_paths.extend(
                (state_file_kind(path, paths["directory_state_file"]), path)
                for path in root.rglob("*")
                if should_read_state_file(path, paths["directory_state_file"], paths["scratch_dir"])
            )
    result: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for kind, path in state_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(read_state_file(kind, resolved, errors))
    return sorted(result, key=lambda item: item["path"])


def collect_asset_roots(
    metadata: dict[str, Any],
    project_root: Path,
    paths: dict[str, Any],
    errors: list[str],
) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    for root in declared_asset_roots(metadata, project_root, paths):
        try:
            roots.append(
                {
                    "path": str(root),
                    "exists": root.exists(),
                    "image_count": count_images(root, paths["scratch_dir"]) if root.is_dir() else 0,
                }
            )
        except OSError as exc:
            errors.append(f"{root}: cannot scan asset root: {exc}")
    return roots


def collect_related_repos(
    metadata: dict[str, Any],
    project_root: Path,
    errors: list[str],
) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for index, repo in enumerate(list_at(metadata, "sources", "relatedRepos")):
        if not isinstance(repo, dict):
            errors.append(f"sources.relatedRepos[{index}]: expected object")
            continue
        repo_root = Path(resolve_project_path(project_root, repo.get("root", ".")))
        metadata_value = repo.get("metadata")
        metadata_file = (
            Path(resolve_project_path(repo_root, metadata_value)) if metadata_value else None
        )
        state_value = repo.get("state") or repo.get("accepted")
        state_file = Path(resolve_project_path(repo_root, state_value)) if state_value else None
        entry: dict[str, Any] = {
            "id": str(repo.get("id", "")),
            "kind": str(repo.get("kind", "related-repo")),
            "root": str(repo_root),
            "exists": repo_root.exists(),
            "metadata": str(metadata_file) if metadata_file else "",
            "metadata_exists": metadata_file.exists() if metadata_file else False,
            "state": str(state_file) if state_file else "",
            "state_exists": state_file.exists() if state_file else False,
        }
        if state_file and state_file.exists():
            state_errors: list[str] = []
            entry["state_summary"] = read_state_file("related_state", state_file, state_errors)[
                "summary"
            ]
            errors.extend(state_errors)
        repos.append(entry)
    return repos


def declared_asset_roots(
    metadata: dict[str, Any],
    project_root: Path,
    paths: dict[str, Any],
) -> list[Path]:
    roots = [
        paths["marketing_root"],
        paths["references_dir"],
        paths["approved_dir"],
        paths["asset_index"].parent,
        paths["accepted_state"].parent,
    ]
    for value in list_at(metadata, "sources", "assetRoots"):
        roots.append(Path(resolve_project_path(project_root, value)))
    return unique_paths(roots)


def should_read_state_file(path: Path, directory_state_file: str, scratch_dir: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in {".git", "node_modules", "__pycache__", "portfolios"} for part in path.parts):
        return False
    try:
        path.relative_to(scratch_dir.resolve())
        return False
    except ValueError:
        pass
    return path.name in {directory_state_file, "accepted.yaml"}


def state_file_kind(path: Path, directory_state_file: str) -> str:
    if path.name == "accepted.yaml":
        return "accepted"
    if path.name == directory_state_file:
        return "directory_state"
    return "state"


def read_state_file(kind: str, path: Path, errors: list[str]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": kind,
        "path": str(path),
        "exists": path.exists(),
        "summary": {},
    }
    if not path.exists():
        return entry
    try:
        data = load_structured_file(path)
    except (OSError, SystemExit, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: cannot read state: {exc}")
        entry["error"] = str(exc)
        return entry
    entry["summary"] = summarize_state_data(data)
    return entry


def load_structured_file(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(raw)
    return parse_yaml_document(raw)


def summarize_state_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"type": type(data).__name__}
    owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
    accepted = data.get("accepted") if isinstance(data.get("accepted"), list) else []
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    patterns = data.get("patterns") if isinstance(data.get("patterns"), list) else []
    return {
        "schema_version": data.get("schema_version", ""),
        "owner_kind": owner.get("kind", ""),
        "owner_id": owner.get("id", ""),
        "revision": data.get("revision", ""),
        "accepted_count": len(accepted),
        "asset_count": len(assets),
        "pattern_count": len(patterns),
        "keys": sorted(str(key) for key in data.keys()),
    }


def count_images(root: Path, scratch_dir: Path) -> int:
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(
            part in {".git", "node_modules", "__pycache__", "portfolios"}
            for part in path.parts
        ):
            continue
        try:
            path.relative_to(scratch_dir.resolve())
            continue
        except ValueError:
            pass
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            count += 1
    return count


def copy_example(marketing_root: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "codefox"
    target = marketing_root / "examples" / "codefox"
    if not example.is_dir() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example, target)


def load_metadata(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    metadata_path = Path(path).expanduser()
    raw = metadata_path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        data = json.loads(raw)
    else:
        data = parse_yaml_document(raw)
    if not isinstance(data, dict):
        raise SystemExit(f"{metadata_path}: metadata root must be an object")
    return data


def parse_yaml_document(raw: str) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return parse_simple_yaml(raw)
    return yaml.safe_load(raw) or {}


def parse_simple_yaml(raw: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = strip_comment(line.strip())
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            raise SystemExit(f"unsupported metadata YAML line: {line}")
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)
    return root


def strip_comment(line: str) -> str:
    quote: str | None = None
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
        if char == "#" and quote is None:
            return line[:index].rstrip()
    return line


def parse_scalar(value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    return value


def project_root_for(metadata: dict[str, Any], fallback: Path | None = None) -> Path:
    root = string_at(metadata, "project", "root")
    if not root:
        return fallback or Path.cwd()
    root_path = Path(root).expanduser()
    if root_path.is_absolute():
        return root_path.resolve()
    return (fallback or Path.cwd()).joinpath(root_path).resolve()


def path_at(metadata: dict[str, Any], base: Path, default: str, *parts: str) -> Path:
    value = metadata_path_value(metadata, *parts) or default
    return Path(resolve_project_path(base, value))


def metadata_path(metadata: dict[str, Any], project_root: Path, *parts: str) -> str | None:
    value = metadata_path_value(metadata, *parts)
    if not value:
        return None
    return resolve_project_path(project_root, value)


def metadata_path_value(metadata: dict[str, Any], *parts: str) -> str | None:
    value = value_at(metadata, *parts)
    return str(value) if value not in (None, "") else None


def theme_metadata_path(metadata: dict[str, Any], project_root: Path, part: str) -> str | None:
    value = theme_metadata_path_value(metadata, part)
    if not value:
        return None
    return resolve_project_path(project_root, value)


def theme_metadata_path_value(metadata: dict[str, Any], part: str) -> str | None:
    return metadata_path_value(metadata, "theme", part) or metadata_path_value(
        metadata, "brand", part
    )


def theme_source_path(metadata: dict[str, Any], project_root: Path) -> str | None:
    value = theme_source_path_value(metadata)
    if not value:
        return None
    return resolve_project_path(project_root, value)


def theme_source_path_value(metadata: dict[str, Any]) -> str | None:
    return (
        metadata_path_value(metadata, "theme", "path")
        or metadata_path_value(metadata, "theme", "lock")
        or metadata_path_value(metadata, "brand", "lock")
    )


def resolve_project_path(project_root: Path, value: object) -> str:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((project_root / path).resolve())


def string_at(metadata: dict[str, Any], *parts: str) -> str | None:
    value = value_at(metadata, *parts)
    if value in (None, ""):
        return None
    return str(value)


def bool_at(metadata: dict[str, Any], default: bool, *parts: str) -> bool:
    value = value_at(metadata, *parts)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return truthy(str(value))


def value_at(metadata: dict[str, Any], *parts: str) -> object | None:
    current: object = metadata
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def list_at(metadata: dict[str, Any], *parts: str) -> list[Any]:
    value = value_at(metadata, *parts)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def mapping_summary(value: object | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("id", "name", "version") if key in value}


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def extract_option(args: list[str], option: str) -> tuple[list[str], str | None]:
    result: list[str] = []
    value: str | None = None
    iterator = iter(args)
    for token in iterator:
        if token == option:
            try:
                value = next(iterator)
            except StopIteration as exc:
                raise SystemExit(f"{option} requires a value") from exc
        elif token.startswith(f"{option}="):
            value = token.split("=", 1)[1]
        else:
            result.append(token)
    return result, value


def add_option(args: list[str], flag: str, value: str | None) -> None:
    if not value or has_flag(args, flag):
        return
    args.extend([flag, value])


def has_flag(args: list[str], flag: str) -> bool:
    return any(token == flag or token.startswith(f"{flag}=") for token in args)


def has_positional(args: list[str], start: int) -> bool:
    skip_next = False
    for token in args[start:]:
        if skip_next:
            skip_next = False
            continue
        if token in VALUE_FLAGS:
            skip_next = True
            continue
        if any(token.startswith(f"{flag}=") for flag in VALUE_FLAGS):
            continue
        if not token.startswith("-"):
            return True
    return False


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def print_kv(values: dict[str, object]) -> None:
    for key, value in values.items():
        print(f"{key}={value}")


def python_module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def shell_quote(value: str) -> str:
    if not value or any(char.isspace() or char in "'\"\\$`" for char in value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
