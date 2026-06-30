#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INTERNAL_METADATA_BASE_KEY = "__brand_studio_metadata_base"
INTERNAL_PROJECT_ROOT_OVERRIDE_KEY = "__brand_studio_project_root_override"
VALUE_FLAGS = {
    "--brand",
    "--theme",
    "--outputs-dir",
}
DEFAULT_MARKETING_ROOT = "assets/marketing"
DEFAULT_SCRATCH_DIR = ".harness/marketing/out"
DEFAULT_APPROVED_DIR = "public/marketing"
PORTFOLIO_DOMAINS = ("release", "promo")
# Fallbacks used only when metadata.brandStandard.* is absent.
FALLBACK_ORG_BRAND_STANDARD = "public/brand/brand-standard.md"
FALLBACK_ORG_THEME_BASE = "public/brand/theme.base.md"
FALLBACK_ORG_REFERENCES = "public/brand/references"
DEFAULT_RELEASE_STYLE = "launch-hero"
DEFAULT_RELEASE_DELIVERABLES = [
    ("release-card", (1200, 640)),
    ("release-square", (1088, 1088)),
    ("release-poster", (1088, 1920)),
]
SLUG_PART_RE = re.compile(r"[^a-z0-9]+")
CHANGELOG_VERSION_HEADING_RE = re.compile(
    r"^#{2,6}\s+(?:\[?[vV]?([0-9]+\.[0-9]+\.[0-9][0-9A-Za-z.+-]*)\]?)"
    r"(?:\s|$|-)"
)
CHANGELOG_LINK_DEF_RE = re.compile(r"^\[[^\]]+\]:\s")
IGNORED_SCAN_DIRS = {
    ".dev-sandbox",
    ".git",
    ".harness",
    ".kobe",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "worktrees",
}
RELEASE_VALUE_OPTIONS = {
    "--version",
    "--name",
    "--style",
    "--headline",
    "--changelog",
    "--releases",
    "--campaign",
    "--copy",
}


def main() -> int:
    args, metadata_path = extract_option(sys.argv[1:], "--metadata")
    args, project_root_value = extract_option(args, "--project-root")
    metadata = load_metadata(metadata_path, project_root_value) if metadata_path else {}
    if project_root_value and not metadata_path:
        metadata[INTERNAL_PROJECT_ROOT_OVERRIDE_KEY] = str(
            Path(project_root_value).expanduser().resolve()
        )

    if not args or args[0] in {"-h", "--help"}:
        print_harness_help()
        return 0

    if args[0] == "org":
        return org_command(args[1:], metadata, metadata_path)
    if args[0] == "repo":
        return repo_command(args[1:], metadata, metadata_path)

    print(
        f"unknown command: {args[0]}; use `repo ...` or `org ...`",
        file=sys.stderr,
    )
    return 2


def bundled_cli_command() -> list[str]:
    return [sys.executable, str(Path(__file__).resolve().parent / "cli.py")]


def print_harness_help() -> None:
    print(
        """
usage: harness.py [--project-root DIR] [--metadata FILE] <command> [options]

Canonical Brand Studio commands:
  org init [--write] [target-dir]
  repo init [--write] [--with-example] [target-dir]
  repo paths
  repo check
  repo state [--compact] [target-dir]
  repo validate
  repo render --dry-run
  repo release copy [--write] [--releases N]
  repo release campaign [--write]
  repo gen release [--changelog FILE] [--releases N]
  repo handoff --campaign NAME --asset-id ID
  repo settle --campaign NAME --asset-id ID --file FILE [--checksum-sha256 SHA256]
  repo report --file FILE
  repo delete candidate --file FILE
""".strip()
    )


def org_command(
    args: list[str],
    metadata: dict[str, Any],
    metadata_path: str | None,
) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print("usage: harness.py org init [--write] [target-dir]")
        return 0
    if args[0] == "init":
        return org_init(args[1:], metadata, metadata_path)
    print(f"unknown org command: {' '.join(args)}", file=sys.stderr)
    return 2


def repo_command(
    args: list[str],
    metadata: dict[str, Any],
    metadata_path: str | None,
) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print(
            "usage: harness.py repo "
            "{init,paths,check,state,validate,render,release,gen,handoff,settle,report,delete} ..."
        )
        return 0
    command_name = args[0]
    rest = args[1:]
    if command_name == "init":
        return bootstrap_project(rest, metadata, metadata_path)
    if command_name == "paths":
        print_plan(metadata)
        return 0
    if command_name == "check":
        return check_project(rest, metadata, metadata_path)
    if command_name == "state":
        return print_state(rest, metadata, metadata_path)
    if command_name in {"validate", "render"}:
        return run_repo_render_command([command_name, *rest], metadata)
    if command_name == "release":
        return repo_release_command(rest, metadata, metadata_path)
    if command_name == "gen" and rest[:1] == ["release"]:
        return release_render(rest[1:], metadata, metadata_path)
    if command_name == "handoff":
        return producer_handoff(rest, metadata, metadata_path)
    if command_name == "settle":
        return accept_asset(rest, metadata, metadata_path)
    if command_name == "report":
        return asset_report(rest, metadata, metadata_path)
    if command_name == "delete" and rest[:1] == ["candidate"]:
        return delete_candidate(rest[1:], metadata, metadata_path)
    print(f"unknown repo command: {' '.join(args)}", file=sys.stderr)
    return 2


def repo_release_command(
    args: list[str],
    metadata: dict[str, Any],
    metadata_path: str | None,
) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print("usage: harness.py repo release {copy,campaign,render} ...")
        return 0
    command_name = args[0]
    rest = args[1:]
    if command_name == "copy":
        return release_copy(rest, metadata, metadata_path)
    if command_name == "campaign":
        return release_campaign(rest, metadata, metadata_path)
    if command_name == "render":
        return release_render(rest, metadata, metadata_path)
    print(f"unknown repo release command: {' '.join(args)}", file=sys.stderr)
    return 2


