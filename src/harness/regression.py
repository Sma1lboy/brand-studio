from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from harness.config import (
    CampaignContent,
    Deliverable,
    load_brand,
    load_yaml,
    resolve_style_alias,
)
from harness.manifest import MANIFEST_SCHEMA_VERSION, AssetManifestInput, checksum_file, write_json
from harness.providers import GenerationRequest, ImageProvider, create_provider
from harness.render import build_asset_prompt, seed_for_asset


class RegressionPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    brief: str = Field(default="Brand regression image")
    style: str = Field(default="launch-hero", pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    headline: str | None = None
    subject: str = Field(min_length=1)
    size: tuple[int, int] = (1024, 1024)


class RegressionPromptSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompts: list[RegressionPrompt] = Field(min_length=1)


@dataclass(frozen=True)
class RegressionResult:
    output_dir: Path
    manifest_path: Path
    run_lock_path: Path
    scorecard_path: Path


def load_regression_prompts(path: Path) -> tuple[RegressionPromptSet, dict[str, Any]]:
    raw = load_yaml(path)
    return RegressionPromptSet.model_validate(raw), raw


def run_regression(
    brand_path: Path = Path("workspace/products/codefox/codefox/brand.lock.yaml"),
    prompts_path: Path = Path("tests/regression/prompts.yaml"),
    outputs_dir: Path = Path("outputs"),
    dry_run: bool = False,
    provider: ImageProvider | None = None,
) -> RegressionResult:
    brand, brand_raw = load_brand(brand_path)
    prompt_set, prompt_raw = load_regression_prompts(prompts_path)
    provider = provider or create_provider(brand.provider)
    generated_at = datetime.now(UTC).isoformat()
    run_id = generated_at.replace(":", "").replace("+", "Z")
    portfolio_id = brand.portfolio.id if brand.portfolio else brand.brand.id
    output_dir = outputs_dir / "regression" / portfolio_id / brand.brand.id / brand.version / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    assets: list[AssetManifestInput] = []
    run_assets: list[dict[str, Any]] = []

    for item in prompt_set.prompts:
        style = resolve_style_alias(brand, item.style)
        deliverable = Deliverable(id=item.id, size=item.size)
        content = CampaignContent(headline=item.headline, subject=item.subject)
        seed = seed_for_asset(
            brand.provider.params.seed_strategy,
            brand.provider.params.seed,
            "regression",
            item.id,
        )
        prompt = build_asset_prompt(style, item.brief, content, deliverable)
        output_format = "svg" if dry_run else brand.provider.params.output_format
        output_path = output_dir / f"{item.id}.{output_format}"
        result = provider.generate(
            GenerationRequest(
                asset_id=item.id,
                prompt=prompt,
                negative_prompt=style.negative,
                size=item.size,
                seed=seed,
                gateway=brand.provider.gateway,
                model=brand.provider.model,
                params=brand.provider.params.model_dump(exclude_none=True),
                references=style.references,
                palette=style.palette,
                typography=style.typography,
                dry_run=dry_run,
            ),
            output_path,
        )
        assets.append(
            AssetManifestInput(
                id=item.id,
                file=result.path.name,
                path=result.path,
                size=item.size,
                seed=result.seed,
                mime_type=result.mime_type,
                provider_metadata=result.provider_metadata,
            )
        )
        run_assets.append(
            {
                "id": item.id,
                "style": item.style,
                "prompt": prompt,
                "negative_prompt": style.negative,
                "seed": result.seed,
                "provider_metadata": result.provider_metadata,
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "campaign": "regression",
        "portfolio": {
            "id": brand.portfolio.id,
            "name": brand.portfolio.name,
            "version": brand.portfolio.version,
        }
        if brand.portfolio
        else None,
        "brand": {
            "id": brand.brand.id,
            "name": brand.brand.name,
            "version": brand.version,
        },
        "brand_lock_version": brand.version,
        "generated_at": generated_at,
        "provider": {
            "gateway": brand.provider.gateway,
            "model": brand.provider.model,
        },
        "assets": [
            {
                "id": asset.id,
                "file": asset.file,
                "path": asset.file,
                "url": None,
                "size": list(asset.size),
                "mime_type": asset.mime_type,
                "checksum_sha256": checksum_file(asset.path),
                "seed": asset.seed,
            }
            for asset in assets
        ],
    }
    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, manifest)

    run_lock = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "dry_run": dry_run,
        "portfolio": {
            "id": brand.portfolio.id,
            "name": brand.portfolio.name,
            "version": brand.portfolio.version,
        }
        if brand.portfolio
        else None,
        "brand_lock_path": str(brand_path),
        "prompts_path": str(prompts_path),
        "brand_lock": brand_raw,
        "regression_prompts": prompt_raw,
        "provider": {
            "gateway": brand.provider.gateway,
            "model": brand.provider.model,
            "params": brand.provider.params.model_dump(exclude_none=True),
        },
        "assets": run_assets,
    }
    run_lock_path = output_dir / "run.lock.json"
    write_json(run_lock_path, run_lock)

    scorecard_path = output_dir / "scores.csv"
    write_scorecard(scorecard_path, prompt_set.prompts)

    return RegressionResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        run_lock_path=run_lock_path,
        scorecard_path=scorecard_path,
    )


def write_scorecard(path: Path, prompts: list[RegressionPrompt]) -> None:
    lines = ["prompt_id,score,reviewer,reviewed_at,notes"]
    lines.extend(f"{item.id},,,," for item in prompts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
