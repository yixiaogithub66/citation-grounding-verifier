#!/usr/bin/env python3
"""Create blinded review packets only from a sealed 120-record coverage pilot.

Offline presentation and integrity checking only: no model imports or requests,
semantic scoring, source edits, or repairs of failed model output. The final
run-complete.json seal is authoritative; progress.json is never consulted.
Give reviewers only their blind packet, not this program or private-key.json.
Obfuscation supplies procedural blinding, not cryptographic anonymity.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile


SCHEMA = "coverage-protocol-blind-review-v1"
RUN_SCHEMA = "coverage-protocol-initial-stage-pilot-v1"
CASE_REL = "research/coverage-protocol-20261024/cases.json"
ARMS = ("legacy", "ledger_text", "ledger_id")
REPETITIONS = 2
CASE_COUNT = 20
RECORD_COUNT = CASE_COUNT * REPETITIONS * len(ARMS)
BLIND_SEED = "coverage-protocol-review-20261024-v1"


GUIDANCE = {
    "scope": (
        "AI semantic review of fictional diagnostic material, not author gold or author "
        "final adjudication. Expected facts are provisional semantic targets, not a "
        "required output wording or count. Do not infer semantic truth from technical validity."
    ),
    "indices": "claim_indices and claim_index are zero-based indices into this record's claims array.",
    "technical_gate": (
        "For status other than valid, diagnostic_only is true. If extraction_readable is true, "
        "assess content_retained only; standalone_retained and source_supported must be null. "
        "selection_pass and strict_fidelity_pass must both be null for every technical-invalid "
        "record, even if all content appears retained. Never convert it into a completed success. "
        "If extraction_readable is false, all target judgments must be null with empty "
        "claim_indices; leave claim_issues empty as unscored, not as zero errors. Explain in "
        "uncertainty. Invalid raw output is diagnostic only and never replaces validated output."
    ),
    "content_retained": (
        "For each fact, map every claim index needed to assess its asserted content. Preserve "
        "subject, relation, attribution, polarity, quantity/unit, modality and applicability "
        "conditions. Semantic paraphrase is allowed. A referent that can be uniquely resolved "
        "from the full answer and extraction can count as content retained, even when the "
        "claim is not self-contained. A missing or changed element is false; genuine ambiguity "
        "is null and must be explained. Do not treat substring or numeric overlap as proof."
    ),
    "standalone_retained": (
        "For a technically valid record, separately judge whether the mapped claim or claims "
        "express the fact with explicit, correct subject, attribution and conditions when "
        "each claim is read by itself. An unresolved pronoun or omitted governing condition "
        "fails this stricter criterion even if full-paragraph context rescues content_retained. "
        "Do not require verbatim source wording. For technical-invalid records use null."
    ),
    "source_supported": (
        "Only score when provenance_scorable is true. Check that the mapped claim's displayed "
        "source spans support its predicate, quantities, attribution, necessary conditions "
        "and scope. A claim may correctly expand an explicit shared antecedent from the "
        "full answer even when the attached fragment itself omits the antecedent's name; "
        "that omission alone is not a source error or strict-score failure. Whether the "
        "attached fragment includes the antecedent may be noted descriptively. Offsets are "
        "start-inclusive/end-exclusive Unicode code-point "
        "indices into answer. Multiple spans are separate exact spans, never an implied "
        "continuous envelope. Exact matching is structural evidence, not semantic proof. "
        "If the sources do not support the mapping use false; uncertain support is null."
    ),
    "claim_issues": (
        "For each readable claim, identify non_factual_as_claim, meaning_changed, "
        "unresolved_reference, compound_claim or source_misaligned as applicable, explaining "
        "the evidence. Advice and questions themselves are non-factual; their asserted "
        "premises remain facts. Asserted conditional rules are factual and retain their "
        "conditions. Mark independent assertions grouped in one claim as compound_claim. "
        "A faithful same-sentence repetition alone is not a false positive, changed meaning, "
        "or compound fact; mention redundant extraction only in uncertainty. For technical "
        "invalids, limit issues to content diagnostics (non_factual_as_claim or meaning_changed); "
        "do not issue standalone, atomicity, or provenance judgments."
    ),
    "selection_pass": (
        "For technically valid, readable output: true only if every target has "
        "content_retained=true and no claim asserts non-factual material or changes meaning. "
        "False when a definite omission or content error exists; null when the result remains "
        "uncertain. Standalone, atomicity and provenance problems are separate from this "
        "content-selection score. Pure NF requires an empty claims array. Technical invalid "
        "always means null, never a completed pass or fail."
    ),
    "strict_fidelity_pass": (
        "For technically valid, readable output: true only if selection_pass=true, every "
        "target is standalone_retained=true and source_supported=true, and there are no "
        "claim issues. Any definite strict failure yields false; otherwise unresolved "
        "judgments yield null. A valid pure-NF empty extraction passes vacuously. "
        "Technical invalid always means null."
    ),
    "blindness": (
        "Do not inspect private-key.json, original journals, prompts, request payloads, "
        "usage, source code or experiment summaries. Repeated answers are expected; judge "
        "each extraction independently. Review IDs and packet order do not imply rank. "
        "The generic technical error code intentionally hides protocol-specific details."
    ),
    "output": "Return one object per review_id using scoring_schema; include one target entry per expected fact.",
}


def nullable_boolean():
    return {"type": ["boolean", "null"]}


SCORING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["review_id", "targets", "claim_issues", "selection_pass", "strict_fidelity_pass", "uncertainty"],
    "properties": {
        "review_id": {"type": "string"},
        "targets": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["fact_id", "claim_indices", "content_retained", "standalone_retained", "source_supported", "reason"],
                "properties": {
                    "fact_id": {"type": "string"},
                    "claim_indices": {"type": "array", "uniqueItems": True,
                                      "items": {"type": "integer", "minimum": 0}},
                    "content_retained": nullable_boolean(),
                    "standalone_retained": nullable_boolean(),
                    "source_supported": nullable_boolean(),
                    "reason": {"type": "string"},
                },
            },
        },
        "claim_issues": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["claim_index", "kind", "reason"],
                "properties": {
                    "claim_index": {"type": "integer", "minimum": 0},
                    "kind": {"type": "string", "enum": ["non_factual_as_claim", "meaning_changed",
                             "unresolved_reference", "compound_claim", "source_misaligned"]},
                    "reason": {"type": "string"},
                },
            },
        },
        "selection_pass": nullable_boolean(),
        "strict_fidelity_pass": nullable_boolean(),
        "uncertainty": {"type": ["string", "null"]},
    },
}


def encoded(value):
    """Match the runner's identity encoding exactly, including its final newline."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       indent=2) + "\n").encode("utf-8", errors="backslashreplace")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8", errors="backslashreplace")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)


