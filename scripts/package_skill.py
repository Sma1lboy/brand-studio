#!/usr/bin/env python3
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

EXCLUDE_ANYWHERE = {
    ".DS_Store",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}

EXCLUDE_TOP_LEVEL = {
    ".env",
    ".uv-venv",
    ".venv",
    "examples",
    "outputs",
    "published",
    "releases",
    "tests",
    "workspace",
}
def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    skill_dir = repo_root / "skills" / "marketing-harness"
    default_output = repo_root.parent / "marketing-harness.zip"
    include_examples = "--include-examples" in sys.argv[1:]
    positional = [arg for arg in sys.argv[1:] if arg != "--include-examples"]
    output = Path(positional[0]).resolve() if positional else default_output
    output.parent.mkdir(parents=True, exist_ok=True)
    if not (skill_dir / "SKILL.md").is_file():
        raise SystemExit(f"Missing skill payload: {skill_dir / 'SKILL.md'}")

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_dir.rglob("*")):
            relative = path.relative_to(skill_dir)
            if (
                should_exclude(relative, include_examples=include_examples)
                or path.resolve() == output
            ):
                continue
            if path.is_file():
                archive.write(path, arcname=relative)

    print(output)
    return 0


def should_exclude(relative: Path, *, include_examples: bool = False) -> bool:
    top_level_excludes = EXCLUDE_TOP_LEVEL - {"examples"} if include_examples else EXCLUDE_TOP_LEVEL
    if relative.parts and relative.parts[0] in top_level_excludes:
        return True
    return any(part in EXCLUDE_ANYWHERE for part in relative.parts)


if __name__ == "__main__":
    raise SystemExit(main())
