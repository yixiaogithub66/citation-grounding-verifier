#!/usr/bin/env python3
"""Score only author-approved reported claims; never promote AI proposals to gold.

Without both --author-reviewed and --approval the report stays pending. The
author file uses AUTHOR_SCHEMA, bindings_sha256 {pending, draft}, and reviews
[{review_id, verdict, reasoning, citations, reviewed_at}]. Approval uses
APPROVAL_SCHEMA, bindings_sha256 {pending, draft, author_reviewed}, reviewer_kind
human_author, method explicit_user_confirmation, approved_review_ids,
confirmed_at, confirmation_text, and confirmation_source {kind: user_message,
reference: a real message/thread reference}. All timestamps require a timezone.
These fields record an external human decision; software cannot authenticate
the person's identity or establish that a supplied confirmation is genuine.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.contracts import validate_report
from grounding.scoring import fraction
from scripts.benchmark_ragtruth import _object, _sha, _write_json

PACKAGE_SCHEMA = "ragtruth-v1-adjudication-v4.0"
AUTHOR_SCHEMA = "ragtruth-v4-author-review-v1"
APPROVAL_SCHEMA = "ragtruth-v4-author-approval-v1"
REPORT_SCHEMA = "ragtruth-v4-adjudicated-flags-v1"
VERDICTS = {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "NON_FACTUAL", "UNCERTAIN"}


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    _nonempty(value, field)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return result


def _package_index(package: dict) -> dict[str, tuple[dict, dict]]:
    if package.get("schema_version") != PACKAGE_SCHEMA or not isinstance(package.get("cases"), list):
        raise ValueError("Expected the versioned exposed-v1 review package")
    result, case_ids = {}, set()
    for case in package["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("reported_claims_for_review"), list):
            raise ValueError("Invalid review case")
        case_id = _nonempty(case.get("id"), "case id")
        if case_id in case_ids:
            raise ValueError("Duplicate case id")
        case_ids.add(case_id)
        contexts = case.get("input", {}).get("context_passages")
        if not isinstance(contexts, list) or any(not isinstance(c, str) for c in contexts):
            raise ValueError("Review case requires source passages")
        for row in case["reported_claims_for_review"]:
            rid = _nonempty(row.get("review_id"), "review_id")
            if rid in result:
                raise ValueError("Duplicate review_id")
            _nonempty(row.get("backend"), "backend")
            if type(row.get("claim_index")) is not int or row["claim_index"] < 0:
                raise ValueError("Invalid reported claim index")
            reported = row.get("reported_claim")
            validate_report({"claims": [reported]}, contexts)
            if reported["verdict"] not in {"CONTRADICTED", "UNSUPPORTED"}:
                raise ValueError("Review scope is reported C/U claims only")
            result[rid] = case, row
    return result


def _identity(case: dict, row: dict) -> dict:
    # Protect every source/label/prediction field while allowing AI draft fields
    # and later author annotations to differ in their separate artifacts.
    return {"case": {k: v for k, v in case.items() if k not in
                     {"reported_claims_for_review", "case_review_status", "case_adjudicated_positive"}},
            "claim": {k: v for k, v in row.items() if k not in {"ai_review", "author_review"}}}


def score_adjudicated(pending_path: Path, draft_path: Path, *,
                     author_reviewed_path: Path | None = None, approval_path: Path | None = None) -> dict:
    pending, draft = _object(pending_path), _object(draft_path)
    required, proposed = _package_index(pending), _package_index(draft)
    if set(required) != set(proposed) or any(_identity(*required[rid]) != _identity(*proposed[rid]) for rid in required):
        raise ValueError("Draft must preserve all pending review IDs and source/claim identities")
    if pending.get("provenance") != draft.get("provenance") or pending.get("counts") != draft.get("counts"):
        raise ValueError("Draft changed pending provenance or scope counts")
    hashes = {"pending": _sha(pending_path), "draft": _sha(draft_path)}
    report = {"schema_version": REPORT_SCHEMA, "status": "pending_author_approval",
              "acceptance": "pending", "input_sha256": hashes, "required_review_count": len(required),
              "approved_review_count": 0, "reported_claim_flags": None,
              "adjudicated_answer_fn_zero": "not_evaluable",
              "policy": {"scope": "Only the selected reported C/U claims; not exhaustive answer gold",
                         "ai_review_is_gold": False, "native_labels_modified": False,
                         "fn": "Reported-claim review cannot establish missed claims or answer-level FN=0",
                         "identity": "Artifact checks do not authenticate a human; approval relies on genuine explicit user confirmation",
                         "acceptance": "Flag counts alone cannot establish overall v4 true-FP/FN acceptance"}}
    if (author_reviewed_path is None) != (approval_path is None):
        report["pending_reason"] = "Both a separate author-reviewed file and a bound explicit approval are required"
        return report
    if author_reviewed_path is None:
        report["pending_reason"] = "AI drafts are unapproved; the human author must review every required claim"
        return report
    if len({p.resolve() for p in (pending_path, draft_path, author_reviewed_path, approval_path)}) != 4:
        raise ValueError("Pending, draft, author review and approval must be separate files")
    author, approval = _object(author_reviewed_path), _object(approval_path)
    if author.get("schema_version") != AUTHOR_SCHEMA or author.get("reviewer_kind") != "human_author":
        raise ValueError("Expected a separate human_author review artifact")
    if author.get("bindings_sha256") != hashes:
        raise ValueError("Author review must bind the exact pending and draft hashes")
    author_hashes = {**hashes, "author_reviewed": _sha(author_reviewed_path)}
    if (approval.get("schema_version") != APPROVAL_SCHEMA or approval.get("reviewer_kind") != "human_author"
            or approval.get("method") != "explicit_user_confirmation"):
        raise ValueError("Approval requires human_author and explicit_user_confirmation")
    if approval.get("bindings_sha256") != author_hashes:
        raise ValueError("Approval must bind all three pending/draft/author hashes")
    confirmed_at = _timestamp(approval.get("confirmed_at"), "confirmed_at")
    _nonempty(approval.get("confirmation_text"), "confirmation_text")
    source = approval.get("confirmation_source")
    if not isinstance(source, dict) or source.get("kind") != "user_message":
        raise ValueError("Approval requires a real user_message confirmation source")
    _nonempty(source.get("reference"), "confirmation source reference")
    approved_ids = approval.get("approved_review_ids")
    if (not isinstance(approved_ids, list) or any(not isinstance(rid, str) for rid in approved_ids)
            or len(approved_ids) != len(set(approved_ids)) or set(approved_ids) != set(required)):
        raise ValueError("Approval must explicitly cover every required review ID exactly once")
    reviews = author.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("Author reviews must be a list")
    reviewed = {}
    for row in reviews:
        if not isinstance(row, dict) or set(row) != {"review_id", "verdict", "reasoning", "citations", "reviewed_at"}:
            raise ValueError("Invalid author review fields")
        rid = _nonempty(row["review_id"], "review_id")
        if rid in reviewed or rid not in required:
            raise ValueError("Duplicate or unknown author review ID")
        if row["verdict"] not in VERDICTS:
            raise ValueError("Invalid author verdict")
        if _timestamp(row["reviewed_at"], "reviewed_at") > confirmed_at:
            raise ValueError("Approval cannot precede an individual review")
        case, original = required[rid]
        validated_verdict = row["verdict"] if row["verdict"] in {"SUPPORTED", "CONTRADICTED"} else "UNSUPPORTED"
        validate_report({"claims": [{"claim_text": original["reported_claim"]["claim_text"],
                                    "verdict": validated_verdict, "reasoning": row["reasoning"],
                                    "citations": row["citations"]}]}, case["input"]["context_passages"])
        reviewed[rid] = row
    if set(reviewed) != set(required):
        raise ValueError("Author file must review every required ID exactly once")
    counts = {}
    rows = []
    for rid, (case, original) in required.items():
        verdict = reviewed[rid]["verdict"]
        flag = "true_flag" if verdict in {"CONTRADICTED", "UNSUPPORTED"} else "false_flag" if verdict in {"SUPPORTED", "NON_FACTUAL"} else "unresolved"
        backend = original["backend"]
        counts.setdefault(backend, Counter({"true_flag": 0, "false_flag": 0, "unresolved": 0}))[flag] += 1
        rows.append({"review_id": rid, "id": case["id"], "backend": backend,
                     "reported_verdict": original["reported_claim"]["verdict"], "author_verdict": verdict,
                     "flag": flag})
    report.update(status="author_approved_reported_claims", input_sha256={**author_hashes, "approval": _sha(approval_path)},
                  approved_review_count=len(reviewed), confirmation_source=source, confirmed_at=approval["confirmed_at"],
                  reported_claim_flags={backend: {**dict(c), "reviewed_count": sum(c.values()),
                      "resolved_flag_precision": fraction(c["true_flag"], c["true_flag"] + c["false_flag"]),
                      "resolution_coverage": fraction(c["true_flag"] + c["false_flag"], sum(c.values()))}
                      for backend, c in sorted(counts.items())}, review_results=rows)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--author-reviewed", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = score_adjudicated(args.pending, args.draft, author_reviewed_path=args.author_reviewed, approval_path=args.approval)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.output, report, exclusive=True)
    print(json.dumps({"status": report["status"], "acceptance": report["acceptance"], "output": str(args.output), "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