def run_repo_render_command(args: list[str], metadata: dict[str, Any]) -> int:
    command_args = apply_metadata_args(args, metadata)
    constraint_errors = producer_constraint_errors(command_args, metadata)
    if constraint_errors:
        for error in constraint_errors:
            print(error, file=sys.stderr)
        return 1
    completed = subprocess.run([*bundled_cli_command(), *command_args], check=False)
    return completed.returncode


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
                "usage: harness.py repo init "
                "[--write] [--with-example] [target-dir]"
            )
            return 0
        elif token.startswith("-"):
            raise SystemExit(f"unknown repo init option: {token}")
        else:
            target = token

    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    plan = project_paths(metadata, project_root)
    dirs = [
        plan["marketing_root"],
        plan["campaigns_root"],
        plan["campaigns_dir"],
        *plan["campaign_dirs"].values(),
        plan["references_dir"],
        plan["plans_dir"],
        plan["asset_index"].parent,
        plan["scratch_dir"],
        plan["approved_dir"],
        plan["accepted_state"].parent,
    ]
    for portfolio in plan["portfolios"].values():
        dirs.extend(
            [
                portfolio["accepted"].parent,
                portfolio["asset_state"].parent,
                portfolio["patterns"].parent,
            ]
        )

    if write:
        for directory in unique_paths(dirs):
            directory.mkdir(parents=True, exist_ok=True)
        write_initial_state_files(plan, project_root, metadata)
        write_default_portfolio_patterns(plan["portfolios"])
        if with_example:
            copy_example(plan["marketing_root"])

    print_kv(
        {
            "mode": "write" if write else "dry-run",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "marketing_root": plan["marketing_root"],
            "campaigns_root": plan["campaigns_root"],
            "campaigns_dir": plan["campaigns_dir"],
            "release_campaigns_dir": plan["campaign_dirs"]["release"],
            "promo_campaigns_dir": plan["campaign_dirs"]["promo"],
            "references_dir": plan["references_dir"],
            "plans_dir": plan["plans_dir"],
            "asset_index": plan["asset_index"],
            "scratch_dir": plan["scratch_dir"],
            "approved_dir": plan["approved_dir"],
            "accepted_state": plan["accepted_state"],
            "release_portfolio": plan["portfolios"]["release"]["accepted"].parent,
            "promo_portfolio": plan["portfolios"]["promo"]["accepted"].parent,
            "created": " ".join(str(path) for path in unique_paths(dirs)) if write else "",
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


def write_initial_state_files(
    plan: dict[str, Any],
    project_root: Path,
    metadata: dict[str, Any],
) -> None:
    owner = {"kind": "repo", "id": string_at(metadata, "project", "id") or project_root.name}
    state_files = [
        (
            plan["asset_index"],
            {
                "schema_version": "1.0",
                "owner": owner,
                "revision": 0,
                "assets": [],
                "patterns": [],
            },
        ),
        (
            plan["accepted_state"],
            {
                "schema_version": "1.0",
                "owner": owner,
                "revision": 0,
                "accepted": [],
            },
        ),
    ]
    for domain, portfolio in plan["portfolios"].items():
        state_files.extend(
            [
                (
                    portfolio["accepted"],
                    {
                        "schema_version": "1.0",
                        "owner": owner,
                        "domain": domain,
                        "revision": 0,
                        "accepted": [],
                    },
                ),
                (
                    portfolio["asset_state"],
                    {
                        "schema_version": "1.0",
                        "owner": owner,
                        "domain": domain,
                        "revision": 0,
                        "assets": [],
                        "patterns": [],
                    },
                ),
            ]
        )
    for path, content in state_files:
        if path.exists():
            continue
        write_yaml_mapping(path, content)


def write_default_portfolio_patterns(portfolios: dict[str, dict[str, Path]]) -> None:
    templates = {
        "release": """# Release Portfolio Patterns

patterns:
  - id: release-log-full-editorial
    rules:
      - release notes are the main subject
      - use changelog/release structure as factual source
      - prefer unified archive/poster layout
      - no screenshots unless explicitly requested
      - no app UI container
      - no campaign scene
      - high text clarity over visual drama
""",
        "promo": """# Promo Portfolio Patterns

patterns:
  - id: screen-first-field-scene
    rules:
      - use campaign brief and references as factual source
      - prefer product-forward promotional composition
      - do not inherit release-note poster composition by default
""",
    }
    for domain, portfolio in portfolios.items():
        path = portfolio["patterns"]
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(templates.get(domain, "# Portfolio Patterns\n"), encoding="utf-8")


def org_init(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    write = False
    target = "."
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token == "--write":
            write = True
        elif token == "--dry-run":
            write = False
        elif token in {"-h", "--help"}:
            print("usage: harness.py org init [--write] [target-dir]")
            return 0
        elif token.startswith("-"):
            raise SystemExit(f"unknown org init option: {token}")
        else:
            target = token

    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    paths = org_brand_paths(metadata, project_root)
    created: list[Path] = []
    existing: list[Path] = []

    if write:
        if paths["references"].exists():
            existing.append(paths["references"])
        else:
            created.append(paths["references"])
        paths["references"].mkdir(parents=True, exist_ok=True)
        for key, content in (
            ("brand_standard", org_brand_standard_template(project_root)),
            ("theme_base", org_theme_base_template(project_root)),
        ):
            path = paths[key]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                existing.append(path)
                continue
            path.write_text(content, encoding="utf-8")
            created.append(path)
    else:
        existing = [path for path in paths.values() if path.exists()]

    print_kv(
        {
            "mode": "write" if write else "dry-run",
            "scope": "org",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "brand_standard": paths["brand_standard"],
            "theme_base": paths["theme_base"],
            "references": paths["references"],
            "created": " ".join(str(path) for path in unique_paths(created)) if write else "",
            "existing": " ".join(str(path) for path in unique_paths(existing)),
            "next": (
                "add references, then update brand-standard.md and "
                "theme.base.md with agent-reviewed brand direction"
            ),
        }
    )
    if not write:
        print("dry_run_note=pass --write to create missing org brand files")
    return 0


def delete_candidate(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = "usage: harness.py repo delete candidate --file FILE"
    file_value: str | None = None
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token == "--file":
            if not remaining:
                print("--file requires a value", file=sys.stderr)
                return 1
            file_value = remaining.pop(0)
        elif token.startswith("--file="):
            file_value = token.split("=", 1)[1]
        elif token in {"-h", "--help"}:
            print(usage)
            return 0
        elif token.startswith("-"):
            print(f"unknown delete candidate option: {token}", file=sys.stderr)
            return 1
        else:
            print(f"unexpected delete candidate argument: {token}", file=sys.stderr)
            return 1
    if not file_value:
        print("delete candidate requires --file", file=sys.stderr)
        return 1

    project_root = project_root_for(metadata)
    paths = project_paths(metadata, project_root)
    candidate = Path(resolve_project_path(project_root, file_value))
    scratch_dir = paths["scratch_dir"].resolve()
    try:
        candidate.resolve().relative_to(scratch_dir)
    except ValueError:
        print(
            f"{candidate}: delete candidate file must be under artifacts.scratch "
            f"({scratch_dir})",
            file=sys.stderr,
        )
        return 1
    if not candidate.is_file():
        print(f"{candidate}: candidate file not found", file=sys.stderr)
        return 1

    checksum = checksum_path(candidate)
    candidate.unlink()
    print_kv(
        {
            "mode": "delete-candidate",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "file": candidate,
            "scratch_dir": scratch_dir,
            "deleted": "true",
            "checksum_sha256": checksum,
        }
    )
    return 0


def accept_asset(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py repo settle --campaign NAME --asset-id ID "
        "--file FILE [--domain release|promo] [--source-kind KIND] "
        "[--asset-type TYPE] [--style-family NAME] [--checksum-sha256 SHA256] "
        "[--notes TEXT] [--tags a,b] [--plan FILE] [--update-asset-state]"
    )
    options = parse_accept_options(args, usage)
    if isinstance(options, str):
        print(options, file=sys.stderr)
        return 1

    project_root = project_root_for(metadata)
    paths = project_paths(metadata, project_root)
    candidate = Path(resolve_project_path(project_root, options["file"]))
    scratch_dir = paths["scratch_dir"].resolve()
    try:
        candidate.resolve().relative_to(scratch_dir)
    except ValueError:
        print(
            f"{candidate}: accepted candidates must come from artifacts.scratch "
            f"({scratch_dir})",
            file=sys.stderr,
        )
        return 1
    if not candidate.is_file():
        print(f"{candidate}: candidate file not found", file=sys.stderr)
        return 1

    actual_checksum = checksum_path(candidate)
    expected_checksum = str(options.get("checksum_sha256") or "")
    if expected_checksum and expected_checksum != actual_checksum:
        print(
            f"{candidate}: checksum mismatch; expected {expected_checksum}, "
            f"got {actual_checksum}",
            file=sys.stderr,
        )
        return 1

    metadata_result = read_candidate_metadata(candidate)
    if metadata_result["error"]:
        print(str(metadata_result["error"]), file=sys.stderr)
        return 1

    campaign = str(options["campaign"])
    asset_id = str(options["asset_id"])
    domain = accepted_domain(str(options.get("domain") or ""), campaign)
    if not domain:
        print("--domain must be release or promo", file=sys.stderr)
        return 1
    portfolio = paths["portfolios"][domain]
    run_lock = candidate.parent / "run.lock.json"
    expected_size = expected_asset_size(run_lock, asset_id)
    if expected_size and metadata_result["size"] != expected_size:
        print(
            f"{candidate}: size mismatch; expected {expected_size[0]}x{expected_size[1]}, "
            f"got {metadata_result['size'][0]}x{metadata_result['size'][1]}",
            file=sys.stderr,
        )
        return 1

    approved_dir = paths["approved_dir"] / campaign
    approved_file = approved_dir / candidate.name
    approved_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, approved_file)

    manifest_path = approved_dir / "manifest.json"
    manifest_asset = build_approved_manifest_asset(
        project_root=project_root,
        asset_id=asset_id,
        source=candidate,
        approved=approved_file,
        checksum=actual_checksum,
        metadata=metadata_result,
        run_lock=run_lock if run_lock.is_file() else None,
    )
    write_approved_manifest(
        manifest_path=manifest_path,
        campaign=campaign,
        project_root=project_root,
        asset=manifest_asset,
    )

    accepted_path = paths["accepted_state"]
    accepted_entry = build_accepted_entry(
        project_root=project_root,
        project_id=string_at(metadata, "project", "id") or project_root.name,
        campaign=campaign,
        asset_id=asset_id,
        approved_file=approved_file,
        manifest_path=manifest_path,
        run_lock=run_lock if run_lock.is_file() else None,
        checksum=actual_checksum,
        metadata=metadata_result,
        notes=str(options.get("notes") or ""),
        tags=accept_tags(str(options.get("tags") or ""), campaign, asset_id),
        domain=domain,
        source_kind=accepted_source_kind(domain, str(options.get("source_kind") or "")),
        asset_type=accepted_asset_type(domain, asset_id, str(options.get("asset_type") or "")),
        style_family=accepted_style_family(domain, str(options.get("style_family") or "")),
    )
    upsert_accepted_entry(accepted_path, accepted_entry, project_root)
    upsert_accepted_entry(portfolio["accepted"], accepted_entry, project_root)

    if options["update_asset_state"]:
        upsert_asset_state(portfolio["asset_state"], accepted_entry, project_root)

    plan_value = options.get("plan")
    if plan_value:
        update_plan_status(Path(resolve_project_path(project_root, plan_value)), accepted_entry)

    print_kv(
        {
            "mode": "settle",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "campaign": campaign,
            "asset_id": asset_id,
            "source": candidate,
            "approved": approved_file,
            "manifest": manifest_path,
            "accepted_state": accepted_path,
            "portfolio": domain,
            "portfolio_accepted": portfolio["accepted"],
            "portfolio_asset_state": portfolio["asset_state"],
            "corpus": "approved",
            "accepted": "true",
            "domain": domain,
            "source_kind": accepted_entry["source_kind"],
            "asset_type": accepted_entry["asset_type"],
            "style_family": accepted_entry["style_family"],
            "mime_type": metadata_result["mime_type"],
            "size": size_text(metadata_result["size"]),
            "checksum_sha256": actual_checksum,
        }
    )
    return 0


def asset_report(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py repo report --file FILE "
        "[--campaign NAME] [--asset-id ID]"
    )
    options = parse_asset_report_options(args, usage)
    if isinstance(options, str):
        print(options, file=sys.stderr)
        return 1

    project_root = project_root_for(metadata)
    paths = project_paths(metadata, project_root)
    file_path = Path(resolve_project_path(project_root, options["file"]))
    if not file_path.is_file():
        print(f"{file_path}: asset file not found", file=sys.stderr)
        return 1

    report = build_asset_report(
        metadata=metadata,
        metadata_path=metadata_path,
        project_root=project_root,
        paths=paths,
        file_path=file_path,
        campaign_hint=str(options.get("campaign") or ""),
        asset_id_hint=str(options.get("asset_id") or ""),
    )
    error = str(report.pop("error", ""))
    if error:
        print(error, file=sys.stderr)
        return 1
    print_kv(report)
    return 0


def producer_handoff(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py repo handoff --campaign NAME "
        "--asset-id ID [--context FILE]"
    )
    options = parse_producer_handoff_options(args, usage)
    if isinstance(options, str):
        print(options, file=sys.stderr)
        return 1

    project_root = project_root_for(metadata)
    paths = project_paths(metadata, project_root)
    campaign = str(options["campaign"])
    asset_id = str(options["asset_id"])
    context_path = (
        Path(resolve_project_path(project_root, options["context"]))
        if options.get("context")
        else paths["scratch_dir"] / campaign / "producer-context.json"
    )
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"{context_path}: producer context not found: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"{context_path}: invalid producer context JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(context, dict) or context.get("kind") != "producer_context":
        print(f"{context_path}: expected kind=producer_context", file=sys.stderr)
        return 1

    asset = producer_context_asset(context, asset_id)
    if asset is None:
        print(f"{context_path}: asset id not found: {asset_id}", file=sys.stderr)
        return 1

    producer_skill = str(
        context.get("producer_skill") or string_at(metadata, "skills", "image") or ""
    )
    size = asset.get("size")
    if not valid_size(size):
        print(f"{context_path}: asset {asset_id} has invalid size", file=sys.stderr)
        return 1
    target = producer_handoff_target(project_root, paths, campaign, asset)
    suffix = target.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        print(
            f"{target}: producer handoff target must be png, jpg, jpeg, or webp",
            file=sys.stderr,
        )
        return 1

    constraint_error = producer_handoff_constraint_error(producer_skill, asset_id, size, suffix)
    if constraint_error:
        print(constraint_error, file=sys.stderr)
        return 1

    try:
        target.resolve().relative_to(paths["scratch_dir"].resolve())
    except ValueError:
        print(
            f"{target}: producer handoff target must stay under artifacts.scratch "
            f"({paths['scratch_dir'].resolve()})",
            file=sys.stderr,
        )
        return 1

    print_kv(
        {
            "mode": "handoff",
            "metadata": metadata_path or "",
            "project_root": project_root,
            "campaign": campaign,
            "asset_id": asset_id,
            "producer_context": context_path,
            "producer_skill": producer_skill,
            "possible_cost": "true",
            "not_generated_yet": "true",
            "target": target,
            "target_exists": bool_text(target.exists()),
            "size": size_text(size),
            "format": suffix.lstrip("."),
            "prompt": single_line(str(asset.get("prompt") or "")),
            "negative_prompt": single_line(str(asset.get("negative_prompt") or "")),
        }
    )
    return 0


def parse_accept_options(args: list[str], usage: str) -> dict[str, Any] | str:
    options: dict[str, Any] = {
        "campaign": "",
        "asset_id": "",
        "file": "",
        "checksum_sha256": "",
        "notes": "",
        "tags": "",
        "plan": "",
        "domain": "",
        "source_kind": "",
        "asset_type": "",
        "style_family": "",
        "update_asset_state": False,
    }
    value_options = {
        "--campaign": "campaign",
        "--asset-id": "asset_id",
        "--file": "file",
        "--domain": "domain",
        "--source-kind": "source_kind",
        "--asset-type": "asset_type",
        "--style-family": "style_family",
        "--checksum-sha256": "checksum_sha256",
        "--notes": "notes",
        "--tags": "tags",
        "--plan": "plan",
    }
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token in {"-h", "--help"}:
            print(usage)
            raise SystemExit(0)
        if token == "--update-asset-state":
            options["update_asset_state"] = True
            continue
        if token in value_options:
            if not remaining:
                return f"{token} requires a value"
            options[value_options[token]] = remaining.pop(0)
            continue
        matched = False
        for flag, key in value_options.items():
            if token.startswith(f"{flag}="):
                options[key] = token.split("=", 1)[1]
                matched = True
                break
        if matched:
            continue
        if token.startswith("-"):
            return f"unknown repo settle option: {token}"
        return usage

    for key in ("campaign", "asset_id", "file"):
        if not options[key]:
            return f"repo settle requires --{key.replace('_', '-')}"
    if options["checksum_sha256"] and not re.fullmatch(
        r"[0-9a-fA-F]{64}", options["checksum_sha256"]
    ):
        return "--checksum-sha256 must be a 64-character hex digest"
    if options["domain"] and options["domain"] not in PORTFOLIO_DOMAINS:
        return "--domain must be release or promo"
    return options


def parse_asset_report_options(args: list[str], usage: str) -> dict[str, Any] | str:
    return parse_value_options(
        args,
        usage=usage,
        command_name="repo report",
        value_options={
            "--file": "file",
            "--campaign": "campaign",
            "--asset-id": "asset_id",
        },
        defaults={"file": "", "campaign": "", "asset_id": ""},
        required=("file",),
    )


def parse_producer_handoff_options(args: list[str], usage: str) -> dict[str, Any] | str:
    return parse_value_options(
        args,
        usage=usage,
        command_name="repo handoff",
        value_options={
            "--campaign": "campaign",
            "--asset-id": "asset_id",
            "--context": "context",
        },
        defaults={"campaign": "", "asset_id": "", "context": ""},
        required=("campaign", "asset_id"),
    )


def parse_value_options(
    args: list[str],
    *,
    usage: str,
    command_name: str,
    value_options: dict[str, str],
    defaults: dict[str, Any],
    required: tuple[str, ...],
) -> dict[str, Any] | str:
    options = dict(defaults)
    remaining = list(args)
    while remaining:
        token = remaining.pop(0)
        if token in {"-h", "--help"}:
            print(usage)
            raise SystemExit(0)
        if token in value_options:
            if not remaining:
                return f"{token} requires a value"
            options[value_options[token]] = remaining.pop(0)
            continue
        matched = False
        for flag, key in value_options.items():
            if token.startswith(f"{flag}="):
                options[key] = token.split("=", 1)[1]
                matched = True
                break
        if matched:
            continue
        if token.startswith("-"):
            return f"unknown {command_name} option: {token}"
        return usage

    for key in required:
        if not options[key]:
            return f"{command_name} requires --{key.replace('_', '-')}"
    return options


def build_asset_report(
    *,
    metadata: dict[str, Any],
    metadata_path: str | None,
    project_root: Path,
    paths: dict[str, Path],
    file_path: Path,
    campaign_hint: str,
    asset_id_hint: str,
) -> dict[str, object]:
    file_metadata = read_candidate_metadata(file_path)
    if file_metadata["error"]:
        return {"error": file_metadata["error"]}

    checksum = checksum_path(file_path)
    corpus = asset_corpus(file_path, paths)
    accepted_entry = None
    if corpus == "approved":
        for accepted_path in accepted_lookup_paths(paths):
            accepted_entry = accepted_entry_for_file(
                accepted_path, project_root, file_path, checksum
            )
            if accepted_entry is not None:
                break
    campaign = (
        campaign_hint
        or string_from_mapping(accepted_entry, "campaign")
        or campaign_from_corpus_path(file_path, paths, corpus)
    )
    asset_id = asset_id_hint or string_from_mapping(accepted_entry, "asset_id") or file_path.stem
    return {
        "mode": "report",
        "metadata": metadata_path or "",
        "project_root": project_root,
        "file": file_path,
        "path": relative_project_path(project_root, file_path),
        "corpus": corpus,
        "accepted": bool_text(accepted_entry is not None),
        "campaign": campaign,
        "asset_id": asset_id,
        "mime_type": file_metadata["mime_type"],
        "size": size_text(file_metadata["size"]),
        "checksum_sha256": checksum,
        "accepted_state": paths["accepted_state"],
        "domain": string_from_mapping(accepted_entry, "domain"),
        "project_id": string_at(metadata, "project", "id") or project_root.name,
        "error": "",
    }


def accepted_lookup_paths(paths: dict[str, Any]) -> list[Path]:
    portfolio_paths = [
        portfolio["accepted"]
        for portfolio in paths.get("portfolios", {}).values()
        if isinstance(portfolio, dict) and isinstance(portfolio.get("accepted"), Path)
    ]
    return unique_paths([paths["accepted_state"], *portfolio_paths])


def asset_corpus(file_path: Path, paths: dict[str, Path]) -> str:
    resolved = file_path.resolve()
    for corpus, root_key in (("scratch", "scratch_dir"), ("approved", "approved_dir")):
        try:
            resolved.relative_to(paths[root_key].resolve())
            return corpus
        except ValueError:
            continue
    return "external"


def accepted_entry_for_file(
    accepted_state: Path,
    project_root: Path,
    file_path: Path,
    checksum: str,
) -> dict[str, Any] | None:
    data = read_yaml_mapping(accepted_state)
    accepted = data.get("accepted") if isinstance(data.get("accepted"), list) else []
    relative_path = relative_project_path(project_root, file_path)
    for entry in accepted:
        if not isinstance(entry, dict):
            continue
        entry_path = str(entry.get("path") or "")
        entry_checksum = str(entry.get("checksum_sha256") or "")
        if entry_path == relative_path and (not entry_checksum or entry_checksum == checksum):
            return entry
    return None


def campaign_from_corpus_path(
    file_path: Path,
    paths: dict[str, Path],
    corpus: str,
) -> str:
    root_key = {"scratch": "scratch_dir", "approved": "approved_dir"}.get(corpus)
    if not root_key:
        return ""
    try:
        relative = file_path.resolve().relative_to(paths[root_key].resolve())
    except ValueError:
        return ""
    return relative.parts[0] if len(relative.parts) > 1 else ""


def string_from_mapping(value: dict[str, Any] | None, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    item = value.get(key)
    return str(item) if item not in (None, "") else ""


def producer_context_asset(context: dict[str, Any], asset_id: str) -> dict[str, Any] | None:
    assets = context.get("assets") if isinstance(context.get("assets"), list) else []
    for asset in assets:
        if isinstance(asset, dict) and str(asset.get("id") or "") == asset_id:
            return asset
    return None


def producer_handoff_target(
    project_root: Path,
    paths: dict[str, Path],
    campaign: str,
    asset: dict[str, Any],
) -> Path:
    target_path = str(asset.get("target_path") or "")
    if target_path:
        return Path(resolve_project_path(project_root, target_path))
    target_file = str(asset.get("target_file") or f"{asset.get('id') or 'asset'}.png")
    return paths["scratch_dir"] / campaign / target_file


def producer_handoff_constraint_error(
    producer_skill: str,
    asset_id: str,
    size: object,
    suffix: str,
) -> str:
    if not valid_size(size):
        return f"producer handoff constraint: asset {asset_id} has invalid size"
    width, height = int(size[0]), int(size[1])  # type: ignore[index]
    if "gpt-image" not in producer_skill.lower():
        return ""
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        return "gpt-image constraint: output format must be png, jpeg, jpg, or webp"
    if width % 16 or height % 16:
        suggested = f"{round_up_to_multiple(width, 16)}x{round_up_to_multiple(height, 16)}"
        return (
            f"gpt-image constraint: asset {asset_id} size {width}x{height} "
            f"must be a multiple of 16; suggested {suggested}"
        )
    ratio = width / height
    if ratio < 0.25 or ratio > 4:
        return (
            f"gpt-image constraint: asset {asset_id} aspect ratio must be between 1:4 and 4:1"
        )
    return ""


def valid_size(size: object) -> bool:
    return (
        isinstance(size, list)
        and len(size) == 2
        and all(isinstance(item, int) and item > 0 for item in size)
    )


def size_text(size: object) -> str:
    if not valid_size(size):
        return "0x0"
    return f"{size[0]}x{size[1]}"  # type: ignore[index]


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def release_campaign(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    usage = (
        "usage: harness.py repo release campaign "
        "[--write] [--force] [--version VERSION] [--name NAME] "
        "[--releases COUNT] [--style STYLE] [--headline TEXT] [--changelog FILE] "
        "[--copy FILE] [--campaign FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=True,
        command_name="repo release campaign",
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
        "usage: harness.py repo release copy "
        "[--write] [--force] [--version VERSION] [--name NAME] "
        "[--releases COUNT] [--headline TEXT] [--changelog FILE] "
        "[--copy FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=True,
        command_name="repo release copy",
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
        "usage: harness.py repo gen release "
        "[--force] [--version VERSION] [--name NAME] [--releases COUNT] [--style STYLE] "
        "[--headline TEXT] [--changelog FILE] [--copy FILE] "
        "[--campaign FILE] [target-dir]"
    )
    options = parse_release_options(
        args,
        usage=usage,
        allow_write=False,
        command_name="repo gen release",
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
        mode="gen-release",
        campaign_status=write_result["status"],
        copy_status=copy_result["status"],
        producer_context_path=Path(str(producer_context_result["path"])),
        producer_skill=str(producer_context_result["producer_skill"]),
        portfolio=str(producer_context_result["portfolio"]),
        portfolio_accepted=Path(str(producer_context_result["portfolio_accepted"])),
        portfolio_asset_state=Path(str(producer_context_result["portfolio_asset_state"])),
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
    release_count = 1
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
            elif token == "--releases":
                release_count = parse_release_count(value, token)
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
        elif token.startswith("--releases="):
            release_count = parse_release_count(token.split("=", 1)[1], "--releases")
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
        "release_count": release_count,
        "campaign_path_value": campaign_path_value,
        "copy_path_value": copy_path_value,
    }


def parse_release_count(value: str, option: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise SystemExit(f"{option} must be a positive integer") from exc
    if count < 1:
        raise SystemExit(f"{option} must be a positive integer")
    return count


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
        int(options["release_count"]),
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
        else paths["campaign_dirs"]["release"]
        / f"{copy_plan['campaign_name']}.campaign.yaml"
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

    product = str(data.get("product") or "").strip()
    releases, releases_error = release_copy_releases(data.get("releases"), path)
    if releases_error:
        return None, releases_error
    if not releases:
        legacy_points, error = release_copy_legacy_points(data.get("key_points"), path)
        if error:
            return None, error
        releases = [
            {
                "package": "",
                "version": str(data.get("version") or "").strip(),
                "changes": legacy_points,
            }
        ]

    raw_visual = data.get("visual_direction")
    visual = raw_visual if isinstance(raw_visual, dict) else {}
    return {
        "schema_version": str(data.get("schema_version") or "1.0"),
        "kind": "release_copy",
        "product": product,
        "version": str(data.get("version") or "").strip(),
        "release_theme": str(data.get("release_theme") or "").strip(),
        "headline": str(data.get("headline") or "").strip(),
        "subheadline": str(data.get("subheadline") or "").strip(),
        "releases": releases,
        "audience": release_copy_string_list(data.get("audience")),
        "visual_direction": {
            "mood": str(visual.get("mood") or "release marketing visual").strip(),
            "motifs": release_copy_string_list(visual.get("motifs")),
            "avoid": release_copy_string_list(visual.get("avoid")),
        },
        "sources": release_copy_sources(data.get("sources")),
    }, None


def release_copy_legacy_points(
    value: Any,
    path: Path,
) -> tuple[list[str], str | None]:
    if not isinstance(value, list) or not value:
        return [], f"{path}: release copy asset releases must be a non-empty list"
    points: list[str] = []
    for index, raw_point in enumerate(value, start=1):
        if not isinstance(raw_point, dict):
            return [], f"{path}: key_points[{index}] must be an object"
        title = str(raw_point.get("title") or "").strip()
        detail = str(raw_point.get("detail") or "").strip()
        if not title or not detail:
            return [], f"{path}: key_points[{index}] requires title and detail"
        points.append(f"{title}: {detail}")
    return points, None


def release_copy_releases(
    value: Any,
    path: Path,
) -> tuple[list[dict[str, Any]], str | None]:
    if value is None:
        return [], None
    if not isinstance(value, list):
        return [], f"{path}: release copy asset releases must be a list"
    if not value:
        return [], f"{path}: release copy asset releases must be a non-empty list"
    releases: list[dict[str, Any]] = []
    for release_index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            return [], f"{path}: releases[{release_index}] must be an object"
        version = str(item.get("version") or "").strip()
        if not version:
            return [], f"{path}: releases[{release_index}] requires version"
        changes: list[str] = []
        raw_changes = item.get("changes")
        if not isinstance(raw_changes, list) or not raw_changes:
            return [], f"{path}: releases[{release_index}].changes must be a non-empty list"
        for change_index, raw_change in enumerate(raw_changes, start=1):
            change, error = release_copy_change_text(raw_change)
            if error:
                return [], f"{path}: releases[{release_index}].changes[{change_index}] {error}"
            changes.append(change)
        releases.append(
            {
                "package": str(item.get("package") or "").strip(),
                "version": version,
                "changes": changes,
            }
        )
    return releases, None


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


def release_copy_change_text(value: Any) -> tuple[str, str | None]:
    if isinstance(value, str):
        text = value.strip()
        return (text, None) if text else ("", "must not be empty")
    if not isinstance(value, dict):
        return "", "must be text or an object"

    text = str(value.get("text") or "").strip()
    if text:
        return text, None

    title = str(value.get("title") or "").strip()
    detail = str(value.get("detail") or "").strip()
    if not title or not detail:
        return "", "requires title and detail"
    return f"{title}: {detail}", None


def release_copy_source_count(copy_asset: dict[str, Any]) -> int:
    sources = copy_asset.get("sources")
    if isinstance(sources, list) and sources:
        return len(sources)
    releases = copy_asset.get("releases")
    return len(releases) if isinstance(releases, list) else 0


def build_release_copy_asset(
    entries: list[dict[str, Any]],
    *,
    version: str,
    headline: str,
) -> dict[str, Any]:
    product = release_product_name(entries)
    release_theme = infer_release_theme(release_highlights(entries))
    return {
        "schema_version": "1.0",
        "kind": "release_copy",
        "product": product,
        "version": version,
        "release_theme": release_theme,
        "headline": headline or headline_from_theme(release_theme),
        "subheadline": subheadline_from_theme(product, version, release_theme),
        "releases": release_sections(entries),
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


def release_highlights(entries: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for entry in entries:
        points.extend(release_points_for_entry(entry))
    return points[:4]


def release_sections(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "package": str(entry["package"]),
            "version": str(entry["version"]),
            "changes": release_points_for_entry(entry),
        }
        for entry in entries
    ]


def release_points_for_entry(entry: dict[str, Any]) -> list[str]:
    points: list[str] = []
    for summary in entry["summary"]:
        points.append(shorten_sentence(str(summary), 180))
    return points


def infer_release_theme(highlights: list[str]) -> str:
    joined = " ".join(point.lower() for point in highlights)
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
    ]
    releases = copy_asset.get("releases")
    emit_packages = release_copy_should_emit_packages(copy_asset)
    if isinstance(releases, list) and releases:
        lines.append("releases:")
        for release in releases:
            if not isinstance(release, dict):
                continue
            if emit_packages:
                lines.extend(
                    [
                        f"  - package: {yaml_string(str(release.get('package') or ''))}",
                        f"    version: {yaml_string(str(release.get('version') or ''))}",
                        "    changes:",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"  - version: {yaml_string(str(release.get('version') or ''))}",
                        "    changes:",
                    ]
                )
            changes = release.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    text = release_change_text(change)
                    if text:
                        lines.append(f"      - {yaml_string(text)}")
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


def release_copy_should_emit_packages(copy_asset: dict[str, Any]) -> bool:
    releases = copy_asset.get("releases")
    if not isinstance(releases, list):
        return False
    packages = {
        str(release.get("package") or "").strip()
        for release in releases
        if isinstance(release, dict) and str(release.get("package") or "").strip()
    }
    return len(packages) > 1


def release_copy_brief(copy_asset: dict[str, Any]) -> str:
    return (
        f"Release notes page for {copy_asset['product']} {copy_asset['version']}: "
        f"{copy_asset['release_theme']}"
    )


def release_copy_subject(copy_asset: dict[str, Any]) -> str:
    product = str(copy_asset["product"])
    version = str(copy_asset["version"])
    releases = release_copy_prompt_releases(copy_asset)
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
        "",
        "Chronological release list from CHANGELOG.md:",
    ]
    for release in releases:
        release_version = str(release["version"])
        lines.extend(
            [
                f'- Version heading: "v{release_version}"',
                '- Change group label: "Patch Changes"',
            ]
        )
        for point in release["changes"]:
            text = release_change_text(point)
            if text:
                lines.append(f'- Change: "{text}"')
        lines.append("")
    if lines[-1] == "":
        lines.pop()
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


def release_copy_prompt_releases(copy_asset: dict[str, Any]) -> list[dict[str, Any]]:
    releases = copy_asset.get("releases")
    if isinstance(releases, list) and releases:
        return [
            release
            for release in releases
            if isinstance(release, dict) and isinstance(release.get("changes"), list)
        ]
    return []


def release_change_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    if str(value.get("text") or "").strip():
        return str(value.get("text") or "").strip()
    title = str(value.get("title") or "").strip()
    detail = str(value.get("detail") or "").strip()
    if title and detail:
        return f"{title}: {detail}"
    return detail or title


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
    project_root = Path(str(plan["project_root"]))
    paths = project_paths(metadata, project_root)
    release_portfolio = paths["portfolios"]["release"]
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
        "portfolio": {
            "domain": "release",
            "theme": theme_source_path(metadata, project_root) or "",
            "accepted": str(release_portfolio["accepted"]),
            "asset_state": str(release_portfolio["asset_state"]),
            "patterns": str(release_portfolio["patterns"]),
            "excluded_domains": ["promo"],
        },
        "producer": producer,
        "resolved_style": run_lock.get("resolved_style", {}) if isinstance(run_lock, dict) else {},
        "assets": assets,
    }
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "path": context_path,
        "producer_skill": producer_skill,
        "portfolio": "release",
        "portfolio_accepted": release_portfolio["accepted"],
        "portfolio_asset_state": release_portfolio["asset_state"],
        "error": "",
    }


def print_release_summary(
    plan: dict[str, object],
    *,
    metadata_path: str | None,
    mode: str,
    campaign_status: str,
    copy_status: str | None = None,
    producer_context_path: Path | None = None,
    producer_skill: str | None = None,
    portfolio: str | None = None,
    portfolio_accepted: Path | None = None,
    portfolio_asset_state: Path | None = None,
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
    if portfolio is not None:
        values["portfolio"] = portfolio
    if portfolio_accepted is not None:
        values["portfolio_accepted"] = portfolio_accepted
    if portfolio_asset_state is not None:
        values["portfolio_asset_state"] = portfolio_asset_state
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
    release_count: int,
) -> tuple[list[dict[str, Any]], str | None]:
    changelog_files = discover_changelog_files(project_root, changelog_value)
    if changelog_value and not changelog_files:
        return [], f"{resolve_project_path(project_root, changelog_value)}: changelog not found"

    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in changelog_files:
        for entry in read_changelog_entries(path, release_count):
            key = (str(entry.get("package") or ""), str(entry.get("version") or ""))
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
            if len(entries) >= release_count:
                return entries, None
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
    entries = read_changelog_entries(path, 1)
    return entries[0] if entries else None


def read_changelog_entries(path: Path, release_count: int) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = raw.splitlines()
    entries: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        version = changelog_version_from_heading(line)
        if not version:
            continue
        end = next_changelog_release_index(lines, index + 1)
        summary = summarize_changelog_body(lines[index + 1 : end], path)
        entries.append(
            {
                "path": path,
                "package": changelog_package_name(path, lines),
                "version": version,
                "summary": summary,
            }
        )
        if len(entries) >= release_count:
            break
    return entries


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
    if entries and entries[0].get("version"):
        return str(entries[0]["version"])
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


def producer_constraint_errors(args: list[str], metadata: dict[str, Any]) -> list[str]:
    if not metadata or not args or args[0] not in {"validate", "render"}:
        return []
    campaign_value = first_positional(args, start=1)
    theme_value = option_value(args, "--theme") or option_value(args, "--brand")
    if not campaign_value or not theme_value:
        return []
    project_root = project_root_for(metadata)
    campaign_path = Path(resolve_project_path(project_root, campaign_value))
    theme_path = Path(resolve_project_path(project_root, theme_value))
    try:
        from harness_runtime.config import load_harness_config

        loaded = load_harness_config(campaign_path=campaign_path, brand_path=theme_path)
    except Exception:
        return []

    producer_name = " ".join(
        value.lower()
        for value in (
            string_at(metadata, "skills", "image") or "",
            loaded.brand.producer.producer_id or "",
            loaded.brand.producer.model or "",
        )
    )
    if "gpt-image" not in producer_name:
        return []

    errors: list[str] = []
    output_format = loaded.brand.producer.params.output_format.lower()
    if output_format not in {"png", "jpeg", "jpg", "webp"}:
        errors.append(
            "gpt-image constraint: producer.params.output_format must be one of "
            "png, jpeg, jpg, or webp"
        )

    for deliverable in loaded.campaign.deliverables:
        width, height = deliverable.size
        if width % 16 or height % 16:
            suggested = f"{round_up_to_multiple(width, 16)}x{round_up_to_multiple(height, 16)}"
            errors.append(
                f"gpt-image constraint: deliverable {deliverable.id} size "
                f"{width}x{height} must be a multiple of 16; suggested {suggested}"
            )
        ratio = width / height
        if ratio < 0.25 or ratio > 4:
            errors.append(
                f"gpt-image constraint: deliverable {deliverable.id} aspect ratio "
                "must be between 1:4 and 4:1"
            )

    references = loaded.resolved_style.references
    if len(references) > 10:
        errors.append("gpt-image constraint: use at most 10 reference images")
    for reference in references:
        suffix = Path(reference).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            errors.append(
                f"gpt-image constraint: reference image {reference} must be png, jpg, jpeg, or webp"
            )
    return errors


def first_positional(args: list[str], start: int) -> str | None:
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
            return token
    return None


def option_value(args: list[str], flag: str) -> str | None:
    for index, token in enumerate(args):
        if token == flag and index + 1 < len(args):
            return args[index + 1]
        if token.startswith(f"{flag}="):
            return token.split("=", 1)[1]
    return None


def round_up_to_multiple(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def slugify(value: str, default: str) -> str:
    slug = SLUG_PART_RE.sub("-", value.strip().lower()).strip("-")
    return slug or default


def check_project(args: list[str], metadata: dict[str, Any], metadata_path: str | None) -> int:
    target = args[0] if args else "."
    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    paths = project_paths(metadata, project_root)
    yaml_ready = python_module_available("yaml")
    theme_path = theme_source_path(metadata, project_root)
    campaign_value = metadata_path_value(metadata, "campaign", "path")
    campaign_path = resolve_project_path(project_root, campaign_value) if campaign_value else None

    print_kv(
        {
            "project_root": project_root,
            "metadata": metadata_path or "",
            "marketing_root": paths["marketing_root"],
            "marketing_root_exists": paths["marketing_root"].exists(),
            "theme": theme_source_path_value(metadata) or "",
            "theme_exists": Path(theme_path).exists() if theme_path else False,
            "campaign": metadata_path_value(metadata, "campaign", "path") or "",
            "campaign_exists": Path(campaign_path).exists() if campaign_path else False,
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
            "campaigns_root": paths["campaigns_root"],
            "campaigns_dir": paths["campaigns_dir"],
            "release_campaigns_dir": paths["campaign_dirs"]["release"],
            "promo_campaigns_dir": paths["campaign_dirs"]["promo"],
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
            print("usage: harness.py repo state [--compact] [target-dir]")
            return 0
        elif token.startswith("-"):
            raise SystemExit(f"unknown repo state option: {token}")
        else:
            target = token

    project_root = project_root_for(metadata, fallback=Path(target).resolve())
    snapshot = collect_state_snapshot(metadata, project_root, metadata_path)
    print(json.dumps(snapshot, indent=2 if pretty else None, sort_keys=True))
    return 1 if snapshot["errors"] else 0


def project_paths(metadata: dict[str, Any], project_root: Path) -> dict[str, Any]:
    marketing_root = path_at(
        metadata, project_root, DEFAULT_MARKETING_ROOT, "project", "marketingRoot"
    )
    scratch_dir = path_at(metadata, project_root, DEFAULT_SCRATCH_DIR, "artifacts", "scratch")
    approved_dir = path_at(metadata, project_root, DEFAULT_APPROVED_DIR, "artifacts", "approved")
    plans_dir = path_at(metadata, project_root, "assets/marketing/plans", "state", "plans")
    asset_index = path_at(
        metadata,
        project_root,
        "assets/marketing/asset-state.yaml",
        "state",
        "assetIndex",
    )
    accepted_state = path_at(
        metadata,
        project_root,
        "assets/marketing/accepted.yaml",
        "state",
        "accepted",
    )
    directory_state_file = string_at(metadata, "state", "directoryStateFile") or "asset-state.yaml"
    references_value = theme_metadata_path_value(metadata, "references")
    legacy_campaigns_value = theme_metadata_path_value(metadata, "campaigns")
    campaigns_root = campaign_root_path(
        metadata,
        project_root,
        Path(resolve_project_path(project_root, legacy_campaigns_value))
        if legacy_campaigns_value
        else marketing_root / "campaigns",
    )
    campaign_dirs = campaign_domain_paths(metadata, project_root, campaigns_root)
    campaigns_dir = campaign_dirs["promo"]
    references_dir = (
        Path(resolve_project_path(project_root, references_value))
        if references_value
        else marketing_root / "references"
    )
    portfolios = portfolio_paths(metadata, project_root, marketing_root)
    return {
        "marketing_root": marketing_root,
        "campaigns_root": campaigns_root,
        "scratch_dir": scratch_dir,
        "approved_dir": approved_dir,
        "plans_dir": plans_dir,
        "asset_index": asset_index,
        "directory_state_file": directory_state_file,
        "accepted_state": accepted_state,
        "campaigns_dir": campaigns_dir,
        "campaign_dirs": campaign_dirs,
        "references_dir": references_dir,
        "portfolios": portfolios,
    }


def campaign_root_path(
    metadata: dict[str, Any],
    project_root: Path,
    default: Path,
) -> Path:
    root_value = metadata_path_value(metadata, "campaigns", "root")
    return (
        Path(resolve_project_path(project_root, root_value))
        if root_value
        else default
    )


def campaign_domain_paths(
    metadata: dict[str, Any],
    project_root: Path,
    campaigns_root: Path,
) -> dict[str, Path]:
    return {
        "release": path_at(
            metadata,
            project_root,
            str(campaigns_root / "release"),
            "campaigns",
            "release",
        ),
        "promo": path_at(
            metadata,
            project_root,
            str(campaigns_root / "promo"),
            "campaigns",
            "promo",
        ),
    }


def portfolio_paths(
    metadata: dict[str, Any],
    project_root: Path,
    marketing_root: Path,
) -> dict[str, dict[str, Path]]:
    root_value = metadata_path_value(metadata, "portfolios", "root")
    root = (
        Path(resolve_project_path(project_root, root_value))
        if root_value
        else marketing_root / "portfolios"
    )
    result: dict[str, dict[str, Path]] = {}
    for domain in PORTFOLIO_DOMAINS:
        domain_root = root / domain
        result[domain] = {
            "accepted": path_at(
                metadata,
                project_root,
                str(domain_root / "accepted.yaml"),
                "portfolios",
                domain,
                "accepted",
            ),
            "asset_state": path_at(
                metadata,
                project_root,
                str(domain_root / "asset-state.yaml"),
                "portfolios",
                domain,
                "assetState",
            ),
            "patterns": path_at(
                metadata,
                project_root,
                str(domain_root / "patterns.md"),
                "portfolios",
                domain,
                "patterns",
            ),
        }
    return result


def org_brand_paths(metadata: dict[str, Any], project_root: Path) -> dict[str, Path]:
    return {
        "brand_standard": path_at(
            metadata,
            project_root,
            FALLBACK_ORG_BRAND_STANDARD,
            "brandStandard",
            "path",
        ),
        "theme_base": path_at(
            metadata,
            project_root,
            FALLBACK_ORG_THEME_BASE,
            "brandStandard",
            "themeBase",
        ),
        "references": path_at(
            metadata,
            project_root,
            FALLBACK_ORG_REFERENCES,
            "brandStandard",
            "references",
        ),
    }


def collect_state_snapshot(
    metadata: dict[str, Any],
    project_root: Path,
    metadata_path: str | None,
) -> dict[str, Any]:
    paths = project_paths(metadata, project_root)
    errors: list[str] = []
    state_files = collect_state_files(metadata, project_root, paths, errors)
    portfolios = collect_portfolio_state(paths, errors)
    asset_roots = collect_asset_roots(metadata, project_root, paths, errors)
    related_repos = collect_related_repos(metadata, project_root, errors)
    required_reads = [
        paths["asset_index"],
        paths["accepted_state"],
        *portfolio_read_paths(portfolios),
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
            "references": theme_metadata_path_value(metadata, "references") or "",
        },
        "campaigns": {
            "root": str(paths["campaigns_root"]),
            "release": str(paths["campaign_dirs"]["release"]),
            "promo": str(paths["campaign_dirs"]["promo"]),
        },
        "state": {
            "plans": str(paths["plans_dir"]),
            "asset_index": str(paths["asset_index"]),
            "accepted": str(paths["accepted_state"]),
            "directory_state_file": paths["directory_state_file"],
        },
        "asset_roots": asset_roots,
        "state_files": state_files,
        "portfolios": portfolios,
        "related_repos": related_repos,
        "read_before_production": unique_strings(str(path) for path in required_reads),
        "errors": errors,
    }


def collect_portfolio_state(
    paths: dict[str, Any],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for domain, portfolio in paths["portfolios"].items():
        result[domain] = {
            "accepted": read_state_file(
                "portfolio_accepted", portfolio["accepted"].resolve(), errors
            ),
            "asset_state": read_state_file(
                "portfolio_asset_state", portfolio["asset_state"].resolve(), errors
            ),
            "patterns": {
                "kind": "portfolio_patterns",
                "path": str(portfolio["patterns"]),
                "exists": portfolio["patterns"].exists(),
            },
        }
    return result


def portfolio_read_paths(portfolios: dict[str, dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for portfolio in portfolios.values():
        for key in ("accepted", "asset_state", "patterns"):
            entry = portfolio.get(key)
            if isinstance(entry, dict) and entry.get("exists"):
                paths.append(str(entry.get("path") or ""))
    return [path for path in paths if path]


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


def checksum_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_candidate_metadata(path: Path) -> dict[str, Any]:
    mime_type = mime_type_for(path)
    if mime_type == "image/png":
        size, error = read_png_size(path)
    elif mime_type in {"image/jpeg", "image/jpg"}:
        size, error = read_jpeg_size(path)
    elif mime_type == "image/svg+xml":
        size, error = read_svg_size(path)
    else:
        size, error = None, f"{path}: unsupported accepted asset format {path.suffix}"
    return {
        "mime_type": mime_type,
        "size": size or [0, 0],
        "error": error,
    }


def mime_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".svg":
        return "image/svg+xml"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def read_png_size(path: Path) -> tuple[list[int] | None, str | None]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"{path}: cannot read PNG: {exc}"
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None, f"{path}: invalid PNG header"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return [width, height], None


def read_jpeg_size(path: Path) -> tuple[list[int] | None, str | None]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"{path}: cannot read JPEG: {exc}"
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None, f"{path}: invalid JPEG header"
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}:
            if index + 7 > len(data):
                break
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return [width, height], None
        index += max(length, 2)
    return None, f"{path}: JPEG dimensions not found"


def read_svg_size(path: Path) -> tuple[list[int] | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path}: cannot read SVG: {exc}"
    width_match = re.search(r'\bwidth="([0-9]+)(?:px)?"', raw)
    height_match = re.search(r'\bheight="([0-9]+)(?:px)?"', raw)
    if not width_match or not height_match:
        viewbox = re.search(r'\bviewBox="(?:[-0-9.]+\s+){2}([0-9.]+)\s+([0-9.]+)"', raw)
        if viewbox:
            return [int(float(viewbox.group(1))), int(float(viewbox.group(2)))], None
        return None, f"{path}: SVG dimensions not found"
    return [int(width_match.group(1)), int(height_match.group(1))], None


def expected_asset_size(run_lock: Path, asset_id: str) -> list[int] | None:
    if not run_lock.is_file():
        return None
    try:
        data = json.loads(run_lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    assets = data.get("assets") if isinstance(data, dict) else []
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict) or str(asset.get("id") or "") != asset_id:
            continue
        size = asset.get("size")
        if (
            isinstance(size, list)
            and len(size) == 2
            and all(isinstance(item, int) and item > 0 for item in size)
        ):
            return [size[0], size[1]]
    return None


def build_approved_manifest_asset(
    *,
    project_root: Path,
    asset_id: str,
    source: Path,
    approved: Path,
    checksum: str,
    metadata: dict[str, Any],
    run_lock: Path | None,
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "file": approved.name,
        "path": relative_project_path(project_root, approved),
        "source_path": relative_project_path(project_root, source),
        "run_lock": relative_project_path(project_root, run_lock) if run_lock else "",
        "size": metadata["size"],
        "mime_type": metadata["mime_type"],
        "checksum_sha256": checksum,
    }


def write_approved_manifest(
    *,
    manifest_path: Path,
    campaign: str,
    project_root: Path,
    asset: dict[str, Any],
) -> None:
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    else:
        manifest = {}
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    assets = [
        existing
        for existing in assets
        if not (isinstance(existing, dict) and existing.get("id") == asset["id"])
    ]
    assets.append(asset)
    manifest = {
        "schema_version": "1.0",
        "kind": "approved_manifest",
        "campaign": campaign,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "assets": assets,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_accepted_entry(
    *,
    project_root: Path,
    project_id: str,
    campaign: str,
    asset_id: str,
    approved_file: Path,
    manifest_path: Path,
    run_lock: Path | None,
    checksum: str,
    metadata: dict[str, Any],
    notes: str,
    tags: list[str],
    domain: str,
    source_kind: str,
    asset_type: str,
    style_family: str,
) -> dict[str, Any]:
    entry_id = f"{campaign}-{asset_id}"
    return {
        "id": entry_id,
        "kind": "artifact",
        "campaign": campaign,
        "asset_id": asset_id,
        "domain": domain,
        "source_kind": source_kind,
        "asset_type": asset_type,
        "style_family": style_family,
        "path": relative_project_path(project_root, approved_file),
        "manifest": relative_project_path(project_root, manifest_path),
        "run_lock": relative_project_path(project_root, run_lock) if run_lock else "",
        "checksum_sha256": checksum,
        "size": metadata["size"],
        "mime_type": metadata["mime_type"],
        "tags": tags,
        "notes": notes or f"Accepted {asset_id} for {campaign}.",
        "owner": {"kind": "repo", "id": project_id},
    }


def upsert_accepted_entry(path: Path, entry: dict[str, Any], project_root: Path) -> None:
    data = read_yaml_mapping(path)
    data.setdefault("schema_version", "1.0")
    data.setdefault(
        "owner",
        {"kind": "repo", "id": str(entry.get("owner", {}).get("id") or project_root.name)},
    )
    accepted = data.get("accepted") if isinstance(data.get("accepted"), list) else []
    accepted = [
        item
        for item in accepted
        if not (isinstance(item, dict) and item.get("id") == entry["id"])
    ]
    stored = dict(entry)
    stored.pop("owner", None)
    accepted.append(stored)
    data["accepted"] = accepted
    data["revision"] = positive_revision(data.get("revision")) + 1
    write_yaml_mapping(path, data)


def upsert_asset_state(path: Path, entry: dict[str, Any], project_root: Path) -> None:
    data = read_yaml_mapping(path)
    data.setdefault("schema_version", "1.0")
    data.setdefault(
        "owner",
        {"kind": "repo", "id": str(entry.get("owner", {}).get("id") or project_root.name)},
    )
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    asset_entry = {
        "id": entry["id"],
        "path": entry["path"],
        "kind": entry["kind"],
        "campaign": entry["campaign"],
        "asset_id": entry["asset_id"],
        "domain": entry.get("domain", ""),
        "source_kind": entry.get("source_kind", ""),
        "asset_type": entry.get("asset_type", ""),
        "style_family": entry.get("style_family", ""),
        "size": entry["size"],
        "mime_type": entry["mime_type"],
        "checksum_sha256": entry["checksum_sha256"],
        "tags": entry["tags"],
    }
    assets = [
        item
        for item in assets
        if not (isinstance(item, dict) and item.get("id") == asset_entry["id"])
    ]
    assets.append(asset_entry)
    data["assets"] = assets
    data["revision"] = positive_revision(data.get("revision")) + 1
    write_yaml_mapping(path, data)


def update_plan_status(path: Path, entry: dict[str, Any]) -> None:
    data = read_yaml_mapping(path)
    data["status"] = "accepted"
    data["accepted_asset"] = {
        "id": entry["id"],
        "path": entry["path"],
        "checksum_sha256": entry["checksum_sha256"],
    }
    write_yaml_mapping(path, data)


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = load_structured_file(path)
    return data if isinstance(data, dict) else {}


def write_yaml_mapping(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_yaml(data), encoding="utf-8")


def render_yaml(value: Any, indent: int = 0) -> str:
    return "\n".join(render_yaml_lines(value, indent)) + "\n"


def render_yaml_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(render_yaml_lines(child, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(child)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{prefix}- {{}}")
                    continue
                first_key, first_child = next(iter(item.items()))
                if isinstance(first_child, (dict, list)):
                    lines.append(f"{prefix}- {first_key}:")
                    lines.extend(render_yaml_lines(first_child, indent + 4))
                else:
                    lines.append(f"{prefix}- {first_key}: {yaml_scalar(first_child)}")
                for key, child in list(item.items())[1:]:
                    if isinstance(child, (dict, list)):
                        lines.append(f"{prefix}  {key}:")
                        lines.extend(render_yaml_lines(child, indent + 4))
                    else:
                        lines.append(f"{prefix}  {key}: {yaml_scalar(child)}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(render_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines
    return [f"{prefix}{yaml_scalar(value)}"]


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if value is None:
        return "null"
    return yaml_string(str(value))


def positive_revision(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def accept_tags(raw: str, campaign: str, asset_id: str) -> list[str]:
    tags = [item.strip() for item in raw.split(",") if item.strip()]
    for default in (campaign, asset_id, "accepted"):
        if default not in tags:
            tags.append(default)
    return tags


def accepted_domain(raw: str, campaign: str) -> str:
    if raw:
        return raw if raw in PORTFOLIO_DOMAINS else ""
    return "release" if campaign.startswith("release-") else "promo"


def accepted_source_kind(domain: str, raw: str) -> str:
    if raw:
        return raw
    return "changelog" if domain == "release" else "campaign-brief"


def accepted_asset_type(domain: str, asset_id: str, raw: str) -> str:
    if raw:
        return raw
    if domain == "release":
        for value in ("release-poster", "release-card", "release-square"):
            if value in asset_id:
                return value
        return "release-poster"
    return "hero"


def accepted_style_family(domain: str, raw: str) -> str:
    if raw:
        return raw
    return "log-full-editorial" if domain == "release" else "screen-first-field-scene"


def relative_project_path(project_root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def copy_example(marketing_root: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "codefox"
    target = marketing_root / "examples" / "codefox"
    if not example.is_dir() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example, target)


def org_brand_standard_template(project_root: Path) -> str:
    org_id = slugify(project_root.name, "org")
    return f"""# {org_id} Brand Standard

## Source Inputs

- Add logos, screenshots, decks, website captures, and marketing references
  under `public/brand/references/`.

## Positioning

Describe the organization's positioning, audience, and product adaptation
rules after reviewing source inputs.

## Visual Language

Describe palette, typography direction, composition rules, materials, lighting,
motion cues, and avoid-list decisions after review.

## Voice

Describe tone, messaging constraints, and do/don't guidance.
"""


def org_theme_base_template(project_root: Path) -> str:
    org_id = slugify(project_root.name, "org")
    return f"""---
organization:
  id: {yaml_string(org_id)}
version: 1.0.0
global:
  color: {{}}
  typography: {{}}
alias:
  style: {{}}
---

# {org_id} Base Theme

Machine-readable base style lock for product repos. Fill this after reviewing
the org brand references.
"""


def load_metadata(path: str | None, project_root: str | None = None) -> dict[str, Any]:
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
    data[INTERNAL_METADATA_BASE_KEY] = str(metadata_path.resolve().parent)
    if project_root:
        data[INTERNAL_PROJECT_ROOT_OVERRIDE_KEY] = str(Path(project_root).expanduser().resolve())
    return data


def parse_yaml_document(raw: str) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required to parse Brand Studio YAML metadata. "
            "Run `uv sync` in the skill checkout or install it with "
            "`python3 -m pip install pyyaml`; JSON metadata still works without PyYAML."
        ) from exc
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
    override = string_at(metadata, INTERNAL_PROJECT_ROOT_OVERRIDE_KEY)
    if override:
        return Path(override).expanduser().resolve()
    root = string_at(metadata, "project", "root")
    base_value = string_at(metadata, INTERNAL_METADATA_BASE_KEY)
    base = Path(base_value).expanduser().resolve() if base_value else None
    if not root:
        return fallback or base or Path.cwd()
    root_path = Path(root).expanduser()
    if root_path.is_absolute():
        return root_path.resolve()
    return (base or fallback or Path.cwd()).joinpath(root_path).resolve()


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
