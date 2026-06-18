from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

TOKEN_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
REFERENCE_RE = re.compile(r"\{([^{}]+)\}")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ConfigError(ValueError):
    """Base configuration error with a user-readable message."""


class TokenReferenceError(ConfigError):
    """Raised when a design token reference cannot be resolved safely."""


class UnknownStyleError(ConfigError):
    """Raised when a campaign references a missing alias style."""


class ProviderParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    seed_strategy: Literal["fixed", "per_asset", "random"] = "fixed"
    seed: int | None = 12345
    guidance: float | None = None
    steps: int | None = None
    timeout_seconds: int = Field(default=120, ge=1)
    retry_attempts: int = Field(default=3, ge=1)
    output_format: str = Field(default="png", pattern=r"^[a-z0-9]+$")

    @model_validator(mode="after")
    def require_fixed_seed(self) -> ProviderParams:
        if self.seed_strategy == "fixed" and self.seed is None:
            raise ValueError("provider.params.seed is required when seed_strategy is fixed")
        return self

    def provider_payload(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        for key in ("seed_strategy", "timeout_seconds", "retry_attempts", "output_format"):
            data.pop(key, None)
        return data


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway: Literal["skill-cli", "gpt-image-skill"] = "gpt-image-skill"
    model: str = Field(min_length=1)
    params: ProviderParams = Field(default_factory=ProviderParams)


class BrandIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)


class PortfolioIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    version: str

    @field_validator("version")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("portfolio.version must be semantic version format")
        return value


class BrandLock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    portfolio: PortfolioIdentity | None = None
    brand: BrandIdentity
    version: str
    provider: ProviderConfig
    global_tokens: dict[str, Any] = Field(alias="global")
    alias_tokens: dict[str, Any] = Field(alias="alias")

    @field_validator("version")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("version must be semantic version format, for example 1.0.0")
        return value


class CampaignContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str | None = None
    subject: str = Field(min_length=1)


class Deliverable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    size: tuple[int, int]

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: tuple[int, int]) -> tuple[int, int]:
        width, height = value
        if width <= 0 or height <= 0:
            raise ValueError("size values must be positive")
        return value


class CampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    brief: str = Field(min_length=1)
    style: str = Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    content: CampaignContent
    deliverables: list[Deliverable] = Field(min_length=1)


class PortfolioMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    portfolio: PortfolioIdentity
    metadata_version: str

    @field_validator("metadata_version")
    @classmethod
    def validate_metadata_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("metadata_version must be semantic version format")
        return value


class BrandMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    portfolio: PortfolioIdentity
    brand: BrandIdentity
    metadata_version: str

    @field_validator("metadata_version")
    @classmethod
    def validate_metadata_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("metadata_version must be semantic version format")
        return value


