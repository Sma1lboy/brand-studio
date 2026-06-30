#!/usr/bin/env python3
"""Introspect bundled, read-only producers and emit a routing registry.

A producer bundled under ``producers/<id>/SKILL.md`` is NOT discoverable by the
agent's Skill tool — the agent *reads* its SKILL.md as procedure/context, so it
never pollutes the user's global skill list. This script enumerates those
producers and parses each frontmatter into a capability -> producers registry
that the producer-selection logic consumes. It is deterministic: it reads
frontmatter only and never executes a producer or a backend.

Directories whose name starts with ``_`` (e.g. ``_template``) are skipped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

VALID_LANES = {"generator", "reference"}


def default_producers_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "producers"


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Return the YAML frontmatter mapping of a SKILL.md, or {} when absent."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def read_producer(skill_md: Path) -> dict[str, Any] | None:
    try:
        front = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not front:
        return None
    producer_id = str(front.get("name") or skill_md.parent.name).strip()
    capability = str(front.get("capability") or "").strip()
    modality = str(front.get("modality") or capability).strip()
    lane = str(front.get("lane") or "generator").strip()
    return {
        "id": producer_id,
        "path": str(skill_md),
        "capability": capability,
        "modality": modality,
        "lane": lane if lane in VALID_LANES else "generator",
        "description": str(front.get("description") or "").strip(),
    }


def scan_producers(producers_dir: Path) -> list[dict[str, Any]]:
    if not producers_dir.is_dir():
        return []
    producers: list[dict[str, Any]] = []
    for child in sorted(producers_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        record = read_producer(skill_md)
        if record is not None:
            producers.append(record)
    return producers


def build_registry(producers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    registry: dict[str, list[dict[str, Any]]] = {}
    for producer in producers:
        key = producer["capability"] or "unbound"
        registry.setdefault(key, []).append(producer)
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="catalog")
    parser.add_argument("--producers-dir", type=Path, default=default_producers_dir())
    parser.add_argument("--json", action="store_true", help="emit JSON registry")
    args = parser.parse_args(argv)

    producers = scan_producers(args.producers_dir)
    registry = build_registry(producers)

    if args.json:
        print(json.dumps({"producers_dir": str(args.producers_dir), "registry": registry},
                         ensure_ascii=False, indent=2))
        return 0

    if not producers:
        print(f"no bundled producers under {args.producers_dir}")
        return 0
    for capability in sorted(registry):
        print(f"{capability}:")
        for producer in registry[capability]:
            print(f"  - {producer['id']} [{producer['lane']}/{producer['modality']}] "
                  f"{producer['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