def read_object(path):
    result = strict_json(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return result


def identity(row):
    if (row.get("probe") != "natural" or not isinstance(row.get("case_id"), str)
            or row.get("arm") not in ARMS or type(row.get("repetition")) is not int
            or row["repetition"] not in range(REPETITIONS)):
        raise ValueError("Invalid scheduled identity")
    return {name: row[name] for name in ("probe", "case_id", "arm", "repetition")}


def identity_key(row):
    return digest(encoded(identity(row)))


def expected_identities(cases):
    return {(case_id, arm, repetition)
            for case_id in cases for arm in ARMS for repetition in range(REPETITIONS)}


def check_matrix(rows, cases, label):
    if not isinstance(rows, list) or len(rows) != RECORD_COUNT or any(not isinstance(row, dict) for row in rows):
        raise ValueError(label + " must contain 120 objects")
    result, identities = {}, set()
    for row in rows:
        value = identity(row)
        key = identity_key(row)
        if row.get("identity_key") != key or key in result:
            raise ValueError(label + " has an invalid or repeated identity key")
        identities.add((value["case_id"], value["arm"], value["repetition"]))
        result[key] = row
    if identities != expected_identities(cases):
        raise ValueError(label + " does not cover the complete fixed identity matrix")
    return result


def checked_source(source, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid frozen source path")
    path = (source / relative).resolve()
    if not path.is_relative_to(source) or not path.is_file():
        raise ValueError("Frozen source path escapes the source directory or is missing")
    return path


def load_completed(run_dir):
    """Validate sealed source, journal and durable identities before making packets."""
    run = Path(run_dir).resolve()
    complete = read_object(run / "run-complete.json")
    if (complete.get("schema_version") != RUN_SCHEMA or complete.get("status") != "complete"
            or complete.get("unknown_reservations") != []
            or complete.get("record_count") != RECORD_COUNT
            or complete.get("expected_records") != RECORD_COUNT
            or complete.get("model_calls_started") != RECORD_COUNT
            or complete.get("frozen_artifacts_unchanged") is not True):
        raise ValueError("A complete sealed 120-record run with no unknown reservations is required")
    freeze_path = run / "freeze.json"
    freeze_hash = sha(freeze_path)
    if (freeze_hash != complete.get("freeze_sha256") or freeze_hash !=
            (run / "freeze.sha256").read_text(encoding="ascii").strip()):
        raise ValueError("Frozen manifest hash mismatch")
    freeze = read_object(freeze_path)
    if (freeze.get("schema_version") != RUN_SCHEMA or freeze.get("arms") != list(ARMS)
            or freeze.get("repetitions") != REPETITIONS
            or freeze.get("max_model_calls") != RECORD_COUNT
            or freeze.get("expected_records") != RECORD_COUNT):
        raise ValueError("Frozen experiment matrix differs from 20 cases x 2 repetitions x 3 arms")
    source = (run / "source").resolve()
    files = freeze.get("files_sha256")
    if not isinstance(files, dict) or CASE_REL not in files:
        raise ValueError("Frozen source does not bind cases.json")
    for name, expected in files.items():
        if sha(checked_source(source, name)) != expected:
            raise ValueError("Frozen source hash mismatch: " + name)
    # Read prompt bytes only for hashing; do not load or export prompt text.
    if sha(run / "prompts.json") != freeze.get("prompts_sha256"):
        raise ValueError("Frozen prompt bundle hash mismatch")
    if sha(run / "planned-requests.json") != freeze.get("planned_requests_sha256"):
        raise ValueError("Frozen request matrix hash mismatch")
    case_data = read_object(source / CASE_REL)
    entries = case_data.get("cases")
    if not isinstance(entries, list) or len(entries) != CASE_COUNT or "controlled_seeds" in case_data:
        raise ValueError("Expected twenty natural cases and no controlled seeds")
    cases = {}
    for case in entries:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
                or not case["id"] or case["id"] in cases
                or not isinstance(case.get("generated_answer"), str)
                or not isinstance(case.get("expected_facts"), list)
                or type(case.get("expected_pure_nf")) is not bool):
            raise ValueError("Malformed or repeated frozen case")
        facts = case["expected_facts"]
        if any(not isinstance(fact, dict) or not isinstance(fact.get("id"), str) for fact in facts):
            raise ValueError("Malformed expected fact inventory")
        if len({fact["id"] for fact in facts}) != len(facts):
            raise ValueError("Repeated expected fact ID")
        cases[case["id"]] = case
    planned = check_matrix(read_object(run / "planned-requests.json").get("requests"), cases, "Planned requests")
    journal = run / "responses.jsonl"
    if sha(journal) != complete.get("responses_sha256"):
        raise ValueError("Sealed response journal hash mismatch")
    lines = journal.read_text(encoding="utf-8").splitlines()
    if any(not line.strip() for line in lines):
        raise ValueError("Blank response journal row")
    rows = [strict_json(line) for line in lines]
    records = check_matrix(rows, cases, "Response journal")
    expected_names = {key + ".json" for key in planned}
    for directory, field in (("reservations", "reservation_files_sha256"), ("responses", "response_files_sha256")):
        actual = {path.name: sha(path) for path in (run / directory).glob("*.json")}
        if set(actual) != expected_names or actual != complete.get(field):
            raise ValueError("Sealed durable file matrix or hash mismatch: " + directory)
    for key, row in records.items():
        if row.get("status") not in {"valid", "error"}:
            raise ValueError("Unexpected technical status")
        if any(name not in row or row[name] != value for name, value in planned[key].items()):
            raise ValueError("Journal request differs from the frozen request")
        if row != read_object(run / "responses" / (key + ".json")):
            raise ValueError("Journal differs from its durable response checkpoint")
        reservation = read_object(run / "reservations" / (key + ".json"))
        if reservation.get("request") != planned[key] or reservation.get("freeze_sha256") != freeze_hash:
            raise ValueError("Reservation differs from its frozen request")
        telemetry = row.get("telemetry")
        if not isinstance(telemetry, dict) or not isinstance(telemetry.get("calls"), list) or len(telemetry["calls"]) != 1:
            raise ValueError("Each response must retain exactly one provider attempt")
    counts = Counter(row["status"] for row in rows)
    if complete.get("valid") != counts["valid"] or complete.get("error") != counts["error"]:
        raise ValueError("Sealed status counts differ from the response journal")
    if sha(run / "responses.events.jsonl") != complete.get("event_journal_sha256"):
        raise ValueError("Sealed event journal hash mismatch")
    return rows, cases, {
        "run_complete_sha256": sha(run / "run-complete.json"),
        "freeze_sha256": freeze_hash,
        "responses_sha256": sha(journal),
        "frozen_cases_sha256": files[CASE_REL],
    }


def exact_source(answer, text, start, end):
    if (not isinstance(text, str) or not text or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(answer) or answer[start:end] != text):
        raise ValueError("Validated claim has a non-exact source span")
    return {"text": text, "start": start, "end": end}


def readable_claims(value):
    if not isinstance(value, dict) or not isinstance(value.get("claims"), list):
        return False
    # One malformed row makes the entire array unreadable. Never filter it out.
    return all(isinstance(claim, dict) and isinstance(claim.get("claim_text"), str)
               and bool(claim["claim_text"].strip()) for claim in value["claims"])


def normalize_extraction(row, answer):
    valid = row["status"] == "valid"
    value = row.get("validated_output" if valid else "raw_output")
    readable = readable_claims(value)
    if valid and not readable:
        raise ValueError("Valid record lacks an entirely readable validated claim list")
    if not readable:
        return {"claims": None, "extraction_readable": False, "diagnostic_only": True,
                "provenance_scorable": False}
    claims = []
    for claim in value["claims"]:
        sources = None
        if valid:
            if "source_units" in claim:
                units = claim["source_units"]
                if not isinstance(units, list) or not units or any(not isinstance(unit, dict) for unit in units):
                    raise ValueError("Validated source_units must be a nonempty list of exact source units")
                # The unit list is the only authority here. Do not form an envelope
                # from claim.source_start or infer spans from identifiers.
                sources = [exact_source(answer, unit.get("text"), unit.get("source_start"),
                                        unit.get("source_end")) for unit in units]
            else:
                sources = [exact_source(answer, claim.get("source_span"), claim.get("source_start"),
                                        claim.get("source_end"))]
        # Invalid raw arrays retain every readable claim in its original order.
        # Their source references are not reconstructed or granted provenance credit.
        claims.append({"claim_text": claim["claim_text"], "sources": sources})
    return {"claims": claims, "extraction_readable": True, "diagnostic_only": not valid,
            "provenance_scorable": valid}


def rank(namespace, *parts):
    return digest(canonical([BLIND_SEED, namespace, *parts]))


def packet(records, hashes):
    records = sorted(records, key=lambda row: rank("record-order", row["review_id"]))
    return {
        "schema_version": SCHEMA,
        "review_guidance": deepcopy(GUIDANCE),
        "scoring_schema": deepcopy(SCORING_SCHEMA),
        "integrity": {
            **hashes,
            "record_count": len(records),
            "unique_review_ids": len({row["review_id"] for row in records}),
            "unique_answer_count": len({row["answer"] for row in records}),
            "technical_status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
            "readable_diagnostic_records": sum(row["diagnostic_only"] and row["extraction_readable"] for row in records),
            "unreadable_records": sum(not row["extraction_readable"] for row in records),
            "target_mapping_slots": sum(len(row["expected_facts"]) for row in records),
            "records_sha256_canonical": digest(canonical(records)),
        },
        "records": records,
    }


def write_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encoded(value))


