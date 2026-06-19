from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on minimal Python installs.
    yaml = None

TOKEN_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
REFERENCE_RE = re.compile(r"\{([^{}]+)\}")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
BRAND_ALLOWED = {
    "repo",
    "theme",
    "brand",
    "portfolio",
    "version",
    "producer",
    "provider",
    "global",
    "alias",
}
PRODUCER_ALLOWED = {"id", "gateway", "model", "params"}
CAMPAIGN_ALLOWED = {"name", "brief", "style", "content", "deliverables"}
CONTENT_ALLOWED = {"headline", "subject"}
DELIVERABLE_ALLOWED = {"id", "size"}


class ConfigError(ValueError):
    """Base configuration error with a user-readable message."""


class TokenReferenceError(ConfigError):
    """Raised when a design token reference cannot be resolved safely."""


class UnknownStyleError(ConfigError):
    """Raised when a campaign references a missing alias style."""


@dataclass(frozen=True)
class ProducerParams:
    seed_strategy: str = "fixed"
    seed: int | None = 12345
    guidance: float | None = None
    steps: int | None = None
    timeout_seconds: int = 120
    retry_attempts: int = 3
    output_format: str = "png"
    extra: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "seed_strategy": self.seed_strategy,
            "seed": self.seed,
            "guidance": self.guidance,
            "steps": self.steps,
            "timeout_seconds": self.timeout_seconds,
            "retry_attempts": self.retry_attempts,
            "output_format": self.output_format,
            **self.extra,
        }
        if exclude_none:
            return {key: value for key, value in data.items() if value is not None}
        return data


@dataclass(frozen=True)
class ProducerConfig:
    producer_id: str = "external-producer"
    model: str | None = None
    params: ProducerParams = field(default_factory=ProducerParams)


@dataclass(frozen=True)
class BrandIdentity:
    id: str
    name: str


@dataclass(frozen=True)
class PortfolioIdentity:
    id: str
    name: str
    version: str


@dataclass(frozen=True)
class BrandLock:
    portfolio: PortfolioIdentity | None
    brand: BrandIdentity
    version: str
    producer: ProducerConfig
    global_tokens: dict[str, Any]
    alias_tokens: dict[str, Any]


@dataclass(frozen=True)
class CampaignContent:
    headline: str | None
    subject: str


@dataclass(frozen=True)
class Deliverable:
    id: str
    size: tuple[int, int]


@dataclass(frozen=True)
class CampaignConfig:
    name: str
    brief: str
    style: str
    content: CampaignContent
    deliverables: list[Deliverable]


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
    if yaml is None:
        raise ConfigError("PyYAML is required to read theme and campaign files")
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(extract_yaml_source(raw, path)) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"{path}: file not found") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a YAML mapping at the document root")
    return data


def extract_yaml_source(raw: str, path: Path) -> str:
    if path.suffix.lower() != ".md":
        return raw
    if not raw.startswith("---\n"):
        raise ConfigError(f"{path}: Markdown theme files must start with YAML frontmatter")
    _start, _sep, rest = raw.partition("---\n")
    frontmatter, sep, _body = rest.partition("\n---")
    if not sep:
        raise ConfigError(f"{path}: Markdown theme frontmatter is not closed")
    return frontmatter


def load_brand(path: Path) -> tuple[BrandLock, dict[str, Any]]:
    raw = load_yaml(path)
    brand = parse_brand_lock(raw, str(path))
    validate_token_tree(brand.global_tokens, ("global",))
    validate_token_tree(brand.alias_tokens, ("alias",))
    validate_alias_references(brand)
    return brand, raw


def load_campaign(path: Path) -> tuple[CampaignConfig, dict[str, Any]]:
    raw = load_yaml(path)
    return parse_campaign(raw, str(path)), raw