class ElementLibrary(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    owner: dict[str, str]
    revision: int = Field(ge=1)
    elements: list[dict[str, Any]] = Field(default_factory=list)


class AcceptedCorpus(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    owner: dict[str, str]
    revision: int = Field(ge=1)
    accepted: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class ResolvedStyle:
    name: str
    prompt: str
    palette: list[str]
    typography: str | None
    negative: str
    references: list[str]
    raw: dict[str, Any]


@dataclass(frozen=True)
class SidecarSnapshot:
    kind: str
    path: Path
    raw: dict[str, Any]


@dataclass(frozen=True)
class LoadedSidecars:
    portfolio_meta: SidecarSnapshot | None = None
    portfolio_elements: SidecarSnapshot | None = None
    portfolio_accepted: SidecarSnapshot | None = None
    brand_meta: SidecarSnapshot | None = None
    brand_elements: SidecarSnapshot | None = None
    brand_accepted: SidecarSnapshot | None = None

    def snapshots(self) -> list[SidecarSnapshot]:
        return [
            snapshot
            for snapshot in (
                self.portfolio_meta,
                self.portfolio_elements,
                self.portfolio_accepted,
                self.brand_meta,
                self.brand_elements,
                self.brand_accepted,
            )
            if snapshot is not None
        ]


@dataclass(frozen=True)
class LoadedConfig:
    brand: BrandLock
    campaign: CampaignConfig
    resolved_style: ResolvedStyle
    brand_raw: dict[str, Any]
    campaign_raw: dict[str, Any]
    brand_path: Path
    campaign_path: Path
    sidecars: LoadedSidecars


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"{path}: file not found") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a YAML mapping at the document root")
    return data


def load_brand(path: Path) -> tuple[BrandLock, dict[str, Any]]:
    raw = load_yaml(path)
    try:
        brand = BrandLock.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    validate_token_tree(brand.global_tokens, ("global",))
    validate_token_tree(brand.alias_tokens, ("alias",))
    validate_alias_references(brand)
    return brand, raw


def load_campaign(path: Path) -> tuple[CampaignConfig, dict[str, Any]]:
    raw = load_yaml(path)
    try:
        campaign = CampaignConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return campaign, raw


def load_harness_config(
    campaign_path: Path,
    brand_path: Path = Path("workspace/products/codefox/codefox/brand.lock.yaml"),
) -> LoadedConfig:
    brand, brand_raw = load_brand(brand_path)
    campaign, campaign_raw = load_campaign(campaign_path)
    resolved_style = resolve_style_alias(brand, campaign.style)
    sidecars = load_sidecars(brand, brand_path)
    return LoadedConfig(
        brand=brand,
        campaign=campaign,
        resolved_style=resolved_style,
        brand_raw=brand_raw,
        campaign_raw=campaign_raw,
        brand_path=brand_path,
        campaign_path=campaign_path,
        sidecars=sidecars,
    )


def load_sidecars(brand: BrandLock, brand_path: Path) -> LoadedSidecars:
    product_dir = product_dir_for_brand_path(brand_path)
    portfolio_dir = portfolio_dir_for_brand(brand, brand_path)
    return LoadedSidecars(
        portfolio_meta=load_optional_sidecar(
            portfolio_dir / "portfolio.meta.yaml",
            "portfolio_meta",
            PortfolioMetadata,
        )
        if portfolio_dir
        else None,
        portfolio_elements=load_optional_sidecar(
            portfolio_dir / "elements.yaml",
            "portfolio_elements",
            ElementLibrary,
        )
        if portfolio_dir
        else None,
        portfolio_accepted=load_optional_sidecar(
            portfolio_dir / "accepted.yaml",
            "portfolio_accepted",
            AcceptedCorpus,
        )
        if portfolio_dir
        else None,
        brand_meta=load_optional_sidecar(
            product_dir / "brand.meta.yaml",
            "brand_meta",
            BrandMetadata,
        ),
        brand_elements=load_optional_sidecar(
            product_dir / "elements.yaml",
            "brand_elements",
            ElementLibrary,
        ),
        brand_accepted=load_optional_sidecar(
            product_dir / "accepted.yaml",
            "brand_accepted",
            AcceptedCorpus,
        ),
    )


def product_dir_for_brand_path(brand_path: Path) -> Path:
    parent = brand_path.parent
    if parent.name == "proposals":
        return parent.parent
    return parent


def portfolio_dir_for_brand(brand: BrandLock, brand_path: Path) -> Path | None:
    if brand.portfolio is None:
        return None
    workspace_root = workspace_root_for_path(brand_path)
    if workspace_root is None:
        return Path("workspace") / "portfolios" / brand.portfolio.id
    return workspace_root / "portfolios" / brand.portfolio.id


def workspace_root_for_path(path: Path) -> Path | None:
    resolved_parts = path.parts
    for index, part in enumerate(resolved_parts):
        if part == "workspace":
            return Path(*resolved_parts[: index + 1])
    return None


def load_optional_sidecar(
    path: Path,
    kind: str,
    model: type[BaseModel],
) -> SidecarSnapshot | None:
    if not path.exists():
        return None
    raw = load_yaml(path)
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return SidecarSnapshot(kind=kind, path=path, raw=raw)


def validate_token_tree(node: Any, path: tuple[str, ...]) -> None:
    if not isinstance(node, dict):
        raise ConfigError(f"{'.'.join(path)}: token group must be a mapping")

    if is_token(node):
        if "$value" not in node:
            raise ConfigError(f"{'.'.join(path)}: token is missing $value")
        if "$type" not in node:
            raise ConfigError(f"{'.'.join(path)}: token is missing $type")
        if not isinstance(node["$type"], str) or not node["$type"]:
            raise ConfigError(f"{'.'.join(path)}.$type: must be a non-empty string")
        return

    if "$value" in node or "$type" in node:
        raise ConfigError(f"{'.'.join(path)}: token must contain both $value and $type")

    for key, child in node.items():
        if key.startswith("$"):
            raise ConfigError(f"{'.'.join(path)}.{key}: group metadata is not supported here")
        if not TOKEN_NAME_RE.fullmatch(key):
            raise ConfigError(f"{'.'.join(path)}.{key}: token/group names must be kebab-case")
        validate_token_tree(child, (*path, key))


def validate_alias_references(brand: BrandLock) -> None:
    for path, token in iter_tokens(brand.alias_tokens, ("alias",)):
        resolve_references(token["$value"], brand, ".".join(path))


def iter_tokens(node: dict[str, Any], path: tuple[str, ...]):
    if is_token(node):
        yield path, node
        return

    for key, child in node.items():
        yield from iter_tokens(child, (*path, key))


def is_token(node: Any) -> bool:
    return isinstance(node, dict) and ("$value" in node or "$type" in node)


def resolve_style_alias(brand: BrandLock, style_name: str) -> ResolvedStyle:
    path = ("alias", "style", style_name)
    token = get_alias_token(brand, ("style", style_name))
    if token is None:
        available = ", ".join(available_style_names(brand)) or "<none>"
        raise UnknownStyleError(
            f"campaign.style '{style_name}' does not exist in brand alias.style. "
            f"Available styles: {available}"
        )

    if token.get("$type") != "composite":
        raise ConfigError(f"{'.'.join(path)}.$type: style aliases must be composite tokens")

    resolved = resolve_references(token["$value"], brand, ".".join(path))
    if not isinstance(resolved, dict):
        raise ConfigError(f"{'.'.join(path)}.$value: style alias must resolve to a mapping")

    prompt = resolved.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ConfigError(f"{'.'.join(path)}.$value.prompt: must be a non-empty string")

    palette = resolved.get("palette", [])
    if not isinstance(palette, list) or not all(isinstance(item, str) for item in palette):
        raise ConfigError(f"{'.'.join(path)}.$value.palette: must be a list of strings")

    references = resolved.get("references", [])
    if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
        raise ConfigError(f"{'.'.join(path)}.$value.references: must be a list of strings")

    negative = resolved.get("negative", "")
    if not isinstance(negative, str):
        raise ConfigError(f"{'.'.join(path)}.$value.negative: must be a string")

    typography = resolved.get("typography")
    if typography is not None and not isinstance(typography, str):
        raise ConfigError(f"{'.'.join(path)}.$value.typography: must be a string when present")

    return ResolvedStyle(
        name=style_name,
        prompt=prompt.strip(),
        palette=palette,
        typography=typography,
        negative=negative,
        references=references,
        raw=resolved,
    )


def available_style_names(brand: BrandLock) -> list[str]:
    style_group = brand.alias_tokens.get("style", {})
    if not isinstance(style_group, dict):
        return []
    return sorted(key for key, value in style_group.items() if is_token(value))


def get_alias_token(brand: BrandLock, parts: tuple[str, ...]) -> dict[str, Any] | None:
    node: Any = brand.alias_tokens
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if is_token(node) else None


def resolve_references(
    value: Any,
    brand: BrandLock,
    context: str,
    stack: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, str):
        matches = list(REFERENCE_RE.finditer(value))
        if not matches:
            return value

        def resolve_match(match: re.Match[str]) -> Any:
            reference = match.group(1).strip()
            return resolve_global_reference(reference, brand, context, stack)

        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return resolve_match(matches[0])

        resolved = value
        for match in reversed(matches):
            replacement = str(resolve_match(match))
            start, end = match.span()
            resolved = f"{resolved[:start]}{replacement}{resolved[end:]}"
        return resolved

    if isinstance(value, list):
        return [resolve_references(item, brand, context, stack) for item in value]

    if isinstance(value, dict):
        return {
            key: resolve_references(item, brand, f"{context}.{key}", stack)
            for key, item in value.items()
        }

    return value


def resolve_global_reference(
    reference: str,
    brand: BrandLock,
    context: str,
    stack: tuple[str, ...],
) -> Any:
    if not reference.startswith("global."):
        raise TokenReferenceError(
            f"{context}: reference {{{reference}}} is not allowed; alias tokens may only "
            "reference global tokens"
        )
    if reference in stack:
        chain = " -> ".join((*stack, reference))
        raise TokenReferenceError(f"{context}: circular token reference detected: {chain}")

    parts = reference.split(".")[1:]
    node: Any = brand.global_tokens
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise TokenReferenceError(f"{context}: reference {{{reference}}} does not exist")
        node = node[part]

    if not is_token(node):
        raise TokenReferenceError(f"{context}: reference {{{reference}}} does not point to a token")

    return resolve_references(node["$value"], brand, context, (*stack, reference))
