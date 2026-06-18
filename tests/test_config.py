from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.config import (
    ConfigError,
    TokenReferenceError,
    UnknownStyleError,
    load_harness_config,
    resolve_style_alias,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_WORKSPACE = ROOT / "skills/marketing-harness/examples/codefox/workspace"


def test_example_config_resolves_alias_tokens() -> None:
    loaded = load_harness_config(
        campaign_path=(
            EXAMPLE_WORKSPACE / "products/codefox/codefox/campaigns/example.campaign.yaml"
        ),
        brand_path=EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml",
    )

    assert loaded.resolved_style.name == "launch-hero"
    assert loaded.brand.brand.id == "codefox"
    assert loaded.brand.brand.name == "CodeFox"
    assert loaded.brand.portfolio is not None
    assert loaded.brand.portfolio.id == "codefox"
    assert loaded.sidecars.portfolio_meta is not None
    assert loaded.sidecars.brand_meta is not None
    assert "#1A1A2E" in loaded.resolved_style.palette
    assert "premium editorial product visual" in loaded.resolved_style.prompt
    assert loaded.campaign.content.subject


def test_proposal_brand_lock_loads_product_sidecars(tmp_path: Path) -> None:
    product_dir = tmp_path / "workspace" / "products" / "codefox" / "codefox"
    proposal_dir = product_dir / "proposals"
    proposal_dir.mkdir(parents=True)

    proposal_path = proposal_dir / "proposal.lock.yaml"
    proposal_path.write_text(
        (EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    for name in ("brand.meta.yaml", "elements.yaml", "accepted.yaml"):
        (product_dir / name).write_text(
            (EXAMPLE_WORKSPACE / "products/codefox/codefox" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    loaded = load_harness_config(
        campaign_path=(
            EXAMPLE_WORKSPACE / "products/codefox/codefox/campaigns/example.campaign.yaml"
        ),
        brand_path=proposal_path,
    )

    assert loaded.sidecars.brand_meta is not None
    assert loaded.sidecars.brand_meta.path == product_dir / "brand.meta.yaml"
    assert loaded.sidecars.brand_elements is not None
    assert loaded.sidecars.brand_elements.path == product_dir / "elements.yaml"
    assert loaded.sidecars.brand_accepted is not None
    assert loaded.sidecars.brand_accepted.path == product_dir / "accepted.yaml"


def test_unknown_campaign_style_fails() -> None:
    loaded = load_harness_config(
        campaign_path=(
            EXAMPLE_WORKSPACE / "products/codefox/codefox/campaigns/example.campaign.yaml"
        ),
        brand_path=EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml",
    )

    with pytest.raises(UnknownStyleError, match="does-not-exist"):
        resolve_style_alias(loaded.brand, "does-not-exist")


def test_broken_global_reference_reports_alias_context(tmp_path: Path) -> None:
    brand = yaml.safe_load(
        (EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml").read_text(
            encoding="utf-8"
        )
    )
    brand["alias"]["style"]["launch-hero"]["$value"]["prompt"] = "{global.style-fragment.missing}"
    brand_path = tmp_path / "brand.lock.yaml"
    brand_path.write_text(yaml.safe_dump(brand), encoding="utf-8")

    with pytest.raises(TokenReferenceError, match=r"alias\.style\.launch-hero.*missing"):
        load_harness_config(
            campaign_path=(
                EXAMPLE_WORKSPACE / "products/codefox/codefox/campaigns/example.campaign.yaml"
            ),
            brand_path=brand_path,
        )


def test_campaign_cannot_inline_style_description(tmp_path: Path) -> None:
    campaign = yaml.safe_load(
        (EXAMPLE_WORKSPACE / "products/codefox/codefox/campaigns/example.campaign.yaml").read_text(
            encoding="utf-8"
        )
    )
    campaign["style_description"] = "hand-written style should not be accepted"
    campaign_path = tmp_path / "bad.campaign.yaml"
    campaign_path.write_text(yaml.safe_dump(campaign), encoding="utf-8")

    with pytest.raises(ConfigError, match="extra_forbidden"):
        load_harness_config(
            campaign_path=campaign_path,
            brand_path=EXAMPLE_WORKSPACE / "products/codefox/codefox/brand.lock.yaml",
        )