def load_harness_config(
    campaign_path: Path,
    brand_path: Path,
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


def parse_brand_lock(raw: dict[str, Any], context: str) -> BrandLock:
    forbid_extra(raw, BRAND_ALLOWED, context)
    repo_raw = (
        optional_mapping(raw, "repo", context)
        or optional_mapping(raw, "theme", context)
        or optional_mapping(raw, "brand", context)
    )
    if repo_raw is None:
        raise ConfigError(f"{context}: repo is required")
    portfolio_raw = optional_mapping(raw, "portfolio", context)
    producer_raw = optional_mapping(raw, "producer", context)
    if producer_raw is None:
        producer_raw = optional_mapping(raw, "provider", context) or {}

    return BrandLock(
        portfolio=parse_portfolio(portfolio_raw, f"{context}.portfolio")
        if portfolio_raw is not None
        else None,
        brand=parse_brand_identity(repo_raw, f"{context}.repo"),
        version=require_semver(raw, "version", context),
        producer=parse_producer(producer_raw, f"{context}.producer"),
        global_tokens=required_mapping(raw, "global", context),
        alias_tokens=required_mapping(raw, "alias", context),
    )


def parse_producer(raw: dict[str, Any], context: str) -> ProducerConfig:
    forbid_extra(raw, PRODUCER_ALLOWED, context)
    producer_id = (
        optional_string(raw, "id", context)
        or optional_string(raw, "gateway", context)
        or "external-producer"
    )
    model = optional_string(raw, "model", context)
    return ProducerConfig(
        producer_id=producer_id,
        model=model,
        params=parse_producer_params(optional_mapping(raw, "params", context) or {}, context),
    )


def parse_producer_params(raw: dict[str, Any], context: str) -> ProducerParams:
    params = dict(raw)
    seed_strategy = str(params.pop("seed_strategy", "fixed"))
    if seed_strategy not in {"fixed", "per_asset", "random"}:
        raise ConfigError(f"{context}.params.seed_strategy: unsupported value {seed_strategy}")

    seed = params.pop("seed", 12345)
    if seed is not None and not isinstance(seed, int):
        raise ConfigError(f"{context}.params.seed: must be an integer or null")
    if seed_strategy == "fixed" and seed is None:
        raise ConfigError(f"{context}.params.seed is required when seed_strategy is fixed")

    guidance = optional_number(params.pop("guidance", None), f"{context}.params.guidance")
    steps = optional_int(params.pop("steps", None), f"{context}.params.steps")
    timeout_seconds = positive_int(
        params.pop("timeout_seconds", 120), f"{context}.params.timeout_seconds"
    )
    retry_attempts = positive_int(
        params.pop("retry_attempts", 3), f"{context}.params.retry_attempts"
    )
    output_format = str(params.pop("output_format", "png"))
    if not re.fullmatch(r"^[a-z0-9]+$", output_format):
        raise ConfigError(f"{context}.params.output_format: must be lowercase alphanumeric")

    return ProducerParams(
        seed_strategy=seed_strategy,
        seed=seed,
        guidance=guidance,
        steps=steps,
        timeout_seconds=timeout_seconds,
        retry_attempts=retry_attempts,
        output_format=output_format,
        extra=params,
    )


def parse_portfolio(raw: dict[str, Any], context: str) -> PortfolioIdentity:
    return PortfolioIdentity(
        id=require_slug(raw, "id", context),
        name=require_string(raw, "name", context),
        version=require_semver(raw, "version", context),
    )


def parse_brand_identity(raw: dict[str, Any], context: str) -> BrandIdentity:
    return BrandIdentity(
        id=require_slug(raw, "id", context),
        name=require_string(raw, "name", context),
    )


def parse_campaign(raw: dict[str, Any], context: str) -> CampaignConfig:
    forbid_extra(raw, CAMPAIGN_ALLOWED, context)
    content_raw = required_mapping(raw, "content", context)
    forbid_extra(content_raw, CONTENT_ALLOWED, f"{context}.content")
    deliverables_raw = raw.get("deliverables")
    if not isinstance(deliverables_raw, list) or not deliverables_raw:
        raise ConfigError(f"{context}.deliverables: must be a non-empty list")
    return CampaignConfig(
        name=require_slug(raw, "name", context),
        brief=require_string(raw, "brief", context),
        style=require_token_name(raw, "style", context),
        content=CampaignContent(
            headline=optional_string(content_raw, "headline", f"{context}.content"),
            subject=require_string(content_raw, "subject", f"{context}.content"),
        ),
        deliverables=[
            parse_deliverable(item, f"{context}.deliverables[{index}]")
            for index, item in enumerate(deliverables_raw)
        ],
    )


def parse_deliverable(raw: Any, context: str) -> Deliverable:
    if not isinstance(raw, dict):
        raise ConfigError(f"{context}: must be a mapping")
    forbid_extra(raw, DELIVERABLE_ALLOWED, context)
    size = raw.get("size")
    if (
        not isinstance(size, (list, tuple))
        or len(size) != 2
        or not all(isinstance(item, int) and item > 0 for item in size)
    ):
        raise ConfigError(f"{context}.size: must be [positive_width, positive_height]")
    return Deliverable(id=require_slug(raw, "id", context), size=(size[0], size[1]))


def load_sidecars(brand: BrandLock, brand_path: Path) -> LoadedSidecars:
    product_dir = product_dir_for_brand_path(brand_path)
    portfolio_dir = portfolio_dir_for_brand(brand, brand_path)
    return LoadedSidecars(
        portfolio_meta=load_optional_sidecar(
            portfolio_dir / "portfolio.meta.yaml",
            "portfolio_meta",
        )
        if portfolio_dir
        else None,
        portfolio_elements=load_optional_sidecar(
            portfolio_dir / "elements.yaml",
            "portfolio_elements",
        )
        if portfolio_dir
        else None,
        portfolio_accepted=load_optional_sidecar(
            portfolio_dir / "accepted.yaml", "portfolio_accepted"
        )
        if portfolio_dir
        else None,
        brand_meta=load_optional_sidecar(product_dir / "brand.meta.yaml", "brand_meta"),
        brand_elements=load_optional_sidecar(product_dir / "elements.yaml", "brand_elements"),
        brand_accepted=load_optional_sidecar(product_dir / "accepted.yaml", "brand_accepted"),
    )


def product_dir_for_brand_path(brand_path: Path) -> Path:
    parent = brand_path.parent
    if parent.name == "proposals":
        return parent.parent
    return parent


def portfolio_dir_for_brand(brand: BrandLock, brand_path: Path) -> Path | None:
    if brand.portfolio is None:
        return None
    product_dir = product_dir_for_brand_path(brand_path)
    return product_dir / "portfolios" / brand.portfolio.id


def load_optional_sidecar(path: Path, kind: str) -> SidecarSnapshot | None:
    if not path.exists():
        return None
    raw = load_yaml(path)
    validate_sidecar(raw, str(path))
    return SidecarSnapshot(kind=kind, path=path, raw=raw)


def validate_sidecar(raw: dict[str, Any], context: str) -> None:
    if "owner" in raw and not isinstance(raw["owner"], dict):
        raise ConfigError(f"{context}.owner: must be a mapping")
    if "revision" in raw and (not isinstance(raw["revision"], int) or raw["revision"] < 1):
        raise ConfigError(f"{context}.revision: must be a positive integer")


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
            f"campaign.style '{style_name}' does not exist in theme alias.style. "
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


def required_mapping(data: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{context}.{key}: must be a mapping")
    return value


def optional_mapping(data: dict[str, Any], key: str, context: str) -> dict[str, Any] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"{context}.{key}: must be a mapping")
    return value


def require_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{context}.{key}: must be a non-empty string")
    return value


def optional_string(data: dict[str, Any], key: str, context: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{context}.{key}: must be a non-empty string when present")
    return value


def require_slug(data: dict[str, Any], key: str, context: str) -> str:
    value = require_string(data, key, context)
    if not re.fullmatch(r"^[a-z0-9][a-z0-9-]*$", value):
        raise ConfigError(f"{context}.{key}: must be kebab-case")
    return value


def require_token_name(data: dict[str, Any], key: str, context: str) -> str:
    value = require_string(data, key, context)
    if not TOKEN_NAME_RE.fullmatch(value):
        raise ConfigError(f"{context}.{key}: must be kebab-case")
    return value


def require_semver(data: dict[str, Any], key: str, context: str) -> str:
    value = require_string(data, key, context)
    if not SEMVER_RE.fullmatch(value):
        raise ConfigError(f"{context}.{key}: must be semantic version format")
    return value


def positive_int(value: Any, context: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise ConfigError(f"{context}: must be a positive integer")
    return value


def optional_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ConfigError(f"{context}: must be an integer")
    return value


def optional_number(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ConfigError(f"{context}: must be a number")
    return float(value)


def forbid_extra(data: dict[str, Any], allowed: set[str], context: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ConfigError(f"{context}: unsupported keys: {', '.join(extra)}")
