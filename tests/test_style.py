from __future__ import annotations

from pathlib import Path

import yaml

from harness.config import load_brand, resolve_style_alias
from harness.style import promote_style, propose_style

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_WORKSPACE = ROOT / "skills/marketing-harness/examples/codefox/workspace"


def test_style_propose_generates_valid_brand_lock(tmp_path: Path) -> None:
    references_dir = tmp_path / "references"
    references_dir.mkdir()
    (references_dir / "main_visual.png").write_bytes(b"not-a-real-image")
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        "Brand colors: #102030 #E04560 #F7F7F0\n"
        "Premium developer tool launch visuals with precise UI surfaces.",
        encoding="utf-8",
    )
    out_path = tmp_path / "brand" / "proposals" / "codefox.lock.yaml"

    result = propose_style(
        base_path=EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml",
        out_path=out_path,
        brief_path=brief_path,
        source_paths=[references_dir],
        version="2.0.0",
    )

    brand, raw = load_brand(result.path)
    resolved = resolve_style_alias(brand, "launch-hero")

    assert result.version == "2.0.0"
    assert raw["global"]["color"]["brand-primary"]["$value"] == "#102030"
    assert raw["global"]["color"]["brand-accent"]["$value"] == "#E04560"
    assert raw["global"]["reference"]["main-visual"]["$value"].endswith("main_visual.png")
    assert "Premium developer tool launch visuals" in resolved.prompt
    assert resolved.references


def test_style_promote_writes_reviewed_lock(tmp_path: Path) -> None:
    proposal = yaml.safe_load(
        (EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml").read_text(
            encoding="utf-8"
        )
    )
    proposal["version"] = "3.0.0"
    proposal_path = tmp_path / "proposal.lock.yaml"
    target_path = tmp_path / "brand.lock.yaml"
    proposal_path.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8")

    promote_style(proposal_path, target_path, version="3.1.0")

    brand, _raw = load_brand(target_path)
    assert brand.version == "3.1.0"