def build(run_dir, output_dir):
    output = Path(output_dir).resolve()
    run = Path(run_dir).resolve()
    if output.exists():
        raise FileExistsError("Review output directory already exists; no overwrite")
    if output.is_relative_to(run):
        raise ValueError("Review output must be outside the sealed run directory")
    rows, cases, hashes = load_completed(run)
    case_order = sorted(cases, key=lambda case_id: rank("case-part", case_id))
    parts = {case_id: 1 if index < 10 else 2 for index, case_id in enumerate(case_order)}
    all_rows, split, private = [], {1: [], 2: []}, {}
    for row in rows:
        ident = identity(row)
        review_id = "r-" + rank("opaque-id", ident)[:24]
        if review_id in private:
            raise ValueError("Opaque review ID collision")
        case = cases[row["case_id"]]
        blind = {
            "review_id": review_id,
            "answer": case["generated_answer"],
            "expected_facts": deepcopy(case["expected_facts"]),
            "expected_pure_nf": case["expected_pure_nf"],
            "status": row["status"],
            "error": None if row["status"] == "valid" else {"code": "technical_invalid"},
            **normalize_extraction(row, case["generated_answer"]),
        }
        private[review_id] = {**ident, "identity_key": row["identity_key"], "part": parts[row["case_id"]],
                              "original_error": deepcopy(row.get("error"))}
        all_rows.append(blind)
        split[parts[row["case_id"]]].append(blind)
    if (len(all_rows), len(split[1]), len(split[2])) != (120, 60, 60):
        raise ValueError("Packet counts differ from the fixed 120/60/60 design")
    packets = {
        "blind-part1.json": packet(split[1], hashes),
        "blind-part2.json": packet(split[2], hashes),
        "blind-all.json": packet(all_rows, hashes),
    }
    # All validation and normalization complete before creating the new directory.
    output.mkdir(parents=True, exist_ok=False)
    for name, value in packets.items():
        write_json(output / name, value)
    write_json(output / "private-key.json", {
        "schema_version": SCHEMA,
        "restricted_to": "coordinating reviewer only; never distribute with blind packets",
        "seed": BLIND_SEED, **hashes,
        "record_count": RECORD_COUNT,
        "mapping": {review_id: private[review_id] for review_id in sorted(private)},
    })
    write_json(output / "packet-manifest.json", {
        "schema_version": SCHEMA, **hashes,
        "qualification": "AI review material only; technical-invalid content diagnostics are never completed semantic results.",
        "packets": {name: {"sha256": sha(output / name), **value["integrity"]}
                    for name, value in packets.items()},
        "private_key_sha256": sha(output / "private-key.json"),
    })
    return {name: value["integrity"] for name, value in packets.items()}


