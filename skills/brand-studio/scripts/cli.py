#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness_runtime.config import ConfigError, load_harness_config
from harness_runtime.producer import ProducerError
from harness_runtime.render import render_campaign


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        args.handler(args)
        return 0
    except (ConfigError, ProducerError, FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness")
    subcommands = parser.add_subparsers(dest="command")

    validate = subcommands.add_parser("validate")
    validate.add_argument("campaign", type=Path)
    validate.add_argument("--theme", type=Path)
    validate.add_argument("--brand", dest="theme", help=argparse.SUPPRESS, type=Path)
    validate.set_defaults(handler=handle_validate)

    render = subcommands.add_parser("render")
    render.add_argument("campaign", type=Path)
    render.add_argument("--theme", type=Path)
    render.add_argument("--brand", dest="theme", help=argparse.SUPPRESS, type=Path)
    render.add_argument("--dry-run", action="store_true")
    render.add_argument("--outputs-dir", default=Path("outputs"), type=Path)
    render.set_defaults(handler=handle_render)

    return parser


def handle_validate(args: argparse.Namespace) -> None:
    theme_path = required_theme_path(args)
    loaded = load_harness_config(campaign_path=args.campaign, brand_path=theme_path)
    print(
        f"OK: {args.campaign} uses repo theme '{loaded.brand.brand.id}' "
        f"theme {loaded.brand.version} "
        f"style '{loaded.resolved_style.name}' "
        f"for {len(loaded.campaign.deliverables)} deliverables"
    )


def handle_render(args: argparse.Namespace) -> None:
    theme_path = required_theme_path(args)
    result = render_campaign(
        campaign_path=args.campaign,
        brand_path=theme_path,
        outputs_dir=args.outputs_dir,
        dry_run=args.dry_run,
    )
    mode = "dry-run" if args.dry_run else "live"
    print(f"Rendered ({mode}): {result.output_dir}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Run lock: {result.run_lock_path}")


def required_theme_path(args: argparse.Namespace) -> Path:
    if args.theme is None:
        raise ValueError("--theme is required")
    return args.theme


if __name__ == "__main__":
    raise SystemExit(main())
