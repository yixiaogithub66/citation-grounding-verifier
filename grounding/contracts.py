"""Shared request, response and error boundaries for every implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.validate_dataset import strict_json_loads, validate_prediction


MAX_PASSAGES = 64
MAX_PASSAGE_CHARS = 32_000
MAX_ANSWER_CHARS = 20_000
MAX_INPUT_CHARS = 200_000
MAX_CLAIMS = 64


class VerificationError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 502,
        telemetry: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.telemetry = telemetry if telemetry is not None else {"calls": []}


@dataclass(frozen=True)
class VerificationRequest:
    context_passages: list[str]
    generated_answer: str

    @classmethod
    def from_dict(cls, value: Any) -> VerificationRequest:
        if not isinstance(value, dict) or set(value) != {"context_passages", "generated_answer"}:
            raise VerificationError(
                "invalid_request", "Expected exactly context_passages and generated_answer.", 400,
            )
        contexts, answer = value["context_passages"], value["generated_answer"]
        if not isinstance(contexts, list) or any(not isinstance(text, str) for text in contexts):
            raise VerificationError("invalid_request", "context_passages must be an array of strings.", 400)
        if not isinstance(answer, str):
            raise VerificationError("invalid_request", "generated_answer must be a string.", 400)
        if (
            len(contexts) > MAX_PASSAGES
            or len(answer) > MAX_ANSWER_CHARS
            or any(len(text) > MAX_PASSAGE_CHARS for text in contexts)
            or sum(map(len, contexts)) + len(answer) > MAX_INPUT_CHARS
        ):
            raise VerificationError("input_too_large", "Request exceeds the documented input limits.", 413)
        try:
            for text in [answer, *contexts]:
                text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VerificationError("invalid_request", "Input must contain valid Unicode text.", 400) from exc
        return cls(list(contexts), answer)

    def to_dict(self) -> dict[str, Any]:
        return {"context_passages": list(self.context_passages), "generated_answer": self.generated_answer}


@dataclass
class VerificationResult:
    report: dict[str, Any]
    telemetry: dict[str, Any] = field(default_factory=lambda: {"calls": []})


def validate_report(report: Any, contexts: list[str]) -> None:
    errors = validate_prediction(report, contexts)
    if errors:
        details = "; ".join(f"{item['location']}: {item['message']}" for item in errors[:8])
        raise VerificationError("invalid_model_output", details)
    if len(report["claims"]) > MAX_CLAIMS:
        raise VerificationError("invalid_model_output", f"At most {MAX_CLAIMS} claims are permitted.")
    for claim in report["claims"]:
        if len(claim["citations"]) > 32:
            raise VerificationError("invalid_model_output", "At most 32 citations per claim are permitted.")
        for text in [claim["claim_text"], claim["reasoning"], *[c["quote"] for c in claim["citations"]]]:
            try:
                text.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise VerificationError("invalid_model_output", "Output contains invalid Unicode.") from exc


__all__ = [
    "VerificationError", "VerificationRequest", "VerificationResult",
    "validate_report", "strict_json_loads",
]
