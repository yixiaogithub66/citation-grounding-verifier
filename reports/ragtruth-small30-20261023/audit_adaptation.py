#!/usr/bin/env python3
"""Read-only mechanical audit of a prepared, frozen exploratory RAGTruth slice.

Run only after preselection freeze and preparation have completed. No text,
answer, question, prompt, native label or model prediction is printed. The only
optional write is a new JSON audit result; inference and data remain untouched.
This is an adaptation/selection check, not a semantic assessment.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected audit metadata object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def same_json(left, right) -> bool:
    """JSON equality with bool/int and null types distinguished."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def rank(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def audit(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    pre_path, binding_path = run_dir / "preselection.json", run_dir / "binding.json"
    require(pre_path.is_file() and binding_path.is_file(), "Freeze and preparation must both exist")
    require(sha(pre_path) == (run_dir / "preselection.sha256").read_text().strip(), "Preselection hash differs")
    require(sha(binding_path) == (run_dir / "binding.sha256").read_text().strip(), "Binding hash differs")
    frozen, binding = read_object(pre_path), read_object(binding_path)
    require(frozen["schema_version"] == "ragtruth-exploratory-small30-v1", "Unexpected evaluation scope")
    require(binding["preselection_sha256"] == sha(pre_path), "Binding references another freeze")
    require(sha(run_dir / "exposure-audit.json") == frozen["exposure_audit_sha256"], "Exposure snapshot differs")
    require(sha(run_dir / "PLAN.md") == frozen["plan_sha256"], "Plan snapshot differs")
    source_root = (run_dir / "source").resolve()
    for name, expected in frozen["code_files_sha256"].items():
        path = (source_root / name).resolve()
        require(path.is_relative_to(source_root) and sha(path) == expected, "Frozen code hash differs")
    require("scripts/ragtruth_data.py" in frozen["code_files_sha256"], "Adapter absent from freeze")
    require("scripts/ragtruth_small30.py" in frozen["code_files_sha256"], "Sampler absent from freeze")
    data_dir = run_dir / "data"
    require(set(binding["data_files_sha256"]) == {"inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json"}, "Unexpected prepared file set")
    for name, expected in binding["data_files_sha256"].items():
        require(sha(data_dir / name) == expected, "Prepared data hash differs")

    exposure = read_object(run_dir / "exposure-audit.json")
    require(exposure["schema_version"] == "ragtruth-small30-exposure-audit-v1", "Unexpected exposure audit")
    for path, expected in exposure["evidence_files_sha256"].items():
        require(sha(Path(path)) == expected, "Prior exposure evidence changed")
    excluded = set(exposure["excluded_source_ids"])
    policy = frozen["sampling"]
    require(len(excluded) == 33 and excluded == set(policy["excluded_source_ids"]), "Known-source exclusion set differs")
    require(set(policy["tasks"]) == {"QA", "Summary", "Data2txt"}, "Unexpected task policy")
    require(policy["sources_per_task"] == 10 and policy["responses_per_source"] == 1, "Unexpected sample size policy")
    require(policy["split"] == "test" and policy["quality"] == "good", "Unexpected eligibility policy")
    require(policy["labels_or_generator_used_for_selection"] is False, "Selection must be label and generator blind")
    require(exposure["not_certified_untouched"] is True, "Unresolved exposure limitation lost")
    raw_dir = Path(frozen["raw_dir"])
    require(frozen["upstream_raw_sha256"] == exposure["upstream_raw_sha256"], "Raw provenance differs")
    for name, expected in frozen["upstream_raw_sha256"].items():
        require(sha(raw_dir / name) == expected, "Raw file hash differs")

    # A fresh process imports only the already hash-checked frozen adapter.
    require("scripts.ragtruth_data" not in sys.modules, "Run audit in a fresh process")
    sys.path.insert(0, str(source_root))
    from scripts import ragtruth_data as adapter
    require(Path(adapter.__file__).resolve() == source_root / "scripts/ragtruth_data.py", "Wrong adapter imported")
    sources = adapter.load_jsonl(raw_dir / "source_info.jsonl")
    responses = adapter.load_jsonl(raw_dir / "response.jsonl")
    sources_by_id = {row["source_id"]: row for row in sources}
    responses_by_id = {row["id"]: row for row in responses}
    require(len(sources_by_id) == len(sources), "Duplicate upstream source")
    require(len(responses_by_id) == len(responses), "Duplicate upstream response")
    groups, splits = defaultdict(list), defaultdict(set)
    for row in responses:
        require(row["source_id"] in sources_by_id, "Broken source join")
        groups[row["source_id"]].append(row)
        splits[row["source_id"]].add(row["split"])
    require(all(len(items) == 1 for items in splits.values()), "Source crosses splits")

    # Reconstruct the frozen hash policy independently of sampler implementation.
    # No labels, generator, model output or result metric is consulted here.
    expected_selection, expected_exclusions = [], []
    for task in policy["tasks"]:
        candidates = [sid for sid in groups if splits[sid] == {policy["split"]}
                      and sources_by_id[sid]["task_type"] == task and sid not in excluded]
        candidates.sort(key=lambda sid: (rank(policy["seed"], task, sid), sid))
        kept = 0
        for sid in candidates:
            good = [row for row in groups[sid] if row["quality"] == policy["quality"]]
            if not good:
                expected_exclusions.append({"source_id": sid, "task_type": task, "reason": "no_good_response"})
                continue
            contexts, mapping = adapter._adapt_source(sources_by_id[sid])
            failures = []
            for row in good:
                failure, _ = adapter._preflight({"context_passages": contexts, "generated_answer": row["response"]})
                if failure:
                    failures.append({"id": row["id"], "reason": failure})
            if failures:
                expected_exclusions.append({"source_id": sid, "task_type": task,
                                            "reason": "source_group_input_limit", "failures": failures})
                continue
            chosen = min(good, key=lambda row: (rank(policy["seed"], "response", sid, row["id"]), row["id"]))
            expected_selection.append((sid, chosen["id"], task))
            kept += 1
            if kept == policy["sources_per_task"]:
                break
        require(kept == 10, "Insufficient eligible source groups")

    inputs = adapter.load_jsonl(data_dir / "inputs.jsonl")
    manifest = adapter.load_jsonl(data_dir / "manifest.jsonl")
    gold = adapter.load_jsonl(data_dir / "native_gold.jsonl")
    preparation = read_object(data_dir / "preparation.json")
    require(len(inputs) == len(manifest) == len(gold) == 30, "Prepared record count differs")
    require(len({row["id"] for row in inputs}) == len({row["source_id"] for row in manifest}) == 30, "Response or source reused")
    require(Counter(row["task_type"] for row in manifest) == {task: 10 for task in policy["tasks"]}, "Task allocation differs")
    require(not ({row["source_id"] for row in manifest} & excluded), "Known exposed source included")
    actual_selection = [(row["source_id"], row["id"], row["task_type"]) for row in manifest]
    require(actual_selection == expected_selection, "Selection differs from frozen hash ranks")
    require(same_json(preparation["eligibility_exclusions"], expected_exclusions), "Eligibility exclusion log differs")
    require(same_json(preparation["sampling"], policy), "Preparation policy differs")
    require(same_json(preparation["selection"], binding["selection"]), "Selection binding differs")
    gold_by_id = {row["id"]: row for row in gold}
    require(len(gold_by_id) == 30, "Duplicate gold identity")
    typed_value_counts = Counter()

    def count_types(value):
        if value is None:
            typed_value_counts["null"] += 1
        elif type(value) is bool:
            typed_value_counts["boolean"] += 1
        elif isinstance(value, dict):
            for item in value.values():
                count_types(item)
        elif isinstance(value, list):
            for item in value:
                count_types(item)

    for case, meta in zip(inputs, manifest):
        require(set(case) == {"id", "input"}, "Unexpected prepared case fields")
        require(case["id"] == meta["id"], "Input manifest ordering differs")
        request = case["input"]
        require(set(request) == {"context_passages", "generated_answer"}, "Non-contract field leaked to request")
        row = responses_by_id[case["id"]]
        source = sources_by_id[meta["source_id"]]
        require(row["source_id"] == meta["source_id"], "Selected response source differs")
        contexts, mapping = adapter._adapt_source(source)
        expected_request = {"context_passages": contexts, "generated_answer": row["response"]}
        require(same_json(request, expected_request), "Adapted request differs from original")
        require(adapter.canonical_input_bytes(request) == adapter.canonical_input_bytes(expected_request), "Canonical request bytes differ")
        require(request["generated_answer"].encode("utf-8") == row["response"].encode("utf-8"), "Generated answer was changed")
        require(adapter.input_sha256(request) == meta["input_sha256"], "Input hash differs")
        require(same_json(mapping, meta["adapter"]), "Adaptation provenance differs")
        require(meta["source_sample_key"] == rank(policy["seed"], source["task_type"], meta["source_id"]), "Source hash key differs")
        require(meta["response_sample_key"] == rank(policy["seed"], "response", meta["source_id"], row["id"]), "Response hash key differs")
        failure, sizes = adapter._preflight(request)
        require(failure is None and same_json(sizes, meta["request_size"]), "Request preflight differs")
        require(mapping["labels_used_as_evidence"] is False and mapping["prompt_used_as_evidence"] is False, "Evidence boundary differs")
        if source["task_type"] == "QA":
            original = source["source_info"]["passages"]
            require("".join(contexts) == original, "QA passages lose or add characters")
            offsets = mapping["passage_offsets"]
            require(len(offsets) == len(contexts), "QA offset count differs")
            cursor = 0
            for text, span in zip(contexts, offsets):
                require(span["start"] == cursor and original[span["start"]:span["end"]] == text, "QA slice differs")
                cursor = span["end"]
            require(cursor == len(original) and mapping["question_included"] is False, "QA boundary or question omission differs")
        elif source["task_type"] == "Summary":
            require(contexts == [source["source_info"]], "Summary evidence changed")
        else:
            require(len(contexts) == 1 and same_json(json.loads(contexts[0]), source["source_info"]), "Structured evidence values or types changed")
            count_types(source["source_info"])
        original_labels = adapter._validate_labels(row)
        require(same_json(gold_by_id[row["id"]], {"id": row["id"], "source_id": row["source_id"],
                    "labels": original_labels, "has_hallucination": bool(original_labels)}), "Native gold was changed")

    return {"schema_version": "ragtruth-small30-adaptation-audit-v1", "status": "pass",
        "created_at": datetime.now(timezone.utc).isoformat(), "audit_script_sha256": sha(Path(__file__)),
        "run_dir": str(run_dir), "preselection_sha256": sha(pre_path), "binding_sha256": sha(binding_path),
        "raw_files_sha256": frozen["upstream_raw_sha256"], "prepared_files_sha256": binding["data_files_sha256"],
        "frozen_adapter_sha256": frozen["code_files_sha256"]["scripts/ragtruth_data.py"],
        "frozen_sampler_sha256": frozen["code_files_sha256"]["scripts/ragtruth_small30.py"],
        "counts": {"responses": 30, "unique_sources": 30, "per_task": dict(Counter(row["task_type"] for row in manifest)),
                   "known_excluded_sources": len(excluded), "overlap": 0, "eligibility_exclusions": len(expected_exclusions),
                   "structured_null_values": typed_value_counts["null"], "structured_boolean_values": typed_value_counts["boolean"]},
        "checks": {"independent_hash_selection": True, "frozen_adapter_reconstruction": True,
                   "answers_unchanged_utf8": True, "qa_exact_contiguous_slices": True, "qa_question_not_added": True,
                   "summary_exact": True, "structured_json_types_preserved": True, "native_annotations_preserved": True,
                   "request_has_only_contract_fields": True, "no_prompt_or_gold_added_to_evidence": True},
        "not_certified_untouched": True, "semantic_accuracy_evaluated": False,
        "qualification": "Mechanical selection/adaptation integrity only; unresolved literature exposure remains. No comparison of model verdicts or semantic correctness."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.run_dir)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        print(rendered, end="")
        return 0
    except Exception as exc:
        # Error values may originate in data; disclose type only, never raw text.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "data_text_printed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
