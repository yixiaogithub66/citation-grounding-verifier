#!/usr/bin/env python3
"""Offline RAGTruth response detection, without claim gold or text alignment.

Only this scoring stage reads native labels. It never calls a verifier or API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.scoring import cost_summary, fraction, usage_summary
from scripts.validate_dataset import CLAIM_FIELDS, VERDICTS, strict_json_loads


LIMITATIONS = [
    "This is response-level hallucination detection on RAGTruth native labels, not an official span-localization score or atomic-claim accuracy. No complete atomic-claim gold is available.",
    "Native gold is positive exactly when labels is nonempty, including implicit_true and due_to_null annotations. Unmarked answer text is never converted into SUPPORTED claim gold.",
    "A valid response predicts positive if any claim is CONTRADICTED or UNSUPPORTED. A valid empty claims array predicts negative, including for a nonempty answer. Native detection does not measure claim extraction coverage.",
    "Answered-only precision, recall, F1 and accuracy condition on successful outputs. Request errors, malformed outputs and missing records remain in all-case coverage and end-to-end denominators; they are never treated as clean responses.",
    "The primary detection_f1 is an explicit pessimistic lower bound, not an official score: positive failures add false negatives and negative failures add false positives. Every failure is incorrect for end_to_end_accuracy.",
    "SUPPORTED / CONTRADICTED / UNSUPPORTED counts are an output distribution, not three-class classification accuracy. Exact citation substring validity is a mechanical check, not semantic citation quality.",
    "Scoring checks output structure independently. Source-dependent schema and exact-substring checks use runner-recorded diagnostics; absent diagnostics are reported as unknown and cannot be reconstructed without source text.",
    "Confidence intervals use percentile bootstrap resampling of whole source_id clusters, retaining all responses and backends for a sampled source. They do not isolate model sampling or API variation; undefined F1 replicates are reported and excluded from its percentile interval.",
    "Usage and latency include recorded failed attempts. Missing telemetry is unknown, not zero. Cost uses explicitly supplied prices and recorded usage, not provider billing.",
]


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _index(rows: list[dict], name: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{name} must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("id")):
            raise ValueError(f"{name} rows require a nonempty string id")
        if row["id"] in result:
            raise ValueError(f"Duplicate {name} id: {row['id']}")
        result[row["id"]] = row
    return result


def _structural_errors(prediction: Any) -> list[str]:
    """Validate the endpoint schema without inventing context passages."""
    if not isinstance(prediction, dict) or set(prediction) != {"claims"}:
        return ["prediction must have exactly the claims field"]
    claims = prediction["claims"]
    if not isinstance(claims, list):
        return ["claims must be an array"]
    errors = []
    if len(claims) > 64:
        errors.append("at most 64 claims are permitted")
    for position, claim in enumerate(claims):
        prefix = f"claims[{position}]"
        if not isinstance(claim, dict) or set(claim) != CLAIM_FIELDS:
            errors.append(prefix + " must have the exact endpoint claim fields")
            continue
        if not _text(claim["claim_text"]) or not _text(claim["reasoning"]):
            errors.append(prefix + " requires nonempty claim_text and reasoning")
        verdict = claim["verdict"]
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            errors.append(prefix + " has an invalid verdict")
        citations = claim["citations"]
        if not isinstance(citations, list):
            errors.append(prefix + ".citations must be an array")
            continue
        if len(citations) > 32:
            errors.append(prefix + " has more than 32 citations")
        if verdict in ("SUPPORTED", "CONTRADICTED") and not citations:
            errors.append(prefix + " requires citations")
        if verdict == "UNSUPPORTED" and citations:
            errors.append(prefix + " must not cite evidence for UNSUPPORTED")
        for citation in citations:
            if not isinstance(citation, dict):
                errors.append(prefix + " has a non-object citation")
                continue
            if not {"index", "quote"} <= citation.keys() or citation.keys() - {
                "index", "quote", "start_char", "end_char"
            }:
                errors.append(prefix + " has invalid citation fields")
            if not _integer(citation.get("index")) or not _text(citation.get("quote")):
                errors.append(prefix + " has an invalid citation index or quote")
            if "start_char" in citation or "end_char" in citation:
                start, end = citation.get("start_char"), citation.get("end_char")
                if not (_integer(start) and _integer(end) and start < end):
                    errors.append(prefix + " has invalid citation offsets")
                elif isinstance(citation.get("quote"), str) and end - start != len(citation["quote"]):
                    errors.append(prefix + " citation offsets do not match quote length")
        for text in [claim["claim_text"], claim["reasoning"], *[
            citation.get("quote") for citation in citations if isinstance(citation, dict)
        ]]:
            if isinstance(text, str):
                try:
                    text.encode("utf-8")
                except UnicodeEncodeError:
                    errors.append(prefix + " contains invalid Unicode")
    return errors


def _observation(item: dict, gold: dict, backend: str, record: dict | None) -> dict:
    positive = bool(gold["labels"])
    prediction = record.get("prediction") if record is not None else None
    errors = _structural_errors(prediction) if prediction is not None else []
    outcome = "valid" if prediction is not None and not errors else "invalid" if prediction is not None else "not_returned"
    error = (record or {}).get("error")
    reported_invalid = bool((record or {}).get("validation_errors")) or (
        isinstance(error, dict) and error.get("code") == "invalid_model_output"
    )
    if reported_invalid or (prediction is not None and record is not None and record.get("schema_valid") is False):
        outcome = "invalid"
    if record is None:
        failure = "missing_record"
    elif reported_invalid:
        failure = "invalid_schema"
    elif record.get("error") is not None:
        failure = "request_error"
    elif prediction is None:
        failure = "missing_prediction"
    elif errors:
        failure = "invalid_schema"
    elif record.get("schema_valid") is False or record.get("validation_errors"):
        failure = "invalid_schema"
        outcome = "invalid"
    elif "schema_valid" in record and not isinstance(record["schema_valid"], bool):
        failure = "invalid_schema_metadata"
    else:
        failure = None
    success = failure is None
    claims = prediction["claims"] if success else []
    detected = any(claim["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for claim in claims) if success else None
    answer_chars = (record or {}).get("answer_chars", item.get("answer_chars"))
    if not _integer(answer_chars):
        answer_chars = None
    return {
        "id": item["id"], "source_id": item["source_id"], "task_type": item["task_type"],
        "generator": item["generator"], "backend": backend,
        "y_true": positive, "y_pred": detected, "success": success, "failure": failure,
        "structural_errors": errors, "schema_outcome": outcome,
        "context_validation_recorded": record is not None and isinstance(record.get("schema_valid"), bool),
        "claims": claims, "answer_chars": answer_chars, "record": record,
    }


COUNT_KEYS = ("tp", "fp", "tn", "fn", "positive_failures", "negative_failures")


def _counts(observations: list[dict]) -> Counter:
    counts = Counter({key: 0 for key in COUNT_KEYS})
    for row in observations:
        if not row["success"]:
            key = "positive_failures" if row["y_true"] else "negative_failures"
        elif row["y_true"]:
            key = "tp" if row["y_pred"] else "fn"
        else:
            key = "fp" if row["y_pred"] else "tn"
        counts[key] += 1
    return counts


def _metric_values(counts: Counter) -> tuple[float | None, float | None]:
    tp, fp, tn, fn, pf, nf = (counts[key] for key in COUNT_KEYS)
    f1_denom = 2 * tp + fp + fn + pf + nf
    total = tp + fp + tn + fn + pf + nf
    return (2 * tp / f1_denom if f1_denom else None, (tp + tn) / total if total else None)


def _aggregate(observations: list[dict], prices: dict | None = None) -> dict:
    counts = _counts(observations)
    tp, fp, tn, fn, pf, nf = (counts[key] for key in COUNT_KEYS)
    success = tp + fp + tn + fn
    total = success + pf + nf
    records = [row["record"] for row in observations if row["record"] is not None]
    verdicts = Counter(claim["verdict"] for row in observations for claim in row["claims"])
    empty = [row for row in observations if row["success"] and not row["claims"]]
    latencies = sorted(
        record["latency_seconds"] for record in records
        if isinstance(record.get("latency_seconds"), (int, float))
        and not isinstance(record["latency_seconds"], bool)
        and math.isfinite(record["latency_seconds"]) and record["latency_seconds"] >= 0
    )
    telemetry_records = [record for record in records if isinstance(record.get("telemetry"), dict)
                         and isinstance(record["telemetry"].get("calls"), list)]
    usage = usage_summary(telemetry_records)
    usage["records_missing_telemetry"] = total - len(telemetry_records)
    if usage["records_missing_telemetry"]:
        usage["usage_complete"] = False
        usage["cache_usage_complete"] = False
        usage["reasoning_usage_complete"] = False
    cost = cost_summary(usage, prices)
    citations = {"citation_count": 0, "checked_citation_count": 0, "valid_exact_citation_count": 0,
                 "records_with_diagnostics": 0, "records_without_diagnostics": 0}
    for record in records:
        payload = record.get("prediction")
        if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
            citations["citation_count"] += sum(
                len(claim["citations"]) for claim in payload["claims"]
                if isinstance(claim, dict) and isinstance(claim.get("citations"), list)
            )
        diagnostic = record.get("citations")
        if (isinstance(diagnostic, dict) and _integer(diagnostic.get("citation_count"))
                and _integer(diagnostic.get("valid_citation_count"))
                and diagnostic["valid_citation_count"] <= diagnostic["citation_count"]):
            citations["records_with_diagnostics"] += 1
            citations["checked_citation_count"] += diagnostic["citation_count"]
            citations["valid_exact_citation_count"] += diagnostic["valid_citation_count"]
        else:
            citations["records_without_diagnostics"] += 1
    citations["records_without_diagnostics"] += total - len(records)
    citations["exact_substring_rate"] = fraction(citations["valid_exact_citation_count"], citations["checked_citation_count"])
    return {
        "total_count": total, "success_count": success, "error_count": pf + nf,
        "record_count": len(records), "missing_record_count": total - len(records),
        "source_count": len({row["source_id"] for row in observations}),
        "positive_count": tp + fn + pf, "negative_count": fp + tn + nf,
        "coverage": fraction(success, total), "confusion": dict(counts),
        "answered_only": {
            "denominator_scope": "Only successful schema-valid predictions; failures excluded from these conditional metrics.",
            "answered_count": success, "answered_positive_count": tp + fn,
            "answered_negative_count": fp + tn,
            "precision": fraction(tp, tp + fp), "recall": fraction(tp, tp + fn),
            "f1": fraction(2 * tp, 2 * tp + fp + fn), "accuracy": fraction(tp + tn, success),
        },
        "detection_f1": fraction(2 * tp, 2 * tp + fp + fn + pf + nf),
        "detection_f1_kind": "pessimistic_failure_lower_bound_not_official",
        "conservative_confusion": {"tp": tp, "fp": fp + nf, "tn": tn, "fn": fn + pf},
        "end_to_end_accuracy": fraction(tp + tn, total),
        "failure_counts": dict(sorted(Counter(row["failure"] for row in observations if row["failure"]).items())),
        "schema_outcomes": {key: sum(row["schema_outcome"] == key for row in observations)
                            for key in ("valid", "invalid", "not_returned")},
        "context_validation_recorded_count": sum(row["context_validation_recorded"] for row in observations),
        "verdict_counts": {verdict: verdicts[verdict] for verdict in VERDICTS},
        "verdict_counts_scope": "Output distribution on successful predictions, not classification accuracy.",
        "empty_claims_count": len(empty),
        "nonempty_answer_empty_claims": sum(row["answer_chars"] is not None and row["answer_chars"] > 0 for row in empty),
        "empty_answer_empty_claims": sum(row["answer_chars"] == 0 for row in empty),
        "empty_claims_answer_length_unknown": sum(row["answer_chars"] is None for row in empty),
        "citations": citations,
        "latency": {
            "measured_count": len(latencies), "unknown_count": total - len(latencies),
            "mean_seconds": statistics.mean(latencies) if latencies else None,
            "p50_seconds": latencies[math.ceil(0.50 * len(latencies)) - 1] if latencies else None,
            "p95_seconds": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
            "total_recorded_seconds": sum(latencies),
        },
        "usage": usage, "cost": cost,
    }


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    left, right = math.floor(position), math.ceil(position)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def _interval(values: list[float], samples: int, point: float | None) -> dict:
    return {"point_estimate": point, "low": _percentile(values, 0.025), "high": _percentile(values, 0.975),
            "defined_replicates": len(values), "undefined_replicates": samples - len(values)}


def _bootstrap(observations: list[dict], backends: list[str], samples: int, seed: int) -> tuple[dict, dict]:
    source_ids = sorted({row["source_id"] for row in observations})
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in observations:
        groups[(row["source_id"], row["backend"])].append(row)
    cluster_counts = {key: _counts(rows) for key, rows in groups.items()}
    names = ["overall", *backends]
    points = {name: _metric_values(_counts([
        row for row in observations if name == "overall" or row["backend"] == name
    ])) for name in names}
    values = {name: ([], []) for name in names}
    candidates = [name for name in backends if name.startswith("optimized") and "minimal" in backends]
    paired_values = {name: ([], []) for name in candidates}
    rng = random.Random(seed)
    for _ in range(samples):
        multiplicities = Counter(rng.choices(source_ids, k=len(source_ids))) if source_ids else Counter()
        draw_counts = {name: Counter() for name in names}
        for source_id, multiplicity in multiplicities.items():
            for backend in backends:
                counts = cluster_counts.get((source_id, backend), {})
                for key, count in counts.items():
                    draw_counts[backend][key] += multiplicity * count
                    draw_counts["overall"][key] += multiplicity * count
        draw_metrics = {name: _metric_values(counts) for name, counts in draw_counts.items()}
        for name in names:
            for index, value in enumerate(draw_metrics[name]):
                if value is not None:
                    values[name][index].append(value)
        for candidate in candidates:
            for index, (left, right) in enumerate(zip(draw_metrics["minimal"], draw_metrics[candidate])):
                if left is not None and right is not None:
                    paired_values[candidate][index].append(right - left)
    info = {"method": "source_cluster_percentile", "confidence_level": 0.95,
            "cluster_key": "source_id", "cluster_count": len(source_ids), "samples": samples, "seed": seed,
            "resampling_unit": "whole source with all responses and backends"}
    intervals = {
        name: {**info, **{metric: _interval(values[name][index], samples, points[name][index])
                         for index, metric in enumerate(("detection_f1", "end_to_end_accuracy"))}}
        for name in names
    }
    paired = {}
    for candidate in candidates:
        differences = [right - left if left is not None and right is not None else None
                       for left, right in zip(points["minimal"], points[candidate])]
        paired[f"{candidate}_minus_minimal"] = {
            **info, "reference": "minimal", "candidate": candidate,
            "paired_response_count": sum(row["backend"] == candidate for row in observations),
            "scope": "All manifest responses, including failures; identical source draws for both backends.",
            **{metric: _interval(paired_values[candidate][index], samples, differences[index])
               for index, metric in enumerate(("detection_f1", "end_to_end_accuracy"))},
        }
    return intervals, paired


def score_records(
    records: list[dict], manifest: list[dict], gold: list[dict], *,
    bootstrap_samples: int = 2000, seed: int = 20261022,
    backends: list[str] | tuple[str, ...] | None = None, prices: dict | None = None,
) -> dict:
    """Score every manifest x backend slot; absent records are failures.

    Explicit ``backends`` is required for an entirely empty record file and
    should be supplied from run configuration to include wholly missing runs.
    Undefined ratios (zero denominator) are None, never silently coerced to 0.
    """
    if not _integer(bootstrap_samples) or not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("bootstrap_samples must be a nonnegative integer and seed an integer")
    manifest_by_id, gold_by_id = _index(manifest, "manifest"), _index(gold, "gold")
    if manifest_by_id.keys() != gold_by_id.keys():
        raise ValueError("Gold ids must exactly match manifest ids (missing or extra gold)")
    for item in manifest:
        if any(not _text(item.get(field)) for field in ("source_id", "task_type", "generator")):
            raise ValueError("Manifest rows require source_id, task_type and generator strings")
        native = gold_by_id[item["id"]]
        if native.get("source_id") != item["source_id"]:
            raise ValueError(f"Gold source_id mismatch: {item['id']}")
        if not isinstance(native.get("labels"), list):
            raise ValueError("Gold labels must be an array")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    record_map = {}
    for record in records:
        if not isinstance(record, dict) or not _text(record.get("id")) or not _text(record.get("backend")):
            raise ValueError("Records require nonempty id and backend strings")
        if record["id"] not in manifest_by_id:
            raise ValueError(f"Record id is absent from manifest: {record['id']}")
        key = (record["id"], record["backend"])
        if key in record_map:
            raise ValueError(f"Duplicate record id/backend: {key}")
        for field in ("source_id", "task_type", "generator", "input_sha256"):
            if field in record and record[field] != manifest_by_id[record["id"]].get(field):
                raise ValueError(f"Record {field} mismatch: {record['id']}")
        record_map[key] = record
    if backends is None:
        backends = sorted({record["backend"] for record in records})
    else:
        if not isinstance(backends, (list, tuple)):
            raise ValueError("backends must be a list or tuple")
        backends = list(backends)
    if not backends or any(not _text(name) or name == "overall" for name in backends) or len(set(backends)) != len(backends):
        raise ValueError("Provide unique nonempty backends; 'overall' is reserved. Empty records require explicit backends.")
    if any(record["backend"] not in backends for record in records):
        raise ValueError("A record backend is not in the explicit backend list")
    observations = [
        _observation(item, gold_by_id[item["id"]], backend, record_map.get((item["id"], backend)))
        for item in sorted(manifest, key=lambda row: row["id"]) for backend in backends
    ]
    intervals, paired = _bootstrap(observations, list(backends), bootstrap_samples, seed)
    summaries = {}
    for backend in backends:
        rows = [row for row in observations if row["backend"] == backend]
        summary = _aggregate(rows, prices)
        summary["bootstrap"] = intervals[backend]
        for field, target in (("task_type", "by_task"), ("generator", "by_generator")):
            summary[target] = {value: _aggregate([row for row in rows if row[field] == value], prices)
                               for value in sorted({row[field] for row in rows})}
        summaries[backend] = summary
    overall = _aggregate(observations, prices)
    overall["bootstrap"] = intervals["overall"]
    return {
        "schema_version": "ragtruth-response-detection-v1", "task": "response_level_hallucination_detection",
        "manifest_count": len(manifest), "backend_count": len(backends),
        "expected_record_count": len(manifest) * len(backends),
        "zero_denominator_policy": "undefined ratios are null",
        "gold_positive_rule": "len(labels) > 0; no annotation types excluded",
        "prediction_positive_rule": "any valid claim verdict in {CONTRADICTED, UNSUPPORTED}",
        "gold_has_hallucination_disagreements": sum(
            "has_hallucination" in item and item["has_hallucination"] != bool(item["labels"]) for item in gold
        ),
        "overall": overall, "backends": summaries, "paired_comparisons": paired,
        "limitations": list(LIMITATIONS),
        "case_results": [
            {key: row[key] for key in ("id", "source_id", "backend", "task_type", "generator", "y_true", "y_pred", "success", "failure", "schema_outcome", "structural_errors")}
            for row in observations
        ],
    }


def _percent(metric: dict) -> str:
    value = metric.get("value")
    return f"{value:.2%} ({metric['numerator']}/{metric['denominator']})" if value is not None else f"undefined (0/{metric['denominator']})"


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_report(report: dict) -> str:
    """Render concise auditable Markdown, retaining denominators and caveats."""
    lines = [
        "# RAGTruth response-level hallucination detection", "",
        f"{report['manifest_count']} responses × {report['backend_count']} backends = {report['expected_record_count']} expected prediction records.", "",
        "Gold is positive when native `labels` is nonempty, including `implicit_true` and `due_to_null`. Prediction is positive when any valid claim is `CONTRADICTED` or `UNSUPPORTED`.", "",
        "Primary F1 is a **pessimistic failure lower bound**, not an official score: positive failures add FN; negative failures add FP. End-to-end accuracy counts every failure as incorrect. Values show numerator/denominator; undefined ratios remain undefined.", "",
        "| Backend | Successful / total | Errors | F1 lower bound | End-to-end accuracy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in report["backends"].items():
        lines.append(f"| {_escape(name)} | {summary['success_count']}/{summary['total_count']} | {summary['error_count']} | {_percent(summary['detection_f1'])} | {_percent(summary['end_to_end_accuracy'])} |")
    for name, summary in report["backends"].items():
        counts = summary["confusion"]
        lines += ["", f"## {_escape(name)}", "",
                  f"Answered confusion: TP {counts['tp']}, FP {counts['fp']}, TN {counts['tn']}, FN {counts['fn']}. Positive failures {counts['positive_failures']}; negative failures {counts['negative_failures']}; missing records {summary['missing_record_count']}.", "",
                  "Answered-only metrics condition on successful outputs:", ""]
        answered = summary["answered_only"]
        lines.append("; ".join(f"{key}: {_percent(answered[key])}" for key in ("precision", "recall", "f1", "accuracy")) + ".")
        bootstrap = summary["bootstrap"]
        lines += ["", f"95% source-cluster percentile intervals ({bootstrap['samples']} draws, {bootstrap['cluster_count']} source clusters, seed {bootstrap['seed']}):", ""]
        for metric in ("detection_f1", "end_to_end_accuracy"):
            interval = bootstrap[metric]
            bounds = f"[{interval['low']:.2%}, {interval['high']:.2%}]" if interval["low"] is not None else "undefined"
            lines.append(f"- {metric}: {bounds}; {interval['defined_replicates']} defined and {interval['undefined_replicates']} undefined draws.")
        lines += ["", f"Valid empty-claims outputs: {summary['empty_claims_count']}; nonempty answer with empty claims: **{summary['nonempty_answer_empty_claims']}**; empty answer: {summary['empty_answer_empty_claims']}; unknown answer length: {summary['empty_claims_answer_length_unknown']}. Empty claims predict negative; native detection does not assess extraction coverage.", "",
                  "Output verdict distribution (not three-class accuracy): " + ", ".join(f"{key} {value}" for key, value in summary["verdict_counts"].items()) + ".", ""]
        citation = summary["citations"]
        lines.append(f"Recorded exact citation substring validity: {_percent(citation['exact_substring_rate'])}; {citation['records_without_diagnostics']} records lack citation diagnostics. This does not measure semantic citation quality.")
        lines += ["", f"Schema outcomes: {_escape(summary['schema_outcomes'])}. Source-dependent validation recorded for {summary['context_validation_recorded_count']}/{summary['total_count']} records.", ""]
        for field, title in (("by_task", "Task"), ("by_generator", "Generator")):
            lines += [f"| {title} | Success / total | Errors | F1 lower bound | End-to-end accuracy |",
                      "| --- | ---: | ---: | ---: | ---: |"]
            for group, values in summary[field].items():
                lines.append(f"| {_escape(group)} | {values['success_count']}/{values['total_count']} | {values['error_count']} | {_percent(values['detection_f1'])} | {_percent(values['end_to_end_accuracy'])} |")
            lines.append("")
        usage, cost, latency = summary["usage"], summary["cost"], summary["latency"]
        amount = cost["estimated_amount"]
        rendered_cost = f"{cost['currency']} {amount:.6f}" if amount is not None else "unknown / incomplete"
        lines += [f"Recorded usage: {usage['calls']} calls, {usage['prompt_tokens']} input tokens, {usage['completion_tokens']} output tokens; complete: {usage['usage_complete']}. Estimated cost: {rendered_cost}.", "",
                  f"Latency: {latency['measured_count']} measured, {latency['unknown_count']} unknown; mean {latency['mean_seconds']} s; total recorded {latency['total_recorded_seconds']} s."]
    if report["paired_comparisons"]:
        lines += ["", "## Paired differences", "", "All manifest responses remain paired, including failures. Differences are candidate minus minimal using identical source-cluster draws.", "",
                  "| Comparison | Metric | Difference | 95% interval | Defined draws |", "| --- | --- | ---: | ---: | ---: |"]
        for name, comparison in report["paired_comparisons"].items():
            for metric in ("detection_f1", "end_to_end_accuracy"):
                values = comparison[metric]
                point = f"{100 * values['point_estimate']:.2f} pp" if values["point_estimate"] is not None else "undefined"
                bounds = f"[{100 * values['low']:.2f}, {100 * values['high']:.2f}] pp" if values["low"] is not None else "undefined"
                lines.append(f"| {_escape(name)} | {metric} | {point} | {bounds} | {values['defined_replicates']} |")
    lines += ["", "## Limitations", "", *[f"- {limitation}" for limitation in report["limitations"]]]
    if report.get("input_hashes"):
        lines += ["", "## Input hashes", "", "```json", json.dumps(report["input_hashes"], ensure_ascii=False, indent=2, sort_keys=True), "```"]
    return "\n".join(lines) + "\n"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"Blank JSONL line: {path.name}:{number}")
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object: {path.name}:{number}")
        rows.append(value)
    return rows


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(path: Path) -> dict:
    value = strict_json_loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _verify_run_bindings(config: dict, data_dir: Path, paths: dict[str, Path]) -> dict:
    """Check opaque artifact hashes before deserializing labels/predictions."""
    if config.get("schema_version") != "ragtruth-inference-run-v1":
        raise ValueError("Unrecognized inference config schema")
    expected = config.get("data_files_sha256")
    files = {"inputs.jsonl", "manifest.jsonl", "preparation.json", "native_gold.jsonl"}
    if not isinstance(expected, dict) or set(expected) != files:
        raise ValueError("Inference config is missing exact prepared-data hash bindings")
    data_paths = {name: data_dir / name for name in files}
    data_paths.update({"manifest.jsonl": paths["manifest"], "native_gold.jsonl": paths["gold"]})
    actual = {name: _sha(path) for name, path in data_paths.items()}
    if actual != expected:
        mismatches = sorted(name for name in files if actual[name] != expected[name])
        raise ValueError("Prepared data hash mismatch: " + ", ".join(mismatches))
    freeze_path, freeze_hash = config.get("freeze_manifest"), config.get("freeze_sha256")
    resolved_freeze = None
    if config.get("mode") == "formal" or freeze_path is not None or freeze_hash is not None:
        if not _text(freeze_path) or not _text(freeze_hash):
            raise ValueError("Inference freeze hash binding is missing or mismatched")
        resolved_freeze = Path(freeze_path)
        if not resolved_freeze.is_file():
            resolved_freeze = data_dir / "freeze.json"
        if not resolved_freeze.is_file() or _sha(resolved_freeze) != freeze_hash:
            raise ValueError("Inference freeze hash binding is missing or mismatched")
        freeze = _object(resolved_freeze)
        if freeze.get("schema_version") != "ragtruth-benchmark-freeze-v1":
            raise ValueError("Unrecognized benchmark freeze schema")
        for key in ("data_files_sha256", "selection", "backends", "price_reference", "settings", "run_options", "provenance"):
            if freeze.get(key) != config.get(key):
                raise ValueError("Inference config differs from freeze: " + key)
    return {"status": "verified", "data_files_sha256": actual, "freeze_sha256": freeze_hash,
            "resolved_freeze_manifest": str(resolved_freeze.resolve()) if resolved_freeze else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--data-dir", type=Path, help="Prepared dataset directory; defaults to config.json data_dir")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--gold", type=Path, help="Native gold JSONL; may remain outside the inference run directory")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--backends", nargs="+", help="Expected backend names; mandatory if no predictions exist")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--prices", type=Path, help="JSON object with explicit per-million token rates")
    args = parser.parse_args(argv)
    run = args.run_dir
    try:
        config_path = run / "config.json" if run else None
        config = _object(config_path) if config_path and config_path.exists() else None
        config_hash = _sha(config_path) if config is not None else None
        data_dir = args.data_dir or (Path(config["data_dir"]) if config and _text(config.get("data_dir")) else run)
        paths = {
            "predictions": args.predictions or (run / "predictions.jsonl" if run else None),
            "manifest": args.manifest or (data_dir / "manifest.jsonl" if data_dir else None),
            "gold": args.gold or (data_dir / "native_gold.jsonl" if data_dir else None),
        }
        if any(path is None for path in paths.values()):
            raise ValueError("Supply --run-dir or explicit --predictions and --data-dir (or --manifest plus --gold)")
        output = args.output_dir or run or paths["predictions"].parent
        if any((output / filename).exists() for filename in ("report.json", "report.md")):
            raise FileExistsError("Scoring report already exists; choose a fresh --output-dir to preserve the first report")
        binding = _verify_run_bindings(config, data_dir, paths) if config is not None and data_dir else {"status": "unbound_standalone_inputs"}
        before = {key: _sha(path) for key, path in paths.items()}
        prices = _object(args.prices) if args.prices else config.get("price_reference") if config else None
        if prices is not None and not isinstance(prices, dict):
            raise ValueError("Prices must be a JSON object")
        backends = args.backends or (config.get("backends") if config else None)
        if config is not None and args.backends is not None and args.backends != config.get("backends"):
            raise ValueError("Explicit backends must match run config exactly")
        records, manifest, gold = (_read_jsonl(paths[key]) for key in ("predictions", "manifest", "gold"))
        if config is not None:
            selection = config.get("selection", {})
            if selection.get("response_ids") != [row.get("id") for row in manifest]:
                raise ValueError("Manifest response selection differs from run config")
            input_hashes = {item.get("id"): item.get("input_sha256") for item in manifest}
            if any(row.get("input_sha256") != input_hashes.get(row.get("id")) for row in records):
                raise ValueError("Prediction input hash differs from selected manifest")
        if before != {key: _sha(path) for key, path in paths.items()} or (config is not None and _sha(config_path) != config_hash):
            raise ValueError("Scoring inputs changed while being read")
        report = score_records(
            records, manifest, gold, bootstrap_samples=args.bootstrap_samples, seed=args.seed, backends=backends, prices=prices,
        )
        report["input_hashes"] = {key: {"path": str(path.resolve()), "sha256": before[key]}
                                  for key, path in paths.items()}
        if config is not None:
            report["input_hashes"]["run_config"] = {"path": str(config_path.resolve()), "sha256": config_hash}
        report["run_binding_validation"] = binding
        output.mkdir(parents=True, exist_ok=True)
        for filename, content in (
            ("report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"),
            ("report.md", render_report(report)),
        ):
            target = output / filename
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"RAGTruth scoring failed: {exc}", file=sys.stderr)
        return 2
    print(f"Scored {report['expected_record_count']} expected records; report: {output / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
