#!/usr/bin/env python3
"""Offline paired behavior diagnostics, never an inference rule or unseen test.

The fixture metadata/expected labels stay in this evaluator. Only the ordinary
request and, in fixed-claim mode, a predeclared atomic claim enter the verifier.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.config_v4 import load_v4_config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.contracts_v4 import validate_v4_report
from grounding.factory import build_verifier
from grounding.scoring import align_claims, cost_summary, fraction, usage_summary
from scripts.benchmark_ragtruth import _jsonl, _now, _redact, _sha, _write_json, public_settings
from scripts.ragtruth_v4 import code_hashes

SCHEMA = "v4-behavioral-ai-draft-v1"
BACKENDS = ("optimized-v4.0", "optimized-v4-combined")
SUPPORTED_BACKENDS = (*BACKENDS, "optimized-v4-m1-faithful")
MODES = ("end_to_end", "fixed_claim")
LABELS = {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED"}
DEFAULT_DATASET = ROOT / "dataset/v4-behavioral-ai-draft/pairs.jsonl"


def load_pairs(path: Path) -> list[dict]:
    pairs = _jsonl(path)
    if not pairs or len({p.get("id") for p in pairs}) != len(pairs):
        raise ValueError("Behavior pairs must be nonempty and have unique IDs")
    for pair in pairs:
        required = {"schema_version", "id", "family", "domain", "provenance", "relation", "rationale", "base", "variant"}
        if set(pair) != required or pair["schema_version"] != SCHEMA:
            raise ValueError("Invalid behavior-pair schema")
        if pair["provenance"] != "AI-authored diagnostic draft; not author-approved gold; not unseen":
            raise ValueError("Draft fixture provenance must remain explicit")
        if any(not isinstance(pair[k], str) or not pair[k].strip() for k in ("id", "family", "domain", "rationale")):
            raise ValueError("Fixture identity, family, domain and rationale are required")
        if pair["relation"] not in ("same_label", "expected_transition"):
            raise ValueError("Unknown predeclared relation")
        for side in ("base", "variant"):
            case = pair[side]
            if not isinstance(case, dict) or set(case) != {"input", "fixed_claim_text", "expected_label", "required_passage_indices"}:
                raise ValueError("Invalid behavior case schema")
            request = VerificationRequest.from_dict(case["input"])
            if case["expected_label"] not in LABELS:
                raise ValueError("These diagnostic cases each declare exactly one factual target")
            if not isinstance(case["fixed_claim_text"], str) or not case["fixed_claim_text"].strip():
                raise ValueError("A predeclared factual claim is required for the fixed-claim control")
            indices = case["required_passage_indices"]
            if (not isinstance(indices, list) or len(indices) != len(set(indices))
                    or any(type(i) is not int or not 0 <= i < len(request.context_passages) for i in indices)
                    or case["expected_label"] == "UNSUPPORTED" and indices
                    or case["expected_label"] != "UNSUPPORTED" and not indices):
                raise ValueError("Invalid expected evidence indices")
        equal = pair["base"]["expected_label"] == pair["variant"]["expected_label"]
        if equal != (pair["relation"] == "same_label"):
            raise ValueError("Relation and predeclared labels disagree")
    return pairs


def fixed_claim_control(verifier, claim_text: str):
    """Use the same one-claim control for either backend; no label-dependent code.

    This is deliberately a local evaluator adapter, never reachable via /verify.
    Its location span records the full original answer, not a claim-text match.
    The fixture's atomic target is an AI draft and is not a human gold extraction.
    """
    def decompose(answer: str, telemetry: dict) -> list[dict]:
        claims = [{"id": "c1", "claim_text": claim_text, "source_span": answer,
                   "source_start": 0, "source_end": len(answer), "extraction_fallback": False}]
        telemetry["extraction"] = {
            "mode": "offline_fixed_claim_control", "claims": deepcopy(claims),
            "non_factual_spans": [], "chunks": [],
            "limitation": "AI-draft atomic target supplied by offline evaluator; no M1 call or semantic coverage claim.",
        }
        return claims
    verifier._decompose = decompose
    return verifier


def score_case(case: dict, prediction, error=None, *, telemetry=None) -> dict:
    """Whole-answer diagnostic, plus a separate literal alignment diagnostic.

    A partial answer may reveal a hallucination, but cannot establish its full
    three-label aggregate. All partial/error cases are unknown for exact labels.
    An empty complete output is NON_FACTUAL, never vacuous SUPPORTED.
    """
    validation_error = None
    if error is None and prediction is not None:
        try:
            validate_v4_report(prediction, case["input"]["context_passages"])
        except VerificationError as exc:
            validation_error = {"code": exc.code, "message": exc.message}
    valid = error is None and prediction is not None and validation_error is None
    claims = prediction["claims"] if valid else []
    errors = prediction.get("errors", []) if valid else []
    status = "partial" if errors else "complete" if valid else "error"
    verdicts = {row["verdict"] for row in claims}
    label = None
    if status == "complete":
        label = ("CONTRADICTED" if "CONTRADICTED" in verdicts else
                 "UNSUPPORTED" if "UNSUPPORTED" in verdicts else
                 "SUPPORTED" if claims else "NON_FACTUAL")
    expected = case["expected_label"]
    gold = [{"claim_text": case["fixed_claim_text"]}]
    alignment = align_claims(gold, claims, case["input"]["generated_answer"], approximate=True)
    matched = alignment["pairs"]
    aligned_correct = sum(claims[item["predicted_index"]]["verdict"] == expected for item in matched)
    used = {cite["index"] for row in claims for cite in row["citations"]}
    required = set(case["required_passage_indices"])
    completion = (telemetry or {}).get("completion") or {}
    if valid:
        known_total = len(claims) + len(errors)
        completed = len(claims)
    elif isinstance(completion.get("total_extracted"), int):
        known_total = completion["total_extracted"] - completion.get("non_factual_fallbacks", 0)
        completed = 0
    else:
        known_total, completed = None, 0
    return {
        "execution_status": status, "observed_label": label, "expected_label": expected,
        "expected_correct": label == expected, "validation_error": validation_error,
        "completed_claim_count": len(claims), "unfinished_claim_count": len(errors),
        "known_extracted_factual_count": known_total, "known_completed_factual_count": completed,
        "positive_detected_in_completed_claims": bool(verdicts & {"CONTRADICTED", "UNSUPPORTED"}),
        "gold_atomic_target_count": 1, "target_alignment": alignment,
        "aligned_target_count": len(matched), "aligned_target_correct_count": aligned_correct,
        "required_evidence_eligible": bool(required),
        "required_evidence_indices_present": bool(required) and required <= used,
        "required_evidence_present_and_label_correct": bool(required) and required <= used and label == expected,
        "note": "Aggregate label and lexical target alignment are diagnostics; neither certifies complete semantic extraction or citation sufficiency.",
    }


def _group_summary(rows: list[dict], prices=None) -> dict:
    scores = [row["score"] for row in rows]
    known = [score for score in scores if score["known_extracted_factual_count"] is not None]
    usage = usage_summary(rows)
    latency = sorted(row["latency_seconds"] for row in rows)
    evidence = [s for s in scores if s["required_evidence_eligible"]]
    summary = {
        "case_count": len(rows), "status_counts": dict(Counter(s["execution_status"] for s in scores)),
        "expected_accuracy_all_cases": fraction(sum(s["expected_correct"] for s in scores), len(scores)),
        "resolved_label_coverage": fraction(sum(s["observed_label"] is not None for s in scores), len(scores)),
        "target_alignment_coverage": fraction(sum(s["aligned_target_count"] for s in scores), len(scores)),
        "aligned_target_label_accuracy": fraction(sum(s["aligned_target_correct_count"] for s in scores), sum(s["aligned_target_count"] for s in scores)),
        "known_claim_completion": fraction(sum(s["known_completed_factual_count"] for s in known), sum(s["known_extracted_factual_count"] for s in known)),
        "unknown_claim_total_case_count": len(scores) - len(known),
        "empty_complete_case_count": sum(s["observed_label"] == "NON_FACTUAL" for s in scores),
        "required_evidence_presence_and_label_correct": fraction(sum(s["required_evidence_present_and_label_correct"] for s in evidence), len(evidence)),
        "mean_latency_seconds": sum(latency) / len(latency) if latency else None,
        "p95_latency_seconds": latency[max(0, math.ceil(len(latency) * .95) - 1)] if latency else None,
        "usage": usage, "cost": cost_summary(usage, prices),
    }
    if rows and rows[0]["mode"] == "fixed_claim":
        summary["review_audit_ai_draft"] = review_audit(rows)
    return summary


def review_audit(rows: list[dict]) -> dict:
    """Only the fixed atomic-target control supports a direct per-review label audit."""
    audits = []
    for row in rows:
        if row["mode"] != "fixed_claim":
            continue
        expected = row["score"]["expected_label"]
        for kind, key in (("C", "contradiction_reviews"), ("U", "unsupported_reviews")):
            for event in row.get("telemetry", {}).get(key, []):
                before, after = event.get("before_verdict"), event.get("after_verdict")
                if event.get("error") or after not in LABELS:
                    outcome = "failure"
                elif before not in LABELS:
                    outcome = "unscorable_initial_label"
                elif before == after:
                    outcome = "unchanged"
                elif before != expected and after == expected:
                    outcome = "wrong_to_right"
                elif before == expected and after != expected:
                    outcome = "right_to_wrong"
                else:
                    outcome = "wrong_to_different_wrong"
                audits.append({"pair_id": row["pair_id"], "side": row["side"], "kind": kind,
                               "claim_id": event.get("claim_id"), "expected_label": expected,
                               "before_verdict": before, "after_verdict": after, "outcome": outcome})
    counts = Counter(item["outcome"] for item in audits)
    return {"review_event_count": len(audits), "outcome_counts": dict(counts),
            "net_corrections": counts["wrong_to_right"] - counts["right_to_wrong"],
            "events": audits,
            "note": "Conditional on triggered reviews, scored against AI-draft fixed-claim labels. Triggers differ across backends; this is not a causal H3-only comparison. Unchanged includes both correct and wrong labels."}


def summarize(pairs: list[dict], records: list[dict], prices=None, *, backends=BACKENDS) -> dict:
    if (not isinstance(backends, (tuple, list)) or not 1 <= len(backends) <= 2
            or len(set(backends)) != len(backends) or any(b not in SUPPORTED_BACKENDS for b in backends)):
        raise ValueError("Select one or two distinct supported behavior backends")
    if any(row["backend"] not in backends for row in records):
        raise ValueError("Behavior record backend differs from declared selection")
    index = {(row["backend"], row["mode"], row["pair_id"], row["side"]): row for row in records}
    if len(index) != len(records):
        raise ValueError("Duplicate behavior result identity")
    groups = defaultdict(list)
    for row in records:
        groups[(row["backend"], row["mode"])].append(row)
    summaries = {}
    pair_results = []
    for (backend, mode), rows in sorted(groups.items()):
        evaluations = []
        for pair in pairs:
            base = index.get((backend, mode, pair["id"], "base"))
            variant = index.get((backend, mode, pair["id"], "variant"))
            actual = [item["score"]["observed_label"] if item else None for item in (base, variant)]
            expected = [pair[side]["expected_label"] for side in ("base", "variant")]
            resolved = all(label is not None for label in actual)
            relation = (actual[0] == actual[1] if pair["relation"] == "same_label" else actual == expected) if resolved else False
            correct = resolved and actual == expected
            evaluations.append({"backend": backend, "mode": mode, "pair_id": pair["id"], "family": pair["family"],
                                "domain": pair["domain"], "expected": expected, "observed": actual,
                                "pair_resolved": resolved, "relation_consistent": relation,
                                "both_expected_correct": correct,
                                "stable_wrong": resolved and actual[0] == actual[1] and not correct})
        summary = _group_summary(rows, prices)
        summary.update({
            "pair_count": len(evaluations),
            "pair_resolution": fraction(sum(p["pair_resolved"] for p in evaluations), len(evaluations)),
            "relation_consistency_all_pairs": fraction(sum(p["relation_consistent"] for p in evaluations), len(evaluations)),
            "both_expected_correct_all_pairs": fraction(sum(p["both_expected_correct"] for p in evaluations), len(evaluations)),
            "stable_wrong_pair_count": sum(p["stable_wrong"] for p in evaluations),
            "by_family": {}, "by_domain": {},
        })
        for dimension in ("family", "domain"):
            for name in sorted({row[dimension] for row in rows}):
                sub = [row for row in rows if row[dimension] == name]
                subpairs = [p for p in evaluations if p[dimension] == name]
                summary["by_" + dimension][name] = {
                    "cases": len(sub), "expected_accuracy": fraction(sum(r["score"]["expected_correct"] for r in sub), len(sub)),
                    "both_expected_correct": fraction(sum(p["both_expected_correct"] for p in subpairs), len(subpairs)),
                    "relation_consistency": fraction(sum(p["relation_consistent"] for p in subpairs), len(subpairs)),
                }
        summaries[backend + "/" + mode] = summary
        pair_results.extend(evaluations)
    comparisons = {}
    for mode in sorted({row["mode"] for row in records}):
        paired = []
        for pair in pairs:
            for side in ("base", "variant"):
                old = index.get((backends[0], mode, pair["id"], side))
                new = index.get((backends[1], mode, pair["id"], side)) if len(backends) == 2 else None
                if old and new:
                    a, b = old["score"], new["score"]
                    paired.append({"pair_id": pair["id"], "side": side,
                                   "old_label": a["observed_label"], "new_label": b["observed_label"],
                                   "old_correct": a["expected_correct"], "new_correct": b["expected_correct"],
                                   "both_resolved": a["observed_label"] is not None and b["observed_label"] is not None})
        comparisons[mode] = {
            "reference_backend": backends[0],
            "candidate_backend": backends[1] if len(backends) == 2 else None,
            "paired_case_count": len(paired),
            "wrong_to_right": sum(not r["old_correct"] and r["new_correct"] and r["both_resolved"] for r in paired),
            "right_to_wrong": sum(r["old_correct"] and not r["new_correct"] and r["both_resolved"] for r in paired),
            "failure_to_right": sum(r["old_label"] is None and r["new_correct"] for r in paired),
            "right_to_failure": sum(r["old_correct"] and r["new_label"] is None for r in paired),
            "label_flip_count_resolved": sum(r["both_resolved"] and r["old_label"] != r["new_label"] for r in paired),
            "cases": paired,
        }
    return {"groups": summaries, "pairs": pair_results, "paired_backend_comparisons": comparisons,
            "note": "AI-draft expected labels, exploratory diagnostic evidence only. Same-label consistency counts stable mistakes; read both-expected-correct separately. No cross-dataset or unseen-generalization claim."}


def run(dataset: Path, output_dir: Path, settings, config, *, backends=BACKENDS, modes=MODES,
        workers=4, limit_pairs=None, prices=None, verifier_factory=build_verifier):
    dataset_hash = _sha(dataset)
    pairs = load_pairs(dataset)
    if _sha(dataset) != dataset_hash:
        raise ValueError("Dataset changed during loading; no inference started")
    if limit_pairs is not None and limit_pairs < 1:
        raise ValueError("Pair limit must be positive")
    if limit_pairs is not None:
        pairs = pairs[:limit_pairs]
    if (not pairs or not 1 <= workers <= 16 or not 1 <= len(backends) <= 2 or not modes
            or len(set(backends)) != len(backends) or len(set(modes)) != len(modes)
            or any(b not in SUPPORTED_BACKENDS for b in backends) or any(m not in MODES for m in modes)):
        raise ValueError("Invalid behavior run selection")
    output_dir.mkdir(parents=True, exist_ok=False)
    hashes = code_hashes()
    for name, digest in hashes.items():
        source = output_dir / "source" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((ROOT / name).read_bytes())
        if _sha(source) != digest:
            raise ValueError("Code changed during snapshot; no inference started")
    dataset_copy = output_dir / "pairs.jsonl"
    dataset_copy.write_bytes(dataset.read_bytes())
    if _sha(dataset_copy) != dataset_hash:
        raise ValueError("Dataset changed during snapshot; no inference started")
    metadata = {
        "schema_version": SCHEMA, "kind": "exposed-ai-draft-behavior-diagnostic-not-unseen",
        "created_at": _now(), "dataset_sha256": dataset_hash, "selected_pair_ids": [p["id"] for p in pairs],
        "settings": public_settings(settings), "v4_config": config.public_dict(), "code_files_sha256": hashes,
        "backends": list(backends), "modes": list(modes), "workers": workers, "prices": prices,
        "author_approval": "not approved", "runtime_metadata_policy": "Only ordinary request and fixed claim control reach inference; no fixture identity, family, domain, expected labels or relations.",
        "fixed_claim_limitation": "Bypasses M1; excludes extraction cost. Atomic target supplied by AI-draft fixture, not author gold.",
        "boundary_family_limitation": "Whitespace and heading surface variants probe boundary sensitivity; identical-byte alternative unit partitions are not evaluated.",
    }
    _write_json(output_dir / "config.json", metadata, exclusive=True)
    # Refuse a race during snapshot before spending any model calls.
    if code_hashes() != hashes:
        raise ValueError("Code changed after snapshot; no inference started")

    def work(pair, side, backend, mode):
        case = pair[side]
        started = time.monotonic()
        prediction, telemetry, error = None, {"calls": []}, None
        try:
            verifier = verifier_factory(backend, settings, v4_config=config)
            if mode == "fixed_claim":
                verifier = fixed_claim_control(verifier, case["fixed_claim_text"])
            result = verifier.verify(VerificationRequest.from_dict(case["input"]))
            prediction, telemetry = result.report, result.telemetry
            validate_v4_report(prediction, case["input"]["context_passages"])
        except VerificationError as exc:
            prediction, telemetry = None, exc.telemetry
            error = {"code": exc.code, "message": exc.message}
        except Exception as exc:
            prediction = None
            error = {"code": "unexpected_error", "message": type(exc).__name__}
        score = score_case(case, prediction, error, telemetry=telemetry)
        record = {"pair_id": pair["id"], "side": side, "family": pair["family"], "domain": pair["domain"],
                  "backend": backend, "mode": mode, "prediction": prediction, "telemetry": telemetry,
                  "error": error, "latency_seconds": time.monotonic() - started, "score": score}
        return _redact(record, settings.api_key)

    records = []
    total = len(pairs) * 2 * len(backends) * len(modes)
    started = time.monotonic()
    with (output_dir / "responses.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(work, p, side, b, m) for p in pairs for side in ("base", "variant") for m in modes for b in backends]
            for future in as_completed(jobs):
                record = future.result()
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                _write_json(output_dir / "progress.json", {"completed": len(records), "expected": total, "elapsed_seconds": time.monotonic() - started})
                print(f"[{len(records)}/{total}] {record['backend']} {record['mode']} {record['pair_id']}/{record['side']} {record['score']['execution_status']}", flush=True)
    unchanged = code_hashes() == hashes
    if not unchanged:
        _write_json(output_dir / "report.json", {
            "run_status": "invalid_source_changed", "kind": metadata["kind"],
            "config_sha256": _sha(output_dir / "config.json"),
            "responses_sha256": _sha(output_dir / "responses.jsonl"),
            "source_files_unchanged_after_run": False,
            "error": "Source files changed after the freeze; no valid scored comparison is published. Raw records are retained for audit.",
        }, exclusive=True)
        raise ValueError("Source files changed during run; frozen comparison is invalid")
    report = summarize(pairs, records, prices, backends=backends)
    report.update({"kind": metadata["kind"], "config_sha256": _sha(output_dir / "config.json"),
                   "responses_sha256": _sha(output_dir / "responses.jsonl"), "elapsed_seconds": time.monotonic() - started,
                   "source_files_unchanged_after_run": True, "run_status": "complete"})
    _write_json(output_dir / "report.json", report, exclusive=True)
    lines = ["# v4 offline behavioral diagnostics", "", report["note"], "",
             "| Backend / mode | Complete / partial / error | Expected accuracy | Both correct pairs | Relation consistency | Stable wrong pairs | Target alignment coverage | Mean s |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    def pct(value):
        return "n/a" if value["value"] is None else f"{value['value']:.2%}"
    for name, summary in report["groups"].items():
        status = summary["status_counts"]
        lines.append(f"| {name} | {status.get('complete', 0)} / {status.get('partial', 0)} / {status.get('error', 0)} | {pct(summary['expected_accuracy_all_cases'])} | {pct(summary['both_expected_correct_all_pairs'])} | {pct(summary['relation_consistency_all_pairs'])} | {summary['stable_wrong_pair_count']} | {pct(summary['target_alignment_coverage'])} | {summary['mean_latency_seconds']:.2f} |")
    lines.extend(["", "Required source-index presence is not a semantic citation audit. Fixed-claim costs exclude M1. All expected labels are AI-authored drafts; no formal acceptance or unseen status is implied."])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--v4-config", type=Path)
    parser.add_argument("--backends", nargs="+", choices=SUPPORTED_BACKENDS, default=list(BACKENDS))
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-pairs", type=int)
    parser.add_argument("--input-per-million", type=float)
    parser.add_argument("--cached-input-per-million", type=float)
    parser.add_argument("--output-per-million", type=float)
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16 or args.limit_pairs is not None and args.limit_pairs < 1:
        parser.error("Invalid workers or pair limit")
    prices = {"input_per_million": args.input_per_million, "cached_input_per_million": args.cached_input_per_million,
              "output_per_million": args.output_per_million, "currency": args.currency}
    if any(value is not None and (not math.isfinite(value) or value < 0) for key, value in prices.items() if key != "currency"):
        parser.error("Prices must be finite and nonnegative")
    settings = load_settings(thinking="enabled")
    if not settings.api_key:
        parser.error("LLM_API_KEY is required")
    run(args.dataset, args.output_dir, settings, load_v4_config(args.v4_config), backends=tuple(args.backends),
        modes=tuple(args.modes), workers=args.workers, limit_pairs=args.limit_pairs, prices=prices)


if __name__ == "__main__":
    main()
