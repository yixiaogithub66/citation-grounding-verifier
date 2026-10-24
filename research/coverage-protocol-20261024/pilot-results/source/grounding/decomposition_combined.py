"""Answer-side immutable locations, explicit residuals, and bounded extraction.

Location tokens are a transport convention, never a semantic atomizer. Only M1
chooses factual targets. Code does not merge extracted assertions or infer labels.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from grounding.contracts import VerificationError
from grounding.prompts_combined_decomposition import (
    DECOMPOSE_PROMPT, DECOMPOSITION_PROTOCOL, RESIDUAL_PASSES, decomposition_prompt_metadata,
)
from grounding.verifiers_v4 import (
    _invalid, _meaningful, _text, _local_telemetry, _merge_telemetry, sentence_spans,
)

# Language-neutral structural locations with separate ideographs. Numeric surface
# strings preserve their decimal marks/signs as a single token whenever possible.
# Long runs are split solely to keep the minimum configured chunk length usable.
_LOCATION_TOKEN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]"
    r"|[+\-−]?\d+(?:[.,]\d+)*(?:[eE][+\-−]?\d+)?"
    r"|[^\W\d_]+(?:['’][^\W\d_]+)*|[^\s]", re.UNICODE,
)
_REF_KEYS = {"unit_id", "start_token", "end_token"}
_SPAN_KINDS = ("non_factual_spans", "ambiguous_spans", "unprocessed_spans")


def answer_units(answer: str) -> list[dict]:
    """Assign deterministic original offsets, retaining exact Unicode strings."""
    units = []
    for number, (start, end) in enumerate(sentence_spans(answer), 1):
        tokens = []
        for match in _LOCATION_TOKEN.finditer(answer, start, end):
            for left in range(match.start(), match.end(), 32):
                right = min(left + 32, match.end())
                tokens.append({"index": len(tokens), "start": left, "end": right, "text": answer[left:right]})
        units.append({"unit_id": f"a{number}", "source_start": start, "source_end": end,
                      "text": answer[start:end], "tokens": tokens})
    return units


def location_chunks(answer: str, units: list[dict], max_chars: int) -> list[tuple[int, int]]:
    """Prefer original sentence ends, then token ends; never cut a pointer token."""
    sentence_ends = [unit["source_end"] for unit in units]
    tokens = [token for unit in units for token in unit["tokens"]]
    chunks, start = [], 0
    while start < len(answer):
        limit = min(len(answer), start + max_chars)
        candidates = [end for end in sentence_ends if start < end <= limit]
        if candidates:
            end = candidates[-1]
        else:
            crossing = next((token for token in tokens if token["start"] < limit < token["end"]), None)
            end = crossing["start"] if crossing else limit
            if end <= start:
                raise VerificationError("configuration_error", "A location token exceeds the chunk capacity.", 503)
        chunks.append((start, end))
        start = end
    return chunks


def _allowed_tokens(units: list[dict], start: int, end: int) -> set[tuple[str, int]]:
    return {(unit["unit_id"], token["index"]) for unit in units for token in unit["tokens"]
            if start <= token["start"] and token["end"] <= end}


def token_ranges(units: list[dict], selected: set[tuple[str, int]]) -> list[dict]:
    ranges = []
    for unit in units:
        indices = [token["index"] for token in unit["tokens"] if (unit["unit_id"], token["index"]) in selected]
        for index in indices:
            if ranges and ranges[-1]["unit_id"] == unit["unit_id"] and ranges[-1]["end_token"] == index:
                ranges[-1]["end_token"] += 1
            else:
                ranges.append({"unit_id": unit["unit_id"], "start_token": index, "end_token": index + 1})
    return ranges


def _materialize_refs(refs: Any, units: list[dict], allowed: set[tuple[str, int]], answer: str) -> list[dict]:
    if not isinstance(refs, list) or not 1 <= len(refs) <= 128:
        _invalid("Each source_refs must be a nonempty array of at most 128 location ranges.")
    indexed = {unit["unit_id"]: unit for unit in units}
    materialized = []
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != _REF_KEYS:
            _invalid("A source reference needs exactly unit_id, start_token and end_token.")
        unit_id, left, right = ref["unit_id"], ref["start_token"], ref["end_token"]
        if not isinstance(unit_id, str) or unit_id not in indexed or type(left) is not int or type(right) is not int:
            _invalid("Source references need an existing unit ID and integer token indices.")
        tokens = indexed[unit_id]["tokens"]
        if not 0 <= left < right <= len(tokens) or any((unit_id, i) not in allowed for i in range(left, right)):
            _invalid("Source reference is outside the designated target token ranges.")
        start, end = tokens[left]["start"], tokens[right - 1]["end"]
        materialized.append({**ref, "source_start": start, "source_end": end, "text": answer[start:end]})
    materialized.sort(key=lambda ref: (ref["source_start"], ref["source_end"]))
    return materialized


def _positions(records: list[dict]) -> set[int]:
    return {position for record in records for ref in record["source_refs"]
            for position in range(ref["source_start"], ref["source_end"])}


def _remaining(units: list[dict], allowed: set[tuple[str, int]], covered: set[int]) -> set[tuple[str, int]]:
    return {(unit["unit_id"], token["index"]) for unit in units for token in unit["tokens"]
            if (unit["unit_id"], token["index"]) in allowed
            and any(_meaningful(char) and token["start"] + i not in covered for i, char in enumerate(token["text"]))}


def parse_decomposition(payload: Any, answer: str, units: list[dict], allowed: set[tuple[str, int]], *, max_claims: int) -> dict:
    """Validate pointers and report remaining text; never claim semantic coverage."""
    if not isinstance(payload, dict) or set(payload) != {"claims", *_SPAN_KINDS}:
        _invalid("Extraction needs exactly claims, non_factual_spans, ambiguous_spans and unprocessed_spans.")
    if not isinstance(payload["claims"], list) or len(payload["claims"]) > max_claims:
        _invalid("Extraction claims exceeds the configured capacity or is not an array.")
    indexed = {unit["unit_id"]: unit for unit in units}
    claims, seen = [], set()
    for row in payload["claims"]:
        if not isinstance(row, dict) or set(row) != {"claim_text", "source_refs", "background_refs"} or not _text(row["claim_text"]):
            _invalid("Each claim needs exactly nonempty claim_text, source_refs and background_refs.")
        refs = _materialize_refs(row["source_refs"], units, allowed, answer)
        background = row["background_refs"]
        if not isinstance(background, list) or len(background) > 128 or any(not isinstance(value, str) or value not in indexed for value in background):
            _invalid("background_refs must contain only existing answer unit IDs.")
        if len(background) != len(set(background)):
            _invalid("background_refs must not repeat an answer unit ID.")
        start, end = refs[0]["source_start"], max(ref["source_end"] for ref in refs)
        identity = (row["claim_text"], tuple((ref["unit_id"], ref["start_token"], ref["end_token"]) for ref in refs))
        if identity in seen:
            _invalid("Duplicate claim with identical source ranges; return each target once.")
        seen.add(identity)
        claims.append({"claim_text": row["claim_text"], "source_span": answer[start:end],
                       "source_start": start, "source_end": end, "source_refs": refs,
                       "answer_background": [{"unit_id": item, "source_start": indexed[item]["source_start"],
                                              "source_end": indexed[item]["source_end"], "text": indexed[item]["text"],
                                              "role": "unverified_answer_background"} for item in background],
                       "extraction_protocol": DECOMPOSITION_PROTOCOL})
    output = {"claims": claims}
    factual_positions = _positions(claims)
    classified = set(factual_positions)
    for kind in _SPAN_KINDS:
        rows = payload[kind]
        if not isinstance(rows, list) or len(rows) > 256:
            _invalid("Extraction span categories must be arrays of at most 256 records.")
        output[kind] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"source_refs", "reason"} or not _text(row["reason"]):
                _invalid("Each classified span needs exactly nonempty source_refs and reason.")
            refs = _materialize_refs(row["source_refs"], units, allowed, answer)
            start, end = refs[0]["source_start"], max(ref["source_end"] for ref in refs)
            record = {"source_refs": refs, "text": answer[start:end], "source_start": start, "source_end": end,
                      "reason": row["reason"]}
            positions = _positions([record])
            if any(_meaningful(answer[position]) for position in positions & classified):
                _invalid("Factual, non-factual, ambiguous and unprocessed categories must not overlap substantive text.")
            classified.update(positions)
            output[kind].append(record)
    covered = factual_positions | _positions(output["non_factual_spans"])
    output["remaining_tokens"] = _remaining(units, allowed, covered)
    claims.sort(key=lambda claim: (claim["source_start"], claim["source_end"]))
    return output


def _payload(answer: str, units: list[dict], selected: set[tuple[str, int]], chunk: dict, max_claims: int) -> dict:
    return {
        "protocol": DECOMPOSITION_PROTOCOL,
        "answer_context": [{key: unit[key] for key in ("unit_id", "source_start", "source_end", "text")} for unit in units],
        "target_units": [{"unit_id": unit["unit_id"], "tokens": [[token["index"], token["text"]] for token in unit["tokens"]
                          if (unit["unit_id"], token["index"]) in selected]} for unit in units
                         if any((unit["unit_id"], token["index"]) in selected for token in unit["tokens"])],
        "target_ranges": token_ranges(units, selected),
        "target_chunk": {key: chunk[key] for key in ("chunk_id", "source_start", "source_end")},
        "max_claims": max_claims,
    }


def _fallback_recovery(answer: str, units: list[dict], claims: list[dict], exclusions: list[dict],
                       unresolved: set[tuple[str, int]], chunks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Replace affected original sentences, never concatenate extracted claims."""
    selected = {i for i, unit in enumerate(units) if any((unit["unit_id"], token["index"]) in unresolved for token in unit["tokens"])}

    def overlap(start: int, end: int, unit: dict) -> bool:
        return max(start, unit["source_start"]) < min(end, unit["source_end"])

    changed = True
    while changed:
        before = set(selected)
        for row in [*claims, *exclusions]:
            if any(overlap(row["source_start"], row["source_end"], units[i]) for i in selected):
                selected.update(i for i, unit in enumerate(units) if overlap(row["source_start"], row["source_end"], unit))
        changed = selected != before
    affected = lambda row: any(overlap(row["source_start"], row["source_end"], units[i]) for i in selected)
    retained = [row for row in claims if not affected(row)]
    retained_exclusions = [row for row in exclusions if not affected(row)]
    audits = []
    for i in sorted(selected):
        unit = units[i]
        start, end, text = unit["source_start"], unit["source_end"], unit["text"]
        origins = [chunk["chunk_id"] for chunk in chunks if max(start, chunk["source_start"]) < min(end, chunk["source_end"])]
        if not any(_meaningful(character) for character in text):
            # Expanding a multi-unit target's enclosing range can include empty
            # lines or formatting-only units. They are not fallback assertions,
            # and an empty token table must never produce a fabricated 0..0 ref.
            audits.append({"unit_id": unit["unit_id"], "source_start": start, "source_end": end,
                           "origin_chunk_ids": origins, "kind": "formatting_only",
                           "reason": "An expanded recovery range crosses formatting without substantive text."})
            continue
        refs = _materialize_refs([{"unit_id": unit["unit_id"], "start_token": 0, "end_token": len(unit["tokens"])}],
                                 units, _allowed_tokens(units, start, end), answer)
        retained.append({"claim_text": text, "source_span": text, "source_start": start, "source_end": end,
                         "source_refs": refs, "answer_background": [{"unit_id": context["unit_id"],
                         "source_start": context["source_start"], "source_end": context["source_end"],
                         "text": context["text"], "role": "unverified_answer_background"}
                         for context in units if context["unit_id"] != unit["unit_id"]],
                         "extraction_fallback": True, "extraction_protocol": DECOMPOSITION_PROTOCOL,
                         "chunk_id": origins[0], "origin_chunk_ids": origins})
        audits.append({"unit_id": unit["unit_id"], "source_start": start, "source_end": end,
                       "origin_chunk_ids": origins, "reason": "Residual or failed extraction retained as an original sentence skeleton.",
                       "superseded_claims": [deepcopy(row) for row in claims if overlap(row["source_start"], row["source_end"], unit)],
                       "superseded_non_factual_spans": [deepcopy(row) for row in exclusions if overlap(row["source_start"], row["source_end"], unit)]})
    retained.sort(key=lambda row: (row["source_start"], row["source_end"]))
    return retained, retained_exclusions, audits


