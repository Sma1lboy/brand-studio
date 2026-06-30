#!/usr/bin/env python3
"""Sandbox lifecycle driver — the regression net for studio runtime changes.

Copies the committed sandbox fixture into a throwaway temp project, then runs the
full lifecycle with a stub backend: validate -> dry-run render -> produce (stub
PNG + a copy asset) -> settle -> report. It asserts the durable state
transitions that real producers would otherwise bill to exercise.

This closes the CI gap: dry-run alone never reaches settle, because settle needs
a real file with mime/dimensions/checksum. A producer subagent can run this in an
isolated worktree; CI runs it via tests/test_sandbox.py.

Exit 0 = PASS, non-zero = FAIL (with a diagnostic on stderr).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
REPO_ROOT = SANDBOX.parents[1]
STUDIO = REPO_ROOT / "skills" / "brand-studio" / "scripts" / "studio.py"
STUB_IMAGE = SANDBOX / "fake_backends" / "stub_image.py"


def studio(args: list[str], project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STUDIO), "--project-root", str(project),
         "--metadata", "marketing.studio.yaml", *args],
        cwd=project, capture_output=True, text=True,
    )


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_drive() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="brand-studio-sandbox-"))
    try:
        project = tmp / "project"
        shutil.copytree(
            SANDBOX, project,
            ignore=shutil.ignore_patterns(".studio", "fake_backends", "drive.py", "__pycache__"),
        )

        expect(studio(["repo", "validate"], project).returncode == 0, "validate failed")

        render = studio(["repo", "render", "--dry-run"], project)
        expect(render.returncode == 0, f"render failed: {render.stderr}")
        run_lock_path = next(
            Path(line.split(":", 1)[1].strip())
            for line in render.stdout.splitlines() if line.startswith("Run lock:")
        )
        run_lock = json.loads(run_lock_path.read_text(encoding="utf-8"))
        campaign = run_lock_path.parent.name
        asset = run_lock["assets"][0]
        asset_id = asset["id"]
        width, height = asset["size"]

        # --- image: stub-produce a real PNG at the scratch target, then settle ---
        png_target = run_lock_path.parent / f"{asset_id}.png"
        produce = subprocess.run(
            [sys.executable, str(STUB_IMAGE), "--target", str(png_target),
             "--width", str(width), "--height", str(height)],
            capture_output=True, text=True,
        )
        expect(produce.returncode == 0, f"stub produce failed: {produce.stderr}")

        settle = studio(
            ["repo", "settle", "--campaign", campaign, "--asset-id", asset_id,
             "--domain", "promo", "--file", str(png_target)],
            project,
        )
        expect(settle.returncode == 0, f"image settle failed: {settle.stderr}")
        result = parse_kv(settle.stdout)
        expect(result.get("accepted") == "true", "image not accepted")
        expect(result.get("corpus") == "approved", "image not in approved corpus")
        expect(result.get("modality") == "image", f"bad image modality: {result.get('modality')}")

        report = studio(["repo", "report", "--file", result["approved"]], project)
        expect(report.returncode == 0, f"report failed: {report.stderr}")
        expect(parse_kv(report.stdout).get("accepted") == "true", "report says not accepted")

        # --- copy (multimodal): a brand-tone text asset settles on mime+checksum ---
        copy_target = run_lock_path.parent / f"{asset_id}-headline.md"
        copy_target.write_text("# Brand headline\n\nOn-brand copy.\n", encoding="utf-8")
        copy_settle = studio(
            ["repo", "settle", "--campaign", campaign, "--asset-id", f"{asset_id}-copy",
             "--domain", "promo", "--file", str(copy_target)],
            project,
        )
        expect(copy_settle.returncode == 0, f"copy settle failed: {copy_settle.stderr}")
        copy_result = parse_kv(copy_settle.stdout)
        copy_modality = copy_result.get("modality")
        expect(copy_modality == "copy", f"bad copy modality: {copy_modality}")
        expect(copy_result.get("accepted") == "true", "copy not accepted")

        print("PASS: validate -> render -> produce -> settle(image+copy) -> report")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    try:
        run_drive()
    except (AssertionError, StopIteration, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
