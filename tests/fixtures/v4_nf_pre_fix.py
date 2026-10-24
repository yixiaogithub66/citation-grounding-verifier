"""Bounded, independently recoverable verification stages for optimized-v4.0.

Each worker owns its telemetry until the coordinator merges it in answer order.
Code validates provenance and output structure; only a model assigns a verdict.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import math
import re
import time
import unicodedata
from typing import Any, Callable

from grounding.client import ChatClient
from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationRequest, VerificationResult, validate_report
from grounding.contracts_v4 import validate_v4_report
from grounding.evidence_v4 import repair_citations, numeric_conflict_signals
from grounding.prompts_v4 import (
    DECOMPOSE_PROMPT, VERIFY_PROMPT, C_REVIEW_PROMPT, U_REVIEW_PROMPT, REPAIR_PROMPT, prompt_metadata,
)


_CORE_FIELDS = {"id", "claim_text", "verdict", "reasoning", "citations"}
_PUBLIC_FIELDS = _CORE_FIELDS - {"id"}
_SENTENCE_END = re.compile(r"[。！？]|[.!?](?=\s|$)|\n+")


def _json(value: Any) -> str:
    # A rejected model row may contain JSON-escaped lone surrogates. Keep such
    # diagnostic data escaped instead of breaking the next request's UTF-8
    # encoding. Valid Unicode and the serialization of valid inputs are unchanged.
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="backslashreplace").decode("utf-8")


def _invalid(message: str) -> None:
    raise VerificationError("invalid_model_output", message)


def _text(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _meaningful(character: str) -> bool:
    return unicodedata.category(character)[0] in "LNMS" or character in "-*/"


def estimate_tokens(value: str, chars_per_token: float = 3.0) -> int:
    """A configured character estimate, never a tokenizer or truncation proof."""
    return max(1, math.ceil(len(value) / chars_per_token))


def sentence_spans(answer: str) -> list[tuple[int, int]]:
    """Structural spans only; no vocabulary, connective, or subject-specific rules."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END.finditer(answer):
        spans.append((start, match.end()))
        start = match.end()
    if start < len(answer):
        spans.append((start, len(answer)))
    return spans


def decomposition_chunks(answer: str, max_chars: int) -> list[tuple[int, int]]:
    """Prefer sentence boundaries; hard split oversized sentences without dropping text."""
    chunks: list[tuple[int, int]] = []
    boundaries = [end for _, end in sentence_spans(answer)]
    start = 0
    while start < len(answer):
        limit = min(len(answer), start + max_chars)
        candidates = [end for end in boundaries if start < end <= limit]
        end = candidates[-1] if candidates else limit
        chunks.append((start, end))
        start = end
    return chunks


def extract_claims(payload: Any, answer: str, *, max_claims: int) -> tuple[list[dict], list[dict]]:
    """Validate exact source spans, lexical coverage, and source occurrence order."""
    if not isinstance(payload, dict) or set(payload) != {"claims", "non_factual_spans"}:
        _invalid("Extraction must contain exactly claims and non_factual_spans.")
    rows, excluded = payload["claims"], payload["non_factual_spans"]
    if not isinstance(rows, list) or not isinstance(excluded, list):
        _invalid("Extraction claims and non_factual_spans must be arrays.")
    if len(rows) > max_claims or len(excluded) > 256:
        _invalid("Extraction exceeds configured claim or non-factual span limits.")
    covered: set[int] = set()
    occurrences: dict[tuple[str, str], int] = {}
    seen: set[tuple[str, int, int]] = set()
    claims: list[dict] = []
    prior_start = 0
    for row in rows:
        if (
            not isinstance(row, dict) or set(row) != {"claim_text", "source_span"}
            or not _text(row["claim_text"]) or not _text(row["source_span"])
        ):
            _invalid("Each extracted claim needs exactly nonempty claim_text and source_span.")
        start = answer.find(row["source_span"], prior_start)
        if start < 0:
            _invalid("Extraction source spans must be exact answer substrings in answer order.")
        pair = (row["claim_text"], row["source_span"])
        if pair in occurrences:
            following = answer.find(row["source_span"], max(prior_start, occurrences[pair] + 1))
            if following >= 0:
                start = following
        end = start + len(row["source_span"])
        prior_start = occurrences[pair] = start
        covered.update(range(start, end))
        occurrence = (row["claim_text"], start, end)
        if occurrence not in seen:
            claims.append({**row, "source_start": start, "source_end": end})
            seen.add(occurrence)
    exclusions: list[dict] = []
    for row in excluded:
        if (
            not isinstance(row, dict) or set(row) != {"text", "reason"}
            or not _text(row["text"]) or not _text(row["reason"])
        ):
            _invalid("Each non-factual span needs exactly nonempty text and reason.")
        start = answer.find(row["text"])
        if start < 0:
            _invalid("A non-factual span is not an exact answer substring.")
        while start >= 0:
            end = start + len(row["text"])
            covered.update(range(start, end))
            exclusions.append({**row, "source_start": start, "source_end": end})
            start = answer.find(row["text"], start + 1)
    uncovered = next((i for i, char in enumerate(answer) if _meaningful(char) and i not in covered), None)
    if uncovered is not None:
        _invalid("Extraction left answer text unaccounted for near: " + repr(answer[uncovered:uncovered + 100]))
    return claims, exclusions


