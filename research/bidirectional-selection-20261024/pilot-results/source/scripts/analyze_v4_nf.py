#!/usr/bin/env python3
"""Offline paired NF occurrence experiment analysis; never imported by inference."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.scoring import fraction, usage_summary
from grounding.contracts import VerificationError, strict_json_loads
from scripts.benchmark_ragtruth import _jsonl, _object, _sha, _write_json
from scripts.benchmark_v4_behavior import score_case as behavior_score
from scripts.ragtruth_score import _interval
from scripts.score_v4 import _observe, _summary, load_prediction_journal, score_claim_case

BACKENDS = ("pre_fix", "post_fix")
REFERENCE_PRICES = {"input_per_million": .30, "cached_input_per_million": .006,
                    "output_per_million": 1.20, "currency": "USD"}


def reference_cost(records, prices=None):
    """Price each fully accounted call; an unpriced call cannot erase known costs."""
    prices = prices or REFERENCE_PRICES
    for name in ("input_per_million", "cached_input_per_million", "output_per_million"):
        value = prices.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError("Finite nonnegative reference prices are required")
    calls = [call for row in records for call in row.get("telemetry", {}).get("calls", [])]
    known, standardized = 0.0, 0.0
    priced, standardized_priced = 0, 0
    for call in calls:
        usage = usage_summary([{"telemetry": {"calls": [call]}}])
        if usage["usage_complete"]:
            standardized += (usage["prompt_tokens"] * prices["input_per_million"] +
                             usage["completion_tokens"] * prices["output_per_million"]) / 1_000_000
            standardized_priced += 1
        if usage["usage_complete"] and usage["cache_usage_complete"]:
            known += (usage["prompt_cache_miss_tokens"] * prices["input_per_million"] +
                      usage["prompt_cache_hit_tokens"] * prices["cached_input_per_million"] +
                      usage["completion_tokens"] * prices["output_per_million"]) / 1_000_000
            priced += 1
    return {"reference_prices": prices, "known_usage_subtotal": known,
            "estimated_total": known if priced == len(calls) else None,
            "priced_calls": priced, "unpriced_calls": len(calls) - priced,
            "complete": priced == len(calls),
            "cache_standardized_all_miss_known_subtotal": standardized,
            "cache_standardized_all_miss_total": standardized if standardized_priced == len(calls) else None,
            "cache_standardized_priced_calls": standardized_priced,
            "cache_standardized_unpriced_calls": len(calls) - standardized_priced,
            "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill."}


def runtime_summary(records, prices=None):
    usage = usage_summary(records)
    usage["calls_missing_usage"] = usage["calls"] - usage["calls_with_usage"]
    usage["calls_missing_cache_accounting"] = usage["calls"] - usage["cache_accounted_calls"]
    latency = sorted(row["latency_seconds"] for row in records)
    stages, errors, models, fingerprints, totals = (Counter() for _ in range(5))
    for row in records:
        telemetry = row.get("telemetry") or {}
        for call in telemetry.get("calls", []):
            stages[call.get("stage", "unknown")] += 1
            models[str(call.get("model"))] += 1
            fingerprints[str(call.get("system_fingerprint"))] += 1
        if row.get("error"):
            errors[row["error"]["code"]] += 1
        for key, value in telemetry.get("summary", {}).items():
            if type(value) is int:
                totals[key] += value
        extraction = telemetry.get("extraction") or {}
        totals["extracted_claim_count"] += len(extraction.get("claims", []))
        totals["non_factual_span_count"] += len(extraction.get("non_factual_spans", []))
        totals["fallback_claim_count"] += sum(bool(c.get("extraction_fallback")) for c in extraction.get("claims", []))
    order = {}
    for position in (0, 1):
        selected = [r for r in records if r.get("backend_order_index") == position]
        if selected:
            times = sorted(r["latency_seconds"] for r in selected)
            order["first" if position == 0 else "second"] = {
                "record_count": len(selected), "mean_latency_seconds": sum(times) / len(times),
                "p95_latency_seconds": times[math.ceil(.95 * len(times)) - 1],
                "usage": usage_summary(selected), "reference_cost": reference_cost(selected, prices)}
    return {"record_count": len(records), "usage": usage, "reference_cost": reference_cost(records, prices),
            "mean_latency_seconds": sum(latency) / len(latency) if latency else None,
            "p95_latency_seconds": latency[math.ceil(.95 * len(latency)) - 1] if latency else None,
            "stage_calls": dict(stages), "summary_totals": dict(totals), "error_codes": dict(errors),
            "returned_models": dict(models), "returned_system_fingerprints": dict(fingerprints),
            "by_variant_execution_order": order}


def _load_pure_extract(path):
    """Execute only the four pure validators from each already verified snapshot."""
    names = {"_invalid", "_text", "_meaningful", "extract_claims"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in body} != names:
        raise ValueError("Frozen extraction validator definition mismatch")
    namespace = {"Any": object, "VerificationError": VerificationError, "unicodedata": unicodedata}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["extract_claims"]


def dual_parser_audit(records, requests, pre_source, post_source, *, max_claims=64):
    """Compare both validators on actual raw responses, without simulating repair."""
    parsers = {"pre_fix": _load_pure_extract(pre_source), "post_fix": _load_pure_extract(post_source)}
    request_map = {(r["dataset"], r["id"]): r for r in requests}
    counters, changes, flags, anomalies = defaultdict(Counter), [], [], []
    for record in records:
        identity = {key: record[key] for key in ("dataset", "id", "backend")}
        group = record["dataset"] + "/" + record["backend"]
        count = counters[group]
        count["records"] += 1
        answer = request_map[record["dataset"], record["id"]]["input"]["generated_answer"]
        telemetry = record.get("telemetry") or {}
        extraction = telemetry.get("extraction") or {}
        chunks = {c["chunk_id"]: c for c in extraction.get("chunks", [])}
        eligible = defaultdict(list)
        flagged = set()
        for index, call in enumerate(telemetry.get("calls", [])):
            if not str(call.get("stage", "")).startswith("decompose"):
                continue
            count["decompose_calls"] += 1
            usable = call.get("http_status") == 200 and call.get("finish_reason") == "stop"
            count["transport_usable_calls"] += usable
            try:
                payload = strict_json_loads(call.get("response_text") or "")
            except (ValueError, TypeError):
                count["strict_json_parse_failures"] += 1
                continue
            chunk = chunks.get(call.get("chunk_id"))
            if chunk is None:
                anomalies.append({**identity, "call_index": index, "issue": "missing_chunk_metadata"})
                continue
            start, end = chunk["source_start"], chunk["source_end"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(answer):
                anomalies.append({**identity, "call_index": index, "issue": "invalid_chunk_bounds"})
                continue
            count["strict_json_parsed_comparable_calls"] += 1
            outcomes = {}
            for name, parser in parsers.items():
                try:
                    claims, excluded = parser(payload, answer[start:end], max_claims=max_claims)
                    outcomes[name] = {"valid": True, "claims": claims, "non_factual_spans": excluded}
                except VerificationError as exc:
                    outcomes[name] = {"valid": False, "error": exc.message}
            a, b = (outcomes[name] for name in BACKENDS)
            kind = None
            if a["valid"] != b["valid"]:
                kind = "acceptance_changed"
            elif not a["valid"]:
                if a["error"] != b["error"]:
                    kind = "rejection_feedback_changed"
            elif a["claims"] != b["claims"]:
                kind = "accepted_claims_changed"
            elif a["non_factual_spans"] != b["non_factual_spans"]:
                kind = "accepted_nf_ledger_changed"
            actual = outcomes[record["backend"]]
            if usable and actual["valid"]:
                eligible[chunk["chunk_id"]].append((index, actual, kind))
            if kind:
                count["raw_payload_" + kind] += 1
                if usable:
                    flagged.add(kind)
                    count["transport_usable_" + kind] += 1
                changes.append({**identity, "call_index": index, "stage": call["stage"], "chunk_id": chunk["chunk_id"],
                                "source_start": start, "source_end": end, "transport_usable": usable, "change": kind,
                                "pre_valid": a["valid"], "post_valid": b["valid"],
                                "pre_error": a.get("error"), "post_error": b.get("error"),
                                "pre_claim_count": len(a.get("claims", [])) if a["valid"] else None,
                                "post_claim_count": len(b.get("claims", [])) if b["valid"] else None,
                                "pre_nf_count": len(a.get("non_factual_spans", [])) if a["valid"] else None,
                                "post_nf_count": len(b.get("non_factual_spans", [])) if b["valid"] else None})
        def nf_key(row):
            return row["text"], row["reason"], row["source_start"], row["source_end"]
        observed_nf = Counter(nf_key(row) for row in extraction.get("non_factual_spans", []))
        for recovery in extraction.get("hard_split_recoveries", []):
            observed_nf.update(nf_key(row) for row in recovery.get("superseded_non_factual_spans", []))
        for chunk_id, chunk in chunks.items():
            candidates = eligible[chunk_id]
            if chunk.get("fallback"):
                if candidates:
                    anomalies.append({**identity, "chunk_id": chunk_id, "issue": "accepted_payload_in_fallback_chunk"})
                continue
            if len(candidates) != 1:
                anomalies.append({**identity, "chunk_id": chunk_id, "issue": "expected_one_accepted_payload", "count": len(candidates)})
                continue
            index, accepted, kind = candidates[0]
            count["actual_accepted_payloads"] += 1
            if kind:
                count["actual_accepted_" + kind] += 1
            offset = chunk["source_start"]
            expected_nf = Counter((row["text"], row["reason"], row["source_start"] + offset, row["source_end"] + offset)
                                  for row in accepted["non_factual_spans"])
            if expected_nf - observed_nf:
                anomalies.append({**identity, "chunk_id": chunk_id, "issue": "accepted_nf_missing_from_final_or_recovery_ledger"})
        flags.append({**identity, "any_transport_usable_parser_difference": bool(flagged), "difference_kinds": sorted(flagged)})
        count["records_with_transport_usable_parser_difference"] += bool(flagged)
    return {"groups": {key: dict(value) for key, value in sorted(counters.items())}, "changed_calls": changes,
            "record_flags": flags, "audit_anomalies": anomalies,
            "note": "Both frozen validators are applied only to actual observed M1 payloads and exact recorded chunks. Changed rejection feedback may change later model responses, so later frozen responses are not a counterfactual rerun. Affected subsets are post-treatment descriptive diagnostics, not causal isolation from model variance."}


def paired_bootstrap(rows, *, samples=2000, seed=20261023):
    if type(samples) is not int or samples < 0:
        raise ValueError("Bootstrap samples must be a nonnegative integer")
    pairs, groups = defaultdict(dict), defaultdict(list)
    for row in rows:
        if row["backend"] not in BACKENDS or row["backend"] in pairs[row["id"]]:
            raise ValueError("Duplicate or unexpected paired observation")
        pairs[row["id"]][row["backend"]] = row
        groups[row["source_id"]].append(row)
    if not pairs or any(set(pair) != set(BACKENDS) for pair in pairs.values()):
        raise ValueError("Every paired case requires both observations, including failures")
    for pair in pairs.values():
        a, b = (pair[name] for name in BACKENDS)
        if a["source_id"] != b["source_id"] or a["y_true"] != b["y_true"]:
            raise ValueError("Paired source or native label mismatch")
    names = ("resolved_accuracy", "resolved_f1", "correct_decisions_per_all_cases", "decision_coverage",
             "complete_case_rate", "claim_completion_known_cases")
    def metrics(items):
        s = _summary(items)
        return [s["resolved_only"]["accuracy"]["value"], s["resolved_only"]["f1"]["value"],
                *(s[k]["value"] for k in names[2:])]
    def difference(items):
        a, b = (metrics([row for row in items if row["backend"] == name]) for name in BACKENDS)
        return [new - old if old is not None and new is not None else None for old, new in zip(a, b)]
    point = difference(rows)
    draws = [[] for _ in names]
    rng, sources = random.Random(seed), sorted(groups)
    for _ in range(samples):
        selected = [row for source in rng.choices(sources, k=len(sources)) for row in groups[source]]
        for bucket, value in zip(draws, difference(selected)):
            if value is not None:
                bucket.append(value)
    return {"reference": BACKENDS[0], "candidate": BACKENDS[1], "source_cluster_count": len(sources),
            "method": "paired whole-source percentile bootstrap", "samples": samples, "seed": seed,
            "confidence_level": .95,
            "deltas": {name: _interval(values, samples, p) for name, values, p in zip(names, draws, point)},
            "limitation": "Descriptive resampling of exposed-dev sources, conditional on one generation per variant. Does not estimate repeated-generation variance or establish unseen generalization."}


def _native_state(row):
    if row["y_pred"] is None:
        return "unknown_positive" if row["y_true"] else "unknown_negative"
    return ("tp" if row["y_pred"] else "fn") if row["y_true"] else ("fp" if row["y_pred"] else "tn")


def dev_changes(observations, records):
    pairs, raw = defaultdict(dict), {(r["id"], r["backend"]): r for r in records}
    for row in observations:
        pairs[row["id"]][row["backend"]] = row
    transitions, correctness = Counter(), Counter()
    changed = []
    identical_extraction = 0
    identical_extraction_decision_changes = 0
    for identifier, pair in sorted(pairs.items()):
        a, b = (pair[name] for name in BACKENDS)
        old, new = _native_state(a), _native_state(b)
        transitions[old + "_to_" + new] += 1
        def correct_state(row):
            return "unknown" if row["y_pred"] is None else "correct" if row["y_pred"] == row["y_true"] else "wrong"
        correctness[correct_state(a) + "_to_" + correct_state(b)] += 1
        ar, br = (raw[identifier, name] for name in BACKENDS)
        ae, be = ((r.get("telemetry") or {}).get("extraction") for r in (ar, br))
        same = isinstance(ae, dict) and isinstance(be, dict) and ae.get("claims") == be.get("claims")
        identical_extraction += same
        identical_extraction_decision_changes += same and a["y_pred"] != b["y_pred"]
        if old != new or a["status"] != b["status"] or a["completed_claims"] != b["completed_claims"] or a["failed_claims"] != b["failed_claims"]:
            changed.append({"id": identifier, "source_id": a["source_id"], "task_type": a["task_type"],
                            "pre_fix": {"state": old, "status": a["status"], "completed_claims": a["completed_claims"], "failed_claims": a["failed_claims"]},
                            "post_fix": {"state": new, "status": b["status"], "completed_claims": b["completed_claims"], "failed_claims": b["failed_claims"]},
                            "identical_extracted_claim_objects": same})
    return {"native_transition_counts": dict(transitions), "correctness_transition_counts": dict(correctness),
            "changed_cases": changed, "identical_extracted_claim_objects_pairs": identical_extraction,
            "decision_changes_with_identical_extracted_claim_objects": identical_extraction_decision_changes,
            "note": "Changes are native-label and execution diagnostics, not author-adjudicated semantic corrections. Identical M1 claim objects alone do not prove identical downstream requests."}


def _alignment_summary(scores, mode):
    totals = Counter()
    exact_cases = 0
    for score in scores:
        alignment = score["alignment_diagnostic"][mode]
        # A partial/error output cannot establish full-case agreement, even if
        # its completed subset happens to match all expected claims.
        exact_cases += score["execution_status"] == "complete" and alignment["case_correct"]
        for key in ("gold_claim_count", "predicted_claim_count", "matched_claim_count", "correct_claim_count", "missing_claim_count", "extra_claim_count"):
            totals[key] += alignment[key]
    return {**dict(totals), "aligned_verdict_accuracy": fraction(totals["correct_claim_count"], totals["matched_claim_count"]),
            "complete_case_text_and_label_agreement": fraction(exact_cases, len(scores)),
            "gold_alignment_coverage": fraction(totals["matched_claim_count"], totals["gold_claim_count"]),
            "correct_aligned_per_all_gold": fraction(totals["correct_claim_count"], totals["gold_claim_count"]),
            "all_gold_f1_diagnostic": fraction(2 * totals["correct_claim_count"], totals["gold_claim_count"] + totals["predicted_claim_count"])}


def analyze_records(records, requests, dev_manifest, dev_gold, behavior_pairs, physics_cases, *, samples=2000, prices=None):
    """Require a complete paired journal; labels are only consumed by this scorer."""
    request_map = {(r["dataset"], r["id"]): r for r in requests}
    if len(request_map) != len(requests):
        raise ValueError("Duplicate request identity")
    record_map = {(r["dataset"], r["id"], r["backend"]): r for r in records}
    expected = {(dataset, identifier, backend) for dataset, identifier in request_map for backend in BACKENDS}
    if len(record_map) != len(records) or set(record_map) != expected:
        raise ValueError("Journal must contain exactly both variants for every frozen request")
    manifest_map = {r["id"]: r for r in dev_manifest}
    gold_map = {r["id"]: r for r in dev_gold}
    behavior_map = {(p["id"], side): p[side] for p in behavior_pairs for side in ("base", "variant")}
    physics_map = {r["id"]: r for r in physics_cases}
    observations = []
    behavior_rows, physics_rows = [], []
    for record in records:
        dataset, identifier = record["dataset"], record["id"]
        request = request_map[dataset, identifier]
        meta = manifest_map[identifier] if dataset == "dev" else {"id": identifier, "source_id": identifier, "task_type": dataset, "generator": "not_applicable"}
        gold = gold_map[identifier] if dataset == "dev" else {"labels": []}
        observation = _observe(meta, gold, record["backend"], record, request["input"]["context_passages"])
        observation["dataset"] = dataset
        observations.append(observation)
        if dataset == "behavior":
            case = behavior_map[record["pair_id"], record["side"]]
            behavior_rows.append({**record, "score": behavior_score(case, record["prediction"], record["error"], telemetry=record.get("telemetry"))})
        elif dataset == "physics":
            physics_rows.append({**record, "score": score_claim_case(physics_map[identifier], record["prediction"], record["error"])})
        elif dataset != "dev":
            raise ValueError("Unexpected dataset")
    report = {"schema_version": "v4-nf-occurrence-analysis-v1", "record_count": len(records), "case_count": len(requests),
              "qualification": "Fresh paired exposed-development diagnostic; all labels unchanged; supplementary labels are not author-adjudicated gold.",
              "backends": list(BACKENDS), "overall_execution": {}, "datasets": {}, "case_observations": observations}
    for backend in BACKENDS:
        rows = [r for r in observations if r["backend"] == backend]
        s = _summary(rows)
        report["overall_execution"][backend] = {k: s[k] for k in ("total_count", "status_counts", "complete_case_rate", "completed_claim_count", "known_failed_claim_count", "claim_completion_known_cases", "unknown_claim_total_case_count", "empty_claims_count")}
        report["overall_execution"][backend]["runtime"] = runtime_summary([r for r in records if r["backend"] == backend], prices)
    for dataset in ("dev", "behavior", "physics"):
        dataset_records = [r for r in records if r["dataset"] == dataset]
        dataset_observations = [r for r in observations if r["dataset"] == dataset]
        result = {"backends": {}}
        for backend in BACKENDS:
            rows = [r for r in dataset_observations if r["backend"] == backend]
            selected = [r for r in dataset_records if r["backend"] == backend]
            s = _summary(rows)
            if dataset == "dev":
                item = s
                item["by_task"] = {task: _summary([r for r in rows if r["task_type"] == task]) for task in sorted({r["task_type"] for r in rows})}
            else:
                item = {k: s[k] for k in ("total_count", "status_counts", "complete_case_rate", "completed_claim_count", "known_failed_claim_count", "claim_completion_known_cases", "unknown_claim_total_case_count", "empty_claims_count")}
                scored = [r["score"] for r in (behavior_rows if dataset == "behavior" else physics_rows) if r["backend"] == backend]
                if dataset == "behavior":
                    item.update(expected_accuracy_all_cases=fraction(sum(v["expected_correct"] for v in scored), len(scored)),
                                resolved_label_coverage=fraction(sum(v["observed_label"] is not None for v in scored), len(scored)),
                                aligned_target_label_accuracy=fraction(sum(v["aligned_target_correct_count"] for v in scored), sum(v["aligned_target_count"] for v in scored)),
                                target_alignment_coverage=fraction(sum(v["aligned_target_count"] for v in scored), len(scored)))
                else:
                    item["strict"] = _alignment_summary(scored, "strict")
                    item["approximate"] = _alignment_summary(scored, "approximate")
            item["runtime"] = runtime_summary(selected, prices)
            result["backends"][backend] = item
        if dataset == "dev":
            result["paired_bootstrap"] = paired_bootstrap(dataset_observations, samples=samples)
            result["paired_changes"] = dev_changes(dataset_observations, dataset_records)
            result["policy"] = "C/U in completed valid claims means detected; complete all-S means clean; partial all-S/error means unknown, never TN/FN. Native FP is not adjudicated true FP. Claim completion is not semantic extraction recall."
        else:
            scored = behavior_rows if dataset == "behavior" else physics_rows
            result["case_scores"] = [{"id": r["id"], "backend": r["backend"], "score": r["score"]} for r in scored]
            result["policy"] = "Supplementary pre-existing exposed labels; no new author approval. Lexical alignment is a diagnostic, not proof of semantic correctness."
        report["datasets"][dataset] = result
    return report


def render_markdown(report):
    def pct(value):
        return "n/a" if value["value"] is None else f"{value['numerator']}/{value['denominator']} ({value['value']:.2%})"
    def statuses(item):
        return " / ".join(str(item["status_counts"].get(key, 0)) for key in ("complete", "partial", "error"))
    lines = ["# NF occurrence repair: fresh paired evaluation", "", report["qualification"], "",
             "Only the NF occurrence parser changes. Prompt, model settings, M3 and review limits are shared. One generation per variant; differences include model and service variability.", "",
             "| Dataset / variant | Complete / partial / error | Accuracy or correct / all gold | Extracted factual claim completion |", "| --- | --- | --- | --- |"]
    for dataset, data in report["datasets"].items():
        for backend, item in data["backends"].items():
            quality = item["correct_decisions_per_all_cases"] if dataset == "dev" else item["expected_accuracy_all_cases"] if dataset == "behavior" else item["strict"]["correct_aligned_per_all_gold"]
            lines.append(f"| {dataset} / {backend} | {statuses(item)} | {pct(quality)} | {pct(item['claim_completion_known_cases'])} |")
    lines += ["", "Dev quality above counts correct native answer decisions over every input; unresolved is not counted as correct or as TN/FN. Physics is strict text-aligned correct / all predeclared claims, not all semantic claims.", "",
              "| Dev variant | TP / FP / TN / FN | Unknown + / − | Decided accuracy | Decided F1 |", "| --- | --- | --- | --- | --- |"]
    dev = report["datasets"]["dev"]
    for backend, item in dev["backends"].items():
        c = item["confusion"]
        lines.append(f"| {backend} | {' / '.join(str(c[k]) for k in ('tp','fp','tn','fn'))} | {c['unknown_positive']} / {c['unknown_negative']} | {pct(item['resolved_only']['accuracy'])} | {pct(item['resolved_only']['f1'])} |")
    lines += ["", "| Dev task / variant | Correct decisions / all | Decided accuracy | Decided F1 | Complete / partial / error |", "| --- | --- | --- | --- | --- |"]
    for backend, item in dev["backends"].items():
        for task, sub in item["by_task"].items():
            lines.append(f"| {task} / {backend} | {pct(sub['correct_decisions_per_all_cases'])} | {pct(sub['resolved_only']['accuracy'])} | {pct(sub['resolved_only']['f1'])} | {statuses(sub)} |")
    lines += ["", "| Dev paired delta (post − pre) | Point, percentage points | Source-cluster 95% interval |", "| --- | ---: | ---: |"]
    for name, interval in dev["paired_bootstrap"]["deltas"].items():
        point, low, high = (interval[k] for k in ("point_estimate", "low", "high"))
        lines.append(f"| {name} | {point * 100:+.2f}" + (f" | {low * 100:+.2f} to {high * 100:+.2f} |" if low is not None and high is not None else " | n/a |") if point is not None else f"| {name} | n/a | n/a |")
    lines += ["", "| Dataset / variant | Calls / missing usage | Input / output / cached tokens | Mean / P95 seconds | Known reference USD / unpriced calls | All-miss standardized known USD |", "| --- | --- | --- | --- | --- | --- |"]
    for dataset, data in [("all", {"backends": report["overall_execution"]}), *report["datasets"].items()]:
        for backend, item in data["backends"].items():
            r = item["runtime"]; u = r["usage"]; c = r["reference_cost"]
            lines.append(f"| {dataset} / {backend} | {u['calls']} / {u['calls_missing_usage']} | {u['prompt_tokens']} / {u['completion_tokens']} / {u['prompt_cache_hit_tokens']} | {r['mean_latency_seconds']:.2f} / {r['p95_latency_seconds']:.2f} | {c['known_usage_subtotal']:.6f} / {c['unpriced_calls']} | {c['cache_standardized_all_miss_known_subtotal']:.6f} |")
    lines += ["", "Reference USD per million tokens: input 0.30, cached input 0.006, output 1.20. Missing usage is not zero cost; subtotals are not complete bills. All-miss standardized cost isolates cache accounting, not output-length or model variability.", "",
              "| Variant / execution order | Records | Mean / P95 seconds | Cached / input tokens | Known USD / unpriced calls |", "| --- | --- | --- | --- | --- |"]
    for backend, item in report["overall_execution"].items():
        for position, r in item["runtime"]["by_variant_execution_order"].items():
            u, c = r["usage"], r["reference_cost"]
            lines.append(f"| {backend} / {position} | {r['record_count']} | {r['mean_latency_seconds']:.2f} / {r['p95_latency_seconds']:.2f} | {u['prompt_cache_hit_tokens']} / {u['prompt_tokens']} | {c['known_usage_subtotal']:.6f} / {c['unpriced_calls']} |")
    lines += ["",
              "No unseen data or adjudicated labels are used. Native score gains are not evidence of claim-level correction or generalization. JSON includes completion denominators, strict/approximate alignment, unknowns, transitions, usage gaps and all case scores.", ""]
    if "dual_parser_audit" in report:
        audit = report["dual_parser_audit"]
        flags = sum(r["any_transport_usable_parser_difference"] for r in audit["record_flags"])
        lines += [f"Dual-parser audit: {flags}/{len(audit['record_flags'])} observed records contain a transport-usable M1 payload whose validator result, NF ledger or rejection feedback differs; {len(audit['audit_anomalies'])} ledger/chunk anomalies.", "", audit["note"], ""]
    return "\n".join(lines)


def summarize(run_dir, output_dir, *, samples=2000):
    config = _object(run_dir / "config.json")
    progress = _object(run_dir / "progress.json")
    if progress.get("status") != "completed" or progress.get("frozen_artifacts_unchanged") is not True:
        raise ValueError("Only a completed paired run can be summarized")
    # Final hash field names are supplied by the paired runner; never trust labels
    # or source data outside the run's immutable archive.
    if _sha(run_dir / "config.json") != (run_dir / "config.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Run configuration hash mismatch")
    hashes = config.get("files_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("Run must bind its archived sources and data")
    for name, digest in hashes.items():
        path = (run_dir / name).resolve()
        if not path.is_relative_to(run_dir.resolve()) or _sha(path) != digest:
            raise ValueError("Frozen artifact hash mismatch: " + name)
    for name in ("scripts/analyze_v4_nf.py", "scripts/score_v4.py", "scripts/ragtruth_score.py", "scripts/benchmark_v4_behavior.py", "grounding/scoring.py", "grounding/contracts.py", "grounding/contracts_v4.py", "scripts/validate_dataset.py"):
        if hashes.get("source/" + name) != _sha(ROOT / name):
            raise ValueError("Scorer or contract dependency differs from freeze; run archived analyzer: " + name)
    requests = _jsonl(run_dir / "requests.jsonl")
    records = load_prediction_journal(run_dir / "responses.jsonl")
    if (len(requests) != config.get("expected_cases") or len(records) != config.get("expected_records")
            or len(records) != progress.get("completed_records") or config.get("backends") != list(BACKENDS)):
        raise ValueError("Final counts or variant pair do not match freeze")
    report = analyze_records(records, requests,
        _jsonl(run_dir / "data/dev/manifest.jsonl"), _jsonl(run_dir / "data/dev/native_gold.jsonl"),
        _jsonl(run_dir / "data/behavior/pairs.jsonl"), _jsonl(run_dir / "data/physics/cases.jsonl"),
        samples=samples, prices=config.get("price_reference", REFERENCE_PRICES))
    audit = dual_parser_audit(records, requests, run_dir / "pre_fix/grounding/verifiers_v4.py",
                             run_dir / "source/grounding/verifiers_v4.py", max_claims=config["v4_config"]["max_claims"])
    report["dual_parser_audit"] = audit
    affected = {r["id"] for r in audit["record_flags"] if r["dataset"] == "dev" and r["any_transport_usable_parser_difference"]}
    affected_observations = [r for r in report["case_observations"] if r["dataset"] == "dev" and r["id"] in affected]
    report["datasets"]["dev"]["observed_parser_difference_subset"] = {
        "case_count": len(affected), "backends": {name: _summary([r for r in affected_observations if r["backend"] == name]) for name in BACKENDS},
        "transitions": dev_changes(affected_observations, [r for r in records if r["dataset"] == "dev" and r["id"] in affected]),
        "warning": "Post-treatment subset: selected when either observed variant has a transport-usable parser difference. Descriptive only; cannot isolate causal effect or remove model randomness."}
    report["run_binding"] = {"run_directory": str(run_dir.resolve()), "config_sha256": _sha(run_dir / "config.json"),
                             "responses_sha256": _sha(run_dir / "responses.jsonl"), "scorer_sha256": _sha(Path(__file__)),
                             "bootstrap_samples": samples, "frozen_artifacts_verified": len(hashes)}
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "report.json", report, exclusive=True)
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args()
    summarize(args.run_dir, args.output_dir, samples=args.bootstrap_samples)
    print(json.dumps({"output_directory": str(args.output_dir), "model_calls": 0}))


if __name__ == "__main__":
    main()
