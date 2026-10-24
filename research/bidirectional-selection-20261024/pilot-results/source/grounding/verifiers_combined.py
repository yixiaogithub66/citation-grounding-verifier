"""Experimental H1/H2/H3 composition with the unchanged v4 bounded scheduler.

H4 is an offline evaluation method, not a fourth inference stage. The old v4
backend remains available as the paired control. No request or batch state is
stored on this verifier; source catalogs are pure functions of request context.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from grounding.contracts import VerificationError, VerificationRequest, VerificationResult
from grounding.decomposition_combined import CombinedDecompositionMixin
from grounding.evidence_combined import EVIDENCE_PROTOCOL, project_evidence_row, source_payload, source_units
from grounding.prompts_combined import BLIND_REVIEW_PROMPT, VERIFY_PROMPT, prompt_metadata
from grounding.prompts_combined_decomposition import decomposition_prompt_metadata
from grounding.verifiers_v4 import OptimizedV4Verifier, _json, _public, conflict_error, estimate_tokens


class OptimizedV4CombinedVerifier(CombinedDecompositionMixin, OptimizedV4Verifier):
    def _call(self, messages: list[dict], stage: str, phase: str, telemetry: dict) -> Any:
        if phase not in ("verify", "review"):
            return super()._call(messages, stage, phase, telemetry)
        sent = deepcopy(messages)
        payload = json.loads(sent[1]["content"])
        contexts = [passage["text"] for passage in payload["context_passages"]]
        payload["context_passages"] = source_payload(contexts)
        payload["evidence_protocol"] = EVIDENCE_PROTOCOL
        sent[0]["content"] = BLIND_REVIEW_PROMPT if phase == "review" else VERIFY_PROMPT
        sent[1]["content"] = _json(payload)
        # Keep one catalog per worker telemetry, not process-global cached state.
        if not any(event.get("kind") == "source_evidence_catalog" for event in telemetry["protocol_events"]):
            units = source_units(contexts)
            telemetry["protocol_events"].append({
                "kind": "source_evidence_catalog", "protocol": EVIDENCE_PROTOCOL,
                "catalog_sha256": hashlib.sha256(_json(units).encode("utf-8")).hexdigest(),
                "units": [{key: unit[key] for key in ("id", "index", "start_char", "end_char")} for unit in units],
                "all_source_text_retained": True,
                "limitation": "Location correctness and model-reported considered IDs do not prove semantic support or exhaustive search.",
            })
        return super()._call(sent, stage, phase, telemetry)

    def _validate_row(self, value: Any, claim: dict, contexts: list[str], stage: str,
                      telemetry: dict, *, review: bool = False) -> dict:
        event = {"kind": "evidence_ir_transition", "claim_id": claim["id"], "stage": stage,
                 "protocol": EVIDENCE_PROTOCOL, "raw_internal": deepcopy(value), "status": "pending"}
        telemetry["protocol_events"].append(event)
        try:
            if isinstance(value, dict) and value.get("non_factual") is True:
                row = super()._validate_row(value, claim, contexts, stage, telemetry, review=review)
                event.update({"status": "validated_non_factual", "validated_internal": deepcopy(value),
                              "public_projection": None})
                return row
            materialized, validated = project_evidence_row(value, contexts)
            row = super()._validate_row(materialized, claim, contexts, stage, telemetry, review=review)
            event.update({"status": "validated", "validated_internal": validated,
                          "materialized_row": deepcopy(row), "public_projection": _public(row),
                          "conflict_gate_pending": row["verdict"] == "CONTRADICTED" and conflict_error(row, contexts) is not None})
            return row
        except VerificationError as exc:
            event.update({"status": "invalid", "error": {"code": exc.code, "message": exc.message}})
            raise

    def _review(self, row: dict, claim: dict, contexts: list[str], state: dict,
                telemetry: dict, kind: str, trigger: Any) -> dict:
        key = "c_review_used" if kind == "C" else "u_review_used"
        if state[key]:
            raise AssertionError("A claim cannot enter the same logical review twice")
        state[key] = True
        event = {"claim_id": claim["id"], "before_verdict": row["verdict"], "after_verdict": None,
                 "trigger": deepcopy(trigger), "reviewed": True, "initial_verdict_blinded": True}
        telemetry["contradiction_reviews" if kind == "C" else "unsupported_reviews"].append(event)
        stage = "contradiction_review" if kind == "C" else "unsupported_review"
        try:
            # Original target/provenance/background and all context remain. The
            # prior judgment and trigger remain only in telemetry, never payload.
            reviewed = self._single_decision(
                claim, contexts, state, telemetry, prompt=BLIND_REVIEW_PROMPT,
                stage=stage, review=True, diagnostics=None, allow_targeted=True,
            )
        except VerificationError as exc:
            event["error"] = {"code": exc.code, "message": exc.message}
            raise
        event["after_verdict"] = reviewed.get("verdict")
        event["evidence"] = reviewed.get("citations", [])
        event["derivation"] = reviewed.get("derivation")
        state["chain"].append({"stage": stage, "verdict": reviewed.get("verdict", "NON_FACTUAL"), "validated": True})
        return reviewed

    def _combined_metadata(self, telemetry: dict, request: VerificationRequest) -> None:
        telemetry["backend"] = "optimized-v4-combined"
        telemetry["prompts"] = {**prompt_metadata(), "decomposition": decomposition_prompt_metadata()}
        telemetry["evidence_protocol"] = EVIDENCE_PROTOCOL
        telemetry["experimental_hypotheses"] = {"H1": "answer locations and target/background separation",
                                               "H2": "separate evidence roles and source pointers",
                                               "H3": "initial-verdict-blinded bounded review",
                                               "H4": "offline behavioral evaluation; no inference stage"}
        telemetry["review_blinding_limitation"] = "Initial judgment, reasoning, chosen evidence and trigger are hidden; the target claim remains visible and model errors are not independent."
        if "common_input_estimated_tokens" in telemetry:
            telemetry["common_input_estimated_tokens"] = estimate_tokens(
                VERIFY_PROMPT + _json(source_payload(request.context_passages)), self.config.chars_per_token,
            )

    def verify(self, request: VerificationRequest) -> VerificationResult:
        try:
            result = super().verify(request)
        except VerificationError as exc:
            self._combined_metadata(exc.telemetry, request)
            raise
        self._combined_metadata(result.telemetry, request)
        return result
