#!/usr/bin/env python3
"""Versioned partial-aware scoring; historical scoring and native labels stay intact."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import random
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.scoring import fraction, score_case
from grounding.contracts import VerificationError
from grounding.contracts_v4 import validate_v4_report
from scripts import ragtruth_score as legacy
from scripts.benchmark_ragtruth import _jsonl, _object, _sha, _write_json
from scripts.validate_dataset import strict_json_loads, validate_prediction

SCHEMA = "ragtruth-partial-detection-v4.0"


def load_prediction_journal(path: Path) -> list[dict]:
    """Keep malformed model text in telemetry; strictly validate public fields."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key in prediction journal")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Non-finite JSON constant in prediction journal: " + value)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line, object_pairs_hook=pairs, parse_constant=invalid_constant)
        if not isinstance(row, dict):
            raise ValueError("Prediction journal rows must be objects")
        # Only raw diagnostics may retain malformed Unicode. Prediction/source/
        # identity metadata still obey the established strict JSON contract.
        strict_json_loads(json.dumps({key: value for key, value in row.items() if key != "telemetry"},
                                    ensure_ascii=True, allow_nan=False))
        rows.append(row)
    return rows


def validate_v4_prediction(prediction: Any, contexts: list[str] | None = None) -> list:
    """Check complete and partial envelopes without turning execution errors into U."""
    if contexts is not None:
        try:
            validate_v4_report(prediction, contexts)
            return []
        except VerificationError as exc:
            return [exc.message]
    # Legacy complete records can use their frozen runner's source diagnostic.
    # A partial envelope requires actual inputs and the shared public contract.
    if isinstance(prediction, dict) and prediction.get("status") == "partial":
        return ["partial scoring requires source inputs for public-contract validation"]
    return legacy._structural_errors(prediction)


