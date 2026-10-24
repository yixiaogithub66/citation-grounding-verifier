"""Independent v4 configuration; frozen v2/v3 settings remain byte-identical."""

from dataclasses import asdict, dataclass, field, replace
import json
import math
from pathlib import Path
from typing import Any

from grounding.config import Settings
from grounding.contracts import VerificationError, strict_json_loads

@dataclass(frozen=True)
class StageConfig:
    thinking: str = "disabled"
    max_output_tokens: int = 8192

@dataclass(frozen=True)
class V4Config:
    decompose: StageConfig = field(default_factory=lambda: StageConfig("disabled", 8192))
    verify: StageConfig = field(default_factory=lambda: StageConfig("disabled", 8192))
    review: StageConfig = field(default_factory=lambda: StageConfig("enabled", 16384))
    decompose_chunk_chars: int = 1200
    verify_batch_token_budget: int = 2400
    max_batch_claims: int = 3
    chars_per_token: float = 3.0
    max_workers: int = 4
    format_retries: int = 1
    transport_retries: int = 1
    targeted_retries: int = 1
    batch_retries: int = 1
    quote_fuzzy_threshold: float = 0.92
    quote_window_tokens: int = 80
    max_claims: int = 64

    def validate(self) -> "V4Config":
        for name in ("decompose", "verify", "review"):
            stage = getattr(self, name)
            if (not isinstance(stage, StageConfig) or stage.thinking not in ("enabled", "disabled")
                    or type(stage.max_output_tokens) is not int or not 256 <= stage.max_output_tokens <= 131072):
                raise VerificationError("configuration_error", f"Invalid v4 {name} stage settings.", 503)
        bounds = {"decompose_chunk_chars": (128, 20000), "verify_batch_token_budget": (128, 32768),
                  "max_batch_claims": (1, 64), "max_workers": (1, 16), "max_claims": (1, 64),
                  "quote_window_tokens": (8, 256)}
        for name in ("format_retries", "targeted_retries", "batch_retries"):
            bounds[name] = (0, 1)
        bounds["transport_retries"] = (0, 2)
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise VerificationError("configuration_error", f"v4 {name} must be within [{low}, {high}].", 503)
        for name, low, high in (("quote_fuzzy_threshold", 0.8, 1.0), ("chars_per_token", 1.0, 8.0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise VerificationError("configuration_error", f"Invalid v4 {name}.", 503)
        return self

    def public_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def stage_settings(self, settings: Settings, stage: str) -> Settings:
        config = getattr(self, stage if stage in ("decompose", "verify") else "review")
        return replace(settings, thinking=config.thinking, max_output_tokens=config.max_output_tokens,
                       upstream_retries=self.transport_retries, repair_attempts=self.format_retries,
                       max_claims=self.max_claims).validate()

    @classmethod
    def from_dict(cls, value: Any) -> "V4Config":
        if not isinstance(value, dict):
            raise VerificationError("configuration_error", "v4 config must be a JSON object.", 503)
        try:
            values = dict(value)
            for name in ("decompose", "verify", "review"):
                if name in values:
                    if not isinstance(values[name], dict):
                        raise TypeError("Stage config must be an object")
                    values[name] = StageConfig(**values[name])
            return cls(**values).validate()
        except (TypeError, ValueError) as exc:
            raise VerificationError("configuration_error", "Unknown or invalid v4 configuration field.", 503) from exc

def load_v4_config(path: Path | str | None = None) -> V4Config:
    if path is None:
        return V4Config().validate()
    try:
        return V4Config.from_dict(strict_json_loads(Path(path).read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, RecursionError) as exc:
        raise VerificationError("configuration_error", "Cannot read valid v4 JSON configuration.", 503) from exc
