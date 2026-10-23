#!/usr/bin/env python3
"""Run baseline, minimal, and optimized verifiers with isolated gold scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.contracts import VerificationError, VerificationRequest
from grounding.factory import (
    BACKENDS, CANONICAL_BACKENDS, DEFAULT_BACKENDS, build_verifier,
    frozen_v2_provenance, normalize_backend,
)
from grounding.scoring import (
    AMBIGUITY_MARGIN, SIMILARITY_THRESHOLD, SPAN_OVERLAP_THRESHOLD,
    aggregate_backend, score_case,
)
from scripts.validate_dataset import check_dataset, strict_json_loads


LIMITATIONS = [
    "Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.",
    "Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.",
    "Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.",
    "Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.",
    "Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.",
    "Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.",
    "Version comparisons use the same completed inputs and settings. A single paired run does not isolate sampling variation, component effects, or the cost of additional calls.",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _redact(value: Any, secret: str | None) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "<redacted>") if secret else value
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item, secret) for key, item in value.items()}
    return value


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def implementation_hashes() -> dict[str, str]:
    code_paths = sorted((ROOT / "grounding").glob("*.py"))
    code_paths += [ROOT / "scripts" / "benchmark.py", ROOT / "scripts" / "validate_dataset.py"]
    code_paths += [ROOT / "grounding" / "frozen_v2.json"]
    prompt_paths = sorted((ROOT / "prompts").glob("**/*"))
    prompt_paths = [path for path in prompt_paths if path.is_file()]
    return {str(path.relative_to(ROOT)).replace("\\", "/"): _sha(path) for path in code_paths + prompt_paths}


def provenance(dataset: Path, sources: Path, check_local: bool) -> dict[str, Any]:
    hashes = implementation_hashes()
    combined = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()
    source_data = json.loads(sources.read_text(encoding="utf-8-sig"))
    return {
        "dataset_path": str(dataset.resolve()),
        "dataset_sha256": _sha(dataset),
        "sources_path": str(sources.resolve()),
        "sources_sha256": _sha(sources),
        "source_documents": [
            {"id": item.get("id"), "sha256": item.get("sha256")}
            for item in source_data.get("documents", [])
        ],
        "local_source_hashes_rechecked": check_local,
        "code_and_prompt_files_sha256": hashes,
        "implementation_sha256": combined,
        "frozen_v2": frozen_v2_provenance(),
        "python_version": sys.version.split()[0],
    }


def _json_object(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _bound_path(owner: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A frozen artifact path is missing")
    candidate = Path(value)
    return (owner.parent / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def _bound_artifact(owner: Path, value: Any) -> Path:
    if not isinstance(value, dict):
        raise ValueError("A frozen artifact binding is missing")
    path = _bound_path(owner, value.get("path"))
    if _sha(path) != value.get("sha256"):
        raise ValueError(f"Frozen artifact hash mismatch: {path.name}")
    return path


def _aware_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Missing {field} timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    if parsed > datetime.now(timezone.utc):
        raise ValueError(f"{field} cannot be in the future")
    return parsed


def _case_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("Frozen case IDs must be a nonempty string array")
    if len(value) != len(set(value)):
        raise ValueError("Frozen case IDs must be unique")
    return value


def check_confirmation_manifest(
    path: Path, dataset: Path, sources: Path, cases: list[dict[str, Any]],
    settings: dict[str, Any], backend_names: list[str], source_info: dict[str, Any],
) -> dict[str, Any]:
    """Verify a data/code freeze and a user-supplied pilot-policy attestation.

    Manifest fields: schema_version, kind=confirmation-freeze, frozen_at,
    case_ids, dataset_sha256, sources_sha256, implementation_files_sha256,
    settings (public settings without api_key_configured), backends,
    annotation_policy={path,sha256}, annotation_policy_review={path,sha256}.
    The review JSON binds exactly three review-split cases and their files via
    dataset_path/dataset_sha256, sources_path/sources_sha256 and case_ids;
    it also requires scope=pilot-annotation-policy, decision=approved,
    policy_sha256, reviewer, reviewed_at and authorization_reference.
    This verifies a recorded attestation, not the human identity of its writer.
    It does not assert individual human review of the final confirmation cases.
    """
    manifest = _json_object(path)
    if manifest.get("schema_version") != "1.0" or manifest.get("kind") != "confirmation-freeze":
        raise ValueError("Expected a version 1.0 confirmation-freeze manifest")
    frozen_at = _aware_time(manifest.get("frozen_at"), "frozen_at")
    if manifest.get("dataset_sha256") != _sha(dataset) or manifest.get("sources_sha256") != _sha(sources):
        raise ValueError("Confirmation dataset or sources differ from the freeze")
    ids = _case_ids(manifest.get("case_ids"))
    if ids != [case["id"] for case in cases] or any(case["split"] != "confirmation" for case in cases):
        raise ValueError("Formal confirmation requires the complete frozen confirmation cases in their recorded order")
    if manifest.get("implementation_files_sha256") != source_info["code_and_prompt_files_sha256"]:
        raise ValueError("Implementation or scoring files changed after confirmation freeze")
    if not source_info.get("frozen_v2", {}).get("verified"):
        raise ValueError("Frozen optimized-v2 inference has not passed hash verification")
    runtime_settings = {key: value for key, value in settings.items() if key != "api_key_configured"}
    if manifest.get("settings") != runtime_settings:
        raise ValueError("Model or generation settings differ from the confirmation freeze")
    if (
        manifest.get("backends") != backend_names
        or len(backend_names) != len(CANONICAL_BACKENDS)
        or set(backend_names) != set(CANONICAL_BACKENDS)
    ):
        raise ValueError("Formal confirmation requires all four frozen backends in the recorded order")
    policy = _bound_artifact(path, manifest.get("annotation_policy"))
    review_path = _bound_artifact(path, manifest.get("annotation_policy_review"))
    review = _json_object(review_path)
    if (
        review.get("schema_version") != "1.0"
        or review.get("scope") != "pilot-annotation-policy"
        or review.get("decision") != "approved"
    ):
        raise ValueError("Confirmation requires an approved author pilot-annotation-policy attestation")
    for field in ("reviewer", "authorization_reference"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            raise ValueError(f"Author pilot-policy attestation is missing {field}")
    if _aware_time(review.get("reviewed_at"), "reviewed_at") > frozen_at:
        raise ValueError("Author policy review must precede the confirmation freeze")
    if review.get("policy_sha256") != _sha(policy):
        raise ValueError("Annotation policy differs from the author-reviewed policy")
    pilot_dataset = _bound_path(review_path, review.get("dataset_path"))
    pilot_sources = _bound_path(review_path, review.get("sources_path"))
    if _sha(pilot_dataset) != review.get("dataset_sha256") or _sha(pilot_sources) != review.get("sources_sha256"):
        raise ValueError("Pilot dataset or sources differ from the author-reviewed files")
    pilot_ids = _case_ids(review.get("case_ids"))
    pilot_cases, validation = check_dataset(pilot_dataset, pilot_sources)
    if (
        not validation["valid"] or len(pilot_ids) != 3
        or pilot_ids != [case["id"] for case in pilot_cases]
        or any(case["split"] != "review" for case in pilot_cases)
        or set(pilot_ids) & set(ids)
    ):
        raise ValueError("Reviewed pilot must contain exactly three valid review cases, disjoint from confirmation")
    pilot_inputs = {json.dumps(case["input"], sort_keys=True, ensure_ascii=False) for case in pilot_cases}
    confirmation_inputs = [json.dumps(case["input"], sort_keys=True, ensure_ascii=False) for case in cases]
    if pilot_inputs.intersection(confirmation_inputs):
        raise ValueError("Pilot inputs cannot be reused as confirmation under different IDs")
    return {
        "verified": True, "manifest_path": str(path.resolve()), "manifest_sha256": _sha(path),
        "frozen_at": manifest["frozen_at"], "annotation_policy_sha256": _sha(policy),
        "author_attestation_sha256": _sha(review_path), "review_scope": review["scope"],
        "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
        "authorization_reference": review["authorization_reference"],
        "review_case_ids": pilot_ids,
        "exposure_fingerprint": hashlib.sha256(json.dumps(sorted(confirmation_inputs), ensure_ascii=False).encode("utf-8")).hexdigest(),
        "limitation": "Validates the supplied pilot-policy attestation and hash bindings; does not authenticate its author or assert human review of each confirmation label.",
    }


def reserve_confirmation_run(
    proof: dict[str, Any], output_dir: Path, *, replicate: bool = False,
    ledger_dir: Path | None = None,
) -> dict[str, Any]:
    """Track exact input-batch exposure in this checkout, across output folders.

    A copied checkout or requests made outside this runner are not observable.
    Retries after an interrupted/failed first run are explicit replicates too.
    """
    ledger_dir = ledger_dir or ROOT / "results" / "confirmation-ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = proof["exposure_fingerprint"]
    initial_path = ledger_dir / f"{fingerprint}.json"
    now = datetime.now(timezone.utc)
    value = {
        "exposure_fingerprint": fingerprint, "manifest_sha256": proof["manifest_sha256"],
        "output_dir": str(output_dir.resolve()), "started_at": now.isoformat(),
        "status": "started", "role": "confirmation-first-run",
        "scope": "Exact confirmation input batch recorded by this runner in this workspace; not global exposure tracking.",
    }
    path = initial_path
    if replicate:
        if not initial_path.exists():
            raise ValueError("No prior confirmation run is registered for this input batch")
        original = _json_object(initial_path)
        value.update(role="confirmation-replicate", initial_run=original["output_dir"])
        path = ledger_dir / f"{fingerprint}.replicate-{now.strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("This confirmation input batch already has a recorded run. Use --confirmation-replicate to explicitly label a repeat.") from exc
    return {**value, "ledger_path": str(path.resolve())}


def _format(value: Any, *, percent: bool = False) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    if value is None:
        return "n/a"
    if percent:
        return f"{100 * value:.1f}%"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def intervention_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter()
    directions = Counter()
    for record in records:
        telemetry = record.get("telemetry") or {}
        for call in telemetry.get("calls", []):
            stage = call.get("stage", "")
            if isinstance(stage, str):
                counts["merge_calls"] += stage.startswith("merge")
                counts["contradiction_review_calls"] += stage.startswith("contradiction_review")
        for audit in telemetry.get("merge_audits", []):
            counts["merge_decisions"] += 1
            merged = audit.get("merged") is True or audit.get("decision") == "merge"
            counts["merged_groups"] += merged
            before, after = audit.get("input_count"), audit.get("output_count")
            if before is None and isinstance(audit.get("before_claims"), list):
                before = len(audit["before_claims"])
            if after is None and isinstance(audit.get("after_claims"), list):
                after = len(audit["after_claims"])
            if merged and isinstance(before, int) and isinstance(after, int) and not isinstance(before, bool) and not isinstance(after, bool):
                counts["claims_removed_by_merge"] += max(0, before - after)
        for review in telemetry.get("contradiction_reviews", []):
            counts["contradiction_reviews"] += 1
            before, after = review.get("before_verdict"), review.get("after_verdict")
            if before in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED") and after in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"):
                directions[f"{before}->{after}"] += 1
                counts["changed_verdicts"] += before != after
            else:
                counts["failed_or_incomplete_reviews"] += 1
    return {
        **{key: counts[key] for key in (
            "merge_calls", "merge_decisions", "merged_groups", "claims_removed_by_merge",
            "contradiction_review_calls", "contradiction_reviews", "changed_verdicts",
            "failed_or_incomplete_reviews",
        )},
        "verdict_directions": dict(sorted(directions.items())),
        "note": "Call counts include attempts and repairs. Decision counts are separate; changed verdicts are not automatically improvements.",
    }


def pair_backends(
    records: list[dict[str, Any]], reference: str, candidate: str, prices: dict[str, Any],
) -> dict[str, Any]:
    left = {record["id"]: record for record in records if record["backend"] == reference}
    right = {record["id"]: record for record in records if record["backend"] == candidate}
    shared = sorted(left.keys() & right.keys())
    comparable = [key for key in shared if left[key].get("input_sha256") == right[key].get("input_sha256")]
    summary: dict[str, Any] = {
        "reference_backend": reference, "candidate_backend": candidate,
        "paired_case_count": len(comparable), "paired_case_ids": comparable,
        "input_mismatch_case_ids": sorted(set(shared) - set(comparable)),
        "unpaired_case_ids": sorted(left.keys() ^ right.keys()),
    }
    left_summary = aggregate_backend([left[key] for key in comparable], prices)
    right_summary = aggregate_backend([right[key] for key in comparable], prices)
    for mode in ("strict", "approximate"):
        summary[f"{mode}_improved_case_ids"] = [
            key for key in comparable if not left[key]["score"][mode]["case_correct"] and right[key]["score"][mode]["case_correct"]
        ]
        summary[f"{mode}_regressed_case_ids"] = [
            key for key in comparable if left[key]["score"][mode]["case_correct"] and not right[key]["score"][mode]["case_correct"]
        ]
        before = left_summary[mode]["claim_f1"]
        after = right_summary[mode]["claim_f1"]
        summary[mode] = {
            "reference_claim_f1": before, "candidate_claim_f1": after,
            "claim_f1_difference": after["value"] - before["value"] if before["value"] is not None and after["value"] is not None else None,
        }
    summary["latency"] = {"reference": left_summary["latency"], "candidate": right_summary["latency"]}
    summary["usage"] = {"reference": left_summary["usage"], "candidate": right_summary["usage"]}
    summary["cost"] = {"reference": left_summary["cost"], "candidate": right_summary["cost"]}
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    config = report["config"]
    lines = [
        "# Verifier benchmark",
        "",
        f"Run `{report['run_id']}`; status **{report['status']}**; split `{config['split']}`.",
        f"Completed {report['completed_records']} / {report['planned_records']} case/backend records.",
        f"Model `{config['settings'].get('model', 'unspecified')}`. All LLM backends share the saved model and generation settings.",
        "",
        "| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    review_directions = []
    for name, summary in report["backends"].items():
        usage, cost = summary["usage"], summary["cost"]
        cost_text = f"{_format(cost['estimated_amount'])} {cost['currency']}" if cost["estimated_amount"] is not None else "not priced / unknown"
        lines.append(
            f"| {name} | {summary['case_count']} | {_format(summary['success_rate'], percent=True)}"
            f" | {_format(summary['strict']['claim_f1'], percent=True)}"
            f" | {_format(summary['strict']['macro_f1'], percent=True)}"
            f" | {_format(summary['approximate']['claim_f1'], percent=True)}"
            f" | {_format(summary['citations']['exact_substring_rate'], percent=True)}"
            f" | {_format(summary['citations']['approximate']['passage_coverage'], percent=True)}"
            f" | {_format(summary['latency']['mean_seconds'])} | {_format(summary['latency']['p50_seconds'])}"
            f" | {_format(summary['latency']['p95_seconds'])}"
            f" | {usage['prompt_tokens']} / {usage['completion_tokens']} | {cost_text} |"
        )
    lines += [
        "",
        "*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.",
        "",
        "## Evidence and alignment audit",
        "",
        "| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["backends"].items():
        cites = summary["citations"]
        lines.append(
            f"| {name} | {_format(cites['strict']['passage_coverage'], percent=True)}"
            f" | {_format(cites['approximate']['passage_coverage'], percent=True)}"
            f" | {_format(cites['approximate']['gold_quote_containment'], percent=True)}"
            f" | {_format(cites['approximate']['gold_quote_exact_match'], percent=True)}"
            f" | {summary['approximate']['alignment_review_case_count']}"
            f" | {summary['approximate']['nonexact_alignment_count']} | {summary['error_count']} |"
        )
    lines += ["", "## Recorded failures", "", "| Approach | Case | Category | Diagnosis |", "|---|---|---|---|"]
    failure_count = 0
    for name, summary in report["backends"].items():
        for failure in summary["failures"]:
            failure_count += 1
            lines.append(f"| {name} | {failure['id']} | {failure['category']} | {', '.join(failure['reasons'])} |")
    if not failure_count:
        lines.append("| All | - | - | No scored failures in completed records |")
    for paired in report.get("paired_comparisons", {}).values():
        lines += [
            "", f"## {paired['reference_backend']} to {paired['candidate_backend']}", "",
            f"Comparable completed cases: {paired.get('paired_case_count', 0)}.",
            f"Strict complete-case improvements: {paired.get('strict_improved_case_ids', [])}.",
            f"Strict complete-case regressions: {paired.get('strict_regressed_case_ids', [])}.",
            f"Approximate diagnostic improvements: {paired.get('approximate_improved_case_ids', [])}.",
            f"Approximate diagnostic regressions: {paired.get('approximate_regressed_case_ids', [])}.",
            "These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.",
        ]
    lines += [
        "", "## Merge and contradiction-review accounting", "",
        "| Approach | Merge calls | Merged groups | Claims removed | Review calls | Reviewed claims | Changed verdicts | Failed reviews |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["backends"].items():
        audit = summary["interventions"]
        lines.append(f"| {name} | {audit['merge_calls']} | {audit['merged_groups']} | {audit['claims_removed_by_merge']} | {audit['contradiction_review_calls']} | {audit['contradiction_reviews']} | {audit['changed_verdicts']} | {audit['failed_or_incomplete_reviews']} |")
        if audit["verdict_directions"]:
            review_directions.append(f"{name} review directions: `{json.dumps(audit['verdict_directions'], sort_keys=True)}`.")
    lines.extend(["", *review_directions])
    lines += ["", "## Reproducibility and limitations", ""]
    lines += [f"- {limitation}" for limitation in report["limitations"]]
    lines += [
        f"- Dataset SHA-256: `{report['provenance']['dataset_sha256']}`.",
        f"- Implementation SHA-256: `{report['provenance']['implementation_sha256']}`.",
        "- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.",
        "- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.",
        "",
    ]
    return "\n".join(lines)


def make_report(
    records: list[dict[str, Any]], config: dict[str, Any], source_info: dict[str, Any],
    run_id: str, status: str,
) -> dict[str, Any]:
    backend_names = config["backends"]
    by_backend = {
        name: aggregate_backend([record for record in records if record["backend"] == name], config["prices"])
        for name in backend_names
    }
    for name, summary in by_backend.items():
        summary["interventions"] = intervention_summary([record for record in records if record["backend"] == name])
    report = {
        "schema_version": "1.1",
        "run_id": run_id,
        "created_at": config["created_at"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "config": config,
        "provenance": source_info,
        "selected_case_ids": config["selected_case_ids"],
        "planned_records": len(config["selected_case_ids"]) * len(backend_names),
        "completed_records": len(records),
        "backends": by_backend,
        "alignment_policy": {
            "strict": "NFC plus collapsed whitespace; otherwise exact case-sensitive claim text",
            "approximate": "strict first, then gold answer span, span overlap, or high SequenceMatcher similarity; mutual-best margin; matching ignores verdict",
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "span_overlap_threshold": SPAN_OVERLAP_THRESHOLD,
            "ambiguity_margin": AMBIGUITY_MARGIN,
            "critical_tokens": "Numeric, negation, and ordered mathematical token mismatch prevents approximate alignment; identifiers and operators remain case-sensitive.",
        },
        "limitations": LIMITATIONS,
    }
    ordered = [name for name in (*CANONICAL_BACKENDS, "optimized") if name in backend_names]
    report["paired_comparisons"] = {
        f"{reference}__vs__{candidate}": pair_backends(records, reference, candidate, config["prices"])
        for reference, candidate in combinations(ordered, 2)
    }
    legacy_candidate = next((name for name in ("optimized-v3", "optimized", "optimized-v2") if name in backend_names), "optimized")
    report["paired_comparison"] = pair_backends(records, "minimal", legacy_candidate, config["prices"])
    return report


def run_cases(
    cases: list[dict[str, Any]], verifiers: dict[str, Any], output_dir: Path,
    config: dict[str, Any], source_info: dict[str, Any], *, secret: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    run_id = output_dir.name

    def checkpoint(status: str) -> dict[str, Any]:
        report = _redact(make_report(records, config, source_info, run_id, status), secret)
        _write_json(output_dir / "report.json", report)
        temporary = output_dir / "report.md.tmp"
        temporary.write_text(render_markdown(report), encoding="utf-8")
        temporary.replace(output_dir / "report.md")
        return report

    checkpoint("running")
    try:
        with (output_dir / "responses.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for case in cases:
                for name, verifier in verifiers.items():
                    started = time.perf_counter()
                    prediction, telemetry, error = None, {"calls": []}, None
                    try:
                        # Build a fresh request for every backend. Gold and metadata stay here.
                        request = VerificationRequest.from_dict({
                            "context_passages": list(case["input"]["context_passages"]),
                            "generated_answer": case["input"]["generated_answer"],
                        })
                        result = verifier.verify(request)
                        prediction, telemetry = result.report, result.telemetry
                    except VerificationError as exc:
                        error = {
                            "code": exc.code,
                            "message": getattr(exc, "message", str(exc)),
                            "status": getattr(exc, "status", 502),
                        }
                        telemetry = getattr(exc, "telemetry", None) or {"calls": []}
                    except Exception as exc:
                        # Unknown exception text may contain an endpoint or credential.
                        error = {"code": "internal_error", "message": type(exc).__name__, "status": 500}
                    duration = time.perf_counter() - started
                    record = _redact({
                        "id": case["id"], "split": case["split"], "category": case["category"],
                        "backend": name,
                        "input_sha256": hashlib.sha256(json.dumps(case["input"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                        "prediction": prediction, "telemetry": telemetry or {"calls": []},
                        "error": error, "latency_seconds": duration,
                        "score": score_case(case, prediction, error),
                    }, secret)
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    records.append(record)
                    checkpoint("running")
                    state = "valid" if record["score"]["schema_valid"] else "error"
                    print(f"[{len(records)}/{len(cases) * len(verifiers)}] {name} {case['id']}: {state}, {duration:.3f}s", flush=True)
    except KeyboardInterrupt:
        report = checkpoint("interrupted")
        print("Interrupted. Completed records and partial reports have been preserved.", file=sys.stderr)
        return report
    except BaseException:
        checkpoint("failed")
        raise
    return checkpoint("complete")


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset" / "cphos28" / "cases.jsonl")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--check-local-sources", action="store_true")
    parser.add_argument("--split", choices=("dev", "test", "edge", "review", "confirmation", "all"), default="dev")
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(DEFAULT_BACKENDS))
    parser.add_argument("--confirmation-manifest", type=Path, help="Required for any selected confirmation cases; defaults to confirmation.freeze.json next to the dataset")
    parser.add_argument("--confirmation-replicate", action="store_true", help="Explicitly label a repeated confirmation input batch; requires a prior run in the workspace ledger")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--thinking", choices=("api-default", "enabled", "disabled"))
    parser.add_argument("--repair-attempts", type=int)
    parser.add_argument("--upstream-retries", type=int)
    parser.add_argument("--json-mode", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--output-dir", type=Path, help="A new or empty directory; prior runs are never overwritten")
    parser.add_argument("--input-price-per-million", type=_nonnegative_float)
    parser.add_argument("--cached-input-price-per-million", type=_nonnegative_float)
    parser.add_argument("--output-price-per-million", type=_nonnegative_float)
    parser.add_argument("--currency", default="USD")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    args.backends = list(dict.fromkeys(normalize_backend(name) for name in args.backends))
    overrides = {
        key: getattr(args, key) for key in
        ("model", "base_url", "timeout", "max_output_tokens", "thinking", "repair_attempts", "upstream_retries", "json_mode", "temperature")
        if getattr(args, key) is not None
    }
    try:
        settings = load_settings(env_file=args.env_file, **overrides)
    except (VerificationError, ValueError, OSError) as exc:
        print(f"Configuration error: {type(exc).__name__}. Check .env and CLI settings.", file=sys.stderr)
        return 2
    if any(name != "baseline" for name in args.backends) and not settings.api_key:
        print("Configuration error: LLM_API_KEY is missing. Set it in the project .env or environment; --backends baseline needs no key.", file=sys.stderr)
        return 2
    cases, validation = check_dataset(args.dataset, args.sources, check_local_sources=args.check_local_sources)
    if not validation["valid"]:
        print(json.dumps({"dataset_validation": validation}, ensure_ascii=False), file=sys.stderr)
        return 2
    dataset_splits = {case["split"] for case in cases}
    cases = [case for case in cases if args.split == "all" or case["split"] == args.split]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        parser.error("No cases selected")
    sources = args.sources or args.dataset.with_name("sources.json")
    source_info = provenance(args.dataset, sources, args.check_local_sources)
    if any(case["split"] == "confirmation" for case in cases):
        manifest_path = args.confirmation_manifest or args.dataset.with_name("confirmation.freeze.json")
        try:
            if args.limit is not None:
                raise ValueError("--limit is not permitted for formal confirmation")
            if dataset_splits != {"confirmation"}:
                raise ValueError("Formal confirmation must use a dedicated dataset containing only confirmation cases")
            source_info["confirmation_freeze"] = check_confirmation_manifest(
                manifest_path, args.dataset, sources, cases, settings.public_dict(), args.backends, source_info,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Confirmation blocked: {exc}", file=sys.stderr)
            return 2
    elif args.confirmation_replicate:
        parser.error("--confirmation-replicate requires confirmation cases")
    try:
        verifiers = {name: build_verifier(name, settings) for name in args.backends}
    except VerificationError as exc:
        print(f"Configuration error: {exc.message}", file=sys.stderr)
        return 2
    created = datetime.now(timezone.utc)
    output_dir = args.output_dir or ROOT / "results" / "benchmark" / created.strftime("%Y%m%dT%H%M%S.%fZ")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        parser.error("--output-dir must be new or empty; existing results are immutable")
    output_dir.mkdir(parents=True, exist_ok=True)
    confirmation_run = None
    if "confirmation_freeze" in source_info:
        try:
            confirmation_run = reserve_confirmation_run(
                source_info["confirmation_freeze"], output_dir, replicate=args.confirmation_replicate,
            )
            source_info["confirmation_run"] = confirmation_run
        except (OSError, ValueError, KeyError) as exc:
            print(f"Confirmation blocked: {_redact(str(exc), settings.api_key)}", file=sys.stderr)
            return 2
    source_info = _redact(source_info, settings.api_key)
    prices = {
        "input_per_million": args.input_price_per_million,
        "cached_input_per_million": args.cached_input_price_per_million,
        "output_per_million": args.output_price_per_million,
        "currency": args.currency,
    }
    config = _redact({
        "created_at": created.isoformat(),
        "split": args.split, "backends": args.backends, "limit": args.limit,
        "selected_case_ids": [case["id"] for case in cases],
        "settings": settings.public_dict(),
        "evaluation_role": confirmation_run["role"] if confirmation_run else args.split,
        "prices": prices,
    }, settings.api_key)
    with (output_dir / "config.json").open("x", encoding="utf-8") as stream:
        json.dump({"config": config, "provenance": source_info}, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    report = run_cases(cases, verifiers, output_dir, config, source_info, secret=settings.api_key)
    if confirmation_run:
        ledger_path = Path(confirmation_run["ledger_path"])
        _write_json(ledger_path, {
            **confirmation_run, "status": report["status"], "completed_records": report["completed_records"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    print(json.dumps({"report": str((output_dir / "report.json").resolve()), "status": report["status"], "completed_records": report["completed_records"]}))
    if report["status"] != "complete":
        return 130
    return 1 if any(summary["error_count"] for summary in report["backends"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
