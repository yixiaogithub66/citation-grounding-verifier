"""Offline audit only; not imported by inference or scoring."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / "grounding").is_dir() and (path / "AGENTS.md").is_file())
sys.path.insert(0, str(ROOT))
from grounding.contracts_v4 import validate_v4_report
from grounding.contracts import VerificationRequest
from grounding.prompts_v4 import prompt_metadata as original_prompts
from grounding.prompts_m1_faithful import prompt_metadata as new_prompts
from grounding.scoring import cost_summary, usage_summary
from grounding.verifiers_v4 import _json
from scripts.ragtruth_v4 import code_hashes
from scripts.summarize_v4_combined import runtime_diagnostics

RUN = ROOT / "results/v4-m1-faithful-20261023"
OUT = ROOT / "reports/v4-m1-faithful-20261023"
BACKENDS = ("optimized-v4.0", "optimized-v4-m1-faithful")
PRICES = {"input_per_million": .30, "cached_input_per_million": .006,
          "output_per_million": 1.20, "currency": "USD"}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def rows(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def known_reference_cost(records):
    calls = [call for record in records for call in record.get("telemetry", {}).get("calls", [])]
    amounts = []
    for call in calls:
        single = usage_summary([{"telemetry": {"calls": [call]}}])
        estimate = cost_summary(single, PRICES)
        if estimate["complete"]:
            amounts.append(estimate["estimated_amount"])
    return {"known_usage_reference_amount": sum(amounts), "currency": "USD",
            "priced_calls": len(amounts), "unpriced_calls": len(calls)-len(amounts),
            "covers_all_calls": len(amounts) == len(calls),
            "note": "Sum only calls with complete input/output/cache usage at the registered reference prices. Unpriced calls are excluded, not assumed free. This is not a complete total when any call is unpriced, and is not an actual bill."}

def main():
    registration = read(RUN / "registration.json")
    current = code_hashes(ROOT)
    progress = read(RUN / "dev/progress.json")
    if progress.get("status") != "completed":
        raise ValueError("Full audit waits for the registered run to complete")
    datasets = {
        "dev": {r["id"]: r["input"] for r in rows(ROOT / "dataset/ragtruth-blind-v1/recovery/inputs.jsonl")},
        "physics": {r["id"]: r["input"] for r in rows(ROOT / "dataset/cphos28/cases.jsonl")},
        "behavior": {(r["id"], side): r[side]["input"] for r in rows(RUN / "behavior/pairs.jsonl") for side in ("base", "variant")},
    }
    issues, details, all_records = [], {}, []
    for suite, expected in (("behavior", 96), ("physics", 92), ("dev", 360)):
        path = RUN / suite / ("predictions.jsonl" if suite == "dev" else "responses.jsonl")
        records = rows(path)
        config = read(RUN / suite / "config.json")
        suite_issues = []
        if len(records) != expected:
            suite_issues.append("Unexpected record count")
        if config["code_files_sha256"] != registration["code_files_sha256"] or current != registration["code_files_sha256"]:
            suite_issues.append("Source hash mismatch")
        if config["v4_config"] != registration["v4_config"] or config["settings"] != registration["settings"]:
            suite_issues.append("Configuration mismatch")
        if suite == "behavior" and digest(RUN / "behavior/pairs.jsonl") != config["dataset_sha256"]:
            suite_issues.append("Behavior input snapshot mismatch")
        if any(digest(RUN / suite / "source" / name) != value for name, value in config["code_files_sha256"].items()):
            suite_issues.append("Source snapshot mismatch")
        identities = set()
        status, empty, quotes, valid_quotes, errors = Counter(), Counter(), Counter(), Counter(), []
        completions = defaultdict(Counter)
        for record in records:
            backend = record["backend"]
            key = (record["pair_id"], record["side"]) if suite == "behavior" else record["id"]
            identity = (backend, key)
            if identity in identities or backend not in BACKENDS:
                suite_issues.append("Duplicate or unexpected record identity: " + repr(identity))
            identities.add(identity)
            request = datasets[suite][key]
            telemetry, prediction = record.get("telemetry") or {}, record.get("prediction")
            serialized_request = _json(VerificationRequest.from_dict(request).to_dict())
            if telemetry.get("input_sha256") != hashlib.sha256(serialized_request.encode("utf-8")).hexdigest():
                suite_issues.append("Per-record inference input binding mismatch: " + repr(identity))
            if telemetry.get("config") != registration["v4_config"]:
                suite_issues.append("Per-record runtime configuration mismatch: " + repr(identity))
            expected_prompts = original_prompts() if backend == BACKENDS[0] else new_prompts()
            if telemetry.get("prompts") != expected_prompts or telemetry.get("backend") != backend:
                suite_issues.append("Prompt/backend metadata mismatch: " + repr(identity))
            state = "error" if record.get("error") or prediction is None else prediction.get("status", "complete")
            status[(backend, state)] += 1
            if state == "error":
                errors.append({"identity": identity, "error": record.get("error")})
            else:
                validate_v4_report(prediction, request["context_passages"])
                if state == "complete" and not prediction["claims"]:
                    empty[backend] += 1
                for claim in prediction["claims"]:
                    for cite in claim["citations"]:
                        quotes[backend] += 1
                        valid_quotes[backend] += cite["quote"] in request["context_passages"][cite["index"]]
            completion = telemetry.get("completion", {})
            for name in ("total_extracted", "completed", "unfinished", "non_factual_fallbacks"):
                completions[backend][name] += completion.get(name, 0)
            for call in telemetry.get("calls", []):
                budget = registration["v4_config"][call["phase"]]
                if any(call.get(name) != budget[name] for name in ("thinking", "max_output_tokens")):
                    suite_issues.append("Stage budget mismatch: " + repr(identity))
            for field, maximum in (("contradiction_reviews", 1), ("unsupported_reviews", 1), ("targeted_reasks", 1)):
                counts = Counter(e["claim_id"] for e in telemetry.get(field, []))
                if any(value > maximum for value in counts.values()):
                    suite_issues.append("Review/requery count exceeded: " + repr(identity) + " " + field)
            for chain in telemetry.get("verdict_chains", []):
                stages = [step["stage"] for step in chain["steps"]]
                u = next((i for i, s in enumerate(stages) if s.startswith("unsupported_review")), None)
                if u is not None and any(s.startswith("contradiction_review") for s in stages[u + 1:]):
                    suite_issues.append("C review after U review: " + repr(identity))
            if state == "partial":
                errors.append({"identity": identity, "error": prediction["errors"]})
        runtime = runtime_diagnostics(records, PRICES, backends=BACKENDS)
        for backend in BACKENDS:
            runtime[backend]["known_usage_reference_cost"] = known_reference_cost([r for r in records if r["backend"] == backend])
        pair_index = defaultdict(dict)
        for record in records:
            pair_key = (record["pair_id"], record["side"]) if suite == "behavior" else record["id"]
            pair_index[pair_key][record["backend"]] = record
        same_extraction, same_initial_inputs, same_extraction_different_detection = [], [], []
        def detection(record):
            prediction = record.get("prediction")
            if record.get("error") or prediction is None:
                return None
            if any(c["verdict"] in ("CONTRADICTED", "UNSUPPORTED") for c in prediction["claims"]):
                return True
            return None if prediction.get("errors") else False
        for key, pair in pair_index.items():
            if set(pair) != set(BACKENDS):
                suite_issues.append("Incomplete backend pair: " + repr(key))
                continue
            a, b = (pair[backend] for backend in BACKENDS)
            a_claims = (a.get("telemetry", {}).get("extraction") or {}).get("claims")
            b_claims = (b.get("telemetry", {}).get("extraction") or {}).get("claims")
            if a_claims is not None and b_claims is not None and _json(a_claims) == _json(b_claims):
                same_extraction.append(key)
                if a_claims and all(any(c.get("stage") == "verify" for c in r["telemetry"]["calls"]) for r in (a, b)):
                    same_initial_inputs.append(key)
                    if detection(a) != detection(b):
                        same_extraction_different_detection.append({"identity": key, "reference": detection(a), "candidate": detection(b)})
        details[suite] = {
            "records": len(records), "sha256": digest(path),
            "status_counts": {backend: {s: status[(backend, s)] for s in ("complete", "partial", "error")} for backend in BACKENDS},
            "complete_empty_outputs": dict(empty), "completion_totals": dict(completions),
            "quote_count": dict(quotes), "valid_quote_count": dict(valid_quotes),
            "runtime": runtime, "errors": errors, "invariant_issues": suite_issues,
            "identical_serialized_extraction_claims": same_extraction,
            "identical_initial_verification_inputs": same_initial_inputs,
            "different_detection_despite_identical_initial_verification": same_extraction_different_detection,
            "identical_extraction_note": "Compared using v4 _json serialization, including dictionary insertion order, IDs, spans, fallback flags and list ordering. Identical initial-input counts additionally require nonempty claims and a verify call in both records. With unchanged v4 judgment/config and bound identical sources, these yield identical deterministic batching and initial verification payloads; later review paths can diverge stochastically. This is a diagnostic, not repeated-generation variance estimation.",
        }
        issues.extend({"suite": suite, "issue": issue} for issue in suite_issues)
        all_records.extend(records)
    hashes_ok = all(digest(ROOT / p) == sha for p, sha in registration["input_plan_config_sha256"].items())
    if not hashes_ok:
        issues.append({"suite": "registration", "issue": "Registered input/plan/config changed"})
    usage = usage_summary(all_records)
    audit = {"kind": "offline-m1-experiment-operational-audit", "registration_sha256": digest(RUN / "registration.json"),
             "git_freeze": registration["git_commit"], "record_count": len(all_records),
             "all_registered_inputs_unchanged": hashes_ok, "invariant_issues": issues,
             "suites": details, "total_usage": usage, "total_cost": cost_summary(usage, PRICES),
             "known_usage_reference_cost": known_reference_cost(all_records),
             "limitations": "Exact citations and execution coverage do not certify answer-to-claim fidelity or evidence entailment. Empty complete outputs may hide factual omissions. No gold is relabeled."}
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / "operational-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"records": len(all_records), "issues": issues, "cost": audit["total_cost"]}, ensure_ascii=True))

if __name__ == "__main__":
    main()