def _fixture_run(root):
    """Invent a complete fake run without opening any project case or prompt."""
    run = root / "fake-run"
    case_path = run / "source" / CASE_REL
    case_path.parent.mkdir(parents=True)
    cases = []
    for number in range(CASE_COUNT):
        answer = f"Object {number} is amber. Please inspect it."
        facts = [{"id": "f1", "description": f"Object {number} is amber.",
                  "source_quote": f"Object {number} is amber.",
                  "required_semantic_elements": [f"Object {number}", "amber"]}]
        cases.append({"id": f"fixture-{number:02}", "generated_answer": answer,
                      "expected_facts": facts, "expected_pure_nf": False})
    write_json(case_path, {"cases": cases})
    write_json(run / "prompts.json", {"fixture_only": "DO_NOT_LEAK_PROMPT"})
    planned = []
    for case_id, arm, repetition in sorted(expected_identities({case["id"]: case for case in cases})):
        request = {"probe": "natural", "case_id": case_id, "arm": arm, "repetition": repetition,
                   "payload": {"secret": "DO_NOT_LEAK_PAYLOAD"}, "task_index": len(planned) // 3,
                   "backend_order_index": len(planned) % 3}
        request["identity_key"] = identity_key(request)
        planned.append(request)
    write_json(run / "planned-requests.json", {"requests": planned})
    freeze = {"schema_version": RUN_SCHEMA, "arms": list(ARMS), "repetitions": REPETITIONS,
              "max_model_calls": RECORD_COUNT, "expected_records": RECORD_COUNT,
              "files_sha256": {CASE_REL: sha(case_path)},
              "prompts_sha256": sha(run / "prompts.json"),
              "planned_requests_sha256": sha(run / "planned-requests.json")}
    write_json(run / "freeze.json", freeze)
    (run / "freeze.sha256").write_text(sha(run / "freeze.json") + "\n", encoding="ascii")
    (run / "reservations").mkdir()
    (run / "responses").mkdir()
    case_map = {case["id"]: case for case in cases}
    rows = []
    for index, request in enumerate(planned):
        answer = case_map[request["case_id"]]["generated_answer"]
        first_end = answer.index(".") + 1
        text = answer[:first_end]
        if index % 3 == 0:
            claim = {"claim_text": text, "source_span": text, "source_start": 0, "source_end": first_end}
        else:
            # Deliberately non-contiguous units, plus an unusable claim-level
            # source_start, prove that the exact list is the only authority.
            subject_end = answer.index(" is")
            predicate_start = answer.index("amber")
            claim = {"claim_text": text, "source_start": -999,
                     "source_units": [{"unit_id": "DO_NOT_LEAK_UNIT_A", "text": answer[:subject_end],
                                       "source_start": 0, "source_end": subject_end},
                                      {"unit_id": "DO_NOT_LEAK_UNIT_B", "text": answer[predicate_start:first_end],
                                       "source_start": predicate_start, "source_end": first_end}]}
        row = {**request, "status": "valid", "error": None,
               "raw_output": {"claims": [deepcopy(claim)]},
               "validated_output": {"claims": [claim], "source_text": "DO_NOT_LEAK_SOURCE_ECHO"},
               "messages": ["DO_NOT_LEAK_MESSAGES"], "usage": "DO_NOT_LEAK_USAGE",
               "telemetry": {"calls": [{"provider": "fixture"}]}}
        if index == 0:
            row.update(status="error", error={"code": "DO_NOT_LEAK_ERROR_FIELD", "message": "DO_NOT_LEAK_ERROR_TEXT"},
                       validated_output=None, raw_output={"claims": [
                           {"claim_text": text, "source_span": text, "source_start": 0, "source_end": first_end},
                           {"claim_text": "Please inspect it.", "claim_id": "DO_NOT_LEAK_ID"}]})
        elif index == 1:
            row.update(status="error", error={"code": "fixture_invalid"}, validated_output=None,
                       raw_output={"claims": [{"claim_text": text}, {"wrong_field": "malformed row"}]})
        elif index == 2:
            row.update(status="error", error={"code": "fixture_empty_invalid"}, validated_output=None,
                       raw_output={"claims": []})
        elif index == 3:
            row.update(status="error", error={"code": "fixture_nonobject"}, validated_output=None,
                       raw_output="not a parsed extraction")
        write_json(run / "reservations" / (request["identity_key"] + ".json"),
                   {"request": request, "freeze_sha256": sha(run / "freeze.json")})
        write_json(run / "responses" / (request["identity_key"] + ".json"), row)
        rows.append(row)
    (run / "responses.jsonl").write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
    (run / "responses.events.jsonl").write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
    counts = Counter(row["status"] for row in rows)
    complete = {"schema_version": RUN_SCHEMA, "status": "complete", "record_count": RECORD_COUNT,
                "expected_records": RECORD_COUNT, "model_calls_started": RECORD_COUNT,
                "unknown_reservations": [], "frozen_artifacts_unchanged": True,
                "valid": counts["valid"], "error": counts["error"],
                "freeze_sha256": sha(run / "freeze.json"), "responses_sha256": sha(run / "responses.jsonl"),
                "event_journal_sha256": sha(run / "responses.events.jsonl"),
                "reservation_files_sha256": {path.name: sha(path) for path in (run / "reservations").glob("*.json")},
                "response_files_sha256": {path.name: sha(path) for path in (run / "responses").glob("*.json")}}
    write_json(run / "run-complete.json", complete)
    # This view is intentionally stale. It is never an authority for review.
    write_json(run / "progress.json", {"status": "running", "record_count": 3})
    return run, rows


