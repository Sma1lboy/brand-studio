from __future__ import annotations

from typing import TYPE_CHECKING

from harness.providers.base import ImageProvider, ProviderError
from harness.providers.skill_cli import SkillCliImageProvider

if TYPE_CHECKING:
    from harness.config import ProviderConfig


class UnsupportedProviderError(ProviderError):
    """Raised when brand.lock references an unsupported provider gateway."""


SUPPORTED_PROVIDER_GATEWAYS = ("gpt-image-skill", "skill-cli")


def create_provider(config: ProviderConfig) -> ImageProvider:
    gateway = normalize_gateway(config.gateway)
    if gateway not in SUPPORTED_PROVIDER_GATEWAYS:
        available = ", ".join(available_provider_gateways())
        raise UnsupportedProviderError(
            f"provider.gateway '{config.gateway}' is not supported. Available gateways: {available}"
        )
    return SkillCliImageProvider()


def available_provider_gateways() -> list[str]:
    return list(SUPPORTED_PROVIDER_GATEWAYS)


def normalize_gateway(gateway: str) -> str:
    return gateway.strip().lower()
