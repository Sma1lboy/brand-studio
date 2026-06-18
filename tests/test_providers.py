from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from harness.config import ProviderConfig
from harness.providers import (
    GenerationRequest,
    SkillCliImageProvider,
    UnsupportedProviderError,
    available_provider_gateways,
    create_provider,
)
from harness.providers.skill_cli import choose_skill_size, command_identity, write_sized_image


def test_create_provider_uses_skill_cli_gateway() -> None:
    provider = create_provider(ProviderConfig(gateway="skill-cli", model="gpt-image-2"))

    assert isinstance(provider, SkillCliImageProvider)


def test_create_provider_uses_gpt_image_skill_alias() -> None:
    provider = create_provider(ProviderConfig(gateway="gpt-image-skill", model="gpt-image-2"))

    assert isinstance(provider, SkillCliImageProvider)


def test_create_provider_rejects_unknown_gateway() -> None:
    with pytest.raises(UnsupportedProviderError, match="not supported"):
        create_provider(cast(ProviderConfig, SimpleNamespace(gateway="missing-provider")))


def test_available_gateways_are_skill_only() -> None:
    assert available_provider_gateways() == ["gpt-image-skill", "skill-cli"]


def test_choose_skill_size_matches_deliverable_orientation() -> None:
    assert choose_skill_size((1920, 600)) == "wide"
    assert choose_skill_size((1080, 1920)) == "portrait"
    assert choose_skill_size((1080, 1080)) == "square"
    assert choose_skill_size((900, 383), "landscape") == "landscape"


def test_write_sized_image_resizes_to_requested_deliverable(tmp_path: Path) -> None:
    source = Image.new("RGB", (32, 24), color=(255, 0, 0))
    source_path = tmp_path / "source.png"
    source.save(source_path)
    output_path = tmp_path / "asset.png"

    write_sized_image(source_path.read_bytes(), output_path, (90, 38), "png")

    with Image.open(output_path) as output:
        assert output.size == (90, 38)
        assert output.format == "PNG"


def test_skill_cli_provider_runs_configured_command_and_resizes(tmp_path: Path) -> None:
    fake_cli = tmp_path / "fake_gpt_image.py"
    fake_cli.write_text(
        """
from __future__ import annotations

import argparse

from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--prompt", required=True)
parser.add_argument("-f", "--file", required=True)
parser.add_argument("--model")
parser.add_argument("--size")
parser.add_argument("--format", default="png")
parser.add_argument("--quality")
args, _ = parser.parse_known_args()

Image.new("RGB", (64, 64), color=(12, 34, 56)).save(args.file, format=args.format.upper())
print(args.file)
""".strip(),
        encoding="utf-8",
    )
    output_path = tmp_path / "asset.png"

    result = SkillCliImageProvider().generate(
        GenerationRequest(
            asset_id="poster",
            prompt="Brand style\nSubject",
            negative_prompt="watermark",
            size=(90, 38),
            seed=12345,
            gateway="skill-cli",
            model="gpt-image-2",
            params={
                "command": [sys.executable, str(fake_cli)],
                "quality": "low",
                "output_format": "png",
                "retry_attempts": 1,
                "timeout_seconds": 10,
            },
        ),
        output_path,
    )

    assert result.mime_type == "image/png"
    assert result.provider_metadata["gateway"] == "skill-cli"
    assert result.provider_metadata["skill_size"] == "wide"
    assert result.provider_metadata["command"] == [Path(sys.executable).name, "fake_gpt_image.py"]
    assert result.provider_metadata["process_output"] == {
        "stdout_present": True,
        "stderr_present": False,
    }
    assert str(tmp_path) not in str(result.provider_metadata)
    with Image.open(output_path) as output:
        assert output.size == (90, 38)
        assert output.format == "PNG"


def test_skill_cli_command_identity_is_portable() -> None:
    assert command_identity(["/Users/example/.local/bin/gpt-image"]) == ["gpt-image"]
    assert command_identity(
        [
            "/usr/bin/python3",
            "/Users/example/.codex/skills/gpt-image/scripts/generate.py",
        ]
    ) == ["python3", "skills/gpt-image/scripts/generate.py"]
