from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from harness.manifest import checksum_file, write_json

PublishChannel = Literal["cdn", "release", "repo"]
PATH_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class PublishResult:
    channel: PublishChannel
    dry_run: bool
    manifest_path: Path
    artifacts: list[dict[str, Any]]
    release_path: Path | None = None


def publish_campaign(
    campaign_name: str,
    channel: PublishChannel = "cdn",
    outputs_dir: Path = Path("outputs"),
    publish: bool = False,
    repo_dir: Path | None = None,
) -> PublishResult:
    output_dir = outputs_dir / campaign_name
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} does not exist; render the campaign first")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if channel == "cdn":
        return publish_cdn(output_dir, manifest_path, manifest, publish=publish)
    if channel == "release":
        return publish_release(output_dir, manifest_path, manifest, publish=publish)
    if channel == "repo":
        return publish_repo(
            output_dir,
            manifest_path,
            manifest,
            publish=publish,
            repo_dir=repo_dir,
        )
    raise ValueError(f"unsupported publish channel: {channel}")


def publish_cdn(
    output_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    publish: bool,
) -> PublishResult:
    campaign_name = manifest["campaign"]
    brand = repo_brand_info(manifest)
    portfolio = repo_portfolio_info(manifest, brand)
    prefix = (os.getenv("HARNESS_CDN_PREFIX") or "marketing-harness").strip("/")
    base_url = os.getenv("HARNESS_CDN_BASE_URL", "").rstrip("/")
    artifacts: list[dict[str, Any]] = []

    for asset in manifest["assets"]:
        key = (
            f"{prefix}/products/{portfolio['id']}/{brand['id']}/"
            f"{brand['version']}/{campaign_name}/{asset['file']}"
        )
        url = f"{base_url}/{key}" if base_url else f"cdn://{key}"
        artifacts.append({"id": asset["id"], "file": asset["file"], "key": key, "url": url})
        if publish:
            upload_s3_compatible(output_dir / asset["file"], key, asset["mime_type"])
            asset["url"] = url
            asset["checksum_sha256"] = checksum_file(output_dir / asset["file"])

    manifest_key = (
        f"{prefix}/products/{portfolio['id']}/{brand['id']}/"
        f"{brand['version']}/{campaign_name}/manifest.json"
    )
    manifest_url = f"{base_url}/{manifest_key}" if base_url else f"cdn://{manifest_key}"
    artifacts.append(
        {
            "id": "manifest",
            "file": "manifest.json",
            "key": manifest_key,
            "url": manifest_url,
        }
    )

    if publish:
        manifest["published_at"] = datetime.now(UTC).isoformat()
        manifest["publish_channel"] = "cdn"
        manifest["portfolio"] = portfolio
        manifest["brand"] = brand
        write_json(manifest_path, manifest)
        upload_s3_compatible(manifest_path, manifest_key, "application/json")

    return PublishResult(
        channel="cdn",
        dry_run=not publish,
        manifest_path=manifest_path,
        artifacts=artifacts,
    )


