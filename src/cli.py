from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from harness.config import ConfigError, load_harness_config
from harness.providers import ProviderError
from harness.publish import publish_campaign
from harness.regression import run_regression
from harness.render import render_campaign
from harness.style import promote_style, propose_style

app = typer.Typer(no_args_is_help=True)
style_app = typer.Typer(no_args_is_help=True)
app.add_typer(style_app, name="style")

DEFAULT_BRAND_LOCK = Path("workspace/products/codefox/codefox/brand.lock.yaml")


class Channel(StrEnum):
    cdn = "cdn"
    release = "release"
    repo = "repo"


class StyleProducerName(StrEnum):
    local = "local"
    command = "command"


@app.command()
def validate(
    campaign: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    brand: Annotated[
        Path,
        typer.Option("--brand", exists=True, dir_okay=False),
    ] = DEFAULT_BRAND_LOCK,
) -> None:
    """Validate brand lock and campaign configuration without rendering."""
    run_with_errors(lambda: _validate(campaign, brand))


@app.command()
def render(
    campaign: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Do not call the image API; write SVG placeholders."),
    ] = False,
    brand: Annotated[
        Path,
        typer.Option("--brand", exists=True, dir_okay=False),
    ] = DEFAULT_BRAND_LOCK,
    outputs_dir: Annotated[Path, typer.Option("--outputs-dir")] = Path("outputs"),
) -> None:
    """Render campaign deliverables and write manifest/run lock files."""
    load_dotenv()
    run_with_errors(lambda: _render(campaign, brand, outputs_dir, dry_run))


@app.command("publish")
def publish_command(
    campaign_name: Annotated[str, typer.Argument()],
    channel: Annotated[Channel, typer.Option("--channel")] = Channel.cdn,
    publish: Annotated[
        bool,
        typer.Option("--publish", help="Perform remote write or release zip creation."),
    ] = False,
    outputs_dir: Annotated[Path, typer.Option("--outputs-dir")] = Path("outputs"),
    repo_dir: Annotated[
        Path | None,
        typer.Option("--repo-dir", help="Repo-channel asset repository directory."),
    ] = None,
) -> None:
    """Publish rendered artifacts. Defaults to dry-run unless --publish is set."""
    load_dotenv()
    run_with_errors(lambda: _publish(campaign_name, channel, outputs_dir, publish, repo_dir))


@app.command()
def regression(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Do not call the image API; write SVG placeholders."),
    ] = False,
    brand: Annotated[
        Path,
        typer.Option("--brand", exists=True, dir_okay=False),
    ] = DEFAULT_BRAND_LOCK,
    prompts: Annotated[
        Path,
        typer.Option("--prompts", exists=True, dir_okay=False),
    ] = Path("tests/regression/prompts.yaml"),
    outputs_dir: Annotated[Path, typer.Option("--outputs-dir")] = Path("outputs"),
) -> None:
    """Run the fixed regression prompt suite."""
    load_dotenv()
    run_with_errors(lambda: _regression(brand, prompts, outputs_dir, dry_run))


@style_app.command("propose")
def style_propose_command(
    out: Annotated[Path, typer.Option("--out", help="Proposal brand.lock output path.")],
    base: Annotated[
        Path,
        typer.Option("--base", exists=True, dir_okay=False),
    ] = DEFAULT_BRAND_LOCK,
    brief: Annotated[
        Path | None,
        typer.Option("--brief", exists=True, dir_okay=False),
    ] = None,
    source: Annotated[
        list[Path] | None,
        typer.Option("--source", exists=True, help="Reference asset file or directory."),
    ] = None,
    version: Annotated[str | None, typer.Option("--version")] = None,
    producer: Annotated[StyleProducerName, typer.Option("--producer")] = StyleProducerName.local,
    producer_command: Annotated[str | None, typer.Option("--producer-command")] = None,
) -> None:
    """Generate a frozen brand.lock proposal from design inputs."""
    run_with_errors(
        lambda: _style_propose(
            base=base,
            out=out,
            brief=brief,
            source=source or [],
            version=version,
            producer=producer,
            producer_command=producer_command,
        )
    )


@style_app.command("promote")
def style_promote_command(
    proposal: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    to: Annotated[Path, typer.Option("--to", help="Target brand.lock path.")],
    version: Annotated[str | None, typer.Option("--version")] = None,
) -> None:
    """Promote a reviewed proposal to a brand lock file."""
    run_with_errors(lambda: _style_promote(proposal=proposal, to=to, version=version))


def _validate(campaign: Path, brand: Path) -> None:
    loaded = load_harness_config(campaign_path=campaign, brand_path=brand)
    typer.echo(
        f"OK: {campaign} uses brand '{loaded.brand.brand.id}' "
        f"brand.lock {loaded.brand.version} "
        f"style '{loaded.resolved_style.name}' "
        f"for {len(loaded.campaign.deliverables)} deliverables"
    )


def _render(campaign: Path, brand: Path, outputs_dir: Path, dry_run: bool) -> None:
    result = render_campaign(
        campaign_path=campaign,
        brand_path=brand,
        outputs_dir=outputs_dir,
        dry_run=dry_run,
    )
    mode = "dry-run" if dry_run else "live"
    typer.echo(f"Rendered ({mode}): {result.output_dir}")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo(f"Run lock: {result.run_lock_path}")


def _publish(
    campaign_name: str,
    channel: Channel,
    outputs_dir: Path,
    publish: bool,
    repo_dir: Path | None,
) -> None:
    result = publish_campaign(
        campaign_name=campaign_name,
        channel=channel.value,
        outputs_dir=outputs_dir,
        publish=publish,
        repo_dir=repo_dir,
    )
    mode = "published" if publish else "dry-run"
    typer.echo(f"{mode}: {result.channel}")
    if result.release_path:
        typer.echo(f"Artifact path: {result.release_path}")
    for artifact in result.artifacts:
        typer.echo(f"- {artifact['id']}: {artifact['url']}")


def _regression(brand: Path, prompts: Path, outputs_dir: Path, dry_run: bool) -> None:
    result = run_regression(
        brand_path=brand,
        prompts_path=prompts,
        outputs_dir=outputs_dir,
        dry_run=dry_run,
    )
    mode = "dry-run" if dry_run else "live"
    typer.echo(f"Regression complete ({mode}): {result.output_dir}")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo(f"Run lock: {result.run_lock_path}")
    typer.echo(f"Scorecard: {result.scorecard_path}")


def _style_propose(
    *,
    base: Path,
    out: Path,
    brief: Path | None,
    source: list[Path],
    version: str | None,
    producer: StyleProducerName,
    producer_command: str | None,
) -> None:
    result = propose_style(
        base_path=base,
        out_path=out,
        brief_path=brief,
        source_paths=source,
        version=version,
        producer_name=producer.value,
        producer_command=producer_command,
    )
    typer.echo(
        f"Style proposal: {result.path} "
        f"(version {result.version}, producer {result.producer}, "
        f"{result.reference_count} references)"
    )


def _style_promote(proposal: Path, to: Path, version: str | None) -> None:
    target = promote_style(proposal_path=proposal, target_path=to, version=version)
    typer.echo(f"Promoted style lock: {target}")


def run_with_errors(fn) -> None:
    try:
        fn()
    except (ConfigError, ProviderError, FileNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