def _observe(meta: dict, gold: dict, backend: str, record: dict | None, contexts: list[str] | None = None) -> dict:
    prediction = (record or {}).get("prediction")
    errors = validate_v4_prediction(prediction, contexts)
    usable = (record is not None and record.get("error") is None and not errors
              and ("schema_valid" not in record or record["schema_valid"] is True)
              and not record.get("validation_errors"))
    partial = usable and prediction.get("status") == "partial"
    claims = prediction["claims"] if usable else []
    failed = len(prediction["errors"]) if partial else 0
    total_known = usable
    completion = (record or {}).get("telemetry", {}).get("completion")
    completion_valid = False
    if isinstance(completion, dict):
        total, done, unfinished, nonfactual = (completion.get(k, 0) for k in
                                              ("total_extracted", "completed", "unfinished", "non_factual_fallbacks"))
        done_ids, failed_ids = completion.get("completed_claim_ids"), completion.get("unfinished_claim_ids")
        if (all(type(n) is int and 0 <= n <= 64 for n in (total, done, unfinished, nonfactual))
                and total == done + unfinished + nonfactual
                and isinstance(done_ids, list) and isinstance(failed_ids, list)
                and all(isinstance(i, str) and bool(i) for i in done_ids + failed_ids)
                and len(done_ids) == len(set(done_ids)) == done
                and len(failed_ids) == len(set(failed_ids)) == unfinished
                and not set(done_ids) & set(failed_ids)):
            completion_valid = not usable or (done == len(claims) and unfinished == failed
                               and (not partial or set(failed_ids) == {e["id"] for e in prediction["errors"]}))
            if completion_valid and not usable:
                # Nothing from an invalid/error report is a completed public
                # claim, but a trustworthy extraction total must not disappear.
                failed, total_known = total - nonfactual, True
    detected = any(c["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for c in claims)
    outcome = "detected" if usable and detected else "unknown" if not usable or partial else "clean"
    return {"id": meta["id"], "source_id": meta["source_id"], "backend": backend,
            "task_type": meta["task_type"], "generator": meta["generator"],
            "y_true": bool(gold["labels"]), "y_pred": True if outcome == "detected" else False if outcome == "clean" else None,
            "outcome": outcome, "status": "partial" if partial else "complete" if usable else "error",
            "completed_claims": len(claims), "failed_claims": failed,
            "claim_total_known": total_known, "completion_telemetry_valid": completion_valid,
            "structural_errors": errors if not usable else [],
            "empty_claims": usable and not claims,
            "nonempty_answer_empty_claims": usable and not claims and bool((record or {}).get("answer_chars", meta.get("answer_chars", 0)))}


def _summary(rows: list[dict]) -> dict:
    counts = Counter({key: 0 for key in ("tp", "fp", "tn", "fn", "unknown_positive", "unknown_negative")})
    for row in rows:
        if row["y_pred"] is None:
            key = "unknown_positive" if row["y_true"] else "unknown_negative"
        elif row["y_true"]:
            key = "tp" if row["y_pred"] else "fn"
        else:
            key = "fp" if row["y_pred"] else "tn"
        counts[key] += 1
    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    resolved = tp + fp + tn + fn
    completed = sum(r["completed_claims"] for r in rows)
    failed = sum(r["failed_claims"] for r in rows)
    status = Counter(r["status"] for r in rows)
    positive_count = sum(r["y_true"] for r in rows)
    return {"total_count": len(rows), "confusion": dict(counts), "status_counts": dict(status),
            "native_fn_zero_target": "not_met" if fn else "not_evaluable" if not positive_count or counts["unknown_positive"] else "met",
            "native_fn_zero_target_policy": "Requires at least one native positive and no FN or unresolved native positive; unknown cannot manufacture FN=0",
            "resolved_only": {"precision": fraction(tp, tp + fp), "recall": fraction(tp, tp + fn),
                              "f1": fraction(2 * tp, 2 * tp + fp + fn), "accuracy": fraction(tp + tn, resolved)},
            "decision_coverage": fraction(resolved, len(rows)),
            "complete_case_rate": fraction(status["complete"], len(rows)),
            "technical_failure_rate": fraction(status["partial"] + status["error"], len(rows)),
            "correct_decisions_per_all_cases": fraction(tp + tn, len(rows)),
            "completed_claim_count": completed, "known_failed_claim_count": failed,
            "empty_claims_count": sum(r["empty_claims"] for r in rows),
            "nonempty_answer_empty_claims_count": sum(r["nonempty_answer_empty_claims"] for r in rows),
            "claim_completion_known_cases": fraction(completed, completed + failed),
            "unknown_claim_total_case_count": sum(not r["claim_total_known"] for r in rows)}


def _partial_bootstrap(rows: list[dict], names: list[str], samples: int, seed: int) -> dict:
    """Source-group uncertainty for the new metrics, separate from legacy bounds."""
    sources = sorted({r["source_id"] for r in rows})
    groups = {sid: [r for r in rows if r["source_id"] == sid] for sid in sources}
    metric_names = ("resolved_f1", "decision_coverage", "correct_decisions_per_all_cases")
    def metrics(items):
        s = _summary(items)
        return (s["resolved_only"]["f1"]["value"], s["decision_coverage"]["value"], s["correct_decisions_per_all_cases"]["value"])
    points = {name: metrics([r for r in rows if r["backend"] == name]) for name in names}
    values = {name: [[], [], []] for name in names}
    pairs = [(candidate, reference) for candidate in names if candidate.startswith("optimized-v4")
             for reference in ("minimal", "optimized-v3") if reference in names]
    differences = {pair: [[], [], []] for pair in pairs}
    rng = random.Random(seed)
    for _ in range(samples):
        draw = [row for sid in rng.choices(sources, k=len(sources)) for row in groups[sid]] if sources else []
        estimates = {name: metrics([r for r in draw if r["backend"] == name]) for name in names}
        for name in names:
            for j, value in enumerate(estimates[name]):
                if value is not None:
                    values[name][j].append(value)
        for candidate, reference in pairs:
            for j, (a, b) in enumerate(zip(estimates[candidate], estimates[reference])):
                if a is not None and b is not None:
                    differences[(candidate, reference)][j].append(a - b)
    return {"method": "pooled_source_cluster_percentile", "samples": samples, "seed": seed,
            "cluster_count": len(sources), "conditional_metric_warning": "Resolved F1 may condition on different cases; read joint coverage and all-case decision yield",
            "backends": {name: {metric: legacy._interval(values[name][j], samples, points[name][j])
                                for j, metric in enumerate(metric_names)} for name in names},
            "paired": {f"{candidate}_minus_{reference}": {metric: legacy._interval(differences[(candidate, reference)][j], samples,
                         points[candidate][j] - points[reference][j] if points[candidate][j] is not None and points[reference][j] is not None else None)
                         for j, metric in enumerate(metric_names)} for candidate, reference in pairs}}


def score_records(records: list[dict], manifest: list[dict], gold: list[dict], *,
                  backends: list[str] | tuple[str, ...] | None = None,
                  bootstrap_samples: int = 2000, seed: int = 20261022, prices: dict | None = None,
                  inputs: list[dict] | None = None) -> dict:
    # The old scorer independently validates joins/duplicates and supplies the
    # deliberately unchanged whole-case-failure comparison, including partials.
    old = legacy.score_records(records, manifest, gold, backends=backends,
                               bootstrap_samples=bootstrap_samples, seed=seed, prices=prices)
    names = list(old["backends"])
    record_map = {(r["id"], r["backend"]): r for r in records}
    gold_map = {r["id"]: r for r in gold}
    input_map = legacy._index(inputs, "inputs") if inputs is not None else {}
    if inputs is not None and set(input_map) != set(gold_map):
        raise ValueError("Inputs must exactly match manifest IDs")
    rows = [_observe(m, gold_map[m["id"]], b, record_map.get((m["id"], b)),
                     input_map[m["id"]]["input"]["context_passages"] if inputs is not None else None)
            for m in manifest for b in names]
    summaries = {}
    for name in names:
        selected = [r for r in rows if r["backend"] == name]
        summary = _summary(selected)
        summary["by_task"] = {task: _summary([r for r in selected if r["task_type"] == task])
                              for task in sorted({r["task_type"] for r in selected})}
        summaries[name] = summary
    return {"schema_version": SCHEMA, "manifest_count": len(manifest), "backends": summaries,
            "overall": _summary(rows), "case_results": rows, "legacy_whole_case_failure": old,
            "partial_aware_bootstrap": _partial_bootstrap(rows, names, bootstrap_samples, seed),
            "policy": {"positive": "any completed valid C/U claim", "negative": "complete output without C/U",
                       "unknown": "partial all-S or execution/contract failure; never TN or FN",
                       "claim_coverage": "completed/(completed+failed) only where extraction total is known; other cases counted separately",
                       "native_claim_accuracy": "not available: RAGTruth has no full claim/verdict/evidence gold",
                       "human_adjudication": "separate report only; never replaces native labels",
                       "resolved_metrics": "conditional on resolved outputs; always read with decision coverage and unknown counts"}}


def score_claim_case(case: dict, prediction: Any, error: Any = None) -> dict:
    """Optional claim-gold diagnostic; does not invent claim gold for RAGTruth."""
    issues = validate_v4_prediction(prediction, case["input"]["context_passages"])
    usable = error is None and not issues
    completed = prediction["claims"] if usable else []
    result = score_case(case, {"claims": completed})
    matched = result["strict"]["matched_claim_count"]
    correct = result["strict"]["correct_claim_count"]
    return {"execution_status": "partial" if usable and prediction.get("status") == "partial" else "complete" if usable else "error",
            "validation_errors": issues, "completed_aligned_verdict_accuracy": fraction(correct, matched),
            "gold_alignment_coverage": fraction(matched, len(case["expected"]["claims"])),
            "completed_claim_count": len(completed),
            "unmatched_completed_claim_count": result["strict"]["extra_claim_count"],
            "alignment_diagnostic": result,
            "legacy_whole_case_failure": score_case(case, prediction, error),
            "note": "Accuracy only on completed text-aligned claims; coverage and unmatched claims are mandatory diagnostics."}


def render_report(report: dict) -> str:
    lines = ["# RAGTruth v4 partial-aware evaluation", "",
             "Native labels are unchanged. Unknown outcomes never enter TN/FN. Conditional metrics require coverage.", "",
             "| Backend | Complete | Partial | Error | TP / FP / TN / FN | Unknown + / - | Decision coverage | Resolved F1 | Legacy F1 lower bound |",
             "| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |"]
    for name, item in report["backends"].items():
        c, s = item["confusion"], item["status_counts"]
        old = report["legacy_whole_case_failure"]["backends"][name]
        lines.append(f"| {name} | {s.get('complete',0)} | {s.get('partial',0)} | {s.get('error',0)} | "
                     f"{c['tp']} / {c['fp']} / {c['tn']} / {c['fn']} | {c['unknown_positive']} / {c['unknown_negative']} | "
                     f"{legacy._percent(item['decision_coverage'])} | {legacy._percent(item['resolved_only']['f1'])} | {legacy._percent(old['detection_f1'])} |")
    lines += ["", "Claim completion counts are not semantic extraction coverage. RAGTruth supplies no complete claim gold.",
              "All technical partials remain whole-case failures in the legacy comparison. Full metrics, costs and uncertainty are in report.json.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args(argv)
    config = _object(args.run_dir / "config.json")
    if config.get("mode") == "test":
        freeze_path = Path(config["freeze_manifest"])
        freeze = _object(freeze_path)
        if _sha(freeze_path) != config.get("freeze_sha256"):
            raise ValueError("Run freeze hash mismatch")
        for field in ("data_files_sha256", "selection", "backends", "settings", "v4_config", "run_options", "code_files_sha256"):
            if freeze.get(field) != config.get(field):
                raise ValueError("Run configuration differs from formal freeze: " + field)
        for name, expected in config["code_files_sha256"].items():
            if _sha(ROOT / name) != expected:
                raise ValueError("Formal frozen scoring/dependency implementation changed")
    actual = {name: _sha(args.data_dir / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json")}
    if actual != config.get("data_files_sha256"):
        raise ValueError("Run/data hash mismatch")
    manifest, gold, inputs = (_jsonl(args.data_dir / name) for name in ("manifest.jsonl", "native_gold.jsonl", "inputs.jsonl"))
    selected = config.get("selection", {}).get("response_ids")
    if selected is not None:
        if len(set(selected)) != len(selected) or set(selected) - {m["id"] for m in manifest}:
            raise ValueError("Run selection IDs are invalid")
        manifest = [m for m in manifest if m["id"] in set(selected)]
        gold = [g for g in gold if g["id"] in set(selected)]
        inputs = [i for i in inputs if i["id"] in set(selected)]
    report = score_records(load_prediction_journal(args.run_dir / "predictions.jsonl"), manifest, gold, backends=config["backends"],
                           bootstrap_samples=args.bootstrap_samples, prices=config.get("price_reference"),
                           inputs=inputs)
    report["input_hashes"] = {**actual, "predictions.jsonl": _sha(args.run_dir / "predictions.jsonl"),
                              "config.json": _sha(args.run_dir / "config.json")}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(args.output_dir / "report.json", report, exclusive=True)
    (args.output_dir / "report.md").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"output_dir": str(args.output_dir), "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
