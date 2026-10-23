#!/usr/bin/env python3
"""Score the paired exposed-dev experiment, including source-cluster uncertainty."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.scoring import usage_summary, cost_summary
from scripts.benchmark_ragtruth import _jsonl, _object, _sha, _write_json
from scripts.benchmark_v4_combined import BACKENDS, SCHEMA
from scripts.ragtruth_v4 import code_hashes
from scripts.ragtruth_score import _interval
from scripts.score_v4 import score_records, _summary, load_prediction_journal, render_report


def paired_comparison(rows, *, samples=2000, seed=20261023):
    if type(samples) is not int or samples < 0:
        raise ValueError("Bootstrap sample count must be nonnegative")
    reference, candidate = BACKENDS
    pairs = defaultdict(dict)
    groups = defaultdict(list)
    for row in rows:
        if row["backend"] not in BACKENDS or row["backend"] in pairs[row["id"]]:
            raise ValueError("Unexpected or duplicate paired backend")
        pairs[row["id"]][row["backend"]] = row
        groups[row["source_id"]].append(row)
    if any(set(pair) != set(BACKENDS) for pair in pairs.values()):
        raise ValueError("Every case must have both observations, including failures")
    changes, cases = Counter(), []
    def state(row):
        return "unknown" if row["y_pred"] is None else "correct" if row["y_pred"] == row["y_true"] else "wrong"
    for identifier, pair in pairs.items():
        a, b = pair[reference], pair[candidate]
        if a["source_id"] != b["source_id"] or a["y_true"] != b["y_true"]:
            raise ValueError("Paired source/gold mismatch")
        changes[state(a) + "_to_" + state(b)] += 1
        if a["y_pred"] != b["y_pred"] or a["status"] != b["status"]:
            cases.append({"id": identifier, "source_id": a["source_id"], "native_positive": a["y_true"],
                          "reference": {"detected": a["y_pred"], "status": a["status"]},
                          "combined": {"detected": b["y_pred"], "status": b["status"]}})
    names = ("resolved_f1", "decision_coverage", "correct_decisions_per_all_cases", "complete_case_rate")
    def delta(items):
        summaries = [_summary([r for r in items if r["backend"] == name]) for name in BACKENDS]
        def values(s):
            return (s["resolved_only"]["f1"]["value"], s["decision_coverage"]["value"],
                    s["correct_decisions_per_all_cases"]["value"], s["complete_case_rate"]["value"])
        return [b - a if a is not None and b is not None else None for a, b in zip(*map(values, summaries))]
    points = delta(rows)
    draws = [[] for _ in names]
    rng, sources = random.Random(seed), sorted(groups)
    for _ in range(samples):
        sampled = [row for source in rng.choices(sources, k=len(sources)) for row in groups[source]]
        for bucket, value in zip(draws, delta(sampled)):
            if value is not None:
                bucket.append(value)
    return {"reference": reference, "candidate": candidate, "transition_counts": dict(changes),
            "case_changes": cases, "source_cluster_count": len(sources),
            "method": "paired whole-source percentile bootstrap; descriptive exposed-dev uncertainty",
            "confidence_level": 0.95, "samples": samples, "seed": seed,
            "deltas": {name: _interval(bucket, samples, point) for name, bucket, point in zip(names, draws, points)},
            "limitation": "Native answer labels only; label flips are not claim-level semantic corrections; no causal attribution to individual H1/H2/H3"}


def runtime_diagnostics(records, prices):
    result = {}
    for backend in BACKENDS:
        rows = [r for r in records if r["backend"] == backend]
        usage = usage_summary(rows)
        stage_calls, requery_reasons, errors, fingerprints, models = Counter(), Counter(), Counter(), Counter(), Counter()
        counters = Counter()
        quote_chars = []
        for row in rows:
            telemetry = row.get("telemetry") or {}
            for call in telemetry.get("calls", []):
                stage_calls[call.get("stage", "unknown")] += 1
                fingerprints[str(call.get("system_fingerprint"))] += 1
                models[str(call.get("model"))] += 1
            for event in telemetry.get("targeted_reasks", []):
                requery_reasons[event.get("reason", "unknown")] += 1
            if row.get("error"):
                errors[row["error"]["code"]] += 1
            for key, value in telemetry.get("summary", {}).items():
                if isinstance(value, int) and not isinstance(value, bool):
                    counters[key] += value
            for claim in (telemetry.get("extraction") or {}).get("claims", []):
                counters["extracted_claim_count"] += 1
                counters["fallback_claim_count"] += bool(claim.get("extraction_fallback"))
            for claim in (row.get("prediction") or {}).get("claims", []):
                quote_chars.extend(len(c["quote"]) for c in claim["citations"])
        latencies = sorted(r["latency_seconds"] for r in rows)
        import math
        result[backend] = {"record_count": len(rows), "usage": usage, "cost": cost_summary(usage, prices),
                           "mean_latency_seconds": sum(latencies) / len(latencies) if latencies else None,
                           "p95_latency_seconds": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
                           "stage_calls": dict(stage_calls), "targeted_requery_reasons": dict(requery_reasons),
                           "summary_totals": dict(counters), "errors": dict(errors),
                           "returned_models": dict(models), "returned_system_fingerprints": dict(fingerprints),
                           "mean_quote_chars": sum(quote_chars) / len(quote_chars) if quote_chars else None,
                           "quote_count": len(quote_chars),
                           "warning": "Text accounting, exact quotes, and completed claims do not establish semantic recall or evidence sufficiency"}
    return result


def summarize(run_dir: Path, data_dir: Path, output_dir: Path, *, samples=2000):
    config, progress = _object(run_dir / "config.json"), _object(run_dir / "progress.json")
    if config.get("schema_version") != SCHEMA or config.get("backends") != list(BACKENDS):
        raise ValueError("Not a combined paired development run")
    if progress.get("status") != "completed" or not progress.get("source_unchanged") or not progress.get("data_unchanged"):
        raise ValueError("Incomplete/changed run cannot be summarized as a complete comparison")
    for name, digest in config["code_files_sha256"].items():
        if _sha(run_dir / "source" / name) != digest:
            raise ValueError("Archived implementation hash mismatch")
    if code_hashes(ROOT) != config["code_files_sha256"]:
        raise ValueError("Current scoring/dependency code differs from the run freeze; execute the archived scorer")
    hashes = {name: _sha(data_dir / name) for name in config["data_files_sha256"]}
    if hashes != config["data_files_sha256"]:
        raise ValueError("Evaluation data hash mismatch")
    chosen = set(config["selection"]["response_ids"])
    inputs, manifest, gold = ([r for r in _jsonl(data_dir / name) if r["id"] in chosen]
                              for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl"))
    records = load_prediction_journal(run_dir / "predictions.jsonl")
    if len(records) != len(chosen) * len(BACKENDS) or progress["completed_records"] != len(records):
        raise ValueError("Complete comparison must include every paired record")
    report = score_records(records, manifest, gold, backends=BACKENDS, inputs=inputs,
                           bootstrap_samples=samples, prices=config.get("price_reference"))
    report["qualification"] = config["qualification"]
    report["combined_paired_comparison"] = paired_comparison(report["case_results"], samples=samples)
    report["runtime_diagnostics"] = runtime_diagnostics(records, config.get("price_reference"))
    report["input_hashes"] = {**hashes, "predictions.jsonl": _sha(run_dir / "predictions.jsonl"),
                              "config.json": _sha(run_dir / "config.json")}
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "report.json", report, exclusive=True)
    text = render_report(report)
    text += "\nPaired source-cluster differences and runtime details are in report.json. Native FP is not author-adjudicated true FP.\n"
    text += "\n| Backend | Calls | Mean / P95 seconds | Reference USD | Mean quote characters |\n| --- | ---: | ---: | ---: | ---: |\n"
    for backend, item in report["runtime_diagnostics"].items():
        text += f"| {backend} | {item['usage']['calls']} | {item['mean_latency_seconds']:.2f} / {item['p95_latency_seconds']:.2f} | {item['cost']['estimated_amount']} | {item['mean_quote_chars']} |\n"
    (output_dir / "report.md").write_text(text, encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dataset/ragtruth-blind-v1/recovery")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args()
    summarize(args.run_dir, args.data_dir, args.output_dir, samples=args.bootstrap_samples)
    print(json.dumps({"output_dir": str(args.output_dir), "model_calls": 0}))