def publish_release(
    output_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    publish: bool,
) -> PublishResult:
    campaign_name = manifest["campaign"]
    brand = repo_brand_info(manifest)
    portfolio = repo_portfolio_info(manifest, brand)
    release_dir = Path(os.getenv("HARNESS_RELEASE_DIR", "releases"))
    release_name = f"{portfolio['id']}-{brand['id']}-{campaign_name}-brand-{brand['version']}.zip"
    release_path = release_dir / release_name
    artifacts: list[dict[str, Any]] = []

    for asset in manifest["assets"]:
        artifacts.append(
            {
                "id": asset["id"],
                "file": asset["file"],
                "url": f"release://{release_name}/{asset['file']}",
            }
        )

    if publish:
        release_dir.mkdir(parents=True, exist_ok=True)
        manifest["published_at"] = datetime.now(UTC).isoformat()
        manifest["publish_channel"] = "release"
        manifest["portfolio"] = portfolio
        manifest["brand"] = brand
        for asset in manifest["assets"]:
            asset["url"] = f"release://{release_name}/{asset['file']}"
            asset["checksum_sha256"] = checksum_file(output_dir / asset["file"])
        write_json(manifest_path, manifest)
        with zipfile.ZipFile(release_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for asset in manifest["assets"]:
                archive.write(output_dir / asset["file"], arcname=asset["file"])
            archive.write(manifest_path, arcname="manifest.json")
            run_lock_path = output_dir / "run.lock.json"
            if run_lock_path.exists():
                archive.write(run_lock_path, arcname="run.lock.json")

    return PublishResult(
        channel="release",
        dry_run=not publish,
        manifest_path=manifest_path,
        artifacts=artifacts,
        release_path=release_path,
    )


def publish_repo(
    output_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    publish: bool,
    repo_dir: Path | None = None,
) -> PublishResult:
    campaign_name = manifest["campaign"]
    brand = repo_brand_info(manifest)
    portfolio = repo_portfolio_info(manifest, brand)
    artifact_root = repo_dir or Path(os.getenv("HARNESS_REPO_PUBLISH_DIR", "published"))
    portfolio_snapshot_dir = artifact_root / "portfolios" / portfolio["id"] / portfolio["version"]
    snapshot_dir = artifact_root / "products" / portfolio["id"] / brand["id"] / brand["version"]
    artifact_dir = snapshot_dir / "artifacts" / campaign_name
    repo_manifest_path = artifact_dir / "manifest.json"
    artifacts: list[dict[str, Any]] = []

    published_manifest = json.loads(json.dumps(manifest))
    published_manifest["portfolio"] = portfolio
    published_manifest["brand"] = brand
    published_manifest["brand_lock_version"] = brand["version"]
    published_manifest["publish_channel"] = "repo"
    published_manifest["storage"] = {
        "channel": "repo",
        "kind": repo_storage_kind(artifact_root),
        "root": artifact_root.as_posix(),
        "portfolio_snapshot_path": portfolio_snapshot_dir.as_posix(),
        "snapshot_path": snapshot_dir.as_posix(),
        "artifact_path": artifact_dir.as_posix(),
    }

    for asset in published_manifest["assets"]:
        asset_path = artifact_dir / asset["file"]
        asset_rel_path = Path("artifacts") / campaign_name / asset["file"]
        url = f"repo://{asset_path.as_posix()}"
        artifacts.append(
            {
                "id": asset["id"],
                "file": asset["file"],
                "path": asset_path.as_posix(),
                "url": url,
            }
        )
        asset["path"] = asset_rel_path.as_posix()
        asset["url"] = url
        asset["checksum_sha256"] = checksum_file(output_dir / asset["file"])

    artifacts.append(
        {
            "id": "manifest",
            "file": "manifest.json",
            "path": repo_manifest_path.as_posix(),
            "url": f"repo://{repo_manifest_path.as_posix()}",
        }
    )

    if publish:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        ensure_asset_repo_gitattributes(artifact_root)
        published_manifest["published_at"] = datetime.now(UTC).isoformat()
        for asset in published_manifest["assets"]:
            shutil.copy2(output_dir / asset["file"], artifact_dir / asset["file"])
        write_json(repo_manifest_path, published_manifest)

        run_lock_path = output_dir / "run.lock.json"
        if run_lock_path.exists():
            shutil.copy2(run_lock_path, artifact_dir / "run.lock.json")
            write_input_snapshot(
                run_lock_path,
                snapshot_dir,
                campaign_name,
                portfolio_snapshot_dir,
            )

    return PublishResult(
        channel="repo",
        dry_run=not publish,
        manifest_path=repo_manifest_path,
        artifacts=artifacts,
        release_path=snapshot_dir,
    )


def repo_brand_info(manifest: dict[str, Any]) -> dict[str, str]:
    brand = manifest.get("brand")
    if isinstance(brand, dict):
        brand_id = str(brand.get("id") or "unknown-brand")
        brand_name = str(brand.get("name") or brand_id)
        brand_version = str(brand.get("version") or manifest.get("brand_lock_version") or "0.0.0")
    else:
        brand_id = "unknown-brand"
        brand_name = "Unknown Brand"
        brand_version = str(manifest.get("brand_lock_version") or "0.0.0")

    return {
        "id": safe_path_segment(brand_id, "brand id"),
        "name": brand_name,
        "version": safe_version_segment(brand_version),
    }


def repo_portfolio_info(manifest: dict[str, Any], brand: dict[str, str]) -> dict[str, str]:
    portfolio = manifest.get("portfolio")
    if isinstance(portfolio, dict):
        portfolio_id = str(portfolio.get("id") or brand["id"])
        portfolio_name = str(portfolio.get("name") or portfolio_id)
        portfolio_version = str(portfolio.get("version") or brand["version"])
    else:
        portfolio_id = brand["id"]
        portfolio_name = brand["name"]
        portfolio_version = brand["version"]

    return {
        "id": safe_path_segment(portfolio_id, "portfolio id"),
        "name": portfolio_name,
        "version": safe_version_segment(portfolio_version),
    }


def safe_path_segment(value: str, label: str) -> str:
    if not PATH_SEGMENT_RE.fullmatch(value):
        raise ValueError(f"{label} must be kebab-case for repo publishing: {value}")
    return value


def safe_version_segment(value: str) -> str:
    if "/" in value or value in {"", ".", ".."}:
        raise ValueError(f"brand version is not safe for repo publishing: {value}")
    return value


def repo_storage_kind(path: Path) -> str:
    git_marker = path / ".git"
    if git_marker.is_file():
        return "git-submodule"
    if git_marker.is_dir():
        return "git-repository"
    return "directory"


def ensure_asset_repo_gitattributes(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    attributes_path = path / ".gitattributes"
    required_lines = [
        "*.png filter=lfs diff=lfs merge=lfs -text",
        "*.jpg filter=lfs diff=lfs merge=lfs -text",
        "*.jpeg filter=lfs diff=lfs merge=lfs -text",
        "*.webp filter=lfs diff=lfs merge=lfs -text",
        "*.gif filter=lfs diff=lfs merge=lfs -text",
    ]
    if attributes_path.exists():
        existing = attributes_path.read_text(encoding="utf-8").splitlines()
    else:
        existing = []

    missing = [line for line in required_lines if line not in existing]
    if not missing:
        return

    lines = existing + missing
    attributes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_input_snapshot(
    run_lock_path: Path,
    snapshot_dir: Path,
    campaign_name: str,
    portfolio_snapshot_dir: Path,
) -> None:
    run_lock = json.loads(run_lock_path.read_text(encoding="utf-8"))

    brand_dir = snapshot_dir / "brand"
    brand_dir.mkdir(parents=True, exist_ok=True)
    brand_source = Path(str(run_lock.get("brand_lock_path", "")))
    if brand_source.exists() and brand_source.is_file():
        shutil.copy2(brand_source, brand_dir / "brand.lock.yaml")
    elif isinstance(run_lock.get("brand_lock"), dict):
        (brand_dir / "brand.lock.yaml").write_text(
            yaml.safe_dump(run_lock["brand_lock"], sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    campaigns_dir = snapshot_dir / "campaigns"
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    campaign_source = Path(str(run_lock.get("campaign_path", "")))
    campaign_snapshot_path = campaigns_dir / f"{campaign_name}.campaign.yaml"
    if campaign_source.exists() and campaign_source.is_file():
        shutil.copy2(campaign_source, campaign_snapshot_path)
    elif isinstance(run_lock.get("campaign"), dict):
        campaign_snapshot_path.write_text(
            yaml.safe_dump(run_lock["campaign"], sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    reference_paths = run_lock.get("resolved_style", {}).get("references", [])
    if isinstance(reference_paths, list) and reference_paths:
        copy_reference_snapshots(reference_paths, snapshot_dir / "references")

    write_sidecar_snapshots(run_lock, snapshot_dir, portfolio_snapshot_dir)


def write_sidecar_snapshots(
    run_lock: dict[str, Any],
    snapshot_dir: Path,
    portfolio_snapshot_dir: Path,
) -> None:
    sidecars = run_lock.get("sidecars", {})
    if not isinstance(sidecars, dict):
        return

    copy_or_write_sidecar(
        sidecars.get("portfolio_meta"),
        snapshot_dir / "portfolio" / "portfolio.meta.yaml",
        portfolio_snapshot_dir / "portfolio.meta.yaml",
    )
    copy_or_write_sidecar(
        sidecars.get("portfolio_elements"),
        snapshot_dir / "portfolio" / "elements.yaml",
        portfolio_snapshot_dir / "elements.yaml",
    )
    copy_or_write_sidecar(
        sidecars.get("portfolio_accepted"),
        snapshot_dir / "portfolio" / "accepted.yaml",
        portfolio_snapshot_dir / "accepted.yaml",
    )
    copy_or_write_sidecar(
        sidecars.get("brand_meta"),
        snapshot_dir / "metadata" / "brand.meta.yaml",
    )
    copy_or_write_sidecar(
        sidecars.get("brand_elements"),
        snapshot_dir / "metadata" / "elements.yaml",
    )
    copy_or_write_sidecar(
        sidecars.get("brand_accepted"),
        snapshot_dir / "metadata" / "accepted.yaml",
    )


def copy_or_write_sidecar(raw_sidecar: Any, *targets: Path) -> None:
    if not isinstance(raw_sidecar, dict):
        return
    source = Path(str(raw_sidecar.get("path", "")))
    content = raw_sidecar.get("content")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists() and source.is_file():
            shutil.copy2(source, target)
        elif isinstance(content, dict):
            target.write_text(
                yaml.safe_dump(content, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )


def copy_reference_snapshots(reference_paths: list[Any], references_dir: Path) -> None:
    references_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    for raw_reference in reference_paths:
        if not isinstance(raw_reference, str):
            continue
        if "://" in raw_reference:
            continue
        source = Path(raw_reference)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(
                f"{source} referenced by run.lock.json does not exist; cannot snapshot"
            )
        target_name = unique_name(source.name, used_names)
        shutil.copy2(source, references_dir / target_name)


def unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name
    source = Path(name)
    stem = source.stem or "reference"
    suffix = source.suffix
    index = 2
    while True:
        candidate = f"{stem}-{index}{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def upload_s3_compatible(path: Path, key: str, content_type: str | None = None) -> None:
    bucket = os.getenv("HARNESS_CDN_BUCKET")
    if not bucket:
        raise ValueError("HARNESS_CDN_BUCKET is required when publishing to cdn")

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("HARNESS_CDN_ENDPOINT") or None,
        region_name=os.getenv("HARNESS_CDN_REGION") or "us-east-1",
        aws_access_key_id=os.getenv("HARNESS_CDN_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("HARNESS_CDN_SECRET_ACCESS_KEY") or None,
    )
    extra_args: dict[str, str] = {}
    guessed_type = content_type or mimetypes.guess_type(path.name)[0]
    if guessed_type:
        extra_args["ContentType"] = guessed_type
    client.upload_file(str(path), bucket, key, ExtraArgs=extra_args or None)
