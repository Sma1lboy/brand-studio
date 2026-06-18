from __future__ import annotations

import io
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from harness.providers.base import (
    AuthenticationError,
    ContentRejectedError,
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    TransientProviderError,
)
from harness.providers.placeholder import write_dry_run_asset

OUTPUT_FORMAT_MIME_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


class SkillCliImageProvider(ImageProvider):
    """Image provider that delegates generation to the installed gpt-image skill CLI."""

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if request.dry_run:
            return write_dry_run_asset(request, output_path)

        attempts = max(1, int(request.params.get("retry_attempts", 3)))
        for attempt in range(1, attempts + 1):
            try:
                return self._generate_once(request, output_path)
            except (RateLimitError, ProviderTimeoutError, TransientProviderError):
                if attempt == attempts:
                    raise
                time.sleep(min(2**attempt, 8))

        raise ProviderError("skill-cli provider retry loop exited unexpectedly")

    def _generate_once(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        output_format = normalize_output_format(request.params.get("output_format", "png"))
        skill_size = choose_skill_size(request.size, request.params.get("skill_size"))
        command = build_skill_cli_command(request, output_path, output_format, skill_size)
        timeout = float(request.params.get("timeout_seconds", 120))

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError(f"skill-cli timed out after {timeout:g}s") from exc
        except OSError as exc:
            raise ProviderError(f"skill-cli command failed to start: {exc}") from exc

        if completed.returncode != 0:
            raise classify_skill_cli_error(completed)

        if not output_path.exists():
            raise ProviderError(f"skill-cli completed but did not write {output_path}")

        image_bytes = output_path.read_bytes()
        write_sized_image(image_bytes, output_path, request.size, output_format)

        metadata = {
            "gateway": request.gateway,
            "model": request.model,
            "command": command_identity(command),
            "exit_code": completed.returncode,
            "skill_size": skill_size,
            "requested_size": list(request.size),
            "resized_to_requested_size": skill_size != f"{request.size[0]}x{request.size[1]}",
            "references_used": portable_reference_paths(request),
            "process_output": process_output_metadata(completed),
        }
        return GenerationResult(
            asset_id=request.asset_id,
            path=output_path,
            seed=request.seed,
            mime_type=OUTPUT_FORMAT_MIME_TYPES[output_format],
            provider_metadata=metadata,
        )


def build_skill_cli_command(
    request: GenerationRequest,
    output_path: Path,
    output_format: str,
    skill_size: str,
) -> list[str]:
    n = request.params.get("n")
    if n is not None and int(n) != 1:
        raise ProviderError("skill-cli provider supports exactly one image per deliverable")

    command = resolve_skill_command(request.params.get("command"))
    args = [
        *command,
        "-p",
        build_skill_cli_prompt(request),
        "-f",
        str(output_path),
        "--model",
        request.model,
        "--size",
        skill_size,
        "--format",
        output_format,
    ]

    for param_key, flag in (
        ("quality", "--quality"),
        ("background", "--background"),
        ("moderation", "--moderation"),
        ("input_fidelity", "--input-fidelity"),
        ("user", "--user"),
    ):
        value = request.params.get(param_key)
        if value is not None:
            args.extend([flag, str(value)])

    compression = request.params.get("compression")
    if compression is not None:
        args.extend(["--compression", str(compression)])

    if as_bool(request.params.get("use_references", True)):
        for reference in existing_reference_paths(request):
            args.extend(["-i", reference])

    mask = request.params.get("mask")
    if mask is not None:
        mask_path = Path(str(mask))
        if not mask_path.exists():
            raise ProviderError(f"skill-cli mask does not exist: {mask_path}")
        args.extend(["-m", str(mask_path)])

    extra_args = request.params.get("skill_cli_extra_args")
    if extra_args:
        if not isinstance(extra_args, list) or not all(
            isinstance(item, str) for item in extra_args
        ):
            raise ProviderError("skill_cli_extra_args must be a list of strings")
        args.extend(extra_args)

    return args


def resolve_skill_command(value: Any = None) -> list[str]:
    configured = value or os.getenv("HARNESS_SKILL_CLI_COMMAND")
    if configured:
        return parse_command(configured)

    executable = shutil.which("gpt-image")
    if executable:
        return [executable]

    codex_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    skill_script = codex_home / "skills" / "gpt-image" / "scripts" / "generate.py"
    if skill_script.is_file():
        return [sys.executable, str(skill_script)]

    raise ProviderError(
        "skill-cli provider could not find gpt-image. Install the gpt-image skill/CLI "
        "or set provider.params.command / HARNESS_SKILL_CLI_COMMAND."
    )


def parse_command(value: Any) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    if isinstance(value, str) and value.strip():
        return shlex.split(value)
    raise ProviderError("provider.params.command must be a command string or list of strings")


def build_skill_cli_prompt(request: GenerationRequest) -> str:
    parts = [request.prompt]
    if request.negative_prompt:
        parts.append(f"Avoid: {request.negative_prompt}")
    if request.seed is not None:
        parts.append(
            f"Reproducibility hint: preserve deterministic composition family {request.seed}."
        )
    return "\n".join(parts)


def choose_skill_size(target_size: tuple[int, int], override: Any = None) -> str:
    if override is not None:
        return str(override)

    width, height = target_size
    ratio = width / height
    if ratio > 2.2:
        return "wide"
    if ratio < 0.45:
        return "tall"
    if ratio > 1.2:
        return "landscape"
    if ratio < 0.83:
        return "portrait"
    return "square"


def normalize_output_format(value: Any) -> str:
    output_format = str(value or "png").lower()
    if output_format == "jpg":
        output_format = "jpeg"
    if output_format not in OUTPUT_FORMAT_MIME_TYPES:
        raise ProviderError("skill-cli output_format must be one of: png, jpeg, webp")
    return output_format


def write_sized_image(
    image_bytes: bytes,
    output_path: Path,
    target_size: tuple[int, int],
    output_format: str,
) -> None:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = image.convert("RGBA") if output_format == "png" else image.convert("RGB")
        resized = ImageOps.fit(
            image,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        save_format = "JPEG" if output_format == "jpeg" else output_format.upper()
        resized.save(output_path, format=save_format)


def existing_reference_paths(request: GenerationRequest) -> list[str]:
    paths: list[str] = []
    strict = as_bool(request.params.get("strict_references", True))
    for reference in request.references:
        path = Path(reference)
        if path.exists():
            paths.append(str(path))
        elif strict:
            raise ProviderError(f"skill-cli reference does not exist: {path}")
    return paths


def portable_reference_paths(request: GenerationRequest) -> list[str]:
    return [portable_path_label(path) for path in existing_reference_paths(request)]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def classify_skill_cli_error(completed: subprocess.CompletedProcess[str]) -> ProviderError:
    message = truncate_process_text(
        "\n".join(part for part in (completed.stderr, completed.stdout) if part)
    )
    lowered = message.lower()
    if "openai_api_key" in lowered or "api key" in lowered or completed.returncode == 2:
        return AuthenticationError(f"skill-cli authentication or argument failure: {message}")
    if "rate limit" in lowered or "429" in lowered:
        return RateLimitError(f"skill-cli rate limit exceeded: {message}")
    if any(word in lowered for word in ("policy", "safety", "moderation", "rejected")):
        return ContentRejectedError(f"skill-cli rejected content: {message}")
    if any(word in lowered for word in ("timeout", "temporarily", "5xx", "server error")):
        return TransientProviderError(f"skill-cli transient failure: {message}")
    return ProviderError(f"skill-cli failed with exit code {completed.returncode}: {message}")


def command_identity(command: list[str]) -> list[str]:
    if not command:
        return []
    executable = Path(command[0]).name
    if len(command) > 1 and executable.startswith("python"):
        return [executable, portable_path_label(command[1])]
    return [executable]


def portable_path_label(value: str) -> str:
    path = Path(value)
    parts = path.parts
    if "workspace" in parts:
        index = parts.index("workspace")
        return Path(*parts[index:]).as_posix()
    if "skills" in parts:
        index = parts.index("skills")
        return Path(*parts[index:]).as_posix()
    return path.name


def process_output_metadata(completed: subprocess.CompletedProcess[str]) -> dict[str, bool]:
    return {
        "stdout_present": bool(completed.stdout.strip()),
        "stderr_present": bool(completed.stderr.strip()),
    }


def truncate_process_text(value: str, limit: int = 1000) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[:limit]}...[truncated]"