def self_test():
    """No project artifacts, actual inference output, or external models are read."""
    checks = []
    with tempfile.TemporaryDirectory(prefix="coverage-review-packets-fixtures-") as temporary:
        root = Path(temporary)
        run, rows = _fixture_run(root)
        first, second = root / "packets-a", root / "packets-b"
        build(run, first)
        build(run, second)
        for path in first.iterdir():
            assert path.read_bytes() == (second / path.name).read_bytes(), "Nondeterministic packet"
        parts = [read_object(first / name) for name in ("blind-part1.json", "blind-part2.json", "blind-all.json")]
        assert [len(part["records"]) for part in parts] == [60, 60, 120]
        assert [len({row["answer"] for row in part["records"]}) for part in parts] == [10, 10, 20]
        assert {row["answer"] for row in parts[0]["records"]}.isdisjoint({row["answer"] for row in parts[1]["records"]})
        keys = read_object(first / "private-key.json")["mapping"]
        by_identity = {value["identity_key"]: key for key, value in keys.items()}
        blind = {row["review_id"]: row for row in parts[2]["records"]}
        for part in parts:
            assert "DO_NOT_LEAK" not in json.dumps(part), "Private field leaked"
            assert part["integrity"]["records_sha256_canonical"] == digest(canonical(part["records"]))
            for row in part["records"]:
                assert set(row) == {"review_id", "answer", "expected_facts", "expected_pure_nf", "status", "error",
                                    "claims", "extraction_readable", "diagnostic_only", "provenance_scorable"}
                for claim in row["claims"] or []:
                    assert set(claim) == {"claim_text", "sources"}
                    for source in claim["sources"] or []:
                        assert set(source) == {"text", "start", "end"}
                        assert row["answer"][source["start"]:source["end"]] == source["text"]
        invalid = blind[by_identity[rows[0]["identity_key"]]]
        assert invalid["extraction_readable"] and invalid["diagnostic_only"] and len(invalid["claims"]) == 2
        assert all(claim["sources"] is None for claim in invalid["claims"])
        assert not invalid["provenance_scorable"]
        assert keys[invalid["review_id"]]["original_error"]["message"] == "DO_NOT_LEAK_ERROR_TEXT"
        malformed = blind[by_identity[rows[1]["identity_key"]]]
        assert malformed["claims"] is None and malformed["extraction_readable"] is False
        empty_invalid = blind[by_identity[rows[2]["identity_key"]]]
        assert empty_invalid["claims"] == [] and empty_invalid["diagnostic_only"] is True
        nonobject = blind[by_identity[rows[3]["identity_key"]]]
        assert nonobject["claims"] is None and nonobject["extraction_readable"] is False
        multi = blind[by_identity[rows[4]["identity_key"]]]
        assert len(multi["claims"][0]["sources"]) == 2
        assert multi["claims"][0]["sources"][0]["end"] < multi["claims"][0]["sources"][1]["start"]
        checks += ["120 identities and 60/60 case-disjoint packets", "determinism and packet hashes",
                   "stale progress ignored", "private metadata isolation", "exact separate source units",
                   "all readable invalid claims retained", "malformed rows not filtered",
                   "invalid empty/nonobject arrays", "original error retained privately"]

        def reject(change, restore, label):
            destination = root / ("rejected-" + str(len(checks)))
            change()
            try:
                build(run, destination)
            except (ValueError, FileNotFoundError):
                assert not destination.exists(), "Rejected run created an output directory"
            else:
                raise AssertionError("Accepted invalid fixture: " + label)
            finally:
                restore()
            checks.append(label)

        seal_path = run / "run-complete.json"
        seal_raw = seal_path.read_bytes()
        seal = read_object(seal_path)
        reject(lambda: seal_path.unlink(), lambda: seal_path.write_bytes(seal_raw), "completion seal required")
        reject(lambda: seal_path.write_bytes(encoded({**seal, "unknown_reservations": ["unknown"]})),
               lambda: seal_path.write_bytes(seal_raw), "unknown reservation rejection")
        reject(lambda: seal_path.write_bytes(encoded({**seal, "status": "running"})),
               lambda: seal_path.write_bytes(seal_raw), "incomplete seal rejection")
        journal = run / "responses.jsonl"
        journal_raw = journal.read_bytes()
        reject(lambda: journal.write_bytes(journal_raw + b" "), lambda: journal.write_bytes(journal_raw),
               "journal hash mismatch rejection")
        source_case = run / "source" / CASE_REL
        source_raw = source_case.read_bytes()
        reject(lambda: source_case.write_bytes(source_raw + b" "), lambda: source_case.write_bytes(source_raw),
               "frozen source hash mismatch rejection")
        response_path = run / "responses" / (rows[0]["identity_key"] + ".json")
        response_raw = response_path.read_bytes()
        reject(lambda: response_path.write_bytes(response_raw + b" "), lambda: response_path.write_bytes(response_raw),
               "durable response hash mismatch rejection")
        reservation_path = run / "reservations" / (rows[0]["identity_key"] + ".json")
        reservation_raw = reservation_path.read_bytes()
        reject(lambda: reservation_path.unlink(), lambda: reservation_path.write_bytes(reservation_raw),
               "missing reservation rejection")

        def duplicate_identity():
            changed = deepcopy(rows)
            changed[-1] = deepcopy(changed[0])
            journal.write_bytes(b"\n".join(canonical(row) for row in changed) + b"\n")
            seal_path.write_bytes(encoded({**seal, "responses_sha256": sha(journal)}))

        def restore_journal():
            journal.write_bytes(journal_raw)
            seal_path.write_bytes(seal_raw)

        reject(duplicate_identity, restore_journal, "duplicate identities rejected despite updated journal seal")
        try:
            build(run, first)
        except FileExistsError:
            checks.append("existing output not overwritten")
        else:
            raise AssertionError("Output overwrite allowed")
        broken = {"status": "valid", "validated_output": {"claims": [{"claim_text": "X", "source_span": "X",
                                                                               "source_start": 0, "source_end": 1}]}}
        try:
            normalize_extraction(broken, "Y")
        except ValueError:
            checks.append("non-exact valid source rejected")
        else:
            raise AssertionError("Invalid validated span accepted")
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            try:
                strict_json(raw)
            except ValueError:
                pass
            else:
                raise AssertionError("Non-strict JSON accepted")
        checks.append("duplicate JSON keys and non-finite values rejected")
    return {"status": "pass", "fixtures_only": True, "model_calls": 0, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if args.run_dir is not None or args.output_dir is not None:
            parser.error("--self-test only uses invented temporary fixtures")
        result = self_test()
    else:
        if args.run_dir is None or args.output_dir is None:
            parser.error("--run-dir and --output-dir are required")
        result = build(args.run_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
