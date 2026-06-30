#!/usr/bin/env python3
"""Stub text-to-image backend for the sandbox.

Deterministic, offline, zero-cost: given a target path and dimensions it writes a
valid solid PNG. It stands in for a real backend (e.g. `codex exec` gpt-image) so
the full produce -> settle loop can be validated without network or billing. A
producer subagent would invoke a real backend the same way the driver invokes
this one.
"""
from __future__ import annotations

import argparse
import zlib
from pathlib import Path


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return len(data).to_bytes(4, "big") + payload + zlib.crc32(payload).to_bytes(4, "big")


def write_png(path: Path, *, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"\x00" * (width * height * 3)
    rows = b"".join(
        b"\x00" + raw[index : index + width * 3] for index in range(0, len(raw), width * 3)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(
            b"IHDR",
            width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00",
        )
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stub_image")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args(argv)
    write_png(args.target, width=args.width, height=args.height)
    print(f"stub_image wrote {args.target} ({args.width}x{args.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
