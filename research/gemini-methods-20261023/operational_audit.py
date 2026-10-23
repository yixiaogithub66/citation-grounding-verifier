"""Independent mechanical audit; no imports from the runner and no model calls."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import unicodedata


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def obj(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(left, right, label):
    require(math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12), label)


def calculate_usage(records):
    calls = [c for r in records for c in r["telemetry"]["calls"]]
    totals = Counter()
    for call in calls:
        usage = call["usage"]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
            require(type(usage[key]) is int and usage[key] >= 0, "Usage missing or not nonnegative integer")
            totals[key] += usage[key]
        require(usage["prompt_cache_hit_tokens"] + usage["prompt_cache_miss_tokens"] == usage["prompt_tokens"], "Cache accounting does not partition input")
        require(usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"], "Total tokens inconsistent")
    return {"calls": len(calls), **dict(totals),
            "cached_reference_usd": (totals["prompt_cache_miss_tokens"] * .30 + totals["prompt_cache_hit_tokens"] * .006 + totals["completion_tokens"] * 1.20) / 1_000_000,
            "all_miss_reference_usd": (totals["prompt_tokens"] * .30 + totals["completion_tokens"] * 1.20) / 1_000_000}


def quote_ok(citation, contexts):
    return (isinstance(citation, dict) and set(citation) == {"index", "quote"}
            and type(citation["index"]) is int and 0 <= citation["index"] < len(contexts)
            and isinstance(citation["quote"], str) and citation["quote"].strip()
            and citation["quote"] in contexts[citation["index"]])


def audit(run, target):
    run, target = Path(run).resolve(), Path(target).resolve()
    progress, manifest = obj(run / "progress.json"), obj(run / "freeze.json")
    require(progress["status"] == "complete", "Run must be complete")
    require(sha(run / "freeze.json") == (run / "freeze.sha256").read_text().strip(), "Freeze manifest hash changed")
    require(sha(run / "responses.jsonl") == progress["responses_sha256"], "Journal changed")
    analysis = obj(run / "analysis.json")
    source, current = run / "source", Path(manifest["project_root"])
    for name, expected in manifest["files_sha256"].items():
        require(sha(source / name) == expected, "Frozen file changed: " + name)
        require(sha(current / name) == expected, "Current bound source/data/plan changed: " + name)
    require(sha(run / "prompts.json") == manifest["prompts_sha256"], "Prompt manifest changed")
    prompts = obj(run / "prompts.json")
    require({key: text_sha(value) for key, value in prompts.items()} == manifest["individual_prompt_sha256"], "Individual prompt digest changed")
    settings = manifest["settings"]
    for key, expected in {"thinking": "disabled", "max_output_tokens": 8192, "upstream_retries": 0,
                          "repair_attempts": 0, "json_mode": True, "model": "deepseek-flash"}.items():
        require(settings[key] == expected, "Unexpected setting: " + key)
    folder = source / "research/gemini-methods-20261023"
    p1 = {c["id"]: c for c in obj(folder / "judgment-cases.json")["cases"]}
    p2 = {c["id"]: c for c in obj(folder / "pilot-cases.json")["cases"]}
    records = [json.loads(line) for line in (run / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    index = {(r["probe"], r["case_id"], r["arm"], r["repetition"]): r for r in records}
    expected_keys = {("p1", case, arm, rep) for case in p1 for arm in ("base", "candidate") for rep in (0, 1)}
    expected_keys |= {("p2", case, arm, 0) for case in p2 for arm in ("base", "repeat", "nf_audit")}
    require(len(p1) == len(p2) == 12 and len(records) == len(index) == 84 and set(index) == expected_keys, "Record identity/coverage differs")
    require(progress["record_count"] == 84 and manifest["max_model_calls"] == 84, "Record count or ceiling differs")
    status_counts = Counter(r["status"] for r in records)
    for status in ("valid", "error", "skipped"):
        require(status_counts[status] == progress[status], "Status count differs")
    models, fingerprints, starts_ends, skip_reasons = Counter(), Counter(), [], Counter()
    quotes, conflict_quotes, safe_repairs, errors = 0, 0, 0, []
    for row in records:
        probe, arm, case_id = row["probe"], row["arm"], row["case_id"]
        calls = row["telemetry"]["calls"]
        if row["status"] == "skipped":
            require(probe == "p2" and arm == "nf_audit" and not calls, "Only NF audit may skip without a call")
            skip_reasons[row["skip_reason"]] += 1
            continue
        require(len(calls) == 1, "Non-skipped record must contain one provider call")
        call = calls[0]
        require(call["attempt"] == 1 and call["thinking"] == "disabled" and call["max_output_tokens"] == 8192, "Call budget/settings differ")
        require(call["stage"] == probe + "_" + arm and call["phase"] == probe, "Unexpected call stage")
        require(call["model"] == settings["model"] and isinstance(call["system_fingerprint"], str), "Returned model/fingerprint missing or changed")
        require(call["http_status"] == 200 and call["finish_reason"] == "stop", "Unexpected provider failure/truncation")
        models[call["model"]] += 1
        fingerprints[call["system_fingerprint"]] += 1
        require(json.loads(call["response_text"]) == row["raw_output"], "Parsed provider output mismatch")
        for key in ("repairs", "targeted_reasks", "batch_retries", "contradiction_reviews", "unsupported_reviews"):
            require(not row["telemetry"][key], "Unplanned model repair/review")
        require(row["safe_quote_repairs"] == len(row["telemetry"]["citation_repairs"]), "Quote-repair count differs")
        safe_repairs += row["safe_quote_repairs"]
        if probe == "p1":
            case = p1[case_id]
            expected_payload = {"context_passages": [{"index": i, "text": text} for i, text in enumerate(case["context_passages"])],
                                "claims": [{"id": "c1", "claim_text": case["claim_text"]}]}
        elif arm in ("base", "repeat"):
            expected_payload = {"generated_answer": p2[case_id]["generated_answer"], "max_claims": 64,
                                "boundary_context": {"before": "", "after": ""}}
        else:
            base = index[("p2", case_id, "base", 0)]
            require(base["status"] == "valid", "Audit ran after invalid base")
            extraction = base["validated_output"]
            require(bool(extraction["non_factual_spans"]), "Audit ran without base NF exclusions")
            expected_payload = {"generated_answer": p2[case_id]["generated_answer"],
                                "excluded_spans": [{"exclusion_id": f"e{i + 1}", "text": item["text"]} for i, item in enumerate(extraction["non_factual_spans"])],
                                "already_extracted_spans": [item["source_span"] for item in extraction["claims"]]}
        # Exact reconstruction is stronger than searching for forbidden words.
        # Neither task/case IDs, expected labels, reasons nor metadata can appear
        # as additional fields in this precisely whitelisted request object.
        require(row["payload"] == expected_payload, "Unexpected payload content or metadata leak")
        expected_prompt = prompts[probe + "_" + arm]
        require(row["messages"] == [{"role": "system", "content": expected_prompt},
                                    {"role": "user", "content": json.dumps(expected_payload, ensure_ascii=False, allow_nan=False)}], "Message wrapper differs from exact whitelist")
        require(text_sha(expected_prompt) == row["prompt_sha256"], "Record prompt digest differs")
        payload_text = json.dumps(expected_payload, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
        require(text_sha(payload_text) == row["payload_sha256"], "Record payload digest differs")
        starts_ends.extend([(datetime.fromisoformat(row["started_at"]), 1), (datetime.fromisoformat(row["completed_at"]), -1)])
        if row["status"] == "error":
            require(row["validated_output"] is None and isinstance(row["error"], dict), "Error was converted into a final judgment")
            errors.append({key: row[key] for key in ("probe", "case_id", "arm", "repetition", "error")})
            continue
        require(row["status"] == "valid" and row["error"] is None, "Unexpected valid/error state")
        value = row["validated_output"]
        if probe == "p1":
            require(set(value) == {"id", "claim_text", "verdict", "reasoning", "citations", "derivation", "conflict"}, "P1 output keys differ")
            require(value["id"] == "c1" and value["claim_text"] == case["claim_text"], "P1 identity/text altered")
            require(value["verdict"] in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"), "Invalid verdict")
            require(value["reasoning"].strip() and value["derivation"].strip(), "Missing public explanation")
            require(len(value["citations"]) <= 32 and all(quote_ok(c, case["context_passages"]) for c in value["citations"]), "Invalid public quote")
            quotes += len(value["citations"])
            require(bool(value["citations"]) == (value["verdict"] != "UNSUPPORTED"), "Public citation/label rule differs")
            if value["verdict"] == "CONTRADICTED":
                conflict = value["conflict"]
                require(set(conflict) == {"claim_span", "evidence", "kind", "explanation"}, "Conflict schema differs")
                require(conflict["claim_span"].strip() and conflict["claim_span"] in value["claim_text"] and conflict["kind"] in ("direct", "calculation") and conflict["explanation"].strip(), "Conflict anchor/type invalid")
                require(1 <= len(conflict["evidence"]) <= 32, "Conflict evidence missing")
                for cite in conflict["evidence"]:
                    require(quote_ok(cite, case["context_passages"]) and any(cite["index"] == public["index"] and cite["quote"] in public["quote"] for public in value["citations"]), "Conflict quote not exact/publicly covered")
                conflict_quotes += len(conflict["evidence"])
            else:
                require(value["conflict"] is None, "Non-C conflict is nonnull")
            if row["safe_quote_repairs"] == 0:
                require(value == row["raw_output"]["claims"][0], "Unrecorded output mutation")
        elif arm in ("base", "repeat"):
            answer, covered = p2[case_id]["generated_answer"], set()
            require(set(value) == {"claims", "non_factual_spans"}, "Extraction schema differs")
            for field, text_field in (("claims", "source_span"), ("non_factual_spans", "text")):
                for item in value[field]:
                    start, end = item["source_start"], item["source_end"]
                    require(type(start) is int and type(end) is int and 0 <= start < end <= len(answer) and answer[start:end] == item[text_field], "M1 span does not match exact original answer")
                    covered.update(range(start, end))
            require(all(i in covered for i, char in enumerate(answer) if unicodedata.category(char)[0] in "LNMS" or char in "-*/"), "M1 meaningful characters unaccounted for")
        else:
            require(set(value) == {"recoveries"}, "Audit output schema differs")
            spans = {item["exclusion_id"]: item["text"] for item in expected_payload["excluded_spans"]}
            for item in value["recoveries"]:
                require(set(item) == {"exclusion_id", "source_span", "claim_text"} and item["source_span"].strip() and item["claim_text"].strip() and item["exclusion_id"] in spans and item["source_span"] in spans[item["exclusion_id"]], "Recovery provenance invalid")
    require(len(fingerprints) == 1, "Multiple provider fingerprints")
    for case_id in p2:
        base, repeat, shadow = [index[("p2", case_id, arm, 0)] for arm in ("base", "repeat", "nf_audit")]
        eligible = base["status"] == "valid" and bool(base["validated_output"]["non_factual_spans"])
        require((shadow["status"] != "skipped") == eligible, "NF audit eligibility differs")
        if not eligible:
            require(shadow["skip_reason"] == ("base_invalid" if base["status"] != "valid" else "no_non_factual_spans"), "Wrong NF skip reason")
        require(repeat["payload"] == base["payload"] and repeat["prompt_sha256"] == base["prompt_sha256"], "Repeat control altered request")
        require(datetime.fromisoformat(repeat["started_at"]) >= datetime.fromisoformat(base["completed_at"]), "Repeat was not fresh second execution")
        if eligible:
            require(datetime.fromisoformat(shadow["started_at"]) >= datetime.fromisoformat(repeat["completed_at"]), "Audit ran before repeat completed")
    ordered_ids = sorted(p1, key=lambda case_id: text_sha("|".join([manifest["seed"], "p1-case", case_id])))
    first_counts = Counter()
    for position, case_id in enumerate(ordered_ids):
        for repetition in (0, 1):
            arms = ("base", "candidate") if (position + repetition) % 2 == 0 else ("candidate", "base")
            a, b = [index[("p1", case_id, arm, repetition)] for arm in arms]
            require(a["backend_order_index"] == 0 and b["backend_order_index"] == 1, "P1 declared paired order differs")
            require(datetime.fromisoformat(a["completed_at"]) <= datetime.fromisoformat(b["started_at"]), "P1 observed paired order differs")
            first_counts[arms[0]] += 1
    require(first_counts == {"base": 12, "candidate": 12}, "P1 first-arm imbalance")
    simultaneous, maximum = 0, 0
    for _, delta in sorted(starts_ends):
        simultaneous += delta
        maximum = max(maximum, simultaneous)
    require(simultaneous == 0 and maximum <= 4, "More than four simultaneous request records")
    usage = calculate_usage(records)
    require(usage["calls"] == progress["model_calls_started"] <= 84, "Call counter/ceiling differs")
    require(analysis["responses_sha256"] == sha(run / "responses.jsonl") and analysis["freeze_sha256"] == sha(run / "freeze.json"), "Analysis binding differs")
    p1scores, group_costs = {}, {}
    for probe, arms in (("p1", ("base", "candidate")), ("p2", ("base", "repeat", "nf_audit"))):
        for arm in arms:
            chosen = [r for r in records if r["probe"] == probe and r["arm"] == arm]
            independently_priced = calculate_usage(chosen)
            reported = analysis[probe][arm]["runtime"]
            require(independently_priced["calls"] == reported["usage"]["calls"], "Per-arm call count differs")
            close(independently_priced["cached_reference_usd"], reported["reference_cost"]["estimated_total"], "Per-arm cached reference cost differs")
            close(independently_priced["all_miss_reference_usd"], reported["reference_cost"]["cache_standardized_all_miss_total"], "Per-arm all-miss reference cost differs")
            group_costs[probe + "/" + arm] = independently_priced
            if probe == "p1":
                valid = hits = valid_hits = 0
                for row in chosen:
                    items = (row.get("raw_output") or {}).get("claims")
                    label = items[0].get("verdict") if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict) else None
                    hit = label == p1[row["case_id"]]["expected_verdict"]
                    valid += row["status"] == "valid"
                    hits += hit
                    valid_hits += row["status"] == "valid" and hit
                p1scores[arm] = {"records": len(chosen), "raw_label_hits": hits, "valid": valid, "valid_and_label_hits": valid_hits}
                for field, number in p1scores[arm].items():
                    require(analysis["p1"][arm][field] == number, "P1 mechanical score differs: " + field)
    for field in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        require(analysis["runtime"]["usage"][field] == usage[field], "Reported total usage differs")
    close(usage["cached_reference_usd"], analysis["runtime"]["reference_cost"]["estimated_total"], "Total cached cost differs")
    close(usage["all_miss_reference_usd"], analysis["runtime"]["reference_cost"]["cache_standardized_all_miss_total"], "Total all-miss cost differs")
    require(safe_repairs == sum(analysis["p1"][arm]["safe_quote_repairs"] for arm in ("base", "candidate")), "Reported safe repair count differs")
    result = {"schema_version": "generic-pilot-operational-audit-v1", "status": "pass", "audited_at": datetime.now(timezone.utc).isoformat(),
              "run_directory": str(run), "record_count": 84, "model_call_count": usage["calls"], "status_counts": dict(status_counts),
              "skip_reasons": dict(skip_reasons), "error_records": errors, "models": dict(models), "fingerprints": dict(fingerprints),
              "max_observed_concurrent_records": maximum, "p1_first_arm_counts": dict(first_counts), "p1_mechanical_scores": p1scores,
              "public_exact_citations": quotes, "conflict_exact_citations": conflict_quotes, "safe_quote_repairs": safe_repairs,
              "usage_and_reference_cost": usage, "by_probe_arm_usage_and_cost": group_costs,
              "frozen_and_current_files_verified": len(manifest["files_sha256"]),
              "production_python_files_verified": sum(name.startswith("grounding/") for name in manifest["files_sha256"]),
              "checks": ["84 unique expected records including explicit NF skips", "one attempt/call per non-skip; no retry or review", "fixed settings/model/fingerprint and no truncation", "exact payload and message whitelist; no gold/metadata/prior-reason leakage", "NF eligibility and source spans bound to valid base", "fresh second extraction retained without best-of selection", "balanced P1 paired order and two repetitions", "exact citations/conflict anchors and M1 source coverage", "frozen/current source/data/PLAN hashes", "independently recomputed label agreement and reference costs"],
              "limitations": ["Mechanical label agreement is not a semantic evidence-sufficiency judgment.", "M1 character coverage is not factual completeness; NF recoveries require separate semantic review.", "Observed telemetry and frozen code establish recorded requests; this is not provider-side packet capture or a bill.", "This audit uses a separate recomputation script by the runner's authoring subagent, not independent human adjudication."],
              "input_sha256": {name: sha(run / name) for name in ("freeze.json", "prompts.json", "progress.json", "responses.jsonl", "analysis.json")},
              "audit_script_sha256": sha(__file__)}
    target.mkdir(parents=True, exist_ok=True)
    with (target / "operational-audit.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    markdown = ["# 小规模初始阶段实验：机械审计", "", "状态：PASS。独立重算脚本没有导入实验 runner，也没有发送模型请求。", "",
                f"检查 {len(manifest['files_sha256'])} 个冻结文件及其当前副本，包含 {result['production_python_files_verified']} 个生产 Python 文件；代码、案例、PLAN、提示词与记录哈希一致。",
                f"84 条唯一预定记录；实际 {usage['calls']} 次请求，{status_counts['skipped']} 条明确跳过。每次请求 attempt=1、thinking=disabled、8192 输出预算；无追加修复/复核。最大同时在途记录 {maximum}。",
                "", "| P1 臂 | 原始标签符合草案 / 24 | 有效 / 24 | 有效且标签符合 / 24 |", "| --- | ---: | ---: | ---: |"]
    for arm, score in p1scores.items():
        markdown.append(f"| {arm} | {score['raw_label_hits']} | {score['valid']} | {score['valid_and_label_hits']} |")
    markdown += ["", "这是机械标签一致性，不是逐条语义正确或证据充分性的认证。",
                 f"公开有效引用 {quotes} 条、C conflict 引用 {conflict_quotes} 条均为原文精确子串；安全引用直修 {safe_repairs} 次。所有非空 NF 审计只看到答案、合法排除跨度和基线已提取原文跨度，没有上下文、金标、基线理由或基线 claim_text。",
                 "P1 每臂先执行各 12 次，重复两轮；P2 保留固定第二次原策略输出，未做 best-of 选择。6 次跳过按基线有效性与 NF 非空条件核实。",
                 f"全部调用的历史固定参考费用：缓存实际账 USD {usage['cached_reference_usd']:.6f}；统一全未命中 USD {usage['all_miss_reference_usd']:.6f}。这是用量估算，非账单。",
                 "", "冻结代码与观测日志支持记录内的调用边界，不能代替服务端抓包；机械覆盖不能证明事实没有遗漏。本审计由编写 runner 的同一子代理用分离脚本重算，不冒充独立人工裁定。详细计数、错误与输入哈希见 operational-audit.json。", ""]
    with (target / "operational-audit.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(markdown))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run_dir, args.output_dir)
    print(json.dumps({key: report[key] for key in ("status", "record_count", "model_call_count", "public_exact_citations", "safe_quote_repairs")}, ensure_ascii=False))
