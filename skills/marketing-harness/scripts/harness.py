#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REMOTE_SPEC = "git+https://github.com/CodeFox-Repo/marketing-harness"


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--resolve"]:
        resolution = resolve_harness_command()
        print(" ".join(shell_quote(part) for part in resolution))
        return 0

    command = resolve_harness_command()
    completed = subprocess.run([*command, *args], check=False)
    return completed.returncode


def resolve_harness_command() -> list[str]:
    configured_project = os.getenv("HARNESS_PROJECT_DIR")
    if configured_project:
        project = Path(configured_project).expanduser().resolve()
        if not is_harness_project(project):
            raise SystemExit(f"HARNESS_PROJECT_DIR is not a marketing-harness project: {project}")
        return project_command(project)

    script_path = Path(__file__).resolve()
    for candidate in script_path.parents:
        if is_harness_project(candidate):
            return project_command(candidate)

    installed = shutil.which("harness")
    if installed:
        return [installed]

    uvx = shutil.which("uvx")
    if uvx:
        remote_spec = os.getenv("HARNESS_REMOTE_SPEC", REMOTE_SPEC)
        return [uvx, "--from", remote_spec, "harness"]

    raise SystemExit(
        "Could not find marketing-harness. Set HARNESS_PROJECT_DIR, install the harness CLI, "
        "or install uvx for remote fallback."
    )


def project_command(project: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "--project", str(project), "run", "harness"]

    venv_harness = project / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "harness"
    if os.name == "nt":
        venv_harness = venv_harness.with_suffix(".exe")
    if venv_harness.is_file():
        return [str(venv_harness)]

    raise SystemExit(
        "Found marketing-harness project but neither uv nor .venv harness is available: "
        f"{project}"
    )


def is_harness_project(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "src" / "harness").is_dir()
        and (path / "src" / "cli.py").is_file()
    )


def shell_quote(value: str) -> str:
    if not value or any(char.isspace() or char in "'\"\\$`" for char in value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
