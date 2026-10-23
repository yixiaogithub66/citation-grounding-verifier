#!/usr/bin/env python3
"""Independent, read-only accounting audit of the fixed thirty comparator run.

Uses the frozen public contract validator, but recomputes detection counts,
cost accounting and exact citations without calling the experiment scorer.
No semantic adjudication, model call, dataset or prediction mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys

BACKENDS = ("baseline", "minimal", "optimized-v4.0")
COUNTS = ("tp", "fp", "tn", "fn", "unknown_positive", "unknown_negative")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Non-finite JSON: " + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def obj(path):
    return parse(Path(path).read_text(encoding="utf-8-sig"))


def rows(path):
    return [parse(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, name):
    if isinstance(actual, float) or isinstance(expected, float):
        require(actual is not None and expected is not None and math.isclose(actual, expected, abs_tol=1e-12), name)
    else:
        require(actual == expected, name)


def fraction_check(actual, numerator, denominator, name):
    equal(actual["numerator"], numerator, name + " numerator")
    equal(actual["denominator"], denominator, name + " denominator")
    equal(actual["value"], numerator / denominator if denominator else None, name + " value")


def numeric(value):
    return type(value) is int and value >= 0


def runtime(records, prices):
    calls = [call for record in records for call in record.get("telemetry", {}).get("calls", [])]
    prompt = completion = hit_total = miss_total = with_usage = with_cache = 0
    known_cost = all_miss = 0.0
    for call in calls:
        usage = call.get("usage") or {}
        p, c = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not numeric(p) or not numeric(c):
            continue
        with_usage += 1
        prompt += p
        completion += c
        all_miss += (p * prices["input_per_million"] + c * prices["output_per_million"]) / 1e6
        details = usage.get("prompt_tokens_details") or {}
        hit = usage.get("prompt_cache_hit_tokens", details.get("cached_tokens"))
        miss = usage.get("prompt_cache_miss_tokens")
        if not numeric(hit) and numeric(miss) and miss <= p:
            hit = p - miss
        if not numeric(miss) and numeric(hit) and hit <= p:
            miss = p - hit
        if not numeric(hit) or not numeric(miss) or hit + miss != p:
            continue
        with_cache += 1
        hit_total += hit
        miss_total += miss
        known_cost += (miss * prices["input_per_million"] + hit * prices["cached_input_per_million"] + c * prices["output_per_million"]) / 1e6
    times = sorted(r["latency_seconds"] for r in records)
    return {"calls": len(calls), "calls_missing_usage": len(calls) - with_usage,
            "calls_missing_cache_accounting": len(calls) - with_cache,
            "prompt_tokens": prompt, "completion_tokens": completion,
            "prompt_cache_hit_tokens": hit_total, "prompt_cache_miss_tokens": miss_total,
            "known_usage_subtotal": known_cost, "unpriced_calls": len(calls) - with_cache,
            "estimated_total": known_cost if with_cache == len(calls) else None,
            "cache_standardized_all_miss_known_subtotal": all_miss,
            "mean_latency_seconds": sum(times) / len(times),
            "p95_latency_seconds": times[math.ceil(.95 * len(times)) - 1],
            "returned_models": dict(Counter(str(c.get("model")) for c in calls)),
            "returned_system_fingerprints": dict(Counter(str(c.get("system_fingerprint")) for c in calls))}


def check_summary(observations, scored, label):
    counts = Counter({key: 0 for key in COUNTS})
    statuses = Counter()
    for row in observations:
        counts[row["confusion_key"]] += 1
        statuses[row["status"]] += 1
    equal(dict(counts), scored["confusion"], label + " confusion")
    equal(dict(statuses), scored["status_counts"], label + " status")
    equal(len(observations), scored["total_count"], label + " total")
    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    resolved = tp + fp + tn + fn
    for key, n, d in (("accuracy", tp + tn, resolved), ("precision", tp, tp + fp),
                      ("recall", tp, tp + fn), ("f1", 2 * tp, 2 * tp + fp + fn)):
        fraction_check(scored["resolved_only"][key], n, d, label + " " + key)
    fraction_check(scored["correct_decisions_per_all_cases"], tp + tn, len(observations), label + " all-case correctness")
    fraction_check(scored["decision_coverage"], resolved, len(observations), label + " decision coverage")
    fraction_check(scored["complete_case_rate"], statuses["complete"], len(observations), label + " complete rate")
    completed = sum(r["completed_claims"] for r in observations)
    failed = sum(r["failed_claims"] for r in observations)
    equal(completed, scored["completed_claim_count"], label + " completed claims")
    equal(failed, scored["known_failed_claim_count"], label + " failed claims")
    equal(sum(r["unknown_claim_total"] for r in observations), scored["unknown_claim_total_case_count"], label + " unknown claim totals")
    fraction_check(scored["claim_completion_known_cases"], completed, completed + failed, label + " output claim completion")
    return {"confusion": dict(counts), "statuses": dict(statuses), "completed_claims": completed,
            "known_failed_claims": failed, "unknown_claim_total_cases": sum(r["unknown_claim_total"] for r in observations)}


def audit(run, workspace):
    freeze = obj(run / "freeze.json")
    equal(sha(run / "freeze.json"), (run / "freeze.sha256").read_text().strip(), "comparator freeze digest")
    source_run = Path(freeze["source_run"])
    original = obj(source_run / "preselection.json")
    equal(sha(source_run / "preselection.json"), (source_run / "preselection.sha256").read_text().strip(), "original freeze digest")
    equal(sha(source_run / "binding.json"), (source_run / "binding.sha256").read_text().strip(), "original binding digest")
    for name, digest in freeze["origin_files_sha256"].items():
        equal(sha(source_run / name), digest, "original artifact " + name)
    for name, digest in freeze["wrapper_files_sha256"].items():
        equal(sha(run / name), digest, "comparator wrapper " + name)
    equal(freeze["original_code_files_sha256"], original["code_files_sha256"], "source manifest equality")
    production_count = 0
    for name, digest in original["code_files_sha256"].items():
        equal(sha(source_run / "source" / name), digest, "original source " + name)
        if name.startswith("grounding/"):
            equal(sha(workspace / name), digest, "unchanged production " + name)
            production_count += 1
    equal(freeze["settings"], original["settings"], "settings unchanged")
    progress = obj(run / "progress.json")
    require(progress["status"] == "completed" and progress["completed_records"] == 60 and progress["frozen_artifacts_unchanged"] is True, "incomplete comparator run")
    require(progress["gold_loaded"] is False, "gold parsed during inference")
    source = (source_run / "source").resolve()
    sys.path.insert(0, str(source))
    validator = importlib.import_module("grounding.contracts_v4").validate_v4_report
    for name, module in list(sys.modules.items()):
        if name in ("grounding", "scripts") or name.startswith(("grounding.", "scripts.")):
            path = Path(module.__file__).resolve()
            require(path.is_relative_to(source), "nonfrozen audit project import " + name)
            equal(sha(path), original["code_files_sha256"][path.relative_to(source).as_posix()], "audit import digest " + name)
    inputs = {r["id"]: r for r in rows(source_run / "data/inputs.jsonl")}
    metas = {r["id"]: r for r in rows(source_run / "data/manifest.jsonl")}
    gold = {r["id"]: r for r in rows(source_run / "data/native_gold.jsonl")}
    require(len(inputs) == len(metas) == len(gold) == 30 and set(inputs) == set(metas) == set(gold), "data joins")
    new = rows(run / "predictions.jsonl")
    old = rows(source_run / "predictions.jsonl")
    require(len(new) == 60 and len(old) == 30, "record count")
    records = new + old
    equal(progress["error_records"], sum(r.get("error") is not None for r in new), "progress error count")
    for backend in BACKENDS[:2]:
        selected_new = [r for r in new if r["backend"] == backend]
        equal(progress["by_backend"][backend]["completed_records"], len(selected_new), backend + " progress records")
        equal(progress["by_backend"][backend]["error_records"], sum(r.get("error") is not None for r in selected_new), backend + " progress errors")
    pairs = [(r["id"], r["backend"]) for r in records]
    require(len(set(pairs)) == 90 and set(pairs) == {(i, b) for i in inputs for b in BACKENDS}, "duplicate or absent id/backend")
    require(all(r["backend"] in BACKENDS[:2] for r in new) and all(r["backend"] == BACKENDS[2] for r in old), "journal backend separation")
    observations, citation_counts = [], Counter()
    for record in records:
        identifier, backend = record["id"], record["backend"]
        request, meta = inputs[identifier]["input"], metas[identifier]
        equal(set(request), {"context_passages", "generated_answer"}, "model input fields")
        request_bytes = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        equal(hashlib.sha256(request_bytes).hexdigest(), meta["input_sha256"], "request digest")
        for field in ("source_id", "task_type", "generator", "input_sha256"):
            equal(record[field], meta[field], identifier + " metadata " + field)
        require(isinstance(gold[identifier]["labels"], list), "native labels must be a list")
        truth = bool(gold[identifier]["labels"])
        prediction = record.get("prediction")
        calls = record.get("telemetry", {}).get("calls", [])
        if backend == "baseline":
            equal(len(calls), 0, "baseline model calls")
        elif backend == "minimal":
            equal(len(calls), 1 if request["generated_answer"].strip() else 0, "minimal single call including failures")
            require(all(c["stage"] == "minimal" and c["attempt"] == 1 for c in calls), "minimal retries or wrong stage")
            require(not record.get("telemetry", {}).get("repairs"), "minimal repair attempts")
            equal(record.get("telemetry", {}).get("prompts"), freeze["backend_execution"]["minimal"]["prompts"], "minimal prompt metadata")
        if record.get("error") is not None:
            require(prediction is None and record["schema_valid"] is False, "error exposed public prediction")
            # Existing comparators cannot certify a failed extraction total.
            require(backend != "optimized-v4.0" and not record.get("telemetry", {}).get("completion"), "unexpected error telemetry requires explicit audit")
            status, decision, completed, failed, unknown = "error", None, 0, 0, True
        else:
            require(record["schema_valid"] is True and not record["validation_errors"], "successful schema flags")
            validator(prediction, request["context_passages"])
            partial = prediction.get("status") == "partial"
            status = "partial" if partial else "complete"
            detected = any(c["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for c in prediction["claims"])
            decision = True if detected else None if partial else False
            completed, failed, unknown = len(prediction["claims"]), len(prediction.get("errors", [])), False
            per_record_citations = 0
            for claim in prediction["claims"]:
                for citation in claim["citations"]:
                    per_record_citations += 1
                    context = request["context_passages"][citation["index"]]
                    require(citation["quote"] in context, "nonexact public citation")
                    if "start_char" in citation or "end_char" in citation:
                        require(context[citation["start_char"]:citation["end_char"]] == citation["quote"], "incorrect quote offsets")
            equal(record["citations"], {"citation_count": per_record_citations, "valid_citation_count": per_record_citations}, "citation telemetry")
            citation_counts[backend] += per_record_citations
        confusion = ("unknown_positive" if truth else "unknown_negative") if decision is None else ("tp" if truth else "fp") if decision else ("fn" if truth else "tn")
        observations.append({"id": identifier, "backend": backend, "task": meta["task_type"], "confusion_key": confusion,
            "status": status, "y_true": truth, "y_pred": decision, "completed_claims": completed,
            "failed_claims": failed, "unknown_claim_total": unknown})
    scored = obj(run / "scored/report.json")
    scored_cases = {(r["id"], r["backend"]): r for r in scored["case_results"]}
    require(len(scored["case_results"]) == len(scored_cases) == 90 and set(scored_cases) == set(pairs), "scored case identity")
    for observation in observations:
        case = scored_cases[observation["id"], observation["backend"]]
        for key in ("y_true", "y_pred", "status", "completed_claims", "failed_claims"):
            equal(observation[key], case[key], "scored case " + key)
    summaries = {}
    for backend in BACKENDS:
        selected = [r for r in observations if r["backend"] == backend]
        summary = check_summary(selected, scored["backends"][backend], backend)
        summary["by_task"] = {task: check_summary([r for r in selected if r["task"] == task], scored["backends"][backend]["by_task"][task], backend + "/" + task) for task in ("QA", "Summary", "Data2txt")}
        measured = runtime([r for r in records if r["backend"] == backend], freeze["price_reference"])
        reported = scored["runtime_by_backend"][backend]
        for key, value in measured.items():
            section = reported["usage"] if key in reported["usage"] else reported["reference_cost"] if key in reported["reference_cost"] else reported
            equal(value, section[key], backend + " runtime " + key)
        summary["runtime"] = measured
        summary["exact_public_citations"] = citation_counts[backend]
        summaries[backend] = summary
    return {"status": "pass", "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Deterministic input/output/accounting audit; no semantic gold adjudication or generalization claim",
        "new_records": len(new), "reused_original_v4_records": len(old), "unique_response_backend_pairs": len(pairs),
        "unchanged_frozen_source_files": len(original["code_files_sha256"]), "unchanged_current_production_files": production_count,
        "frozen_contract_imports_only": True, "native_labels_unchanged": True,
        "artifacts_sha256": {"audit_script": sha(__file__), "freeze": sha(run / "freeze.json"),
            "new_predictions": sha(run / "predictions.jsonl"), "original_predictions": sha(source_run / "predictions.jsonl"),
            "scored_report": sha(run / "scored/report.json")}, "backends": summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run_dir.resolve(), args.workspace.resolve())
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "new_records": result["new_records"], "output": str(args.output)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
