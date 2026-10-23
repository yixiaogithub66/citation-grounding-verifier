"""Independent offline contract audit; never imported by inference or the scorer."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ("pre_fix", "post_fix")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_issues(telemetry):
    """Count logical gates, not transport/format attempts within a gate."""
    issues = []
    for name in ("contradiction_reviews", "unsupported_reviews", "targeted_reasks"):
        counts = Counter(event.get("claim_id") for event in telemetry.get(name, []))
        for claim_id, count in counts.items():
            if not isinstance(claim_id, str) or not claim_id or count > 1:
                issues.append({"kind": "logical_gate_bound", "gate": name, "claim_id": claim_id, "count": count})
    chains = telemetry.get("verdict_chains", [])
    chain_ids = Counter(chain.get("claim_id") for chain in chains)
    for claim_id, count in chain_ids.items():
        if count != 1:
            issues.append({"kind": "duplicate_verdict_chain", "claim_id": claim_id, "count": count})
    for chain in chains:
        claim_id = chain.get("claim_id")
        saw_u = False
        for step in chain.get("steps", []):
            stage = step.get("stage", "")
            if stage.startswith("unsupported_review"):
                saw_u = True
            if saw_u and stage.startswith("contradiction_review"):
                issues.append({"kind": "C_after_U", "claim_id": claim_id, "stage": stage})
        if chain.get("status") == "error":
            if chain.get("final_verdict") is not None or not chain.get("error"):
                issues.append({"kind": "terminal_error_has_verdict_or_no_error", "claim_id": claim_id})
        elif chain.get("status") == "complete":
            validated = [step for step in chain.get("steps", []) if step.get("validated") is True]
            if (chain.get("error") or not validated
                    or validated[-1].get("verdict") != chain.get("final_verdict")):
                issues.append({"kind": "complete_chain_not_validated", "claim_id": claim_id})
        else:
            issues.append({"kind": "unknown_chain_status", "claim_id": claim_id})
    completion = telemetry.get("completion") or {}
    completed = set(completion.get("completed_claim_ids", []))
    failed = set(completion.get("unfinished_claim_ids", []))
    failed.update(chain.get("claim_id") for chain in chains if chain.get("status") == "error")
    if completed & failed:
        issues.append({"kind": "terminal_error_exposed_as_completed", "claim_ids": sorted(completed & failed)})
    return issues


def audit(run_dir: Path, output: Path):
    # Imports bind to the exact executed dependency snapshot, not today's checkout.
    sys.path.insert(0, str(run_dir / "source"))
    from grounding.contracts import VerificationRequest
    from grounding.contracts_v4 import validate_v4_report
    from grounding.prompts_v4 import prompt_metadata
    from grounding.verifiers_v4 import _json
    from scripts.benchmark_v4_nf import verify_freeze, balanced_schedule

    config = verify_freeze(run_dir)
    progress = read(run_dir / "progress.json")
    if progress.get("status") != "completed" or progress.get("frozen_artifacts_unchanged") is not True:
        raise ValueError("Full operational audit waits for a completed verified run")
    requests = rows(run_dir / "requests.jsonl")
    records = rows(run_dir / "responses.jsonl")
    expected = {(r["dataset"], r["id"], variant) for r in requests for variant in VARIANTS}
    identities = Counter((r["dataset"], r["id"], r["variant"]) for r in records)
    issues = []
    if set(identities) != expected or any(n != 1 for n in identities.values()):
        issues.append({"kind": "journal_identity_mismatch"})
    if len(records) != config["expected_records"] or len(records) != progress["completed_records"]:
        issues.append({"kind": "record_count_mismatch"})
    if requests != balanced_schedule(requests, config["run_options"]["seed"]):
        issues.append({"kind": "schedule_mismatch"})
    inputs = {(r["dataset"], r["id"]): r for r in requests}
    summary = defaultdict(lambda: {"records": 0, "status_counts": Counter(), "quotes": 0, "exact_quotes": 0,
                                   "logical_gates": Counter(), "call_stages": Counter(), "models": Counter(),
                                   "fingerprints": Counter(), "missing_model_calls": 0, "missing_fingerprint_calls": 0,
                                   "terminal_error_claims": 0, "completed_unsupported_claims": 0,
                                   "calls_with_errors": 0, "complete_empty_outputs": 0})
    expected_prompts = prompt_metadata()
    if config["prompts"] != expected_prompts:
        issues.append({"kind": "manifest_prompt_metadata_mismatch"})
    for record in records:
        identity = {"dataset": record["dataset"], "id": record["id"], "variant": record["variant"]}
        frozen = inputs[(record["dataset"], record["id"])]
        request = frozen["input"]
        telemetry = record.get("telemetry") or {}
        prediction = record.get("prediction")
        key = record["dataset"] + "/" + record["variant"]
        item = summary[key]
        item["records"] += 1
        local = review_issues(telemetry)
        if record.get("backend") != record["variant"] or record["backend_order"] != frozen["backend_order"]:
            local.append({"kind": "variant_or_order_mismatch"})
        if record["backend_order"][record["backend_order_index"]] != record["variant"]:
            local.append({"kind": "order_index_mismatch"})
        canonical = _json(VerificationRequest.from_dict(request).to_dict()).encode("utf-8")
        if telemetry.get("input_sha256") != hashlib.sha256(canonical).hexdigest():
            local.append({"kind": "inference_input_binding_mismatch"})
        if telemetry.get("config") != config["v4_config"]:
            local.append({"kind": "runtime_configuration_mismatch"})
        if telemetry.get("backend") != "optimized-v4.0" or telemetry.get("prompts") != expected_prompts:
            local.append({"kind": "runtime_backend_or_prompt_mismatch"})
        state = "error" if record.get("error") or prediction is None else prediction.get("status", "complete")
        item["status_counts"][state] += 1
        if state == "error":
            if prediction is not None:
                local.append({"kind": "error_record_has_public_prediction"})
        else:
            try:
                validate_v4_report(prediction, request["context_passages"])
            except Exception as exc:
                local.append({"kind": "public_contract_invalid", "exception": type(exc).__name__})
            item["complete_empty_outputs"] += state == "complete" and not prediction["claims"]
            completion = telemetry.get("completion", {})
            ids = completion.get("completed_claim_ids", [])
            if prediction["claims"] and len(ids) != len(prediction["claims"]):
                local.append({"kind": "public_claim_completion_count_mismatch"})
            chains = {chain.get("claim_id"): chain for chain in telemetry.get("verdict_chains", [])}
            for claim_id, claim in zip(ids, prediction["claims"]):
                chain = chains.get(claim_id, {})
                if chain.get("status") != "complete" or chain.get("final_verdict") != claim["verdict"]:
                    local.append({"kind": "public_verdict_differs_from_complete_chain", "claim_id": claim_id})
            for claim in prediction["claims"]:
                item["completed_unsupported_claims"] += claim["verdict"] == "UNSUPPORTED"
                for citation in claim["citations"]:
                    item["quotes"] += 1
                    index, quote = citation["index"], citation["quote"]
                    exact = (type(index) is int and 0 <= index < len(request["context_passages"])
                             and isinstance(quote, str) and bool(quote) and quote in request["context_passages"][index])
                    item["exact_quotes"] += exact
                    if not exact:
                        local.append({"kind": "public_quote_not_exact"})
            if state == "partial":
                public_errors = {error["id"] for error in prediction["errors"]}
                if public_errors != set(completion.get("unfinished_claim_ids", [])):
                    local.append({"kind": "partial_error_ids_mismatch"})
        for name in ("contradiction_reviews", "unsupported_reviews", "targeted_reasks"):
            item["logical_gates"][name] += len(telemetry.get(name, []))
        item["terminal_error_claims"] += sum(c.get("status") == "error" for c in telemetry.get("verdict_chains", []))
        for call in telemetry.get("calls", []):
            item["call_stages"][call.get("stage", "unknown")] += 1
            item["calls_with_errors"] += bool(call.get("error"))
            phase = call.get("phase")
            budget = config["v4_config"].get(phase)
            if not budget or any(call.get(k) != budget[k] for k in ("thinking", "max_output_tokens")):
                local.append({"kind": "stage_budget_mismatch", "stage": call.get("stage")})
            if call.get("model") is None:
                item["missing_model_calls"] += 1
            else:
                item["models"][call["model"]] += 1
                if call["model"] != config["settings"]["model"]:
                    local.append({"kind": "returned_model_differs", "model": call["model"]})
            if call.get("system_fingerprint") is None:
                item["missing_fingerprint_calls"] += 1
            else:
                item["fingerprints"][call["system_fingerprint"]] += 1
        issues.extend({**identity, **issue} for issue in local)
    result = {"kind": "nf-pre-post-independent-operational-audit", "records": len(records),
              "config_sha256": sha(run_dir / "config.json"), "journal_sha256": sha(run_dir / "responses.jsonl"),
              "audit_script_sha256": sha(Path(__file__)), "invariant_issues": issues,
              "summary": dict(summary),
              "review_count_policy": "Logical contradiction_reviews/unsupported_reviews/targeted_reasks events are bounded per claim; format and transport attempts are not additional logical review gates.",
              "error_policy_scope": "Terminal error chains must have no final verdict and cannot appear among completed public claims. Earlier failed attempts followed by successful validated repair are allowed.",
              "limitations": "This checks recorded execution contracts and exact citation substrings, not entailment, factual extraction coverage, author gold, or semantic accuracy. Missing returned model/fingerprint metadata remains unknown. No labels are loaded or changed."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"records": len(records), "violations": len(issues), "output": str(output)}))
    return result


def self_test():
    good = {"contradiction_reviews": [{"claim_id": "c1"}], "unsupported_reviews": [{"claim_id": "c1"}],
            "targeted_reasks": [{"claim_id": "c1"}],
            "calls": [{"stage": "contradiction_review"}, {"stage": "contradiction_review_repair_1"}],
            "verdict_chains": [{"claim_id": "c1", "status": "complete", "error": None,
                "final_verdict": "UNSUPPORTED", "steps": [
                    {"stage": "contradiction_review", "verdict": "UNSUPPORTED", "validated": True},
                    {"stage": "unsupported_review", "verdict": "UNSUPPORTED", "validated": True}]}],
            "completion": {"completed_claim_ids": ["c1"], "unfinished_claim_ids": []}}
    assert review_issues(good) == []
    duplicate = json.loads(json.dumps(good))
    duplicate["unsupported_reviews"].append({"claim_id": "c1"})
    assert any(x["kind"] == "logical_gate_bound" for x in review_issues(duplicate))
    reverse = json.loads(json.dumps(good))
    reverse["verdict_chains"][0]["steps"].reverse()
    assert any(x["kind"] == "C_after_U" for x in review_issues(reverse))
    bad_error = json.loads(json.dumps(good))
    bad_error["verdict_chains"][0].update(status="error", error={"code": "timeout"})
    kinds = {x["kind"] for x in review_issues(bad_error)}
    assert {"terminal_error_has_verdict_or_no_error", "terminal_error_exposed_as_completed"} <= kinds
    print("4 synthetic invariant audits passed; no model calls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "results/v4-nf-live-20261023")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("operational-audit.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        audit(args.run_dir.resolve(), args.output.resolve())