def skeleton_claims(answer: str) -> tuple[list[dict], list[dict]]:
    """Retain every sentence as an explicitly non-atomic fallback candidate."""
    claims, exclusions = [], []
    for start, end in sentence_spans(answer):
        text = answer[start:end]
        if any(_meaningful(char) for char in text):
            claims.append({
                "claim_text": text, "source_span": text,
                "source_start": start, "source_end": end, "extraction_fallback": True,
            })
        elif text.strip():
            exclusions.append({
                "text": text, "reason": "Formatting punctuation only.",
                "source_start": start, "source_end": end,
            })
    return claims, exclusions


def _public(row: dict) -> dict:
    return {key: deepcopy(row[key]) for key in ("claim_text", "verdict", "reasoning", "citations")}


def _error(claim: dict, exc: VerificationError, *, stage: str) -> dict:
    return {
        "id": claim["id"], "claim_text": claim["claim_text"],
        "code": exc.code, "message": exc.message, "stage": stage,
    }


def _evidence_error(evidence: Any, contexts: list[str], public: list[dict] | None = None) -> str | None:
    if not isinstance(evidence, list) or not evidence or len(evidence) > 32:
        return "Evidence must be a nonempty array of at most 32 quotes."
    for item in evidence:
        if not isinstance(item, dict) or not {"index", "quote"} <= set(item) or set(item) - {"index", "quote", "start_char", "end_char"}:
            return "Evidence items need index and quote, with optional exact offsets only."
        index, quote = item["index"], item["quote"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(contexts):
            return "Evidence index must be an in-bounds integer."
        if not _text(quote) or quote not in contexts[index]:
            return "Evidence must be an exact nonempty passage substring."
        if public is not None and not any(cite["index"] == index and quote in cite["quote"] for cite in public):
            return "Internal evidence must be covered by public citations from the same passage."
    return None


def conflict_error(row: dict, contexts: list[str]) -> str | None:
    conflict = row.get("conflict")
    if not isinstance(conflict, dict) or set(conflict) != {"claim_span", "evidence", "kind", "explanation"}:
        return "CONTRADICTED needs a complete structured conflict."
    if not _text(conflict["claim_span"]) or conflict["claim_span"] not in row["claim_text"]:
        return "Conflict claim_span must be an exact nonempty substring of claim_text."
    if conflict["kind"] not in ("direct", "calculation") or not _text(conflict["explanation"]):
        return "Conflict needs a direct/calculation kind and a nonempty explanation."
    return _evidence_error(conflict["evidence"], contexts, row["citations"])


class _NeedsRequery(VerificationError):
    def __init__(self, details: dict) -> None:
        super().__init__("citation_requery_required", "Citation content needs a new semantic judgment.")
        self.details = details


_EVENT_LISTS = (
    "calls", "repairs", "citation_repairs", "citation_checks", "citation_candidates", "targeted_reasks",
    "batch_retries", "batches", "contradiction_checks", "contradiction_reviews",
    "unsupported_reviews", "numeric_signals", "verdict_chains", "fallback_exclusions",
    "protocol_events", "errors", "error_statuses",
)


def _local_telemetry() -> dict:
    return {name: [] for name in _EVENT_LISTS}


def _merge_telemetry(destination: dict, source: dict) -> None:
    for name in _EVENT_LISTS:
        destination[name].extend(source.get(name, []))


class OptimizedV4Verifier:
    def __init__(self, settings: Settings, client: Any = None, config: V4Config | None = None) -> None:
        self.settings = settings
        self.config = (config if config is not None else V4Config()).validate()
        self.clients = {
            phase: client if client is not None else ChatClient(self.config.stage_settings(settings, phase))
            for phase in ("decompose", "verify", "review")
        }

    def _call(self, messages: list[dict], stage: str, phase: str, telemetry: dict) -> Any:
        first_call = len(telemetry["calls"])
        try:
            return self.clients[phase].complete(messages, stage, telemetry)
        finally:
            generation = getattr(self.config, phase)
            for call in telemetry["calls"][first_call:]:
                call["phase"] = phase
                call["thinking"] = generation.thinking
                call["max_output_tokens"] = generation.max_output_tokens

    def _format_stage(
        self, prompt: str, payload: dict, stage: str, phase: str,
        validate: Callable[[Any], Any], telemetry: dict,
    ) -> Any:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": _json(payload)},
        ]
        for attempt in range(self.config.format_retries + 1):
            parsed = None
            try:
                parsed = self._call(messages, stage if attempt == 0 else f"{stage}_repair_{attempt}", phase, telemetry)
                return validate(parsed)
            except _NeedsRequery:
                # A content-changing quotation is a semantic requery, never a
                # formatter pretending to preserve the original judgment.
                raise
            except VerificationError as exc:
                if exc.code != "invalid_model_output" or attempt == self.config.format_retries:
                    raise
                telemetry["repairs"].append({
                    "stage": stage, "attempt": attempt + 1, "reason": exc.message,
                    "retry_layer": "format",
                })
                previous = _json(parsed) if parsed is not None else (
                    telemetry["calls"][-1].get("response_text") if telemetry["calls"] else None
                )
                if previous:
                    # Escaping invalid Unicode in diagnostic JSON prevents an
                    # invalid model string from breaking the repair transport.
                    previous = previous.encode("utf-8", errors="backslashreplace").decode("utf-8")
                    messages.append({"role": "assistant", "content": previous})
                messages.append({"role": "user", "content": REPAIR_PROMPT + "\nValidation errors:\n" + exc.message})
        raise AssertionError("Unreachable format retry state")

    @staticmethod
    def _envelope(value: Any) -> list[Any]:
        if not isinstance(value, dict) or set(value) != {"claims"} or not isinstance(value["claims"], list):
            _invalid("Verification must contain exactly a claims array.")
        return value["claims"]

    def _repair_quotes(self, citations: Any, contexts: list[str], claim: dict, stage: str, telemetry: dict) -> list[dict]:
        outcome = repair_citations(
            citations, contexts, fuzzy_threshold=self.config.quote_fuzzy_threshold,
            window_tokens=self.config.quote_window_tokens,
        )
        events = [{"claim_id": claim["id"], "stage": stage, **event} for event in outcome["events"]]
        telemetry["citation_checks"].extend(events)
        telemetry["citation_repairs"].extend(event for event in events if event.get("kind") == "repair")
        telemetry["citation_candidates"].extend({"claim_id": claim["id"], "stage": stage, **candidate} for candidate in outcome["candidates"])
        if outcome["needs_requery"]:
            raise _NeedsRequery({"errors": outcome["errors"], "candidates": outcome["candidates"]})
        return outcome["citations"]

    def _validate_row(
        self, value: Any, claim: dict, contexts: list[str], stage: str,
        telemetry: dict, *, review: bool = False,
    ) -> dict:
        if not isinstance(value, dict):
            _invalid("Each verification result must be an object.")
        if value.get("id") != claim["id"] or value.get("claim_text") != claim["claim_text"]:
            _invalid("Verification must preserve supplied id and exact claim_text.")
        if value.get("non_factual") is True:
            if (
                not claim.get("extraction_fallback")
                or set(value) != {"id", "claim_text", "non_factual", "reason"}
                or not _text(value["reason"])
            ):
                _invalid("Only provisional fallback skeletons may be excluded as non-factual, with a reason.")
            return deepcopy(value)
        required = _CORE_FIELDS | {"derivation", "conflict"}
        if set(value) != required or not _text(value.get("derivation")):
            _invalid("Each verified claim needs id, claim_text, verdict, reasoning, citations, derivation, and conflict.")
        row = deepcopy(value)
        if row["verdict"] not in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"):
            _invalid("A verdict must be SUPPORTED, CONTRADICTED, or UNSUPPORTED.")
        if row["verdict"] != "CONTRADICTED" and row["conflict"] is not None:
            _invalid("Non-contradicted claims must use conflict:null.")
        if row["verdict"] == "UNSUPPORTED":
            if row["citations"] != []:
                _invalid("UNSUPPORTED must have citations:[]; never silently remove an invalid citation.")
        else:
            row["citations"] = self._repair_quotes(row["citations"], contexts, claim, stage, telemetry)
        validate_report({"claims": [_public(row)]}, contexts)
        for text in (row["derivation"],):
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                _invalid("Derivation contains invalid Unicode.")
        # Internal conflict anchors use the same conservative quotation repairs.
        # An invalid/missing structure is left to the C gate or review formatter.
        conflict = row.get("conflict")
        if row["verdict"] == "CONTRADICTED" and isinstance(conflict, dict) and isinstance(conflict.get("evidence"), list):
            conflict["evidence"] = self._repair_quotes(conflict["evidence"], contexts, claim, stage + ".conflict", telemetry)
        if review and row["verdict"] == "CONTRADICTED":
            error = conflict_error(row, contexts)
            if error:
                _invalid("Review returned CONTRADICTED without valid conflict evidence: " + error)
        return row

    def _single_decision(
        self, claim: dict, contexts: list[str], state: dict, telemetry: dict, *,
        prompt: str, stage: str, review: bool, diagnostics: dict | None = None,
        allow_targeted: bool = True,
    ) -> dict:
        payload = {
            "context_passages": [{"index": i, "text": text} for i, text in enumerate(contexts)],
            "claims": [claim],
        }
        if diagnostics:
            payload["diagnostics"] = diagnostics

        def validate(value: Any) -> dict:
            rows = self._envelope(value)
            matches = [row for row in rows if isinstance(row, dict) and row.get("id") == claim["id"]]
            extras = [i for i, row in enumerate(rows) if not isinstance(row, dict) or row.get("id") != claim["id"]]
            if extras:
                telemetry["protocol_events"].append({
                    "claim_id": claim["id"], "stage": stage,
                    "kind": "unrequested_or_unidentifiable_rows", "positions": extras,
                })
            if len(matches) != 1:
                _invalid("The expected claim is missing or duplicated.")
            raw_row = matches[0]
            try:
                return self._validate_row(raw_row, claim, contexts, stage, telemetry, review=review)
            except VerificationError as exc:
                self._record_unvalidated(raw_row, claim, state, stage)
                if isinstance(exc, _NeedsRequery):
                    exc.details["previous_result"] = deepcopy(raw_row)
                raise

        try:
            return self._format_stage(prompt, payload, stage, "review" if review else "verify", validate, telemetry)
        except _NeedsRequery as exc:
            if not allow_targeted or state["targeted_used"] >= self.config.targeted_retries:
                raise
            state["targeted_used"] += 1
            event = {
                "claim_id": claim["id"], "stage": stage, "attempt": state["targeted_used"],
                "reason": exc.message, **exc.details, "retry_layer": "targeted", "kind": "targeted",
            }
            telemetry["targeted_reasks"].append(event)
            try:
                result = self._single_decision(
                    claim, contexts, state, telemetry, prompt=prompt, stage=stage + "_targeted",
                    review=review, diagnostics={"previous_diagnostics": diagnostics, **exc.details},
                    allow_targeted=False,
                )
                event["final_result"] = deepcopy(result)
                event["after_verdict"] = result.get("verdict")
                state["chain"].append({
                    "stage": stage + "_targeted", "verdict": result.get("verdict", "NON_FACTUAL"),
                    "validated": True,
                })
                return result
            except VerificationError as error:
                event["error"] = {"code": error.code, "message": error.message}
                raise

    @staticmethod
    def _record_unvalidated(row: Any, claim: dict, state: dict, stage: str) -> None:
        if (
            isinstance(row, dict) and row.get("id") == claim["id"]
            and row.get("claim_text") == claim["claim_text"]
            and isinstance(row.get("verdict"), str)
            and row["verdict"] in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED")
        ):
            state["chain"].append({"stage": stage + "_unvalidated", "verdict": row["verdict"], "validated": False})

    def _review(self, row: dict, claim: dict, contexts: list[str], state: dict, telemetry: dict, kind: str, trigger: Any) -> dict:
        key = "c_review_used" if kind == "C" else "u_review_used"
        if state[key]:
            raise AssertionError("A claim cannot enter the same logical review twice")
        state[key] = True
        event = {
            "claim_id": claim["id"], "before_verdict": row["verdict"], "after_verdict": None,
            "trigger": trigger, "reviewed": True,
        }
        telemetry["contradiction_reviews" if kind == "C" else "unsupported_reviews"].append(event)
        stage = "contradiction_review" if kind == "C" else "unsupported_review"
        try:
            reviewed = self._single_decision(
                claim, contexts, state, telemetry,
                prompt=C_REVIEW_PROMPT if kind == "C" else U_REVIEW_PROMPT, stage=stage,
                review=True, diagnostics={"previous_result": row, "trigger": trigger},
                # A final U review may spend the one remaining per-claim quote
                # requery. It remains this logical review, never another C/U gate.
                allow_targeted=True,
            )
        except VerificationError as exc:
            event["error"] = {"code": exc.code, "message": exc.message}
            raise
        event["after_verdict"] = reviewed.get("verdict")
        event["evidence"] = reviewed.get("citations", [])
        event["derivation"] = reviewed.get("derivation")
        state["chain"].append({"stage": stage, "verdict": reviewed.get("verdict", "NON_FACTUAL"), "validated": True})
        return reviewed

    def _finish_claim(self, row: dict, claim: dict, contexts: list[str], state: dict, telemetry: dict) -> dict:
        state["chain"].append({"stage": state.get("decision_stage", "verify"), "verdict": row.get("verdict", "NON_FACTUAL"), "validated": True})
        if row.get("non_factual") is True:
            return row
        if row["verdict"] in ("SUPPORTED", "CONTRADICTED"):
            error = conflict_error(row, contexts) if row["verdict"] == "CONTRADICTED" else None
            signals = numeric_conflict_signals(claim["claim_text"], row["citations"], contexts)
            telemetry["numeric_signals"].extend({"claim_id": claim["id"], **signal} for signal in signals)
            if row["verdict"] == "CONTRADICTED" or signals:
                telemetry["contradiction_checks"].append({
                    "claim_id": claim["id"], "passed": error is None, "reason": error,
                    "conflict": row["conflict"], "numeric_signals": signals,
                })
            if error or signals:
                row = self._review(row, claim, contexts, state, telemetry, "C", {"conflict_error": error, "numeric_signals": signals})
        if not row.get("non_factual") and row["verdict"] == "UNSUPPORTED" and any(text.strip() for text in contexts):
            row = self._review(row, claim, contexts, state, telemetry, "U", "Final unsupported entailment/contradiction search")
        return row

    def _batch(self, batch_number: int, claims: list[dict], contexts: list[str], estimated: int) -> tuple[list[dict], list[dict], dict]:
        telemetry = _local_telemetry()
        batch_id = f"b{batch_number + 1}"
        started = time.monotonic()
        batch_event = {
            "batch_id": batch_id, "claim_ids": [claim["id"] for claim in claims],
            "estimated_variable_tokens": estimated, "token_budget": self.config.verify_batch_token_budget,
            "oversize_single_claim": len(claims) == 1 and estimated > self.config.verify_batch_token_budget,
        }
        telemetry["batches"].append(batch_event)
        payload = {
            "context_passages": [{"index": i, "text": text} for i, text in enumerate(contexts)],
            "claims": claims,
        }
        messages = [{"role": "system", "content": VERIFY_PROMPT}, {"role": "user", "content": _json(payload)}]
        outputs: list[dict] = []
        errors: list[dict] = []
        try:
            for attempt in range(self.config.batch_retries + 1):
                try:
                    value = self._call(messages, "verify" if attempt == 0 else f"verify_batch_retry_{attempt}", "verify", telemetry)
                    rows = self._envelope(value)
                    break
                except VerificationError as exc:
                    if exc.code != "invalid_model_output" or attempt == self.config.batch_retries:
                        raise
                    telemetry["batch_retries"].append({
                        "batch_id": batch_id, "attempt": attempt + 1, "reason": exc.message,
                        "retry_layer": "batch",
                    })
                    messages.append({"role": "user", "content": REPAIR_PROMPT + "\nBatch validation error: " + exc.message})
            else:
                raise AssertionError("Unreachable batch retry state")

            # A malformed row does not invalidate any other requested row. Unknown
            # or duplicate IDs are never silently substituted for an expected ID.
            by_id: dict[str, list[tuple[int, Any]]] = {}
            for position, row in enumerate(rows):
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    by_id.setdefault(row["id"], []).append((position, row))
            expected_ids = {claim["id"] for claim in claims}
            extras = [
                i for i, row in enumerate(rows)
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] not in expected_ids
            ]
            if extras:
                telemetry["protocol_events"].append({
                    "batch_id": batch_id, "kind": "unrequested_or_unidentifiable_rows", "positions": extras,
                })
            for position, claim in enumerate(claims):
                state = {"targeted_used": 0, "c_review_used": False, "u_review_used": False, "chain": []}
                raw_row = None
                try:
                    try:
                        matches = by_id.get(claim["id"], [])
                        if len(matches) != 1:
                            _invalid("The expected claim is missing or duplicated.")
                        if matches[0][0] != position:
                            telemetry["protocol_events"].append({
                                "batch_id": batch_id, "claim_id": claim["id"], "kind": "restored_claim_order",
                                "model_position": matches[0][0], "expected_position": position,
                            })
                        raw_row = matches[0][1]
                        row = self._validate_row(raw_row, claim, contexts, "verify", telemetry)
                    except VerificationError as exc:
                        self._record_unvalidated(raw_row, claim, state, "verify")
                        if state["targeted_used"] >= self.config.targeted_retries:
                            raise
                        state["targeted_used"] += 1
                        diagnostics = {"error": {"code": exc.code, "message": exc.message}}
                        if isinstance(exc, _NeedsRequery):
                            diagnostics.update(exc.details)
                        diagnostics["previous_result"] = deepcopy(raw_row)
                        event = {
                            "claim_id": claim["id"], "stage": "verify", "attempt": state["targeted_used"],
                            "reason": exc.message, "retry_layer": "targeted", "kind": "targeted", **diagnostics,
                        }
                        telemetry["targeted_reasks"].append(event)
                        try:
                            row = self._single_decision(
                                claim, contexts, state, telemetry, prompt=VERIFY_PROMPT,
                                stage="verify_claim_requery", review=False, diagnostics=diagnostics, allow_targeted=False,
                            )
                            event["final_result"] = deepcopy(row)
                            event["after_verdict"] = row.get("verdict")
                        except VerificationError as error:
                            event["error"] = {"code": error.code, "message": error.message}
                            raise
                        state["decision_stage"] = "targeted_requery"
                    row = self._finish_claim(row, claim, contexts, state, telemetry)
                    state["final_verdict"] = row.get("verdict", "NON_FACTUAL")
                    if row.get("non_factual") is True:
                        telemetry["fallback_exclusions"].append({
                            "claim_id": claim["id"], "text": claim["source_span"],
                            "source_start": claim["source_start"], "source_end": claim["source_end"],
                            "reason": row["reason"],
                        })
                    else:
                        outputs.append(row)
                except VerificationError as exc:
                    error = _error(claim, exc, stage="review" if state["c_review_used"] or state["u_review_used"] else "verify")
                    errors.append(error)
                    telemetry["error_statuses"].append({"claim_id": claim["id"], "code": exc.code, "status": exc.status})
                    state["error"] = error
                finally:
                    telemetry["verdict_chains"].append({
                        "claim_id": claim["id"], "steps": state["chain"],
                        "status": "error" if state.get("error") else "complete",
                        "final_verdict": state.get("final_verdict"), "error": state.get("error"),
                    })
            return outputs, errors, telemetry
        except VerificationError as exc:
            errors = [_error(claim, exc, stage="verify_batch") for claim in claims]
            telemetry["error_statuses"].extend({
                "claim_id": claim["id"], "code": exc.code, "status": exc.status,
            } for claim in claims)
            telemetry["verdict_chains"].extend({
                "claim_id": claim["id"], "steps": [], "status": "error", "final_verdict": None,
                "error": error,
            } for claim, error in zip(claims, errors))
            return [], errors, telemetry
        finally:
            telemetry["errors"].extend(errors)
            batch_event["latency_seconds"] = time.monotonic() - started
            batch_event["completed_claim_ids"] = [row["id"] for row in outputs]
            batch_event["error_claim_ids"] = [error["id"] for error in errors]
            for call in telemetry["calls"]:
                call["batch_id"] = batch_id

    @staticmethod
    def _recover_hard_split_fallbacks(answer: str, claims: list[dict], exclusions: list[dict], chunks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        """Replace failed boundary fragments with original full-sentence skeletons.

        No extracted claims are concatenated or semantically merged. If a model
        span crosses an affected sentence boundary, the replacement area expands
        to whole original sentences until no retained span is cut in half.
        """
        failed = [chunk for chunk in chunks if chunk["hard_split"] and chunk["fallback"]]
        if not failed:
            return claims, exclusions, []
        sentences = sentence_spans(answer)

        def intersects(left: tuple[int, int], right: tuple[int, int]) -> bool:
            return max(left[0], right[0]) < min(left[1], right[1])

        selected = {
            i for i, sentence in enumerate(sentences)
            if any(intersects(sentence, (chunk["source_start"], chunk["source_end"])) for chunk in failed)
        }
        changed = True
        while changed:
            before = set(selected)
            for record in [*claims, *exclusions]:
                interval = (record["source_start"], record["source_end"])
                if any(intersects(interval, sentences[i]) for i in selected):
                    selected.update(i for i, sentence in enumerate(sentences) if intersects(interval, sentence))
            changed = selected != before

        def affected(record: dict) -> bool:
            return any(intersects((record["source_start"], record["source_end"]), sentences[i]) for i in selected)

        retained = [claim for claim in claims if not affected(claim)]
        kept_exclusions = [exclusion for exclusion in exclusions if not affected(exclusion)]
        audits = []
        for i in sorted(selected):
            start, end = sentences[i]
            text = answer[start:end]
            origins = [chunk["chunk_id"] for chunk in chunks if intersects((start, end), (chunk["source_start"], chunk["source_end"]))]
            replacement = {
                "claim_text": text, "source_span": text, "source_start": start, "source_end": end,
                "extraction_fallback": True, "hard_split_recovery": True,
                "chunk_id": origins[0], "origin_chunk_ids": origins,
            }
            if any(_meaningful(char) for char in text):
                retained.append(replacement)
            elif text.strip():
                kept_exclusions.append({"text": text, "reason": "Formatting punctuation only.", "source_start": start, "source_end": end})
            audits.append({
                "source_start": start, "source_end": end, "source_span": text,
                "origin_chunk_ids": origins,
                "superseded_claims": [deepcopy(claim) for claim in claims if intersects((start, end), (claim["source_start"], claim["source_end"]))],
                "superseded_non_factual_spans": [deepcopy(exclusion) for exclusion in exclusions if intersects((start, end), (exclusion["source_start"], exclusion["source_end"]))],
                "reason": "An exhausted hard-split chunk requires original complete sentence context; partial skeletons are not judged.",
            })
        retained.sort(key=lambda claim: (claim["source_start"], claim["source_end"]))
        kept_exclusions.sort(key=lambda exclusion: (exclusion["source_start"], exclusion["source_end"]))
        return retained, kept_exclusions, audits

    def _decompose(self, answer: str, telemetry: dict) -> list[dict]:
        all_claims, all_exclusions, chunks = [], [], []
        sentence_ends = {end for _, end in sentence_spans(answer)}
        for number, (start, end) in enumerate(decomposition_chunks(answer, self.config.decompose_chunk_chars)):
            text = answer[start:end]
            local = _local_telemetry()
            chunk = {
                "chunk_id": f"d{number + 1}", "source_start": start, "source_end": end,
                "hard_split": (start != 0 and start not in sentence_ends) or end not in sentence_ends,
                "fallback": False,
            }
            chunks.append(chunk)
            boundary_size = self.config.decompose_chunk_chars // 4
            payload = {
                "generated_answer": text, "max_claims": self.config.max_claims,
                "boundary_context": {
                    "before": answer[max(0, start - boundary_size):start],
                    "after": answer[end:min(len(answer), end + boundary_size)],
                },
            }
            try:
                claims, exclusions = self._format_stage(
                    DECOMPOSE_PROMPT, payload, "decompose", "decompose",
                    lambda value: extract_claims(value, text, max_claims=self.config.max_claims), local,
                )
            except VerificationError as exc:
                claims, exclusions = skeleton_claims(text)
                chunk["fallback"] = True
                chunk["error"] = {"code": exc.code, "message": exc.message}
                chunk["fallback_limitation"] = "Sentence skeletons preserve text but do not certify factuality or atomicity."
            finally:
                for call in local["calls"]:
                    call["chunk_id"] = chunk["chunk_id"]
                for event in local["repairs"]:
                    event["chunk_id"] = chunk["chunk_id"]
                _merge_telemetry(telemetry, local)
            for claim in claims:
                claim.update({
                    "source_start": start + claim["source_start"], "source_end": start + claim["source_end"],
                    "id": f"c{len(all_claims) + 1}", "chunk_id": chunk["chunk_id"],
                })
                if claim.get("extraction_fallback"):
                    claim["boundary_context"] = payload["boundary_context"]
                all_claims.append(claim)
            for exclusion in exclusions:
                exclusion.update({"source_start": start + exclusion["source_start"], "source_end": start + exclusion["source_end"]})
                all_exclusions.append(exclusion)
            chunk["claim_ids"] = [claim["id"] for claim in claims]
        all_claims, all_exclusions, recoveries = self._recover_hard_split_fallbacks(answer, all_claims, all_exclusions, chunks)
        for i, claim in enumerate(all_claims):
            claim["id"] = f"c{i + 1}"
        for chunk in chunks:
            chunk["claim_ids"] = [
                claim["id"] for claim in all_claims
                if max(claim["source_start"], chunk["source_start"]) < min(claim["source_end"], chunk["source_end"])
            ]
        telemetry["extraction"] = {
            "claims": all_claims, "non_factual_spans": all_exclusions, "chunks": chunks,
            "hard_split_recoveries": recoveries,
            "coverage_check": "Every substantive answer character is accounted for by an exact source span.",
            "limitation": "Lexical coverage and fallback skeletons do not prove atomicity or factual completeness.",
        }
        if len(all_claims) > self.config.max_claims:
            raise VerificationError("claim_limit_exceeded", "Decomposition exceeds the configured claim capacity; no claims were silently truncated.", 413)
        covered: set[int] = set()
        for span in [*all_claims, *all_exclusions]:
            covered.update(range(span["source_start"], span["source_end"]))
        if any(_meaningful(char) and i not in covered for i, char in enumerate(answer)):
            raise VerificationError("invalid_model_output", "Global answer coverage failed after decomposition.")
        return all_claims

    def _batches(self, claims: list[dict]) -> list[tuple[list[dict], int]]:
        batches: list[tuple[list[dict], int]] = []
        current: list[dict] = []
        total = 0
        for claim in claims:
            # Variable prompt plus an output allowance for identity, explanation,
            # citations and structured conflict. All source passages remain input.
            cost = estimate_tokens(_json(claim), self.config.chars_per_token) * 2 + 256
            if current and (len(current) >= self.config.max_batch_claims or total + cost > self.config.verify_batch_token_budget):
                batches.append((current, total))
                current, total = [], 0
            current.append(claim)
            total += cost
        if current:
            batches.append((current, total))
        return batches

    def verify(self, request: VerificationRequest) -> VerificationResult:
        telemetry = {
            **_local_telemetry(), "backend": "optimized-v4.0", "prompts": prompt_metadata(),
            "config": self.config.public_dict(), "extraction": None,
            "input_sha256": hashlib.sha256(_json(request.to_dict()).encode("utf-8")).hexdigest(),
            "input_serialization_version": "json-utf8-insertion-order-default-separators-v1",
            "batch_budget_scope": "Variable claim input and estimated output; all common source input is retained and measured separately.",
            "gate_limitation": "Exact anchors, literal units, and quote coverage do not prove semantic or algebraic incompatibility.",
        }
        started = time.monotonic()
        try:
            if not request.generated_answer.strip():
                return VerificationResult({"claims": []}, telemetry)
            claims = self._decompose(request.generated_answer, telemetry)
            if not claims:
                return VerificationResult({"claims": []}, telemetry)
            contexts = request.context_passages
            telemetry["common_input_estimated_tokens"] = estimate_tokens(
                VERIFY_PROMPT + _json([{"index": i, "text": text} for i, text in enumerate(contexts)]),
                self.config.chars_per_token,
            )
            if not any(context.strip() for context in contexts):
                # Ordinary extracted claims are factual already. A fallback
                # skeleton still needs semantic factuality classification; sending
                # it through the usual verifier prevents pure advice becoming U.
                ordinary = [claim for claim in claims if not claim.get("extraction_fallback")]
                pending = [claim for claim in claims if claim.get("extraction_fallback")]
                outputs = [{
                    "id": claim["id"], "claim_text": claim["claim_text"], "verdict": "UNSUPPORTED",
                    "reasoning": "No nonempty context passage was supplied to verify this factual claim.",
                    "citations": [], "conflict": None, "derivation": "No source premise is available.",
                } for claim in ordinary]
                for claim in ordinary:
                    telemetry["verdict_chains"].append({
                        "claim_id": claim["id"],
                        "steps": [{"stage": "empty_context", "verdict": "UNSUPPORTED", "validated": True}],
                        "status": "complete", "final_verdict": "UNSUPPORTED", "error": None,
                    })
            else:
                outputs, pending = [], claims
            batches = self._batches(pending)
            errors: list[dict] = []
            if batches:
                with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(batches))) as pool:
                    futures = [pool.submit(self._batch, i, rows, contexts, estimated) for i, (rows, estimated) in enumerate(batches)]
                    for future in futures:
                        completed, failed, local = future.result()
                        outputs.extend(completed)
                        errors.extend(failed)
                        _merge_telemetry(telemetry, local)
            ordinal = {claim["id"]: i for i, claim in enumerate(claims)}
            outputs.sort(key=lambda row: ordinal[row["id"]])
            errors.sort(key=lambda row: ordinal[row["id"]])
            excluded = {row["claim_id"] for row in telemetry["fallback_exclusions"]}
            completed_ids = {row["id"] for row in outputs}
            failed_ids = {row["id"] for row in errors}
            if completed_ids & failed_ids or (completed_ids | failed_ids | excluded) != set(ordinal):
                raise VerificationError("invalid_model_output", "Aggregation did not account for each extracted claim exactly once.")
            telemetry["completion"] = {
                "total_extracted": len(claims), "completed": len(outputs), "unfinished": len(errors),
                "non_factual_fallbacks": len(excluded), "completed_claim_ids": [row["id"] for row in outputs],
                "unfinished_claim_ids": [row["id"] for row in errors],
                "coverage": len(outputs) / (len(claims) - len(excluded)) if len(claims) > len(excluded) else 1.0,
            }
            if errors and not outputs:
                # Preserve an upstream failure's existing HTTP semantics when it
                # is the common cause of every unfinished claim. Keep statuses
                # internal so the additive public errors contract stays stable.
                statuses = {(item["code"], item["status"]) for item in telemetry["error_statuses"]}
                if len(statuses) == 1 and len(telemetry["error_statuses"]) == len(errors):
                    code, status = next(iter(statuses))
                    if code in {"upstream_timeout", "upstream_http_error", "upstream_connection_error"}:
                        raise VerificationError(code, errors[0]["message"], status)
                raise VerificationError("verification_failed", "No factual claim completed verification; see per-claim errors in telemetry.")
            report = {"claims": [_public(row) for row in outputs]}
            if errors:
                report.update({"status": "partial", "errors": errors})
            validate_v4_report(report, contexts)
            return VerificationResult(report, telemetry)
        except VerificationError as exc:
            exc.telemetry = telemetry
            raise
        finally:
            telemetry["latency_seconds"] = time.monotonic() - started
            telemetry["summary"] = {
                "citation_repairs": len(telemetry["citation_repairs"]),
                "format_repairs": len(telemetry["repairs"]),
                "targeted_reasks": len(telemetry["targeted_reasks"]),
                "batch_retries": len(telemetry["batch_retries"]),
                "transport_retries": sum(call.get("attempt", 1) > 1 for call in telemetry["calls"]),
                "contradiction_review_triggers": len(telemetry["contradiction_reviews"]),
                "unsupported_review_triggers": len(telemetry["unsupported_reviews"]),
                "contradiction_review_flips": sum(event.get("after_verdict") not in (None, event["before_verdict"]) for event in telemetry["contradiction_reviews"]),
                "unsupported_review_flips": sum(event.get("after_verdict") not in (None, event["before_verdict"]) for event in telemetry["unsupported_reviews"]),
                "decomposition_fallback_chunks": sum(chunk["fallback"] for chunk in (telemetry.get("extraction") or {}).get("chunks", [])),
                "unfinished_claims": len(telemetry["errors"]),
            }
