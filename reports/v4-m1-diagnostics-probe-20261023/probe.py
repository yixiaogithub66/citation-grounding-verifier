"""Synthetic one-repair experiment, isolated from production and native benchmarks."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from grounding.client import ChatClient, _redact
from grounding.config import load_settings
from grounding.config_v4 import load_v4_config
from grounding.contracts import VerificationError
from grounding.prompts_v4 import DECOMPOSE_PROMPT, REPAIR_PROMPT, prompt_metadata
from grounding.scoring import usage_summary
from grounding.verifiers_v4 import extract_claims, _meaningful, _text, _json
from scripts.analyze_v4_nf import reference_cost

HERE = Path(__file__).resolve().parent
ARMS = ("terse_existing", "detailed_diagnostic")
LIMIT = 1200  # Predeclared resource limit; not selected from results.


def positions(answer, text):
    result, start = [], 0
    while len(result) < 8:
        start = answer.find(text, start)
        if start < 0:
            break
        result.append(start)
        start += 1
    return result


def diagnostic(payload, answer):
    """Report only deterministic coordinates; never assign, rewrite or classify text."""
    lines = ["Offsets are zero-based Unicode character positions; intervals are half-open.",
             "These are lexical diagnostics only, not factual/non-factual labels. "
             "Do not infer a label from coverage. Re-extract under the original task."]
    if not isinstance(payload, dict) or set(payload) != {"claims", "non_factual_spans"}:
        return "\n".join(lines + ["Top-level keys must be exactly claims and non_factual_spans."])[:LIMIT]
    if not all(isinstance(payload[k], list) for k in ("claims", "non_factual_spans")):
        return "\n".join(lines + ["Both fields must be arrays."])[:LIMIT]
    covered = set()
    for kind, fields in (("claims", {"claim_text", "source_span"}),
                         ("non_factual_spans", {"text", "reason"})):
        prior, occurrences = 0, {}
        for number, row in enumerate(payload[kind], 1):
            if not isinstance(row, dict) or set(row) != fields or not all(_text(row[k]) for k in fields):
                lines.append(f"{kind}[row {number}]: needs exactly nonempty fields {sorted(fields)}.")
                return "\n".join(lines)[:LIMIT]
            text = row["source_span"] if kind == "claims" else row["text"]
            key = (row["claim_text"], text) if kind == "claims" else text
            cursor = prior if kind == "claims" else max(prior, occurrences.get(key, -1) + 1)
            start = answer.find(text, cursor)
            if kind == "claims" and start >= 0 and key in occurrences:
                following = answer.find(text, max(prior, occurrences[key] + 1))
                if following >= 0:
                    start = following
            if start < 0:
                lines.append(f"{kind}[row {number}]: no permitted exact occurrence at/after cursor {cursor}; "
                             f"first up to 8 exact starts anywhere: {positions(answer, text)}. "
                             "Keep each array in source order; NF repeats need separate occurrences.")
                return "\n".join(lines)[:LIMIT]
            prior = occurrences[key] = start
            covered.update(range(start, start + len(text)))
    gaps, start = [], None
    for i in range(len(answer) + 1):
        missing = i < len(answer) and _meaningful(answer[i]) and i not in covered
        if missing and start is None:
            start = i
        elif not missing and start is not None:
            gaps.append([start, i])
            start = None
    lines.append(f"First up to 8 uncovered meaningful-character intervals: {gaps[:8]}; "
                 f"total intervals: {len(gaps)}. Decide their roles using the original task, not this diagnostic.")
    return "\n".join(lines)[:LIMIT]


def make_cases():
    def c(text, span=None): return {"claim_text": text, "source_span": span or text}
    def n(text, reason="Request or courtesy wording."): return {"text": text, "reason": reason}
    def case(name, answer, claims, nf, targets):
        return {"id": name, "answer": answer, "seed": {"claims": claims, "non_factual_spans": nf},
                "factual_source_targets": targets}
    return [
        case("nf_missing_repeat_zh", "请等候。北塔有六层。请等候。", [c("北塔有六层。")], [n("请等候。")], ["北塔有六层。"]),
        case("nf_excess_fr", "Merci. La caisse pèse 4 kg.", [c("La caisse pèse 4 kg.")], [n("Merci."), n("Merci.")], ["La caisse pèse 4 kg."]),
        case("nf_reverse_zh", "请坐。铜盒有两个锁。请稍候。", [c("铜盒有两个锁。")], [n("请稍候。"), n("请坐。")], ["铜盒有两个锁。"]),
        case("claim_nonexact_en", "The blue spool weighs 7 g. Please note this.", [c("The blue spool weighs 7 g.", "The blue spool weighs 7g.")], [n("Please note this.")], ["The blue spool weighs 7 g."]),
        case("claim_reverse_en", "The canoe is green. The shed has four windows.", [c("The shed has four windows."), c("The canoe is green.")], [], ["The canoe is green.", "The shed has four windows."]),
        case("coverage_missing_fact_zh", "展厅朝北。木柜高两米。", [c("展厅朝北。")], [], ["展厅朝北。", "木柜高两米。"]),
        case("instruction_premise_zh", "请关闭风扇，因为开关位于东墙。", [], [n("请关闭风扇，")], ["开关位于东墙。"]),
        case("nf_three_occurrences_en", "Continue. The tray holds nine beads. Continue. Continue.", [c("The tray holds nine beads.")], [n("Continue."), n("Continue.", "Instruction repeated.")], ["The tray holds nine beads."]),
        case("claim_negation_exactness_en", "Miro did not open the hatch. Please wait.", [c("Miro did not open the hatch.", "Miro opened the hatch.")], [n("Please wait.")], ["Miro did not open the hatch."]),
        case("coverage_numeric_sign_zh", "温度为−8°C。请记录。", [c("温度为−8°C。", "温度为")], [n("请记录。")], ["温度为−8°C。"]),
        case("condition_gap_en", "When the gate is shut, the lamp is amber. Please check.", [c("When the gate is shut, the lamp is amber.", "the lamp is amber.")], [n("Please check.")], ["When the gate is shut, the lamp is amber."]),
        case("nf_partial_order_es", "Por favor, espera. El armario tiene tres puertas. Gracias.", [c("El armario tiene tres puertas.")], [n("Gracias."), n("Por favor, espera.")], ["El armario tiene tres puertas."]),
    ]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
def error(seed, answer):
    try: extract_claims(seed, answer, max_claims=64)
    except VerificationError as exc: return exc.message
    raise AssertionError("Every seed must be invalid before either arm runs")


def self_check():
    cases = make_cases()
    assert len(cases) == 12 and len({c["id"] for c in cases}) == 12
    for case in cases:
        before = _json(case)
        assert error(case["seed"], case["answer"])
        detail = diagnostic(case["seed"], case["answer"])
        assert 0 < len(detail) <= LIMIT and "lexical diagnostics only" in detail
        assert _json(case) == before
        assert all(target in case["answer"] for target in case["factual_source_targets"])
    assert "non_factual_spans[row 2]" in diagnostic(cases[1]["seed"], cases[1]["answer"])
    assert "claims[row 1]" in diagnostic(cases[3]["seed"], cases[3]["answer"])
    assert "uncovered" in diagnostic(cases[5]["seed"], cases[5]["answer"])
    assert len(diagnostic({"claims": [], "non_factual_spans": []}, "x " * 100000)) <= LIMIT
    print("Offline checks passed: 12 invalid seeds; row, gap, bound, target and nonmutation checks.")


def prepare():
    self_check()
    if (HERE / "freeze.json").exists(): raise SystemExit("Freeze exists; do not overwrite or reselect cases.")
    settings = load_settings()
    config = load_v4_config(ROOT / "results/v4-nf-live-20261023/v4-config.json")
    cases = make_cases()
    write(HERE / "cases.json", cases)
    requests = []
    for index, case in enumerate(cases):
        arms = ARMS if index % 2 == 0 else ARMS[::-1]
        for arm in arms:
            feedback = error(case["seed"], case["answer"])
            if arm == ARMS[1]: feedback += "\n" + diagnostic(case["seed"], case["answer"])
            payload = {"generated_answer": case["answer"], "max_claims": config.max_claims,
                       "boundary_context": {"before": "", "after": ""}}
            requests.append({"id": case["id"], "arm": arm, "messages": [
                {"role": "system", "content": DECOMPOSE_PROMPT}, {"role": "user", "content": _json(payload)},
                {"role": "assistant", "content": _json(case["seed"])},
                {"role": "user", "content": REPAIR_PROMPT + "\nValidation errors:\n" + feedback}]})
    write(HERE / "requests.json", requests)
    files = [Path(__file__), HERE / "PLAN.md", HERE / "cases.json", HERE / "requests.json"]
    files += sorted((ROOT / "grounding").glob("*.py"))
    files += sorted((ROOT / "scripts").glob("*.py"))
    write(HERE / "freeze.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "settings": settings.public_dict(), "v4_config": config.public_dict(), "prompts": prompt_metadata(),
        "diagnostic_char_limit": LIMIT, "workers": 4, "pairs": 12, "logical_calls": 24,
        "files_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in files}})
    print("Frozen 12 synthetic pairs / 24 repair requests; no model calls.")


def run():
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    for path, digest in frozen["files_sha256"].items():
        if sha(ROOT / path) != digest: raise SystemExit("Freeze mismatch: " + path)
    settings = load_settings()
    if settings.public_dict() != frozen["settings"]: raise SystemExit("Settings changed since freeze")
    config = load_v4_config(ROOT / "results/v4-nf-live-20261023/v4-config.json")
    if config.public_dict() != frozen["v4_config"]: raise SystemExit("Stage settings changed since freeze")
    stage = config.stage_settings(settings, "decompose")
    cases = {c["id"]: c for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))}
    requests = json.loads((HERE / "requests.json").read_text(encoding="utf-8"))
    journal = HERE / "responses.jsonl"
    if journal.exists(): raise SystemExit("Journal exists; no accidental rerun or overwrite permitted")
    def one(request):
        telemetry, started = {}, time.monotonic()
        case = cases[request["id"]]
        row = {"id": request["id"], "arm": request["arm"], "valid": False,
               "response": None, "error": None, "factual_target_span_coverage": None, "telemetry": telemetry}
        try:
            response = ChatClient(stage).complete(request["messages"], "decompose_repair_1", telemetry)
            row["response"] = response
            claims, nf = extract_claims(response, case["answer"], max_claims=config.max_claims)
            row["valid"] = True
            claimed = {i for c in claims for i in range(c["source_start"], c["source_end"])}
            targets = []
            for target in case["factual_source_targets"]:
                start = case["answer"].index(target)
                needed = {i for i in range(start, start + len(target)) if _meaningful(case["answer"][i])}
                targets.append({"text": target, "source_covered_by_claims": needed <= claimed})
            row["factual_target_span_coverage"] = targets
        except VerificationError as exc:
            row["error"] = {"code": exc.code, "message": exc.message}
        except Exception as exc:
            row["error"] = {"code": "probe_unexpected_error", "message": str(exc), "type": type(exc).__name__}
        finally:
            row["latency_seconds"] = time.monotonic() - started
            for call in telemetry.get("calls", []):
                call.update(phase="decompose", thinking=stage.thinking, max_output_tokens=stage.max_output_tokens)
        return _redact(row, settings.api_key)
    # Keep each pair sequential; four pairs may be in flight. First arm balanced 6/6.
    def pair(pair_requests):
        return [one(request) for request in pair_requests]
    records = []
    with journal.open("x", encoding="utf-8", newline="\n") as handle, ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(pair, requests[i:i+2]) for i in range(0, len(requests), 2)]
        for future in as_completed(futures):
            for row in future.result():
                records.append(row)
                handle.write(_json(row) + "\n"); handle.flush(); os.fsync(handle.fileno())
                print(row["id"], row["arm"], "valid=" + str(row["valid"]), flush=True)
    summary = {}
    for arm in ARMS:
        selected = [r for r in records if r["arm"] == arm]
        summary[arm] = {"records": len(selected), "accepted": sum(r["valid"] for r in selected),
            "accepted_and_all_factual_source_targets_claim_covered": sum(r["valid"] and all(t["source_covered_by_claims"] for t in r["factual_target_span_coverage"]) for r in selected),
            "usage": usage_summary(selected), "cost": reference_cost(selected),
            "latency_seconds": [r["latency_seconds"] for r in selected]}
    changed_artifacts = [path for path, digest in frozen["files_sha256"].items()
                         if not (ROOT / path).exists() or sha(ROOT / path) != digest]
    write(HERE / "summary.json", {"arms": summary,
        "frozen_artifacts_unchanged": not changed_artifacts, "changed_frozen_artifacts": changed_artifacts,
        "note": "AI-authored protocol probe; lexical claim-source coverage is not semantic correctness. Fixed one-repair design cannot measure initial repair-trigger reduction or end-to-end F1."})
    print("All 24 responses journaled; summary written.")
    if changed_artifacts:
        raise SystemExit("Frozen artifacts changed during execution; results cannot be attributed to one frozen implementation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "prepare", "run"))
    command = parser.parse_args().command
    {"check": self_check, "prepare": prepare, "run": run}[command]()
