#!/usr/bin/env python3
"""Independent deterministic audit. No model calls, scorer imports or relabeling.

Only the frozen public contract validator is shared with inference. Detection,
completion, usage, costs, pair transitions and source-bootstrap are recomputed.
The CLI refuses an unfinished run before reading native labels.
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
import random
import sys

BACKENDS = ("baseline", "minimal", "optimized-v4.0")
PAIRS = (("minimal", "baseline"), ("optimized-v4.0", "baseline"), ("optimized-v4.0", "minimal"))
COUNTS = ("tp", "fp", "tn", "fn", "unknown_positive", "unknown_negative")
METRICS = ("correct_decisions_per_all_cases", "resolved_f1", "complete_case_rate", "decision_coverage")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def obj(path):
    value = parse(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), "Expected object: " + str(path))
    return value


def rows(path):
    result = [parse(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    require(all(isinstance(row, dict) for row in result), "JSONL rows must be objects")
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, name):
    if type(actual) is float or type(expected) is float:
        require(actual is not None and expected is not None and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12), name)
    else:
        require(actual == expected, name)


def fraction(actual, numerator, denominator, name):
    equal(actual["numerator"], numerator, name + " numerator")
    equal(actual["denominator"], denominator, name + " denominator")
    equal(actual["value"], numerator / denominator if denominator else None, name + " value")


def uint(value):
    return type(value) is int and value >= 0


def time_value(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def observe(record, meta, native, request, validator):
    prediction = record.get("prediction")
    try:
        validator(prediction, request["context_passages"])
        contract_valid = True
    except Exception:
        contract_valid = False
    usable = (record.get("error") is None and contract_valid and not record.get("validation_errors")
              and ("schema_valid" not in record or record["schema_valid"] is True))
    partial = usable and prediction.get("status") == "partial"
    claims = prediction["claims"] if usable else []
    done = len(claims)
    failed = len(prediction["errors"]) if partial else 0
    known = usable
    completion_valid = False
    telemetry = record.get("telemetry")
    completion = telemetry.get("completion") if isinstance(telemetry, dict) else None
    if isinstance(completion, dict):
        total, completed, unfinished, nonfactual = [completion.get(key, 0) for key in ("total_extracted", "completed", "unfinished", "non_factual_fallbacks")]
        completed_ids, failed_ids = completion.get("completed_claim_ids"), completion.get("unfinished_claim_ids")
        structural = (all(uint(value) and value <= 64 for value in (total, completed, unfinished, nonfactual))
                      and total == completed + unfinished + nonfactual
                      and isinstance(completed_ids, list) and isinstance(failed_ids, list)
                      and all(isinstance(identifier, str) and identifier for identifier in completed_ids + failed_ids))
        if structural:
            structural = (len(set(completed_ids)) == len(completed_ids) == completed
                          and len(set(failed_ids)) == len(failed_ids) == unfinished
                          and not set(completed_ids).intersection(failed_ids))
        if structural:
            completion_valid = not usable or (completed == done and unfinished == failed
                               and (not partial or set(failed_ids) == {item["id"] for item in prediction["errors"]}))
            if completion_valid and not usable:
                failed, known = total - nonfactual, True
    detected = any(claim["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for claim in claims)
    prediction_label = True if usable and detected else None if not usable or partial else False
    truth = bool(native["labels"])
    key = ("unknown_positive" if truth else "unknown_negative") if prediction_label is None else ("tp" if truth else "fp") if prediction_label else ("fn" if truth else "tn")
    citations = 0
    for claim in claims:
        for citation in claim["citations"]:
            citations += 1
            passage = request["context_passages"][citation["index"]]
            require(citation["quote"] in passage, "Public quote is not an exact substring")
            if "start_char" in citation or "end_char" in citation:
                equal(passage[citation["start_char"]:citation["end_char"]], citation["quote"], "Public quote offsets")
    if usable:
        equal(record["citations"], {"citation_count": citations, "valid_citation_count": citations}, "Citation diagnostics")
    status = "partial" if partial else "complete" if usable else "error"
    return {"id": meta["id"], "source_id": meta["source_id"], "backend": record["backend"],
            "task_type": meta["task_type"], "generator": meta["generator"], "y_true": truth,
            "y_pred": prediction_label, "status": status, "confusion_key": key,
            "completed_claims": done, "failed_claims": failed, "claim_total_known": known,
            "completion_telemetry_valid": completion_valid, "empty_claims": usable and not claims,
            "nonempty_answer_empty_claims": usable and not claims and bool(record.get("answer_chars", meta.get("answer_chars", 0))),
            "citation_count": citations}


def tally(observations):
    result = Counter({key: 0 for key in COUNTS})
    result["total"] = len(observations)
    result["complete"] = sum(row["status"] == "complete" for row in observations)
    for row in observations:
        result[row["confusion_key"]] += 1
    return result


def metric_values(counts):
    tp, fp, tn, fn = [counts[key] for key in ("tp", "fp", "tn", "fn")]
    total, resolved = counts["total"], tp + fp + tn + fn
    return {"correct_decisions_per_all_cases": (tp + tn) / total if total else None,
            "resolved_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "complete_case_rate": counts["complete"] / total if total else None,
            "decision_coverage": resolved / total if total else None}


def check_summary(observations, scored, label):
    counts = tally(observations)
    equal({key: counts[key] for key in COUNTS}, scored["confusion"], label + " confusion")
    statuses = dict(Counter(row["status"] for row in observations))
    equal(statuses, scored["status_counts"], label + " execution statuses")
    equal(len(observations), scored["total_count"], label + " total")
    tp, fp, tn, fn = [counts[key] for key in ("tp", "fp", "tn", "fn")]
    resolved = tp + fp + tn + fn
    for key, numerator, denominator in (("accuracy", tp + tn, resolved), ("precision", tp, tp + fp),
                                       ("recall", tp, tp + fn), ("f1", 2 * tp, 2 * tp + fp + fn)):
        fraction(scored["resolved_only"][key], numerator, denominator, label + " conditional " + key)
    for key, numerator in (("correct_decisions_per_all_cases", tp + tn), ("decision_coverage", resolved),
                            ("complete_case_rate", counts["complete"]), ("technical_failure_rate", len(observations) - counts["complete"])):
        fraction(scored[key], numerator, len(observations), label + " " + key)
    completed, failed = [sum(row[key] for row in observations) for key in ("completed_claims", "failed_claims")]
    equal(completed, scored["completed_claim_count"], label + " completed claims")
    equal(failed, scored["known_failed_claim_count"], label + " known failed claims")
    equal(sum(not row["claim_total_known"] for row in observations), scored["unknown_claim_total_case_count"], label + " unknown claim totals")
    fraction(scored["claim_completion_known_cases"], completed, completed + failed, label + " claim execution completion")
    equal(sum(row["empty_claims"] for row in observations), scored["empty_claims_count"], label + " empty claims")
    equal(sum(row["nonempty_answer_empty_claims"] for row in observations), scored["nonempty_answer_empty_claims_count"], label + " nonempty answer empty claims")
    positive = sum(row["y_true"] for row in observations)
    expected_target = "not_met" if fn else "not_evaluable" if not positive or counts["unknown_positive"] else "met"
    equal(expected_target, scored["native_fn_zero_target"], label + " native FN-zero target")
    return {"confusion": {key: counts[key] for key in COUNTS}, "statuses": statuses,
            "correct_decisions": tp + tn, "total": len(observations), "completed_claims": completed,
            "known_failed_claims": failed, "unknown_claim_total_cases": sum(not row["claim_total_known"] for row in observations),
            "empty_claims": sum(row["empty_claims"] for row in observations)}


def runtime(records, prices):
    calls, missing_records = [], 0
    for record in records:
        telemetry = record.get("telemetry")
        if not isinstance(telemetry, dict) or not isinstance(telemetry.get("calls"), list):
            missing_records += 1
        else:
            require(all(isinstance(call, dict) for call in telemetry["calls"]), "Invalid call telemetry")
            calls.extend(telemetry["calls"])
    prompt = completion = hit_total = miss_total = reasoning = with_usage = with_cache = with_reasoning = 0
    cost = all_miss = 0.0
    for call in calls:
        usage = call.get("usage")
        if not isinstance(usage, dict):
            continue
        p, c = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not uint(p) or not uint(c):
            continue
        prompt += p; completion += c; with_usage += 1
        all_miss += (p * prices["input_per_million"] + c * prices["output_per_million"]) / 1e6
        detail = usage.get("prompt_tokens_details")
        detail = detail if isinstance(detail, dict) else {}
        hit = usage.get("prompt_cache_hit_tokens", detail.get("cached_tokens"))
        miss = usage.get("prompt_cache_miss_tokens")
        if not uint(hit) and uint(miss) and miss <= p:
            hit = p - miss
        if not uint(miss) and uint(hit) and hit <= p:
            miss = p - hit
        if uint(hit) and uint(miss) and hit + miss == p:
            hit_total += hit; miss_total += miss; with_cache += 1
            cost += (miss * prices["input_per_million"] + hit * prices["cached_input_per_million"] + c * prices["output_per_million"]) / 1e6
        detail = usage.get("completion_tokens_details")
        r = detail.get("reasoning_tokens") if isinstance(detail, dict) else None
        if uint(r):
            reasoning += r; with_reasoning += 1
    times = sorted(row["latency_seconds"] for row in records if time_value(row.get("latency_seconds")))
    return {"usage": {"calls": len(calls), "calls_with_usage": with_usage,
                       "calls_missing_usage": len(calls) - with_usage, "calls_missing_cache_accounting": len(calls) - with_cache,
                       "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                       "prompt_cache_hit_tokens": hit_total, "prompt_cache_miss_tokens": miss_total,
                       "reasoning_tokens": reasoning, "cache_accounted_calls": with_cache, "reasoning_accounted_calls": with_reasoning,
                       "usage_complete": with_usage == len(calls) and not missing_records,
                       "cache_usage_complete": with_cache == len(calls) and not missing_records,
                       "reasoning_usage_complete": with_reasoning == len(calls) and not missing_records,
                       "records_missing_telemetry": missing_records, "call_count_complete": not missing_records},
            "reference_cost": {"known_usage_subtotal": cost, "estimated_total": cost if with_cache == len(calls) and not missing_records else None,
                               "priced_calls": with_cache, "unpriced_calls": len(calls) - with_cache,
                               "complete": with_cache == len(calls) and not missing_records,
                               "cache_standardized_all_miss_known_subtotal": all_miss,
                               "cache_standardized_all_miss_total": all_miss if with_usage == len(calls) and not missing_records else None,
                               "cache_standardized_priced_calls": with_usage, "cache_standardized_unpriced_calls": len(calls) - with_usage,
                               "records_missing_telemetry": missing_records},
            "record_count": len(records), "latency_measured_count": len(times), "latency_unknown_count": len(records) - len(times),
            "mean_latency_seconds": sum(times) / len(times) if times else None,
            "p50_latency_seconds": times[math.ceil(.5 * len(times)) - 1] if times else None,
            "p95_latency_seconds": times[math.ceil(.95 * len(times)) - 1] if times else None,
            "total_recorded_latency_seconds": sum(times),
            "returned_models": dict(Counter(str(call.get("model")) for call in calls)),
            "returned_system_fingerprints": dict(Counter(str(call.get("system_fingerprint")) for call in calls)),
            "stage_calls": dict(Counter(call.get("stage", "unknown") for call in calls))}


def check_runtime(actual, expected, label):
    for key, value in actual.items():
        if key in ("usage", "reference_cost"):
            for subkey, subvalue in value.items():
                equal(subvalue, expected[key][subkey], label + " " + key + "/" + subkey)
        else:
            equal(value, expected[key], label + " " + key)


def percentile(values, probability):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * probability
    left = int(math.floor(position)); right = int(math.ceil(position))
    return values[left] + (values[right] - values[left]) * (position - left)


def bootstrap(observations, samples=2000, seed=20261024):
    sources = sorted({row["source_id"] for row in observations})
    groups = {(source, backend): tally([row for row in observations if row["source_id"] == source and row["backend"] == backend])
              for source in sources for backend in BACKENDS}
    points = {backend: metric_values(tally([row for row in observations if row["backend"] == backend])) for backend in BACKENDS}
    distributions = {backend: {metric: [] for metric in METRICS} for backend in BACKENDS}
    paired = {f"{candidate}_minus_{reference}": {metric: [] for metric in METRICS} for candidate, reference in PAIRS}
    rng = random.Random(seed)
    for _ in range(samples):
        # Same source draw as frozen scoring; independent weighted-count math.
        draw = Counter(rng.choices(sources, k=len(sources)))
        estimates = {}
        for backend in BACKENDS:
            aggregate = Counter()
            for source, multiplicity in draw.items():
                for key, count in groups[source, backend].items():
                    aggregate[key] += count * multiplicity
            estimates[backend] = metric_values(aggregate)
            for metric, value in estimates[backend].items():
                if value is not None:
                    distributions[backend][metric].append(value)
        for candidate, reference in PAIRS:
            for metric in METRICS:
                a, b = estimates[candidate][metric], estimates[reference][metric]
                if a is not None and b is not None:
                    paired[f"{candidate}_minus_{reference}"][metric].append(a - b)
    def interval(values, point):
        return {"point_estimate": point, "low": percentile(values, .025), "high": percentile(values, .975),
                "defined_replicates": len(values), "undefined_replicates": samples - len(values)}
    result = {"backends": {backend: {metric: interval(distributions[backend][metric], points[backend][metric]) for metric in METRICS} for backend in BACKENDS}, "paired": {}}
    for candidate, reference in PAIRS:
        key = f"{candidate}_minus_{reference}"
        result["paired"][key] = {}
        for metric in METRICS:
            a, b = points[candidate][metric], points[reference][metric]
            result["paired"][key][metric] = interval(paired[key][metric], a - b if a is not None and b is not None else None)
    return result


def transitions(observations):
    lookup = {(row["id"], row["backend"]): row for row in observations}
    identifiers = sorted({row["id"] for row in observations})
    def state(row):
        return "unknown" if row["y_pred"] is None else "correct" if row["y_pred"] == row["y_true"] else "wrong"
    result = {}
    for candidate, reference in PAIRS:
        changes = Counter({f"{old}_to_{new}": 0 for old in ("correct", "wrong", "unknown") for new in ("correct", "wrong", "unknown")})
        common = Counter({key: 0 for key in ("count", "candidate_correct", "reference_correct", "candidate_correct_only", "reference_correct_only")})
        for identifier in identifiers:
            a, b = state(lookup[identifier, reference]), state(lookup[identifier, candidate])
            changes[f"{a}_to_{b}"] += 1
            if a != "unknown" and b != "unknown":
                common["count"] += 1
                common["candidate_correct"] += b == "correct"
                common["reference_correct"] += a == "correct"
                common["candidate_correct_only"] += a == "wrong" and b == "correct"
                common["reference_correct_only"] += a == "correct" and b == "wrong"
        result[f"{candidate}_minus_{reference}"] = {"all_cases": len(identifiers), "reference_to_candidate": dict(changes), "common_resolved": dict(common)}
    return result


def audit(run, data, source, scored_path):
    # No native data is loaded before completion and integrity gates pass.
    progress = obj(run / "progress.json")
    require(progress.get("status") in ("completed", "completed_with_unknown") and progress.get("finalized_records") == 540 and progress.get("frozen_artifacts_unchanged") is True, "Run is not finalized")
    config, preselection, binding, integrity = [obj(run / name) for name in ("config.json", "preselection.json", "binding.json", "result-integrity.json")]
    equal(config["backends"], list(BACKENDS), "Three frozen backends")
    equal(config["preselection_freeze_sha256"], sha(run / "preselection.json"), "Preselection digest")
    equal(config["binding_sha256"], sha(run / "binding.json"), "Binding digest")
    equal(binding.get("preselection_sha256", binding.get("preselection_freeze_sha256")), sha(run / "preselection.json"), "Binding/preselection join")
    for field in ("settings", "v4_config", "backends", "run_options", "price_reference", "code_files_sha256", "runner_sha256"):
        equal(config.get(field), preselection.get(field), "Frozen config " + field)
    equal(integrity["record_count"], 540, "Final integrity count")
    equal(integrity["predictions_sha256"], sha(run / "predictions.jsonl"), "Prediction journal checksum")
    for name, digest in integrity["files_sha256"].items():
        path = (run / name).resolve()
        require(path.is_relative_to(run), "Integrity path escaped run directory")
        equal(sha(path), digest, "Durable artifact " + name)
    for name, digest in preselection["code_files_sha256"].items():
        path = (source / name).resolve()
        require(path.is_relative_to(source), "Frozen path escaped source directory")
        equal(sha(path), digest, "Frozen source " + name)
    actual_data = {name: sha(data / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json")}
    equal(actual_data, config["data_files_sha256"], "Frozen data checksums")
    equal(actual_data, binding["data_files_sha256"], "Bound data checksums")
    sys.path.insert(0, str(source))
    validator = importlib.import_module("grounding.contracts_v4").validate_v4_report
    require(not any(name == "scripts.score_v4" or name.endswith("summarize") for name in sys.modules), "Audit imported scoring implementation")
    for name, module in list(sys.modules.items()):
        if name == "grounding" or name.startswith("grounding."):
            path = Path(module.__file__).resolve()
            require(path.is_relative_to(source), "Nonfrozen contract import")
            equal(sha(path), preselection["code_files_sha256"][path.relative_to(source).as_posix()], "Contract dependency digest")
    input_rows, manifest_rows, gold_rows = [rows(data / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl")]
    inputs, manifest, gold = [{row["id"]: row for row in group} for group in (input_rows, manifest_rows, gold_rows)]
    require(len(input_rows) == len(manifest_rows) == len(gold_rows) == len(inputs) == len(manifest) == len(gold) == 180, "Data must have 180 unique IDs")
    require(set(inputs) == set(manifest) == set(gold), "Input/manifest/native ID joins")
    source_counts = Counter(row["source_id"] for row in manifest_rows)
    require(len(source_counts) == 30 and set(source_counts.values()) == {6}, "Thirty sources with six answers each")
    equal(dict(Counter(row["task_type"] for row in manifest_rows)), {"QA": 60, "Summary": 60, "Data2txt": 60}, "Task counts")
    for identifier, meta in manifest.items():
        request = inputs[identifier]["input"]
        equal(set(request), {"context_passages", "generated_answer"}, "Inference input field boundary")
        encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        equal(hashlib.sha256(encoded).hexdigest(), meta["input_sha256"], "Input hash")
        equal(gold[identifier]["source_id"], meta["source_id"], "Native source join")
        require(isinstance(gold[identifier]["labels"], list), "Native labels must be a list")
    for source_id in source_counts:
        group = [row for row in manifest_rows if row["source_id"] == source_id]
        require(len({row["generator"] for row in group}) == 6 and len({row["task_type"] for row in group}) == 1, "Source generator/task structure")
    records = rows(run / "predictions.jsonl")
    slots = [(row["id"], row["backend"]) for row in records]
    require(len(slots) == len(set(slots)) == 540 and set(slots) == {(identifier, backend) for identifier in inputs for backend in BACKENDS}, "Exactly 540 unique answer/backend slots")
    require(len({row["pair_key"] for row in records}) == 540, "Unique reservation pair keys")
    observations = []
    for record in records:
        identifier = record["id"]; meta = manifest[identifier]; request = inputs[identifier]["input"]
        for field in ("source_id", "task_type", "generator", "input_sha256"):
            equal(record[field], meta[field], "Journal metadata " + field)
        calls = (record.get("telemetry") or {}).get("calls")
        if isinstance(calls, list):
            if record["backend"] == "baseline":
                equal(len(calls), 0, "Baseline must make no model calls")
            if record["backend"] == "minimal":
                require(len(calls) <= 1, "Minimal exceeded single-call budget")
        equal(record["answer_chars"], len(request["generated_answer"]), "Answer character count")
        require(record["backend_order_index"] in (0, 1, 2) and record["backend_order"][record["backend_order_index"]] == record["backend"], "Execution order metadata")
        observations.append(observe(record, meta, gold[identifier], request, validator))
    scored = obj(scored_path)
    scored_rows = {(row["id"], row["backend"]): row for row in scored["case_results"]}
    require(len(scored["case_results"]) == len(scored_rows) == 540 and set(scored_rows) == set(slots), "Scored identity slots")
    for observation in observations:
        expected = scored_rows[observation["id"], observation["backend"]]
        for key in ("source_id", "task_type", "generator", "y_true", "y_pred", "status", "completed_claims", "failed_claims", "claim_total_known", "completion_telemetry_valid", "empty_claims", "nonempty_answer_empty_claims"):
            equal(observation[key], expected[key], "Per-answer observation " + key)
    summaries = {}
    for backend in BACKENDS:
        selected = [row for row in observations if row["backend"] == backend]
        summary = check_summary(selected, scored["backends"][backend], backend)
        summary["by_task"] = {task: check_summary([row for row in selected if row["task_type"] == task], item, backend + "/" + task) for task, item in scored["backends"][backend]["by_task"].items()}
        summary["by_generator"] = {generator: check_summary([row for row in selected if row["generator"] == generator], item, backend + "/" + generator) for generator, item in scored["backends"][backend]["by_generator"].items()}
        selected_records = [row for row in records if row["backend"] == backend]
        measured = runtime(selected_records, config["price_reference"])
        check_runtime(measured, scored["runtime_by_backend"][backend], backend)
        for position in (0, 1, 2):
            group = [row for row in selected_records if row["backend_order_index"] == position]
            if group:
                check_runtime(runtime(group, config["price_reference"]), scored["runtime_by_backend"][backend]["by_execution_position"][str(position)], backend + " position " + str(position))
        summary["runtime"] = measured
        citation_count = sum(row["citation_count"] for row in selected)
        citation_score = scored["backends"][backend]["public_citation_contract"]
        equal(citation_count, citation_score["checked_citations"], "Checked citation count")
        equal(citation_count, citation_score["valid_exact_citations"], "Valid citation count")
        equal(1.0 if citation_count else None, citation_score["rate"], "Citation mechanical-validity fraction")
        summary["exact_public_citations"] = citation_count
        old = scored["legacy_whole_case_failure"]["backends"][backend]
        whole = Counter({key: 0 for key in ("tp", "fp", "tn", "fn", "positive_failures", "negative_failures")})
        for row in selected:
            key = row["confusion_key"] if row["status"] == "complete" else "positive_failures" if row["y_true"] else "negative_failures"
            whole[key] += 1
        equal(dict(whole), old["confusion"], backend + " historical whole-case confusion")
        fraction(old["end_to_end_accuracy"], whole["tp"] + whole["tn"], 180, backend + " historical all-case accuracy")
        fraction(old["detection_f1"], 2 * whole["tp"], 2 * whole["tp"] + sum(whole[key] for key in ("fp", "fn", "positive_failures", "negative_failures")), backend + " historical lower-bound F1")
        summaries[backend] = summary
    paired = transitions(observations)
    for key, item in paired.items():
        for field, value in item.items():
            equal(value, scored["paired_transitions"][key][field], "Pair transitions " + key + "/" + field)
    intervals = bootstrap(observations)
    declared = scored["three_backend_source_bootstrap"]
    equal(declared["samples"], 2000, "Bootstrap sample count")
    equal(declared["seed"], 20261024, "Bootstrap seed")
    equal(declared["source_count"], 30, "Bootstrap source count")
    for section, groups in intervals.items():
        for name, metrics in groups.items():
            for metric, interval in metrics.items():
                for field, value in interval.items():
                    equal(value, declared[section][name][metric][field], "Independent bootstrap " + "/".join((section, name, metric, field)))
    return {"status": "pass", "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": "Deterministic independent accounting audit; no model call, semantic adjudication or generalization claim",
            "record_count": 540, "answer_count": 180, "source_count": 30,
            "scoring_implementation_imported": False, "frozen_public_contract_validator_used": True,
            "native_labels_unchanged": True, "source_files_verified": len(preselection["code_files_sha256"]),
            "durable_artifacts_verified": len(integrity["files_sha256"]),
            "artifacts_sha256": {"audit_script": sha(__file__), "predictions": sha(run / "predictions.jsonl"),
                                 "report": sha(scored_path), "config": sha(run / "config.json"), "native_gold": sha(data / "native_gold.jsonl")},
            "backends": summaries, "paired_transitions": paired, "independent_source_bootstrap": intervals}


def self_test():
    # Only generated bookkeeping fixtures, never RAGTruth records.
    prices = {"input_per_million": .30, "cached_input_per_million": .006, "output_per_million": 1.20}
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60,
             "completion_tokens_details": {"reasoning_tokens": 5}}
    fake = [{"telemetry": {"calls": [{"usage": usage}]}, "latency_seconds": 2.0},
            {"telemetry": {"calls": [{"usage": None}]}, "latency_seconds": 4.0},
            {"telemetry": {"usage_unknown": True}, "latency_seconds": None}]
    measured = runtime(fake, prices)
    equal(measured["usage"]["calls"], 2, "Self-test known call count")
    equal(measured["usage"]["calls_missing_usage"], 1, "Self-test missing usage")
    equal(measured["usage"]["records_missing_telemetry"], 1, "Self-test missing record telemetry")
    equal(measured["usage"]["total_tokens"], 120, "Self-test no double-counting reasoning")
    equal(measured["reference_cost"]["estimated_total"], None, "Self-test unknown total cost")
    equal(measured["reference_cost"]["known_usage_subtotal"], (60 * .30 + 40 * .006 + 20 * 1.20) / 1e6, "Self-test known cost")
    equal(measured["reference_cost"]["cache_standardized_all_miss_total"], None, "Self-test unknown standardized total")
    equal(measured["mean_latency_seconds"], 3.0, "Self-test mean excludes unknown")
    observations = [{"id": str(i), "source_id": "s" + str(i // 2), "backend": backend,
                     "status": "complete", "y_true": i % 2 == 0, "y_pred": True,
                     "confusion_key": "tp" if i % 2 == 0 else "fp"} for i in range(6) for backend in BACKENDS]
    result = bootstrap(observations, samples=30)
    for pair in result["paired"].values():
        for interval in pair.values():
            equal(interval["point_estimate"], 0.0, "Self-test paired bootstrap point")
            equal(interval["low"], 0.0, "Self-test paired bootstrap low")
            equal(interval["high"], 0.0, "Self-test paired bootstrap high")
    equal(transitions(observations)["optimized-v4.0_minus_minimal"]["common_resolved"]["count"], 6, "Self-test no repeated pair counts")
    print(json.dumps({"status": "synthetic_checks_pass", "model_calls": 0, "native_data_loaded": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--scored-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if any(value is None for value in (args.run_dir, args.data_dir, args.source_root, args.scored_report, args.output)):
        parser.error("Audit requires --run-dir, --data-dir, --source-root, --scored-report and --output")
    result = audit(args.run_dir.resolve(), args.data_dir.resolve(), args.source_root.resolve(), args.scored_report.resolve())
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "records": result["record_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
