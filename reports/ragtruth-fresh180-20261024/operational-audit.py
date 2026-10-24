"""Post-freeze, read-only operational audit; never loads native labels or scores.

This audit script is not an inference dependency and cannot dispatch model calls.
Pass --final only after the runner has ended. Its output does not certify semantic
correctness, unseenness beyond the separately audited exclusion ledger, or billing.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root, final=False):
    root = Path(root).resolve()
    output = root / "results/ragtruth-fresh180-20261024"
    freeze = root / "results/ragtruth-fresh180-freeze-20261024"
    data = root / "dataset/ragtruth-fresh180-20261024"
    pre = read(freeze / "preselection.json")
    source = Path(pre["source_root"])
    runner_path = source / "research/ragtruth-fresh180-20261024/run.py"
    spec = importlib.util.spec_from_file_location("operational_frozen_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    _, binding, _ = runner.check_freeze(freeze / "preselection.json", freeze / "binding.json", data)
    api = runner.frozen_imports(source, pre["code_files_sha256"])
    prompts = importlib.import_module("grounding.prompts")
    prompts_v4 = importlib.import_module("grounding.prompts_v4")
    v4_module = importlib.import_module("grounding.verifiers_v4")
    config = read(output / "config.json")
    progress = read(output / "progress.json")
    inputs, manifest = runner.load_requests(data, api, pre)
    expected = runner.schedule(inputs, manifest, pre["run_options"]["seed"])
    cases = {c["id"]: c for c in inputs}
    metadata = {m["id"]: m for m in manifest}
    planned = read(output / "planned-pairs.json")
    violations, notes = [], []
    def require(condition, code, **details):
        if not condition:
            violations.append({"code": code, **details})
    require(planned == expected, "schedule_differs_from_freeze")
    require(len(expected) == 540 and len({p["key"] for p in expected}) == 540, "expected_pair_count")
    allowed = {t["key"]: t for t in expected}
    require(config.get("preselection_freeze_sha256") == sha(freeze / "preselection.json"), "preselection_binding")
    require(config.get("binding_sha256") == sha(freeze / "binding.json"), "data_binding")
    for key in ("data_files_sha256",):
        require(config.get(key) == binding.get(key), "config_binding_mismatch", field=key)
    for key in ("code_files_sha256", "runner_sha256", "settings", "v4_config", "backends", "run_options", "price_reference"):
        require(config.get(key) == pre.get(key), "config_freeze_mismatch", field=key)
    # Enumerate results first; their reservations necessarily predate publication.
    rows = {p.stem: read(p) for p in sorted((output / "records").glob("*.json"))}
    reservations = {p.stem: read(p) for p in sorted((output / "reservations").glob("*.json"))}
    require(set(rows) <= set(reservations), "result_without_reservation")
    require(set(reservations) <= set(allowed), "unplanned_reservation")
    for key, reservation in reservations.items():
        require(reservation.get("task") == allowed.get(key), "reservation_identity", key=key)
    by_backend = {b: {"records": 0, "error_records": 0, "partial_records": 0, "provider_attempts": 0,
                      "usage_known_attempts": 0, "usage_unknown_attempts": 0, "prompt_tokens": 0,
                      "completion_tokens": 0, "total_tokens": 0, "cache_hit_tokens": 0, "cache_miss_tokens": 0,
                      "reasoning_tokens": 0, "reasoning_usage_known_attempts": 0,
                      "attempts_with_errors": 0, "attempts_with_response_text": 0,
                      "finish_reasons": Counter(), "models": Counter(), "system_fingerprints": Counter(),
                      "stages": Counter(), "phases": Counter(), "http_statuses": Counter(),
                      "review_events": Counter(), "maximum_C_reviews_per_claim": 0, "maximum_U_reviews_per_claim": 0}
                  for b in runner.BACKENDS}
    for key, row in rows.items():
        task = allowed.get(key)
        if task is None:
            require(False, "unplanned_result", key=key)
            continue
        require(row.get("pair_key") == key, "result_filename_identity", key=key)
        require(all(row.get(k) == task.get(k) for k in ("id", "backend", "source_id", "input_sha256", "backend_order", "backend_order_index")), "result_identity", key=key)
        case, meta = cases[task["id"]], metadata[task["id"]]
        require(all(row.get(k) == meta.get(k) for k in ("source_id", "task_type", "generator", "input_sha256")), "result_input_metadata", key=key)
        require(row["started_at"] >= reservations[key]["reserved_at"], "verification_preceded_reservation", key=key)
        stats = by_backend[row["backend"]]
        stats["records"] += 1
        stats["error_records"] += row.get("error") is not None
        stats["partial_records"] += bool(row.get("prediction") and row["prediction"].get("status") == "partial")
        if row.get("error") is None:
            try:
                api.validate(row.get("prediction"), case["input"]["context_passages"])
            except Exception as exc:
                require(False, "saved_public_report_invalid", key=key, error_type=type(exc).__name__)
            require(row.get("schema_valid") is True, "successful_record_schema_flag", key=key)
        else:
            require(row.get("prediction") is None and row.get("schema_valid") is False, "error_not_preserved", key=key)
        telemetry = row.get("telemetry", {})
        calls = telemetry.get("calls")
        require(isinstance(calls, list), "missing_attempt_list", key=key)
        calls = calls if isinstance(calls, list) else []
        if row["backend"] == "baseline":
            require(len(calls) == 0, "baseline_model_call", key=key)
        elif row["backend"] == "minimal":
            require(len(calls) <= 1, "minimal_multiple_attempts", key=key)
            require(telemetry.get("prompts") == prompts.prompt_metadata("minimal"), "minimal_prompt_mismatch", key=key)
        else:
            require(telemetry.get("config") == pre["v4_config"], "v4_effective_config_mismatch", key=key)
            require(telemetry.get("prompts") == prompts_v4.prompt_metadata(), "v4_prompt_mismatch", key=key)
            request = api.contracts.VerificationRequest.from_dict(case["input"])
            input_hash = hashlib.sha256(v4_module._json(request.to_dict()).encode()).hexdigest()
            require(telemetry.get("input_sha256") == input_hash, "v4_input_hash_mismatch", key=key)
            for kind, name in (("C", "contradiction_reviews"), ("U", "unsupported_reviews")):
                counts = Counter(event.get("claim_id") for event in telemetry.get(name, []))
                maximum = max(counts.values(), default=0)
                stats["maximum_" + kind + "_reviews_per_claim"] = max(stats["maximum_" + kind + "_reviews_per_claim"], maximum)
                stats["review_events"][kind] += sum(counts.values())
                require(maximum <= 1, "logical_review_limit", key=key, kind=kind, maximum=maximum)
            for chain in telemetry.get("verdict_chains", []):
                gates = [s.get("stage") for s in chain.get("steps", []) if s.get("stage") in ("contradiction_review", "unsupported_review")]
                require(gates in ([], ["contradiction_review"], ["unsupported_review"], ["contradiction_review", "unsupported_review"]), "review_chain_order", key=key, claim_id=chain.get("claim_id"))
        for call in calls:
            stats["provider_attempts"] += 1
            required_fields = ("attempt", "stage", "latency_seconds", "http_status", "usage", "finish_reason", "response_text", "model", "system_fingerprint")
            require(all(k in call for k in required_fields), "attempt_diagnostic_fields_missing", key=key)
            stats["attempts_with_errors"] += bool(call.get("error"))
            stats["attempts_with_response_text"] += isinstance(call.get("response_text"), str)
            for field, dest in (("finish_reason", "finish_reasons"), ("model", "models"), ("system_fingerprint", "system_fingerprints"), ("stage", "stages"), ("phase", "phases"), ("http_status", "http_statuses")):
                stats[dest][str(call.get(field))] += 1
            attempt = call.get("attempt")
            ceiling = 1 if row["backend"] == "minimal" else 1 + pre["v4_config"]["transport_retries"]
            require(type(attempt) is int and 1 <= attempt <= ceiling, "transport_attempt_bound", key=key)
            if row["backend"] == "optimized-v4.0":
                phase = call.get("phase")
                stage = pre["v4_config"].get(phase, {})
                require(phase in ("decompose", "verify", "review") and call.get("thinking") == stage.get("thinking") and call.get("max_output_tokens") == stage.get("max_output_tokens"), "v4_stage_budget_mismatch", key=key)
            usage = call.get("usage")
            if isinstance(usage, dict):
                stats["usage_known_attempts"] += 1
                for source_name, destination in (("prompt_tokens", "prompt_tokens"), ("completion_tokens", "completion_tokens"), ("total_tokens", "total_tokens"), ("prompt_cache_hit_tokens", "cache_hit_tokens"), ("prompt_cache_miss_tokens", "cache_miss_tokens")):
                    value = usage.get(source_name)
                    if type(value) is int:
                        stats[destination] += value
                reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                if type(reasoning) is int:
                    stats["reasoning_tokens"] += reasoning
                    stats["reasoning_usage_known_attempts"] += 1
            else:
                stats["usage_unknown_attempts"] += 1
    for identifier in cases:
        group = sorted((row for row in rows.values() if row.get("id") == identifier), key=lambda row: row["backend_order_index"])
        for previous, current in zip(group, group[1:]):
            require(previous["completed_at"] <= current["started_at"], "same_input_backends_overlap", id=identifier)
    operations = [read(p) for p in (output / "operations").glob("*.json")]
    unmatched = sorted(set(reservations) - set(rows))
    if not final:
        notes.append("While running, unmatched reservations are inflight/unknown observations and are not classified as lost results.")
    else:
        require(progress.get("status") in ("completed", "completed_with_unknown"), "runner_not_final")
        require(set(reservations) == set(allowed), "unreserved_final_pairs")
        integrity = read(output / "result-integrity.json")
        require(integrity.get("predictions_sha256") == sha(output / "predictions.jsonl"), "journal_hash")
        for name, digest in integrity.get("files_sha256", {}).items():
            require(sha(output / name) == digest, "durable_artifact_hash", file=name)
        journal = [json.loads(line) for line in (output / "predictions.jsonl").read_text().splitlines()]
        require(len(journal) == 540 and len({(r["id"], r["backend"]) for r in journal}) == 540, "final_journal_pairs")
        for row in journal:
            key = row["pair_key"]
            if key in rows:
                require(row == rows[key], "journal_result_changed", key=key)
            else:
                require(key in unmatched and (row.get("error") or {}).get("code") == "reserved_result_unknown" and "calls" not in row.get("telemetry", {}), "unknown_record_not_explicit", key=key)
    api.guard()
    runner.check_freeze(freeze / "preselection.json", freeze / "binding.json", data)
    notes.extend(["No gold was deserialized; no accuracy, hallucination label, or selection decision was computed.",
                  "Provider-attempt totals include every saved telemetry.calls entry, including retries, repairs, reviews, failed requests, and partial reports.",
                  "Missing provider usage remains unknown. Token totals are sums of known reported usage, not provider invoices.",
                  "Minimal request budgets are verified through frozen source/config; unlike v4 traces they are not echoed as per-call thinking/token fields.",
                  "This audit checks durable artifacts and recorded traces. It cannot independently observe requests outside the instrumented process."])
    result = {"schema_version": "ragtruth-fresh180-operational-audit-v1", "audited_at": datetime.now(timezone.utc).isoformat(),
              "final": final, "status": "passed" if not violations else "violations", "gold_loaded": False,
              "frozen_source_file_count": len(pre["code_files_sha256"]), "frozen_artifacts_unchanged": True,
              "snapshot": {"planned_pairs": len(expected), "durable_reservations": len(reservations), "durable_results": len(rows),
                           "unmatched_reservations": unmatched, "unmatched_meaning": "unknown_final" if final else "inflight_or_unknown_not_classified",
                           "run_operations": operations, "progress_io_warnings": progress.get("io_warnings", [])},
              "by_backend": by_backend, "violations": violations, "notes": notes,
              "audit_script_sha256": sha(__file__), "preselection_sha256": sha(freeze / "preselection.json"), "binding_sha256": sha(freeze / "binding.json")}
    destination = Path(__file__).parent
    runner.write_view(destination / "operational-audit.json", result)
    lines = ["# Fresh 180 operational audit", "", "Status: " + result["status"] + (" (final)" if final else " (running snapshot)"), "",
             f"Frozen source files: {len(pre['code_files_sha256'])}; reservations: {len(reservations)}; durable results: {len(rows)} / 540.", "",
             "| Backend | Records | Errors | Partial | Provider attempts | Usage unknown | C / U logical reviews |", "|---|---:|---:|---:|---:|---:|---:|"]
    for backend, stats in by_backend.items():
        lines.append(f"| {backend} | {stats['records']} | {stats['error_records']} | {stats['partial_records']} | {stats['provider_attempts']} | {stats['usage_unknown_attempts']} | {stats['review_events'].get('C',0)} / {stats['review_events'].get('U',0)} |")
    lines += ["", "Violations: " + str(len(violations)), "", *["- " + n for n in notes], ""]
    if violations:
        lines += ["```json", json.dumps(violations, ensure_ascii=False, indent=2), "```", ""]
    raw = "\n".join(lines).encode("utf-8")
    temporary = destination / "operational-audit.md.tmp"
    temporary.write_bytes(raw)
    temporary.replace(destination / "operational-audit.md")
    return {"final": final, "status": result["status"], "records": len(rows), "reservations": len(reservations),
            "violations": violations, "by_backend": {b: {k: s[k] for k in ("records", "provider_attempts", "usage_unknown_attempts")} for b, s in by_backend.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.root, args.final), ensure_ascii=True, sort_keys=True))
