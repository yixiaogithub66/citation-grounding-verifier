"""Build blinded semantic-review packets from a completed, frozen pilot.

This is an offline presentation tool. It never calls a model, assigns semantic
labels, changes expected facts, or edits inference artifacts. Keep this script
and private-key.json with the coordinating reviewer; give each blind reviewer
only their assigned packet. Deterministic obfuscation is procedural blinding,
not a cryptographic guarantee against a reviewer trying to reconstruct the key.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile


SCHEMA = "bidirectional-blind-review-v1"
CASE_REL = "research/bidirectional-selection-20261024/cases.json"
BLIND_SEED = "bidirectional-selection-review-20261024-v1"
NATURAL_ARMS = ("base", "fresh", "generic", "bidirectional")
CONTROLLED_ARMS = ("generic", "bidirectional")


GUIDANCE = {
    "scope": "AI semantic review of synthetic M1 selection only; not author final adjudication.",
    "indices": "claim_indices and claim_index are zero-based indices into validated_output.claims.",
    "technical_gate": (
        "If status is not valid, set semantic_complete to null, all target retained values to null, "
        "and uncertainty to a technical-unscorable explanation. Leave spurious_claims empty as "
        "unscored, never count that empty list as zero false positives. Raw output is diagnostic "
        "only and must not silently replace a failed validated output."
    ),
    "target_mapping": (
        "For each expected fact, map the claim indices that preserve its asserted meaning. "
        "Semantic paraphrases are allowed. Subject, relation, attribution, polarity, necessary "
        "versus sufficient conditions, numeric scope and modality must be retained. Explain "
        "missing or altered elements; do not use word overlap alone as proof."
    ),
    "spurious": (
        "List every claim that asserts content the answer does not assert, including advice "
        "or a question promoted to a fact, unsupported strengthening, lost attribution/scope, "
        "or new invented content. A list of expected facts is not a whitelist that excuses "
        "other invented assertions. Do not automatically classify all conditional statements "
        "as non-factual; asserted conditional rules remain facts."
    ),
    "completeness": (
        "For technically valid output, semantic_complete is true only if every expected fact "
        "is retained and no spurious asserted claim remains. Pure NF answers require no "
        "asserted fact. For technical failure semantic_complete is null, not false or true."
    ),
    "scoped_assumption_only": (
        "Flag true if the apparent extra assertions are exclusively explicitly scoped "
        "fictional assumptions rather than statements about actual conditions. Explain the "
        "scope in uncertainty. Keep their status visible for coordinator adjudication; do "
        "not silently redefine the expected labels. Otherwise use false."
    ),
    "blindness": (
        "Do not inspect private-key.json, original responses, prompts, draft inputs, usage "
        "or this generator while reviewing. The packet order and review IDs do not encode "
        "a meaningful rank. Repeated answers are expected; judge each output independently."
    ),
    "output": "Return one review object for every review_id, using the supplied scoring schema.",
}


SCORING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["review_id", "target_mappings", "spurious_claims", "semantic_complete",
                 "scoped_assumption_only", "uncertainty"],
    "properties": {
        "review_id": {"type": "string"},
        "target_mappings": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["fact_id", "claim_indices", "retained", "reason"],
                "properties": {
                    "fact_id": {"type": "string"},
                    "claim_indices": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "retained": {"type": ["boolean", "null"]},
                    "reason": {"type": "string"},
                },
            },
        },
        "spurious_claims": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["claim_index", "type", "reason"],
                "properties": {
                    "claim_index": {"type": "integer", "minimum": 0},
                    "type": {"type": "string", "enum": ["advice_as_fact", "question_as_fact",
                              "hypothesis_scope_lost", "attribution_lost", "semantic_strengthening",
                              "invented_content", "other"]},
                    "reason": {"type": "string"},
                },
            },
        },
        "semantic_complete": {"type": ["boolean", "null"]},
        "scoped_assumption_only": {"type": "boolean"},
        "uncertainty": {"type": ["string", "null"]},
    },
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
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
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("Non-finite JSON value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def read_json(path):
    return strict_json(Path(path).read_text(encoding="utf-8"))


def rank(namespace, *parts):
    return digest(canonical([BLIND_SEED, namespace, *parts]))


def expected_identities(cases, seeds):
    result = {("natural", row["id"], arm, repetition)
              for row in cases for arm in NATURAL_ARMS for repetition in range(2)}
    result |= {("controlled", row["seed_id"], arm, 0)
               for row in seeds for arm in CONTROLLED_ARMS}
    return result


def load_completed(responses):
    responses = Path(responses).resolve()
    run = responses.parent
    if responses.name != "responses.jsonl":
        raise ValueError("Expected the completed run's responses.jsonl")
    progress = read_json(run / "progress.json")
    if progress.get("status") != "complete" or progress.get("record_count") != 152:
        raise ValueError("The 152-record pilot is not complete")
    if progress.get("frozen_artifacts_unchanged") is not True:
        raise ValueError("The run did not confirm unchanged frozen artifacts")
    if sha(responses) != progress.get("responses_sha256"):
        raise ValueError("Completed response journal hash mismatch")
    freeze_path = run / "freeze.json"
    if sha(freeze_path) != (run / "freeze.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Frozen manifest hash mismatch")
    frozen = read_json(freeze_path)
    source = (run / "source").resolve()
    files = frozen.get("files_sha256", {})
    if CASE_REL not in files or frozen.get("expected_journal_records") != 152:
        raise ValueError("Frozen pilot does not bind the expected cases and size")
    for name, expected in files.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or sha(path) != expected:
            raise ValueError("Frozen artifact hash mismatch: " + name)
    if sha(run / "prompts.json") != frozen.get("prompts_sha256"):
        raise ValueError("Frozen prompt bundle hash mismatch")
    case_data = read_json(source / CASE_REL)
    cases, seeds = case_data.get("cases", []), case_data.get("controlled_seeds", [])
    if len(cases) != 16 or len(seeds) != 12:
        raise ValueError("Expected 16 natural cases and 12 controlled seeds")
    case_map = {row["id"]: row for row in cases}
    seed_map = {row["seed_id"]: row for row in seeds}
    if len(case_map) != 16 or len(seed_map) != 12:
        raise ValueError("Duplicate source case or seed ID")
    if any(row["case_id"] not in case_map for row in seeds):
        raise ValueError("Controlled seed has no natural source case")
    rows = [strict_json(line) for line in responses.read_text(encoding="utf-8").splitlines() if line.strip()]
    identities = [(r["probe"], r["case_id"], r["arm"], r["repetition"]) for r in rows]
    if len(rows) != 152 or len(set(identities)) != 152 or set(identities) != expected_identities(cases, seeds):
        raise ValueError("Response identities are incomplete, duplicated or unexpected")
    for row in rows:
        if row.get("status") not in {"valid", "error"}:
            raise ValueError("Unexpected technical status")
        valid = row.get("validated_output")
        if row["status"] == "valid" and (
            not isinstance(valid, dict) or not isinstance(valid.get("claims"), list)
            or not isinstance(valid.get("non_factual_spans"), list)
        ):
            raise ValueError("Valid record is missing validated extraction arrays")
    return rows, case_map, seed_map, {
        "responses_sha256": sha(responses), "freeze_sha256": sha(freeze_path),
        "frozen_cases_sha256": files[CASE_REL],
    }


def extraction_arrays(value):
    # Retain raw claim/NF arrays even when their contents are structurally invalid.
    # Other raw JSON keys and any unparsed provider text stay in the original
    # private journal, never silently become the output being scored.
    if not isinstance(value, dict):
        return None
    return {key: deepcopy(value.get(key)) for key in ("claims", "non_factual_spans")}


def packet(rows, source_hashes):
    rows = sorted(rows, key=lambda row: rank("packet-order", row["review_id"]))
    return {
        "schema_version": SCHEMA,
        "review_guidance": deepcopy(GUIDANCE),
        "scoring_schema": deepcopy(SCORING_SCHEMA),
        "integrity": {
            **source_hashes,
            "record_count": len(rows),
            "unique_review_ids": len({row["review_id"] for row in rows}),
            "unique_answer_count": len({digest(canonical(row["generated_answer"])) for row in rows}),
            "technical_status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
            "target_mapping_slots": sum(len(row["expected_facts"]) for row in rows),
            "pure_nf_records": sum(row["expected_pure_nf"] for row in rows),
            "records_sha256_canonical": digest(canonical(rows)),
        },
        "records": rows,
    }


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8", errors="backslashreplace")
    with Path(path).open("xb") as stream:
        stream.write(raw)


def build(responses, output_dir):
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError("Review output directory already exists; no overwrite")
    rows, cases, seeds, hashes = load_completed(responses)
    ordered_cases = sorted(cases, key=lambda cid: rank("case-part", cid))
    parts = {cid: 1 if index < 8 else 2 for index, cid in enumerate(ordered_cases)}
    natural, controlled, split = [], [], {1: [], 2: []}
    private = {}
    for row in rows:
        identity = (row["probe"], row["case_id"], row["arm"], row["repetition"])
        review_id = "r-" + rank("opaque-id", *identity)[:24]
        if review_id in private:
            raise ValueError("Opaque review ID collision")
        seed = seeds[row["case_id"]] if row["probe"] == "controlled" else None
        origin = seed["case_id"] if seed else row["case_id"]
        case = cases[origin]
        blind = {
            "review_id": review_id,
            "generated_answer": case["generated_answer"],
            "expected_facts": deepcopy(case["expected_facts"]),
            "expected_pure_nf": case["expected_pure_nf"],
            "status": row["status"],
            "error": deepcopy(row.get("error")),
            "raw_output": extraction_arrays(row.get("raw_output")),
            "validated_output": extraction_arrays(row.get("validated_output")) if row["status"] == "valid" else None,
        }
        private[review_id] = {
            "probe": row["probe"], "case_id": row["case_id"], "arm": row["arm"],
            "repetition": row["repetition"], "origin_case_id": origin,
            "natural_part": parts[origin] if not seed else None,
        }
        if seed:
            blind["expected_missing_fact_ids"] = deepcopy(seed["expected_missing_fact_ids"])
            blind["injected_fault_kind"] = seed["kind"]
            controlled.append(blind)
        else:
            natural.append(blind)
            split[parts[origin]].append(blind)
    if (len(natural), len(controlled), len(split[1]), len(split[2])) != (128, 24, 64, 64):
        raise ValueError("Blinded packet sizes do not match the fixed experiment")
    packets = {
        "blind-natural.json": packet(natural, hashes),
        "blind-controlled.json": packet(controlled, hashes),
        "natural-part1.json": packet(split[1], hashes),
        "natural-part2.json": packet(split[2], hashes),
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in packets.items():
        write_json(output / name, value)
    write_json(output / "private-key.json", {
        "schema_version": SCHEMA, "restricted_to": "coordinating reviewer only",
        "seed": BLIND_SEED, **hashes, "record_count": 152,
        "mapping": {key: private[key] for key in sorted(private)},
    })
    manifest = {"schema_version": SCHEMA, **hashes, "packets": {
        name: {"sha256": sha(output / name), **value["integrity"]}
        for name, value in packets.items()
    }}
    write_json(output / "packet-manifest.json", manifest)
    return {name: value["integrity"] for name, value in packets.items()}


def self_test():
    """Exercise packet construction solely with invented shape fixtures."""
    with tempfile.TemporaryDirectory(prefix="tabby-blind-packets-test-") as tmp:
        root = Path(tmp)
        run = root / "fake-run"
        frozen_cases = run / "source" / CASE_REL
        frozen_cases.parent.mkdir(parents=True)
        cases = [{"id": f"fixture-{i:02}", "generated_answer": f"Synthetic instruction {i}.",
                  "expected_facts": [], "expected_pure_nf": True} for i in range(16)]
        seeds = [{"seed_id": f"injection-{i:02}", "case_id": cases[i]["id"],
                  "kind": ("omission", "spurious", "clean")[i // 4],
                  "expected_missing_fact_ids": [], "draft": {}} for i in range(12)]
        write_json(frozen_cases, {"cases": cases, "controlled_seeds": seeds})
        write_json(run / "prompts.json", {"fixture_only": "Not a model prompt."})
        freeze = {"files_sha256": {CASE_REL: sha(frozen_cases)}, "expected_journal_records": 152,
                  "prompts_sha256": sha(run / "prompts.json")}
        write_json(run / "freeze.json", freeze)
        (run / "freeze.sha256").write_text(sha(run / "freeze.json") + "\n", encoding="ascii")
        records = []
        for index, (probe, cid, arm, repetition) in enumerate(sorted(expected_identities(cases, seeds))):
            records.append({"probe": probe, "case_id": cid, "arm": arm, "repetition": repetition,
                            "messages": ["DO_NOT_LEAK_PROMPT"], "usage": "DO_NOT_LEAK_USAGE",
                            "draft": "DO_NOT_LEAK_DRAFT", "backend_order_index": 9,
                            "status": "valid" if index else "error",
                            "error": None if index else {"code": "fixture_invalid", "message": "Synthetic failure"},
                            "raw_output": {"claims": [], "non_factual_spans": [], "private_hint": "DO_NOT_LEAK_RAW_EXTRA"},
                            "validated_output": {"claims": [], "non_factual_spans": []}})
        responses = run / "responses.jsonl"
        responses.write_bytes(b"\n".join(canonical(r) for r in records) + b"\n")
        progress = {"status": "complete", "record_count": 152, "frozen_artifacts_unchanged": True,
                    "responses_sha256": sha(responses)}
        write_json(run / "progress.json", progress)
        first, second = root / "packets-a", root / "packets-b"
        build(responses, first)
        build(responses, second)
        for path in first.iterdir():
            assert path.read_bytes() == (second / path.name).read_bytes(), "Not deterministic"
        natural = read_json(first / "blind-natural.json")
        controlled = read_json(first / "blind-controlled.json")
        part1 = read_json(first / "natural-part1.json")
        part2 = read_json(first / "natural-part2.json")
        assert [len(p["records"]) for p in (natural, controlled, part1, part2)] == [128, 24, 64, 64]
        assert {r["generated_answer"] for r in part1["records"]}.isdisjoint(
            {r["generated_answer"] for r in part2["records"]})
        for pack in (natural, controlled, part1, part2):
            assert digest(canonical(pack["records"])) == pack["integrity"]["records_sha256_canonical"]
            assert "DO_NOT_LEAK" not in json.dumps(pack)
            for row in pack["records"]:
                assert not ({"arm", "prompt", "messages", "draft", "usage", "repetition", "order", "case_id"} & row.keys())
                if row["status"] != "valid":
                    assert row["validated_output"] is None
        try:
            build(responses, first)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Overwrite was allowed")
        progress["status"] = "running"
        (run / "progress.json").write_bytes(canonical(progress))
        try:
            build(responses, root / "must-not-exist")
        except ValueError:
            assert not (root / "must-not-exist").exists()
        else:
            raise AssertionError("Incomplete journal was allowed")
    return {"status": "pass", "fixtures_only": True,
            "checks": ["152 identities", "four packet counts", "case-disjoint 8+8 split",
                       "determinism", "hashes", "metadata isolation", "invalid output gating",
                       "no overwrite", "incomplete journal rejection"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if args.responses or args.output_dir:
            parser.error("--self-test cannot read a real journal or write review packets")
        result = self_test()
    else:
        if args.responses is None or args.output_dir is None:
            parser.error("--responses and --output-dir are required")
        result = build(args.responses, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
