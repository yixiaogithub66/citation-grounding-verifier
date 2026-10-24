#!/usr/bin/env python3
"""Frozen, offline native scoring of the fresh 180-answer three-backend run."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import score_v4
from scripts.analyze_v4_nf import runtime_summary
from scripts.ragtruth_score import _interval
from scripts.validate_dataset import strict_json_loads

BACKENDS = ("baseline", "minimal", "optimized-v4.0")
PAIRS = (("minimal", "baseline"), ("optimized-v4.0", "baseline"), ("optimized-v4.0", "minimal"))
METRICS = ("correct_decisions_per_all_cases", "resolved_f1", "complete_case_rate", "decision_coverage")
SAMPLES, SEED = 2000, 20261024
DATA_FILES = ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_object(path):
    value = strict_json_loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return value


def read_rows(path):
    return [strict_json_loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def valid_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def measured_runtime(records, prices, *, positions=True):
    """Keep missing whole-record accounting unknown, not a zero-cost run."""
    clean, missing_telemetry = [], 0
    for row in records:
        telemetry = row.get("telemetry")
        present = isinstance(telemetry, dict) and isinstance(telemetry.get("calls"), list)
        if present and any(not isinstance(call, dict) for call in telemetry["calls"]):
            raise ValueError("Call telemetry entries must be objects")
        if not present:
            missing_telemetry += 1
        copied = dict(row)
        copied["telemetry"] = telemetry if present else {"calls": []}
        # The shared helper expects latency for every row. Replace only for its
        # invocation; all displayed latency statistics are rebuilt below.
        copied["latency_seconds"] = row["latency_seconds"] if valid_time(row.get("latency_seconds")) else 0.0
        clean.append(copied)
    result = runtime_summary(clean, prices)
    times = sorted(row["latency_seconds"] for row in records if valid_time(row.get("latency_seconds")))
    result.update(latency_measured_count=len(times), latency_unknown_count=len(records) - len(times),
                  mean_latency_seconds=sum(times) / len(times) if times else None,
                  p50_latency_seconds=times[math.ceil(.50 * len(times)) - 1] if times else None,
                  p95_latency_seconds=times[math.ceil(.95 * len(times)) - 1] if times else None,
                  total_recorded_latency_seconds=sum(times))
    result["usage"]["records_missing_telemetry"] = missing_telemetry
    result["usage"]["call_count_complete"] = not missing_telemetry
    if missing_telemetry:
        for key in ("usage_complete", "cache_usage_complete", "reasoning_usage_complete"):
            result["usage"][key] = False
        result["reference_cost"].update(estimated_total=None, complete=False, cache_standardized_all_miss_total=None)
    result["reference_cost"]["records_missing_telemetry"] = missing_telemetry
    # Do not retain the two-arm helper's incomplete position table.
    result.pop("by_variant_execution_order", None)
    if positions:
        result["by_execution_position"] = {}
        for position in (0, 1, 2, None):
            selected = [row for row in records if (row.get("backend_order_index") if type(row.get("backend_order_index")) is int else None) == position]
            if selected:
                result["by_execution_position"][str(position) if position is not None else "unrecorded"] = measured_runtime(selected, prices, positions=False)
        invalid = [row for row in records if type(row.get("backend_order_index")) is int and row["backend_order_index"] not in (0, 1, 2)]
        if invalid:
            raise ValueError("Execution position must be 0, 1, 2 or absent")
    return result


def metric_values(rows):
    summary = score_v4._summary(rows)
    return {name: summary["resolved_only"]["f1"]["value"] if name == "resolved_f1" else summary[name]["value"] for name in METRICS}


def paired_bootstrap(rows, *, samples=SAMPLES, seed=SEED):
    sources = sorted({row["source_id"] for row in rows})
    groups = {source: [row for row in rows if row["source_id"] == source] for source in sources}
    points = {backend: metric_values([row for row in rows if row["backend"] == backend]) for backend in BACKENDS}
    values = {backend: {metric: [] for metric in METRICS} for backend in BACKENDS}
    differences = {f"{candidate}_minus_{reference}": {metric: [] for metric in METRICS} for candidate, reference in PAIRS}
    rng = random.Random(seed)
    for _ in range(samples):
        draw = [row for source in rng.choices(sources, k=len(sources)) for row in groups[source]] if sources else []
        estimates = {backend: metric_values([row for row in draw if row["backend"] == backend]) for backend in BACKENDS}
        for backend in BACKENDS:
            for metric, value in estimates[backend].items():
                if value is not None:
                    values[backend][metric].append(value)
        for candidate, reference in PAIRS:
            for metric in METRICS:
                left, right = estimates[candidate][metric], estimates[reference][metric]
                if left is not None and right is not None:
                    differences[f"{candidate}_minus_{reference}"][metric].append(left - right)
    paired = {}
    for candidate, reference in PAIRS:
        key = f"{candidate}_minus_{reference}"
        paired[key] = {}
        for metric in METRICS:
            left, right = points[candidate][metric], points[reference][metric]
            point = left - right if left is not None and right is not None else None
            paired[key][metric] = _interval(differences[key][metric], samples, point)
    return {"method": "pooled_whole_source_cluster_percentile", "confidence_level": .95,
            "samples": samples, "seed": seed, "source_count": len(sources),
            "resampling_unit": "source_id; all six responses and all three backends retained together",
            "primary_comparison": "optimized-v4.0_minus_minimal",
            "backends": {backend: {metric: _interval(values[backend][metric], samples, points[backend][metric]) for metric in METRICS} for backend in BACKENDS},
            "paired": paired, "warning": "Resolved F1 may condition on different answers. Single generation; intervals do not isolate model or service variation."}


def pair_transitions(rows):
    lookup = {(row["id"], row["backend"]): row for row in rows}
    identifiers = sorted({row["id"] for row in rows})
    result = {}
    def state(row):
        return "unknown" if row["y_pred"] is None else "correct" if row["y_pred"] == row["y_true"] else "wrong"
    for candidate, reference in PAIRS:
        transitions = Counter({f"{before}_to_{after}": 0 for before in ("correct", "wrong", "unknown") for after in ("correct", "wrong", "unknown")})
        common = candidate_correct = reference_correct = candidate_only = reference_only = 0
        for identifier in identifiers:
            a, b = lookup[identifier, reference], lookup[identifier, candidate]
            old, new = state(a), state(b)
            transitions[f"{old}_to_{new}"] += 1
            if a["y_pred"] is not None and b["y_pred"] is not None:
                common += 1
                candidate_correct += new == "correct"
                reference_correct += old == "correct"
                candidate_only += new == "correct" and old == "wrong"
                reference_only += old == "correct" and new == "wrong"
        result[f"{candidate}_minus_{reference}"] = {
            "all_cases": len(identifiers), "reference_to_candidate": dict(transitions),
            "common_resolved": {"count": common, "candidate_correct": candidate_correct, "reference_correct": reference_correct,
                                "candidate_correct_only": candidate_only, "reference_correct_only": reference_only},
            "note": "Common-resolved subset is descriptive and selected by observed outcomes; it is not the all-case primary endpoint."}
    return result


def analyze(records, manifest, gold, inputs, config, *, samples=SAMPLES, seed=SEED):
    if config.get("backends") != list(BACKENDS):
        raise ValueError("Expected the frozen three backends in canonical order")
    identifiers = {row["id"] for row in manifest}
    expected = {(identifier, backend) for identifier in identifiers for backend in BACKENDS}
    actual = [(row["id"], row["backend"]) for row in records]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Final report requires exactly one record per manifest/backend slot")
    prices = config.get("price_reference")
    if not isinstance(prices, dict):
        raise ValueError("Explicit frozen reference prices are required")
    report = score_v4.score_records(records, manifest, gold, inputs=inputs, backends=list(BACKENDS),
                                    bootstrap_samples=samples, seed=seed, prices=prices)
    report["fresh180_schema"] = "ragtruth-fresh180-three-backend-v1"
    report["qualification"] = "Native answer-level comparison; no author adjudication or claim-level semantic gold. One realized run per backend and request."
    report["runtime_by_backend"] = {}
    for backend in BACKENDS:
        selected = [row for row in records if row["backend"] == backend]
        if backend == "baseline" and any((row.get("telemetry") or {}).get("calls") for row in selected):
            raise ValueError("Non-LLM baseline unexpectedly contains model calls")
        report["runtime_by_backend"][backend] = measured_runtime(selected, prices)
        observations = [row for row in report["case_results"] if row["backend"] == backend]
        report["backends"][backend]["by_generator"] = {
            generator: score_v4._summary([row for row in observations if row["generator"] == generator])
            for generator in sorted({row["generator"] for row in observations})}
        usable_ids = {row["id"] for row in observations if row["status"] != "error"}
        citation_count = sum(len(claim["citations"]) for row in selected if row["id"] in usable_ids for claim in row["prediction"]["claims"])
        report["backends"][backend]["public_citation_contract"] = {
            "valid_exact_citations": citation_count, "checked_citations": citation_count,
            "rate": 1.0 if citation_count else None,
            "scope": "Completed public claims in contract-valid reports, including partial. Mechanical validity is not semantic support."}
    report["three_backend_source_bootstrap"] = paired_bootstrap(report["case_results"], samples=samples, seed=seed)
    report["paired_transitions"] = pair_transitions(report["case_results"])
    report["native_sample_composition"] = {
        "answer_count": len(manifest), "source_count": len({row["source_id"] for row in manifest}),
        "answers_by_task": dict(Counter(row["task_type"] for row in manifest)),
        "answers_by_generator": dict(Counter(row["generator"] for row in manifest)),
        "positive_answers": sum(bool(row["labels"]) for row in gold),
        "negative_answers": sum(not row["labels"] for row in gold)}
    gold_map = {row["id"]: row for row in gold}
    report["native_sample_composition"]["by_task"] = {
        task: {"answers": len(selected), "sources": len({row["source_id"] for row in selected}),
               "positive": sum(bool(gold_map[row["id"]]["labels"]) for row in selected),
               "negative": sum(not gold_map[row["id"]]["labels"] for row in selected)}
        for task in sorted({row["task_type"] for row in manifest})
        for selected in ([row for row in manifest if row["task_type"] == task],)}
    report["measurement_notes"] = [
        "Correct decisions/all answers is the primary all-case yield; unknown is not counted as correct or forced into FN/FP.",
        "Complete empty claims predicts negative and is separately counted. Native FP is not adjudicated true FP.",
        "Claim completion only covers extracted/accounted targets, not semantic fact recall.",
        "Legacy whole-case-failure metrics are retained unchanged and treat all partials as whole failures.",
        "Reference cost uses frozen prices; all-miss normalization is not provider billing. Missing usage or telemetry is unknown, not free.",
        "Reasoning tokens are included in completion tokens; do not charge twice. Concurrent per-answer latency sums are not run wall time."]
    return report


def percent(value):
    if isinstance(value, dict):
        return "n/a" if value["value"] is None else f"{value['numerator']}/{value['denominator']} ({value['value']:.2%})"
    return "n/a" if value is None else f"{value:.2%}"


def number(value):
    return "unknown" if value is None else f"{value:.6f}"


def render(report):
    lines = ["# RAGTruth 新 180 条：三方案完整比较", "", report["qualification"], "",
             "主分母是同一批全部回答。unknown 不计正确、不进入 TN/FN；合法 partial 中的 C/U 可完成回答级检测，但不等于完整报告。", "",
             "| 后端 | 正确决策/全部 | 已决准确率 | 已决 F1 | 完整/部分/错误 | unknown 正/负 | 合法完整空 claims |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for backend in BACKENDS:
        item = report["backends"][backend]; c, s = item["confusion"], item["status_counts"]
        lines.append(f"| {backend} | {percent(item['correct_decisions_per_all_cases'])} | {percent(item['resolved_only']['accuracy'])} | {percent(item['resolved_only']['f1'])} | {s.get('complete',0)}/{s.get('partial',0)}/{s.get('error',0)} | {c['unknown_positive']}/{c['unknown_negative']} | {item['empty_claims_count']} |")
    lines += ["", "| 后端 | TP/FP/TN/FN | 决策覆盖率 | 完整报告率 | 已提取目标完成率 | 未知目标总数的回答 |", "| --- | --- | --- | --- | --- | --- |"]
    for backend in BACKENDS:
        item = report["backends"][backend]; c = item["confusion"]
        lines.append(f"| {backend} | {'/'.join(str(c[k]) for k in ('tp','fp','tn','fn'))} | {percent(item['decision_coverage'])} | {percent(item['complete_case_rate'])} | {percent(item['claim_completion_known_cases'])} | {item['unknown_claim_total_case_count']} |")
    lines += ["", "| 任务 / 后端 | 正确决策/全部 | 已决 F1 | 完整报告率 |", "| --- | --- | --- | --- |"]
    for backend in BACKENDS:
        for task, item in report["backends"][backend]["by_task"].items():
            lines.append(f"| {task} / {backend} | {percent(item['correct_decisions_per_all_cases'])} | {percent(item['resolved_only']['f1'])} | {percent(item['complete_case_rate'])} |")
    lines += ["", "| 后端 | 调用/缺 usage | input/output/reasoning tokens | mean/P95 秒 | 已知缓存参考 USD / 未计价调用 | 全未缓存已知 USD |", "| --- | --- | --- | --- | --- | --- |"]
    for backend in BACKENDS:
        r = report["runtime_by_backend"][backend]; u, c = r["usage"], r["reference_cost"]
        count = str(u["calls"]) if u["call_count_complete"] else ">=" + str(u["calls"])
        lines.append(f"| {backend} | {count}/{u['calls_missing_usage']} | {u['prompt_tokens']}/{u['completion_tokens']}/{u['reasoning_tokens']} | {number(r['mean_latency_seconds'])}/{number(r['p95_latency_seconds'])} | {number(c['known_usage_subtotal'])}/{c['unpriced_calls']} | {number(c['cache_standardized_all_miss_known_subtotal'])} |")
    lines += ["", "费用表是已知小计；完整总额、缺整条 telemetry 数、缺缓存账数、执行位置、返回模型和 fingerprint 见 JSON。reasoning 是 output 的组成部分。", "",
              "| 配对差值 | 全部回答正确产出率差 | 来源簇 95% 区间 | 完整报告率差 | 来源簇 95% 区间 |", "| --- | --- | --- | --- | --- |"]
    for pair, values in report["three_backend_source_bootstrap"]["paired"].items():
        a, b = values["correct_decisions_per_all_cases"], values["complete_case_rate"]
        lines.append(f"| {pair} | {percent(a['point_estimate'])} | [{percent(a['low'])}, {percent(a['high'])}] | {percent(b['point_estimate'])} | [{percent(b['low'])}, {percent(b['high'])}] |")
    lines += ["", "区间以整个 source_id 为重抽单位，同源 6 个回答与 3 个后端一起保留，2,000 次、seed=20261024。单次生成无法分离模型随机性和服务波动。", "",
              "完整 JSON 保留历史整条失败口径、逐生成模型分层、全 3 组配对转移表、共同已决诊断、所有逐条结果和输入哈希。原生标签不替代作者裁定；执行完成率不证明事实保真。", ""]
    return "\n".join(lines)


def check_finalization(run_dir, *, expected_records=540):
    progress = read_object(run_dir / "progress.json")
    if (progress.get("status") not in ("completed", "completed_with_unknown")
            or progress.get("finalized_records") != expected_records
            or progress.get("frozen_artifacts_unchanged") is not True):
        raise ValueError("Only a finalized frozen run may be reported")
    integrity = read_object(run_dir / "result-integrity.json")
    if integrity.get("record_count") != expected_records or integrity.get("predictions_sha256") != sha(run_dir / "predictions.jsonl"):
        raise ValueError("Prediction integrity differs from finalized records")
    hashes = integrity.get("files_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("Durable result and reservation hashes are required")
    for name, digest in hashes.items():
        path = (run_dir / name).resolve()
        if not path.is_relative_to(run_dir.resolve()) or sha(path) != digest:
            raise ValueError("Durable result/reservation changed: " + name)
    return integrity


def summarize(run_dir, data_dir, output_dir):
    config = read_object(run_dir / "config.json")
    integrity = check_finalization(run_dir)
    actual = {name: sha(data_dir / name) for name in DATA_FILES}
    if config.get("data_files_sha256") != actual:
        raise ValueError("Data hashes differ from frozen run config")
    preselection_digest = config.get("preselection_freeze_sha256", config.get("preselection_sha256"))
    for name, digest in (("preselection", preselection_digest), ("binding", config.get("binding_sha256"))):
        if not isinstance(digest, str) or sha(run_dir / (name + ".json")) != digest:
            raise ValueError("Missing or mismatched " + name + " binding")
    preselection = read_object(run_dir / "preselection.json")
    binding = read_object(run_dir / "binding.json")
    if binding.get("preselection_sha256", binding.get("preselection_freeze_sha256")) != preselection_digest or binding.get("data_files_sha256") != actual:
        raise ValueError("Selection binding differs from config/data")
    source_hashes = preselection.get("code_files_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("Preselection must bind frozen implementation")
    for field in ("settings", "v4_config", "backends", "run_options", "price_reference", "code_files_sha256", "runner_sha256"):
        if config.get(field) != preselection.get(field):
            raise ValueError("Run configuration differs from preselection freeze: " + field)
    for name, expected in source_hashes.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha(path) != expected:
            raise ValueError("Frozen source changed: " + name)
    manifest, gold, inputs = (read_rows(data_dir / name) for name in ("manifest.jsonl", "native_gold.jsonl", "inputs.jsonl"))
    sources = Counter(row["source_id"] for row in manifest)
    if len(manifest) != 180 or len(sources) != 30 or set(sources.values()) != {6}:
        raise ValueError("Expected 180 answers from 30 sources with six answers each")
    if Counter(row["task_type"] for row in manifest) != {"QA": 60, "Summary": 60, "Data2txt": 60}:
        raise ValueError("Expected sixty answers per task")
    for source in sources:
        group = [row for row in manifest if row["source_id"] == source]
        if len({row["generator"] for row in group}) != 6 or len({row["task_type"] for row in group}) != 1:
            raise ValueError("Each source must retain six distinct generators in one task")
    records = score_v4.load_prediction_journal(run_dir / "predictions.jsonl")
    report = analyze(records, manifest, gold, inputs, config)
    dependencies = {}
    for name, module in sorted(sys.modules.items()):
        if (name in ("grounding", "scripts") or name.startswith(("grounding.", "scripts."))) and getattr(module, "__file__", None):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(ROOT.resolve()):
                raise ValueError("Scoring imported a nonfrozen project dependency: " + name)
            relative = path.relative_to(ROOT).as_posix()
            if source_hashes.get(relative) != sha(path):
                raise ValueError("Imported scorer is outside frozen hash manifest: " + relative)
            dependencies[relative] = sha(path)
    report["artifact_binding"] = {"data_files_sha256": actual, "config_sha256": sha(run_dir / "config.json"),
                                  "predictions_sha256": sha(run_dir / "predictions.jsonl"), "summarizer_sha256": sha(__file__),
                                  "preselection_sha256": preselection_digest, "binding_sha256": config["binding_sha256"],
                                  "imported_scoring_files_sha256": dependencies,
                                  "result_integrity_sha256": sha(run_dir / "result-integrity.json"),
                                  "durable_result_count": integrity["durable_result_count"],
                                  "unknown_reserved_result_count": integrity["unknown_count"]}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output_dir / "report.md").write_text(render(report), encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = summarize(args.run_dir.resolve(), args.data_dir.resolve(), args.output_dir.resolve())
    print(json.dumps({"manifest_count": report["manifest_count"], "model_calls": 0, "output_directory": str(args.output_dir)}))


if __name__ == "__main__":
    main()
