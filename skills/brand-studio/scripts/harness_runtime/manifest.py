from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_runtime.config import BrandLock, CampaignConfig

MANIFEST_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class AssetManifestInput:
    id: str
    file: str
    path: Path
    size: tuple[int, int]
    seed: int | None
    mime_type: str
    producer_metadata: dict[str, Any] = field(default_factory=dict)


def build_manifest(
    campaign: CampaignConfig,
    brand: BrandLock,
    assets: list[AssetManifestInput],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "campaign": campaign.name,
        "repo": {
            "id": brand.brand.id,
            "name": brand.brand.name,
            "version": brand.version,
        },
        "theme_version": brand.version,
        "generated_at": generated_at,
        "producer": {
            "id": brand.producer.producer_id,
            "model": brand.producer.model,
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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
