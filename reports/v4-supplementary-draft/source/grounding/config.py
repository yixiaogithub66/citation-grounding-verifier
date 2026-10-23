"""Settings from local .env, the process environment and explicit CLI overrides."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from grounding.contracts import VerificationError


ROOT = Path(__file__).resolve().parents[1]


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise VerificationError("configuration_error", f"Invalid .env syntax at line {number}.", 503)
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name.isidentifier():
            raise VerificationError("configuration_error", f"Invalid .env variable at line {number}.", 503)
        if value[:1] in ('"', "'"):
            if len(value) < 2 or value[-1] != value[0]:
                raise VerificationError("configuration_error", f"Unclosed .env quote at line {number}.", 503)
            value = value[1:-1]
        values[name] = value
    return values


@dataclass(frozen=True)
class Settings:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    api_key: str = field(default="", repr=False)
    timeout: float = 180.0
    max_output_tokens: int = 16384
    json_mode: bool = True
    thinking: str | None = None
    temperature: float | None = None
    repair_attempts: int = 1
    upstream_retries: int = 1
    max_claims: int = 64

    def public_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values.pop("api_key")
        values["api_key_configured"] = bool(self.api_key)
        return values

    def validate(self) -> Settings:
        url = urlsplit(self.base_url)
        if (
            url.scheme not in ("http", "https") or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or self.base_url.rstrip("/").endswith("/chat/completions")
        ):
            raise VerificationError(
                "configuration_error", "LLM_BASE_URL must be an HTTP(S) API base URL without credentials or query.", 503,
            )
        if not self.model.strip():
            raise VerificationError("configuration_error", "LLM_MODEL must not be empty.", 503)
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 600:
            raise VerificationError("configuration_error", "LLM_TIMEOUT must be within (0, 600] seconds.", 503)
        if not 1 <= self.max_output_tokens <= 131072:
            raise VerificationError("configuration_error", "LLM_MAX_OUTPUT_TOKENS must be within [1, 131072].", 503)
        if not 0 <= self.repair_attempts <= 2 or not 0 <= self.upstream_retries <= 2:
            raise VerificationError("configuration_error", "Retry limits must be within [0, 2].", 503)
        if not 1 <= self.max_claims <= 64:
            raise VerificationError("configuration_error", "max_claims must be within [1, 64].", 503)
        if self.thinking not in (None, "enabled", "disabled"):
            raise VerificationError("configuration_error", "LLM_THINKING must be api-default, enabled or disabled.", 503)
        if self.temperature is not None and (not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2):
            raise VerificationError("configuration_error", "LLM_TEMPERATURE must be within [0, 2].", 503)
        return self


def load_settings(env_file: Path | None = None, **overrides: Any) -> Settings:
    values = read_env_file(Path(env_file) if env_file is not None else ROOT / ".env")
    names = [
        "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "DEEPSEEK_API_KEY",
        "LLM_TIMEOUT", "LLM_MAX_OUTPUT_TOKENS", "LLM_JSON_MODE",
        "LLM_THINKING", "LLM_TEMPERATURE", "LLM_REPAIR_ATTEMPTS", "LLM_UPSTREAM_RETRIES",
    ]
    values.update({name: os.environ[name] for name in names if name in os.environ})
    try:
        json_mode = values.get("LLM_JSON_MODE", "true").lower()
        if json_mode not in ("true", "false", "1", "0"):
            raise ValueError("Invalid boolean")
        params: dict[str, Any] = {
            "base_url": values.get("LLM_BASE_URL", Settings.base_url).rstrip("/"),
            "model": values.get("LLM_MODEL", Settings.model),
            "api_key": values.get("LLM_API_KEY") or values.get("DEEPSEEK_API_KEY", ""),
            "timeout": float(values.get("LLM_TIMEOUT", "180")),
            "max_output_tokens": int(values.get("LLM_MAX_OUTPUT_TOKENS", "16384")),
            "json_mode": json_mode in ("true", "1"),
            "thinking": values.get("LLM_THINKING") or None,
            "temperature": float(values["LLM_TEMPERATURE"]) if values.get("LLM_TEMPERATURE") else None,
            "repair_attempts": int(values.get("LLM_REPAIR_ATTEMPTS", "1")),
            "upstream_retries": int(values.get("LLM_UPSTREAM_RETRIES", "1")),
        }
        params.update({name: value for name, value in overrides.items() if value is not None})
        if params["thinking"] == "api-default":
            params["thinking"] = None
        return Settings(**params).validate()
    except (ValueError, TypeError) as exc:
        raise VerificationError("configuration_error", "Invalid value in model configuration.", 503) from exc
