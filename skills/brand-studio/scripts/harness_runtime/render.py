from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_runtime.config import (
    CampaignContent,
    Deliverable,
    LoadedConfig,
    ResolvedStyle,
    load_harness_config,
)
from harness_runtime.manifest import AssetManifestInput, build_manifest, checksum_file, write_json
from harness_runtime.producer import GenerationRequest, ProducerError, write_dry_run_asset


@dataclass(frozen=True)
class RenderResult:
    output_dir: Path
    manifest_path: Path
    run_lock_path: Path
    assets: list[AssetManifestInput]


def render_campaign(
    campaign_path: Path,
    brand_path: Path,
    outputs_dir: Path = Path("outputs"),
    dry_run: bool = False,
) -> RenderResult:
    loaded = load_harness_config(campaign_path=campaign_path, brand_path=brand_path)
    return render_loaded_config(loaded, outputs_dir=outputs_dir, dry_run=dry_run)


def render_loaded_config(
    loaded: LoadedConfig,
    outputs_dir: Path = Path("outputs"),
    dry_run: bool = False,
) -> RenderResult:
    if not dry_run:
        raise ProducerError(
            "live asset generation is handled by an external producer skill. "
            "Run render --dry-run to export prompts, manifest, and run.lock context, "
            "then pass that context to the selected producer."
        )

    campaign = loaded.campaign
    brand = loaded.brand
    output_dir = outputs_dir / campaign.name
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    assets: list[AssetManifestInput] = []
    run_assets: list[dict[str, Any]] = []

    for deliverable in campaign.deliverables:
        seed = seed_for_asset(
            brand.producer.params.seed_strategy,
            brand.producer.params.seed,
            campaign.name,
            deliverable.id,
        )
        prompt = build_asset_prompt(
            loaded.resolved_style,
            campaign.brief,
            campaign.content,
            deliverable,
        )
        output_format = "svg" if dry_run else brand.producer.params.output_format
        output_path = output_dir / f"{deliverable.id}.{output_format}"
        request = GenerationRequest(
            asset_id=deliverable.id,
            prompt=prompt,
            negative_prompt=loaded.resolved_style.negative,
            size=deliverable.size,
            seed=seed,
            producer_id=brand.producer.producer_id,
            model=brand.producer.model,
            params=brand.producer.params.model_dump(exclude_none=True),
            references=loaded.resolved_style.references,
            palette=loaded.resolved_style.palette,
            typography=loaded.resolved_style.typography,
            dry_run=dry_run,
        )
        result = write_dry_run_asset(request, output_path)
        asset = AssetManifestInput(
            id=deliverable.id,
            file=result.path.name,
            path=result.path,
            size=deliverable.size,
            seed=result.seed,
            mime_type=result.mime_type,
            producer_metadata=result.producer_metadata,
        )
        assets.append(asset)
        run_assets.append(
            {
                "id": deliverable.id,
                "file": result.path.name,
                "size": list(deliverable.size),
                "seed": result.seed,
                "prompt": prompt,
                "negative_prompt": loaded.resolved_style.negative,
                "producer_metadata": result.producer_metadata,
            }
        )

    run_lock = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "dry_run": dry_run,
        "repo": {
            "id": brand.brand.id,
            "name": brand.brand.name,
            "version": brand.version,
        },
        "theme_path": str(loaded.brand_path),
        "campaign_path": str(loaded.campaign_path),
        "theme": loaded.brand_raw,
        "campaign": loaded.campaign_raw,
        "sidecars": {
            snapshot.kind: {
                "path": str(snapshot.path),
                "checksum_sha256": checksum_file(snapshot.path),
                "content": snapshot.raw,
            }
            for snapshot in loaded.sidecars.snapshots()
        },
        "resolved_style": {
            "name": loaded.resolved_style.name,
            "prompt": loaded.resolved_style.prompt,
            "palette": loaded.resolved_style.palette,
            "typography": loaded.resolved_style.typography,
            "negative": loaded.resolved_style.negative,
            "references": loaded.resolved_style.references,
        },
        "producer": {
            "id": brand.producer.producer_id,
            "model": brand.producer.model,
            "params": brand.producer.params.model_dump(exclude_none=True),
        },
        "assets": run_assets,
    }
    run_lock_path = output_dir / "run.lock.json"
    write_json(run_lock_path, run_lock)

    manifest = build_manifest(
        campaign=campaign,
        brand=brand,
        assets=assets,
        generated_at=generated_at,
    )
    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, manifest)

    return RenderResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        run_lock_path=run_lock_path,
        assets=assets,
    )


def build_asset_prompt(
    style: ResolvedStyle,
    brief: str,
    content: CampaignContent,
    deliverable: Deliverable,
) -> str:
    width, height = deliverable.size
    parts = [
        f"Locked visual style: {style.prompt}",
        f"Campaign brief: {brief}",
        f"Subject: {content.subject}",
        f"Deliverable: {deliverable.id}, {width}x{height}px",
    ]
    if content.headline:
        parts.append(f'Headline text to render exactly: "{content.headline}"')
    if style.palette:
        parts.append(
            "Use only this locked palette unless natural lighting requires subtle neutrals: "
            f"{', '.join(style.palette)}"
        )
    if style.typography:
        parts.append(f"Typography direction for visible text: {style.typography}")
    if style.references:
        parts.append(f"Respect visual reference assets: {', '.join(style.references)}")
    parts.append(
        "Keep the locked visual style constant; vary only the campaign content and "
        "composition for this deliverable."
    )
    return "\n".join(parts)


def seed_for_asset(
    seed_strategy: str,
    base_seed: int | None,
    campaign_name: str,
    asset_id: str,
) -> int | None:
    if seed_strategy == "fixed":
        return base_seed
    if seed_strategy == "per_asset":
        material = f"{base_seed or 0}:{campaign_name}:{asset_id}".encode()
        return int(hashlib.sha256(material).hexdigest()[:8], 16)
    if seed_strategy == "random":
        return random.SystemRandom().randint(0, 2**31 - 1)
    raise ValueError(f"unknown seed_strategy: {seed_strategy}")
