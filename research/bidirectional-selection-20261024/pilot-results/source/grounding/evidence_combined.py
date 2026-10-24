"""Versioned evidence pointers; location correctness is not entailment proof.

The catalog contains every source character exactly once, in source order. Units
are structural sentence/line locations, never retrieved or ranked evidence. IDs
bind to the request's source identity and Python Unicode character offsets.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from grounding.contracts import VerificationError
from grounding.verifiers_v4 import sentence_spans


EVIDENCE_PROTOCOL = "source-evidence-pointers-v1"


def _invalid(message: str) -> None:
    raise VerificationError("invalid_model_output", message)


def source_units(contexts: list[str]) -> list[dict]:
    """Code-owned stable locations, including repeated text as distinct units."""
    return [
        {"id": f"p{index}u{ordinal}", "index": index,
         "start_char": start, "end_char": end, "text": text[start:end]}
        for index, text in enumerate(contexts)
        for ordinal, (start, end) in enumerate(sentence_spans(text), 1)
    ]


def source_payload(contexts: list[str]) -> list[dict]:
    """All original source text appears once; no top-k or context truncation."""
    grouped = [{"index": index, "source_units": []} for index in range(len(contexts))]
    for unit in source_units(contexts):
        grouped[unit["index"]]["source_units"].append(unit)
    return grouped


def validate_ids(value: Any, units: dict[str, dict], field: str, *, maximum: int | None = None) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _invalid(f"{field} must be an array of source unit IDs.")
    if len(value) != len(set(value)):
        _invalid(f"{field} must not contain duplicate IDs.")
    if maximum is not None and len(value) > maximum:
        _invalid(f"{field} exceeds its limit of {maximum} source units.")
    if any(item not in units for item in value):
        _invalid(f"{field} contains an unknown source unit ID.")
    return list(value)


def materialize_ids(ids: list[str], units: dict[str, dict], contexts: list[str], *,
                    require_nonblank: bool = True) -> list[dict]:
    """Materialize from the original string, checking the catalog binding too."""
    citations = []
    for unit_id in ids:
        unit = units[unit_id]
        index, start, end = unit["index"], unit["start_char"], unit["end_char"]
        if (type(index) is not int or not 0 <= index < len(contexts)
                or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(contexts[index])):
            _invalid("The selected source unit has an invalid source identity or offset.")
        quote = contexts[index][start:end]
        if quote != unit["text"] or (require_nonblank and not quote.strip()):
            _invalid("The selected source unit is empty or differs from its original source span.")
        citations.append({"index": index, "quote": quote})
    return citations


def project_evidence_row(value: Any, contexts: list[str]) -> tuple[dict, dict]:
    """Validate the new IR before producing the existing internal row contract.

Invalid initial C conflict *structure* remains for the existing bounded C gate;
unknown pointers always fail immediately. A review still must pass the existing
full conflict checker. No legacy invalid citations are silently dropped.
    """
    required = {"evidence_protocol", "id", "claim_text", "verdict", "reasoning",
                "considered_evidence_ids", "decision_evidence_ids", "derivation", "conflict"}
    if not isinstance(value, dict) or set(value) != required:
        _invalid("Each evidence row must use the versioned pointer schema with considered_evidence_ids and decision_evidence_ids; legacy citations are not accepted.")
    if value["evidence_protocol"] != EVIDENCE_PROTOCOL:
        _invalid("Unknown evidence protocol version.")
    if value["verdict"] not in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"):
        _invalid("A verdict must be SUPPORTED, CONTRADICTED, or UNSUPPORTED.")
    units = {unit["id"]: unit for unit in source_units(contexts)}
    considered = validate_ids(value["considered_evidence_ids"], units, "considered_evidence_ids")
    decision = validate_ids(value["decision_evidence_ids"], units, "decision_evidence_ids", maximum=32)
    if not set(decision) <= set(considered):
        _invalid("Every decision evidence ID must also occur in considered_evidence_ids.")
    if value["verdict"] == "UNSUPPORTED":
        if decision:
            _invalid("UNSUPPORTED must have decision_evidence_ids:[]; invalid decision evidence is never silently removed.")
    elif not decision:
        _invalid("SUPPORTED and CONTRADICTED require nonempty decision_evidence_ids.")
    # Validate even considered-only locations; they remain model-reported search
    # traces and never become public evidence for an unsupported claim.
    materialize_ids(considered, units, contexts, require_nonblank=False)
    row = {name: deepcopy(value[name]) for name in ("id", "claim_text", "verdict", "reasoning", "derivation", "conflict")}
    row["citations"] = materialize_ids(decision, units, contexts)
    conflict = value["conflict"]
    if isinstance(conflict, dict):
        evidence = []
        if "evidence_ids" in conflict:
            conflict_ids = validate_ids(conflict["evidence_ids"], units, "conflict.evidence_ids", maximum=32)
            if not set(conflict_ids) <= set(decision):
                _invalid("Conflict evidence IDs must be a subset of decision_evidence_ids.")
            evidence = materialize_ids(conflict_ids, units, contexts)
        if set(conflict) == {"claim_span", "evidence_ids", "kind", "explanation"}:
            row["conflict"] = {key: deepcopy(item) for key, item in conflict.items() if key != "evidence_ids"}
            row["conflict"]["evidence"] = evidence
        else:
            # In particular, a legacy free-text evidence field cannot bypass
            # pointer binding. Preserve the defect for the existing C gate.
            row["conflict"] = {"invalid_pointer_conflict": deepcopy(conflict)}
    return row, deepcopy(value)
