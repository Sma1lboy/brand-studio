#!/usr/bin/env python3
from __future__ import annotations

import json
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
