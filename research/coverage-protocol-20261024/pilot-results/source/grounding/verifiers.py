"""Single-call and multi-stage grounding verifiers with bounded format repair."""

from __future__ import annotations

import json
import time
import unicodedata
from dataclasses import replace
from typing import Any, Callable

from grounding.client import ChatClient
from grounding.config import Settings
from grounding.contracts import VerificationError, VerificationRequest, VerificationResult, validate_report
from grounding.prompts import (
    DECOMPOSE_PROMPT, MINIMAL_PROMPT, REPAIR_PROMPT, VERIFY_PROMPT, prompt_metadata,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _invalid(message: str) -> None:
    raise VerificationError("invalid_model_output", message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _telemetry(backend: str) -> dict[str, Any]:
    return {
        "backend": backend, "prompts": prompt_metadata(backend),
        "calls": [], "repairs": [], "extraction": None,
    }


class MinimalVerifier:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        self.settings = settings
        # Minimal is intentionally one attempt, even when the optimized client retries.
        self.client = client if client is not None else ChatClient(replace(settings, upstream_retries=0))

    def verify(self, request: VerificationRequest) -> VerificationResult:
        telemetry = _telemetry("minimal")
        started = time.monotonic()
        try:
            if not request.generated_answer.strip():
                report = {"claims": []}
            else:
                report = self.client.complete(
                    [
                        {"role": "system", "content": MINIMAL_PROMPT},
                        {"role": "user", "content": _json(request.to_dict())},
                    ],
                    "minimal", telemetry,
                )
            validate_report(report, request.context_passages)
            if len(report["claims"]) > self.settings.max_claims:
                _invalid("Output exceeds configured max_claims.")
            return VerificationResult(report, telemetry)
        except VerificationError as exc:
            exc.telemetry = telemetry
            raise
        finally:
            telemetry["latency_seconds"] = time.monotonic() - started


class OptimizedVerifier:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        self.settings = settings
        self.client = client if client is not None else ChatClient(settings)

    def _stage(
        self, stage: str, prompt: str, payload: dict[str, Any],
        validator: Callable[[dict[str, Any]], Any], telemetry: dict[str, Any],
    ) -> Any:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": _json(payload)},
        ]
        for repair in range(self.settings.repair_attempts + 1):
            parsed = None
            try:
                parsed = self.client.complete(
                    messages, stage if repair == 0 else f"{stage}_repair_{repair}", telemetry,
                )
                return validator(parsed)
            except VerificationError as exc:
                if exc.code != "invalid_model_output" or repair >= self.settings.repair_attempts:
                    raise
                telemetry["repairs"].append({"stage": stage, "attempt": repair + 1, "reason": exc.message})
                if parsed is not None:
                    previous = _json(parsed)
                else:
                    calls = telemetry.get("calls", [])
                    previous = calls[-1].get("response_text") if calls else None
                if previous:
                    messages.append({"role": "assistant", "content": previous})
                messages.append({
                    "role": "user",
                    "content": REPAIR_PROMPT + "\nValidation errors:\n" + exc.message,
                })
        raise AssertionError("Unreachable repair state")

    def _extract(self, payload: dict[str, Any], answer: str) -> list[dict[str, str]]:
        if not isinstance(payload, dict) or set(payload) != {"claims", "non_factual_spans"}:
            _invalid("Extraction must contain exactly claims and non_factual_spans.")
        claims, exclusions = payload["claims"], payload["non_factual_spans"]
        if not isinstance(claims, list) or not isinstance(exclusions, list):
            _invalid("Extraction claims and non_factual_spans must be arrays.")
        if len(claims) > self.settings.max_claims:
            _invalid("Extraction exceeds configured max_claims; do not omit factual assertions.")
        if len(exclusions) > 256:
            _invalid("Too many non_factual_spans.")
        covered: set[int] = set()

        def cover(span: str) -> int:
            first = answer.find(span)
            if first < 0:
                _invalid("An extraction source span is not an exact substring of generated_answer.")
            start = first
            while start >= 0:
                covered.update(range(start, start + len(span)))
                start = answer.find(span, start + 1)
            return first

        extracted = []
        seen: set[tuple[str, str]] = set()
        previous_start = -1
        for item in claims:
            if (
                not isinstance(item, dict) or set(item) != {"claim_text", "source_span"}
                or not _text(item["claim_text"]) or not _text(item["source_span"])
            ):
                _invalid("Each extracted claim needs exactly nonempty claim_text and source_span.")
            pair = (item["claim_text"], item["source_span"])
            if pair in seen:
                _invalid("Extraction contains a duplicate claim.")
            seen.add(pair)
            start = cover(item["source_span"])
            if start < previous_start:
                _invalid("Extracted claims must follow their source order.")
            previous_start = start
            extracted.append({"id": f"c{len(extracted) + 1}", **item})
        for item in exclusions:
            if (
                not isinstance(item, dict) or set(item) != {"text", "reason"}
                or not _text(item["text"]) or not _text(item["reason"])
            ):
                _invalid("Each non_factual_spans item needs exactly nonempty text and reason.")
            cover(item["text"])
        # This detects uncovered text, not whether the model's exclusions are truthful.
        uncovered = [
            index for index, char in enumerate(answer)
            if unicodedata.category(char)[0] in "LNMS" and index not in covered
        ]
        if uncovered:
            start = uncovered[0]
            _invalid("Extraction left answer text unaccounted for near: " + repr(answer[start:start + 100]))
        return extracted

    def _verified(
        self, payload: dict[str, Any], claims: list[dict[str, str]], contexts: list[str],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != {"claims"} or not isinstance(payload["claims"], list):
            _invalid("Verification must contain exactly a claims array.")
        if len(payload["claims"]) != len(claims):
            _invalid("Verification must return exactly one result per extracted claim.")
        report = {"claims": []}
        expected_fields = {"id", "claim_text", "verdict", "reasoning", "citations"}
        for result, original in zip(payload["claims"], claims):
            if not isinstance(result, dict) or set(result) != expected_fields:
                _invalid("Verified claim has incorrect fields; preserve id, claim_text, verdict, reasoning, citations.")
            if result["id"] != original["id"] or result["claim_text"] != original["claim_text"]:
                _invalid("Verification must preserve each supplied claim id, exact claim_text, and order.")
            report["claims"].append({key: value for key, value in result.items() if key != "id"})
        validate_report(report, contexts)
        return report

    def verify(self, request: VerificationRequest) -> VerificationResult:
        telemetry = _telemetry("optimized")
        started = time.monotonic()
        try:
            if not request.generated_answer.strip():
                return VerificationResult({"claims": []}, telemetry)

            def validate_extraction(value: dict[str, Any]) -> list[dict[str, str]]:
                extracted = self._extract(value, request.generated_answer)
                telemetry["extraction"] = {
                    "claims": extracted,
                    "non_factual_spans": value["non_factual_spans"],
                    "coverage_check": "Every letter, number, mark and symbol is covered by a claim or model-classified non-factual span.",
                    "limitation": "Lexical coverage cannot prove atomicity, factual completeness or correct exclusion of non-factual text.",
                }
                return extracted

            claims = self._stage(
                "decompose", DECOMPOSE_PROMPT,
                {"generated_answer": request.generated_answer, "max_claims": self.settings.max_claims},
                validate_extraction, telemetry,
            )
            if not claims:
                report = {"claims": []}
            elif not any(passage.strip() for passage in request.context_passages):
                report = {"claims": [{
                    "claim_text": claim["claim_text"], "verdict": "UNSUPPORTED",
                    "reasoning": "No nonempty context passage was supplied to verify this factual claim.",
                    "citations": [],
                } for claim in claims]}
            else:
                report = self._stage(
                    "verify", VERIFY_PROMPT,
                    {
                        "context_passages": [
                            {"index": index, "text": text}
                            for index, text in enumerate(request.context_passages)
                        ],
                        "claims": claims,
                    },
                    lambda value: self._verified(value, claims, request.context_passages), telemetry,
                )
            validate_report(report, request.context_passages)
            return VerificationResult(report, telemetry)
        except VerificationError as exc:
            exc.telemetry = telemetry
            raise
        finally:
            telemetry["latency_seconds"] = time.monotonic() - started