class CombinedDecompositionMixin:
    """M1 replacement only; verification/review stay owned by the host verifier."""

    def _decompose(self, answer: str, telemetry: dict) -> list[dict]:
        units = answer_units(answer)
        all_claims, all_exclusions, chunks, ambiguities, unprocessed = [], [], [], [], []
        unresolved: set[tuple[str, int]] = set()
        sentence_ends = {unit["source_end"] for unit in units}
        for number, (start, end) in enumerate(location_chunks(answer, units, self.config.decompose_chunk_chars), 1):
            selected = _allowed_tokens(units, start, end)
            local = _local_telemetry()
            chunk = {"chunk_id": f"d{number}", "source_start": start, "source_end": end,
                     "hard_split": (start != 0 and start not in sentence_ends) or end not in sentence_ends,
                     "fallback": False, "residual_passes": [], "initial_remaining_ranges": []}
            chunks.append(chunk)
            payload = _payload(answer, units, selected, chunk, self.config.max_claims)
            rows, exclusions = [], []
            remaining = _remaining(units, selected, set())
            try:
                if remaining:
                    result = self._format_stage(DECOMPOSE_PROMPT, payload, "decompose", "decompose",
                        lambda value: parse_decomposition(value, answer, units, selected, max_claims=self.config.max_claims), local)
                    rows.extend(result["claims"])
                    exclusions.extend(result["non_factual_spans"])
                    ambiguities.extend({**row, "chunk_id": chunk["chunk_id"], "pass": "initial"} for row in result["ambiguous_spans"])
                    unprocessed.extend({**row, "chunk_id": chunk["chunk_id"], "pass": "initial"} for row in result["unprocessed_spans"])
                    remaining = result["remaining_tokens"]
                    chunk["initial_remaining_ranges"] = token_ranges(units, remaining)
                for residual_number in range(RESIDUAL_PASSES):
                    if not remaining:
                        break
                    residual_targets = set(remaining)
                    residual_payload = _payload(answer, units, residual_targets, chunk, self.config.max_claims)
                    residual_payload.update({"residual_pass": residual_number + 1,
                                             "previously_accounted_claims": [row["claim_text"] for row in rows]})
                    event = {"pass": residual_number + 1, "target_ranges": token_ranges(units, residual_targets)}
                    chunk["residual_passes"].append(event)
                    result = self._format_stage(DECOMPOSE_PROMPT, residual_payload, "decompose_residual", "decompose",
                        lambda value: parse_decomposition(value, answer, units, residual_targets, max_claims=self.config.max_claims), local)
                    rows.extend(result["claims"])
                    exclusions.extend(result["non_factual_spans"])
                    ambiguities.extend({**row, "chunk_id": chunk["chunk_id"], "pass": "residual"} for row in result["ambiguous_spans"])
                    unprocessed.extend({**row, "chunk_id": chunk["chunk_id"], "pass": "residual"} for row in result["unprocessed_spans"])
                    remaining = _remaining(units, selected, _positions(rows) | _positions(exclusions))
                    event["remaining_ranges"] = token_ranges(units, remaining)
            except VerificationError as exc:
                chunk["error"] = {"code": exc.code, "message": exc.message}
                remaining = _remaining(units, selected, _positions(rows) | _positions(exclusions))
            finally:
                for call in local["calls"]:
                    call["chunk_id"] = chunk["chunk_id"]
                for repair in local["repairs"]:
                    repair["chunk_id"] = chunk["chunk_id"]
                _merge_telemetry(telemetry, local)
            for row in rows:
                row["chunk_id"] = chunk["chunk_id"]
            all_claims.extend(rows)
            all_exclusions.extend(exclusions)
            unresolved.update(remaining)
            chunk["unresolved_ranges_before_fallback"] = token_ranges(units, remaining)
            if remaining:
                chunk["fallback"] = True
                chunk["fallback_limitation"] = "Sentence skeletons preserve text but certify neither atomicity nor factuality."
        all_claims, all_exclusions, recoveries = _fallback_recovery(answer, units, all_claims, all_exclusions, unresolved, chunks)
        for number, claim in enumerate(all_claims, 1):
            claim["id"] = f"c{number}"
        for chunk in chunks:
            chunk["claim_ids"] = [row["id"] for row in all_claims if max(row["source_start"], chunk["source_start"]) < min(row["source_end"], chunk["source_end"])]
        covered = _positions(all_claims) | _positions(all_exclusions)
        global_remaining = _remaining(units, _allowed_tokens(units, 0, len(answer)), covered)
        telemetry["extraction"] = {
            "protocol": decomposition_prompt_metadata(), "claims": all_claims, "non_factual_spans": all_exclusions,
            "ambiguous_spans": ambiguities, "unprocessed_spans": unprocessed, "chunks": chunks,
            "answer_units": units, "residual_ranges_before_fallback": token_ranges(units, unresolved),
            "residual_ranges_after_fallback": token_ranges(units, global_remaining),
            "hard_split_recoveries": recoveries,
            "coverage_check": "Substantive original characters are accounted for by exact source_refs, not enclosing spans or background.",
            "limitation": "Lexical accounting and sentence fallback do not prove semantic recall, extraction fidelity or atomicity.",
            "context_cost": "Complete original answer repeated for each chunk/residual pass to preserve cross-boundary dependencies.",
        }
        if global_remaining:
            raise VerificationError("invalid_model_output", "Global original-answer location accounting failed after bounded fallback.")
        if len(all_claims) > self.config.max_claims:
            raise VerificationError("claim_limit_exceeded", "Decomposition exceeds the configured claim capacity; no claims were silently truncated.", 413)
        return all_claims
