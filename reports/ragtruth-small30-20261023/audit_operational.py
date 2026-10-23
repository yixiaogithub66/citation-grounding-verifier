"""Independent offline execution audit of the exploratory thirty-response run.

No native labels, scoring report, prompts from external sources, or model calls.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports/v4-nf-live-20261023/audit_operational.py"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_review_checker():
    """Reuse only a pure gate checker, never run the historical 548-record audit."""
    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "review_issues"]
    if len(functions) != 1:
        raise ValueError("Expected one historical pure review checker")
    namespace = {"Counter": Counter}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(HELPER), "exec"), namespace)
    return namespace["review_issues"]


def completion_chain_issues(chains, done, failed, exclusions, extracted):
    """NON_FACTUAL is a completed fallback decision, but not a public claim."""
    issues = []
    excluded = [row.get("claim_id") for row in exclusions]
    if len(excluded) != len(set(excluded)) or set(excluded) & (set(done) | set(failed)):
        issues.append({"kind": "fallback_exclusion_identity_overlap"})
    if {key for key, chain in chains.items() if chain.get("status") == "complete"} != set(done) | set(excluded):
        issues.append({"kind": "complete_chain_ids_mismatch"})
    if {key for key, chain in chains.items() if chain.get("status") == "error"} != set(failed):
        issues.append({"kind": "error_chain_ids_mismatch"})
    for cid in excluded:
        if not extracted.get(cid, {}).get("extraction_fallback") or chains.get(cid, {}).get("final_verdict") != "NON_FACTUAL":
            issues.append({"kind": "fallback_exclusion_not_valid_fallback_decision", "claim_id": cid})
    return issues


def audit(run_dir: Path, output: Path):
    sys.path.insert(0, str(run_dir / "source"))
    from grounding.contracts import VerificationRequest
    from grounding.contracts_v4 import validate_v4_report
    from grounding.prompts_v4 import prompt_metadata
    from grounding.verifiers_v4 import _json
    from scripts.benchmark_ragtruth import _canonical_sha
    from scripts.ragtruth_small30 import check_freeze
    from scripts.analyze_v4_nf import runtime_summary
    from scripts.score_v4 import load_prediction_journal

    # Verify imports actually resolved to the bound snapshot.
    imported = {name: str(Path(sys.modules[name].__file__).resolve()) for name in
                ("grounding.contracts", "grounding.contracts_v4", "grounding.prompts_v4",
                 "grounding.verifiers_v4", "scripts.ragtruth_small30", "scripts.analyze_v4_nf", "scripts.score_v4")}
    if any(not Path(path).is_relative_to((run_dir / "source").resolve()) for path in imported.values()):
        raise ValueError("Audit dependency was imported from outside the frozen snapshot")
    config = check_freeze(run_dir, bound=True)  # Gold is hashed opaquely, never parsed.
    binding, progress = read(run_dir / "binding.json"), read(run_dir / "progress.json")
    if progress.get("status") != "completed" or progress.get("frozen_artifacts_unchanged") is not True:
        raise ValueError("Audit requires a completed run with verified frozen artifacts")
    requests, manifest = rows(run_dir / "data/inputs.jsonl"), rows(run_dir / "data/manifest.jsonl")
    records = load_prediction_journal(run_dir / "predictions.jsonl")
    expected = {(case["id"], config["backend"]) for case in requests}
    identities = Counter((record["id"], record["backend"]) for record in records)
    if len(records) != 30 or len(expected) != 30 or set(identities) != expected or any(n != 1 for n in identities.values()):
        raise ValueError("Journal must contain all thirty frozen identities exactly once")
    inputs = {row["id"]: row["input"] for row in requests}
    metadata = {row["id"]: row for row in manifest}
    if len(metadata) != 30 or set(metadata) != set(inputs):
        raise ValueError("Input and manifest identity mismatch")
    review_issues = load_review_checker()
    issues = []
    counters = Counter({key: 0 for key in ("missing_returned_model_calls", "missing_fingerprint_calls",
        "missing_completion_empty_extraction", "complete_empty_outputs", "calls_with_errors")})
    status_counts, logical_gates, stages, models, fingerprints, errors = (Counter() for _ in range(6))
    expected_prompts = prompt_metadata()
    if config["prompts"] != expected_prompts:
        issues.append({"kind": "frozen_prompt_metadata_mismatch"})
    if progress.get("completed_records") != 30 or progress.get("expected_records") != 30:
        issues.append({"kind": "progress_count_mismatch"})
    per_case = []
    for record in records:
        rid = record["id"]
        request, meta = inputs[rid], metadata[rid]
        parsed_request = VerificationRequest.from_dict(request)
        telemetry = record.get("telemetry") or {}
        prediction = record.get("prediction")
        local = review_issues(telemetry)
        if set(request) != {"context_passages", "generated_answer"}:
            local.append({"kind": "request_metadata_leak"})
        canonical = _json(parsed_request.to_dict()).encode("utf-8")
        if telemetry.get("input_sha256") != hashlib.sha256(canonical).hexdigest():
            local.append({"kind": "inference_input_sha_mismatch"})
        if meta.get("input_sha256") != _canonical_sha(request) or record.get("input_sha256") != meta.get("input_sha256"):
            local.append({"kind": "manifest_record_input_sha_mismatch"})
        for field in ("source_id", "task_type", "generator"):
            if record.get(field) != meta.get(field):
                local.append({"kind": "identity_metadata_mismatch", "field": field})
        if telemetry.get("config") != config["v4_config"]:
            local.append({"kind": "runtime_configuration_mismatch"})
        if telemetry.get("backend") != config["backend"] or telemetry.get("prompts") != expected_prompts:
            local.append({"kind": "runtime_backend_or_prompt_mismatch"})
        state = "error" if record.get("error") or prediction is None else prediction.get("status", "complete")
        status_counts[state] += 1
        if record.get("error"):
            errors[record["error"].get("code")] += 1
        chains = {chain.get("claim_id"): chain for chain in telemetry.get("verdict_chains", [])}
        extracted = {claim.get("id"): claim for claim in (telemetry.get("extraction") or {}).get("claims", [])}
        completion = telemetry.get("completion")
        if completion is None:
            # All-non-factual early return has no claim-completion ledger.
            counters["missing_completion_empty_extraction"] += not extracted
            if extracted or chains or (prediction or {}).get("claims"):
                local.append({"kind": "completion_ledger_missing_for_nonempty_claims"})
            completion = {"total_extracted": 0, "completed": 0, "unfinished": 0,
                          "non_factual_fallbacks": 0, "completed_claim_ids": [], "unfinished_claim_ids": []}
        done, failed = completion.get("completed_claim_ids", []), completion.get("unfinished_claim_ids", [])
        nf = telemetry.get("fallback_exclusions", [])
        if (len(done) != len(set(done)) or len(failed) != len(set(failed)) or set(done) & set(failed)
                or completion.get("completed") != len(done) or completion.get("unfinished") != len(failed)
                or completion.get("total_extracted") != len(extracted)
                or completion.get("non_factual_fallbacks") != len(nf)
                or len(extracted) != len(done) + len(failed) + len(nf)):
            local.append({"kind": "completion_accounting_mismatch"})
        local.extend(completion_chain_issues(chains, done, failed, nf, extracted))
        counters["completed_claims"] += len(done)
        counters["terminal_error_claims"] += len(failed)
        counters["fallback_excluded_claims"] += len(nf)
        if state == "error":
            if prediction is not None:
                local.append({"kind": "error_record_exposes_prediction"})
        else:
            try:
                validate_v4_report(prediction, request["context_passages"])
            except Exception as exc:
                local.append({"kind": "public_contract_invalid", "exception": type(exc).__name__})
            if record.get("schema_valid") is not True or record.get("validation_errors"):
                local.append({"kind": "public_runner_validation_metadata_mismatch"})
            claims = prediction.get("claims", [])
            counters["complete_empty_outputs"] += state == "complete" and not claims
            if len(claims) != len(done):
                local.append({"kind": "public_completion_count_mismatch"})
            for cid, claim in zip(done, claims):
                chain = chains.get(cid, {})
                if chain.get("status") != "complete" or chain.get("final_verdict") != claim["verdict"]:
                    local.append({"kind": "public_verdict_complete_chain_mismatch", "claim_id": cid})
                if extracted.get(cid, {}).get("claim_text") != claim.get("claim_text"):
                    local.append({"kind": "public_claim_text_extraction_mismatch", "claim_id": cid})
                counters["completed_unsupported_claims"] += claim["verdict"] == "UNSUPPORTED"
                for citation in claim["citations"]:
                    counters["quotes"] += 1
                    index, quote = citation["index"], citation["quote"]
                    exact = (type(index) is int and 0 <= index < len(request["context_passages"])
                             and isinstance(quote, str) and bool(quote) and quote in request["context_passages"][index])
                    counters["exact_quotes"] += exact
                    if not exact:
                        local.append({"kind": "public_quote_not_exact", "claim_id": cid})
            if state == "partial":
                public_errors = prediction["errors"]
                if len(public_errors) != len(failed) or {error["id"] for error in public_errors} != set(failed):
                    local.append({"kind": "partial_error_ids_mismatch"})
                for error in public_errors:
                    cid = error["id"]
                    if error.get("claim_text") != extracted.get(cid, {}).get("claim_text"):
                        local.append({"kind": "partial_error_text_mismatch", "claim_id": cid})
                    if error.get("code") != chains.get(cid, {}).get("error", {}).get("code"):
                        local.append({"kind": "partial_error_code_mismatch", "claim_id": cid})
            elif failed:
                local.append({"kind": "complete_envelope_has_unfinished_claims"})
        for name in ("contradiction_reviews", "unsupported_reviews", "targeted_reasks"):
            logical_gates[name] += len(telemetry.get(name, []))
        for call in telemetry.get("calls", []):
            stages[call.get("stage", "unknown")] += 1
            counters["calls_with_errors"] += bool(call.get("error"))
            budget = config["v4_config"].get(call.get("phase"))
            if not budget or any(call.get(k) != budget[k] for k in ("thinking", "max_output_tokens")):
                local.append({"kind": "stage_budget_mismatch", "stage": call.get("stage")})
            if call.get("model") is None:
                counters["missing_returned_model_calls"] += 1
            else:
                models[call["model"]] += 1
                if call["model"] != config["settings"]["model"]:
                    local.append({"kind": "returned_model_differs", "model": call["model"]})
            if call.get("system_fingerprint") is None:
                counters["missing_fingerprint_calls"] += 1
            else:
                fingerprints[call["system_fingerprint"]] += 1
        issues.extend({"id": rid, **issue} for issue in local)
        per_case.append({"id": rid, "status": state, "completed_claims": len(done),
                         "unfinished_claims": len(failed), "fallback_exclusions": len(nf),
                         "calls": len(telemetry.get("calls", [])), "issues": len(local)})
    runtime = runtime_summary(records, config["price_reference"])
    if (progress.get("partial_records") != status_counts["partial"]
            or progress.get("error_records") != status_counts["error"]):
        issues.append({"kind": "progress_status_totals_mismatch"})
    result = {"schema_version": "ragtruth-small30-independent-operational-audit-v1",
        "records": len(records), "invariant_issues": issues, "passed": not issues,
        "summary": {**counters, "status_counts": dict(status_counts), "logical_gates": dict(logical_gates),
            "call_stages": dict(stages), "returned_models": dict(models), "returned_fingerprints": dict(fingerprints),
            "record_errors": dict(errors), "usage": runtime["usage"], "reference_cost": runtime["reference_cost"]},
        "per_case": per_case, "frozen_dependency_paths": imported,
        "input_hashes": {"preselection.json": sha(run_dir / "preselection.json"), "binding.json": sha(run_dir / "binding.json"),
            "predictions.jsonl": sha(run_dir / "predictions.jsonl"), "progress.json": sha(run_dir / "progress.json"),
            "inputs.jsonl": sha(run_dir / "data/inputs.jsonl"), "manifest.jsonl": sha(run_dir / "data/manifest.jsonl")},
        "audit_script_sha256": sha(Path(__file__)), "pure_review_checker_source_sha256": sha(HELPER),
        "review_policy": "Each logical C/U/targeted event is bounded per claim; transport/format attempts are not additional logical gates. C cannot follow U.",
        "error_policy": "Terminal error has no final verdict and cannot be public completed U; earlier errors followed by validated repair are allowed.",
        "nonfactual_completion_policy": "A validated NON_FACTUAL completion of a provisional extraction_fallback skeleton is an exclusion; its chain is complete but it cannot count as a completed public claim.",
        "limitations": "Recorded deterministic contracts only; not semantic correctness, extraction recall, or author adjudication. Native labels and score report were not parsed. Returned model/fingerprint metadata can remain unknown."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"records": len(records), "violations": len(issues), "passed": not issues,
                      "audit_script_sha256": result["audit_script_sha256"], "output": str(output)}))
    return result


def self_test():
    checker = load_review_checker()
    assert checker({"unsupported_reviews": [{"claim_id": "x"}, {"claim_id": "x"}]})
    chains = {"x": {"status": "complete", "final_verdict": "SUPPORTED"},
              "nf": {"status": "complete", "final_verdict": "NON_FACTUAL"},
              "err": {"status": "error", "final_verdict": None}}
    excluded = [{"claim_id": "nf"}]
    assert not completion_chain_issues(chains, ["x"], ["err"], excluded, {"nf": {"extraction_fallback": True}})
    assert completion_chain_issues(chains, ["x"], ["err"], excluded, {"nf": {"extraction_fallback": False}})
    assert completion_chain_issues(chains, ["x", "err"], ["err"], excluded, {"nf": {"extraction_fallback": True}})
    print("4 synthetic audit checks passed; no model calls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "results/ragtruth-small30-20261023")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("operational-audit.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        audit(args.run_dir.resolve(), args.output.resolve())
