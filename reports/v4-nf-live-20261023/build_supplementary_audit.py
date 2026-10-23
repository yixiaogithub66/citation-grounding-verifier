"""Package the explicit AI review notes; offline only, no inference imports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/v4-nf-live-20261023"
OUT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


NOTES = {
    ("behavior", "behavior-05/base"): ("shared_attribution_loss_hidden_by_label", "两版均删除 Passage 0 归属，S 标签仍正确；提取保真问题不反映于该标签。"),
    ("behavior", "behavior-05/variant"): ("shared_attribution_loss_hidden_by_label", "两版均删除 Passage 1 归属，S 标签仍正确；提取保真问题不反映于该标签。"),
    ("behavior", "behavior-06/base"): ("shared_attribution_loss_wrong_label", "两版均删除 Passage 0 归属，改核全局 fee 并从另一段支持，遗漏实际归属冲突。"),
    ("behavior", "behavior-06/variant"): ("attribution_retained_in_post_observation", "前版删除来源；后版保留 Passage 1 归属，判 C。可见语义改善，非 NF 解析器触发。"),
    ("behavior", "behavior-16/base"): ("factual_nf_exclusion_recovered", "前版把完整事实句 Approved tokens are active 排为 NF，后版正常核查为 S。"),
    ("behavior", "behavior-16/variant"): ("factual_nf_exclusion_recovered", "前版把完整事实句 Unapproved tokens are active 排为 NF，后版对照 inactive 判 C。"),
    ("behavior", "behavior-20/variant"): ("alignment_only_change", "两个表述都保留泵、批准压力上限和 11 kPa，S 不变；仅后版与目标近似匹配。"),
    ("behavior", "behavior-24/base"): ("embedded_fact_lost_after_fallback", "后版初判漏 because 覆盖，修复跨度逆序，降级后 M3 把含事实前提的整个指令排除；两个解析器在同一输出上均如此。"),
    ("physics", "cphos28-q1-06"): ("terminal_punctuation_alignment_only", "后版三个 claim 去句末句号，严格正确 3→0、近似 3→3，S/C/U 与内容均保留。"),
    ("physics", "cphos28-q2-05"): ("translation_alignment_only", "英文同义转述变回中文目标，严格/近似 0→1；两版 S 和三阶段总时长均合理。"),
    ("physics", "cphos28-q2-06"): ("translation_alignment_only", "后版三条改英文，保留归属、数值和材料内容，S/C/U 不变；严格及近似 3→0。"),
    ("physics", "cphos28-q3-05"): ("qualifier_preserved_both", "本轮两版都保留给定扰动后；不能套用上一轮 M1-faithful 的限定丢失诊断。"),
    ("physics", "cphos28-q4-01"): ("shared_one_to_many_alignment", "H、B 为不同主体，两目标保留范围并共享合法 source_span；草案为一条，匹配漏报不等于事实漏提。"),
    ("physics", "cphos28-q4-05"): ("shared_paraphrase_strict_mismatch", "两版都保留相同线负荷条件并作同义改写；严格未匹配，近似匹配。"),
    ("physics", "cphos28-q5-02"): ("shared_text_formula_granularity", "文字 r^3 与公式 r^3 分为两条，均 C；草案为单目标，两种匹配都未匹配。"),
    ("physics", "cphos28-q5-03"): ("shared_granularity_and_scope_risk", "文字与公式分开且都 C；公式独立目标不重述迎风面条件，引用仍含条件。属于作用域风险，不据此改分。"),
    ("physics", "cphos28-q5-06"): ("granularity_and_denominator_reasoning", "前版把分母是m弱化为2*m包含m并给S，另一个同句公式给C；后版同句目标C避免冲突，严格1→3、近似2→3。"),
    ("physics", "cphos28-q6-01"): ("translation_alignment_only", "英文波速转述变回中文，S 不变；严格及近似0→1。"),
    ("physics", "cphos28-edge-02"): ("legitimate_empty_input", "真正空回答，两版空报告合理。"),
    ("physics", "cphos28-edge-03"): ("legitimate_non_factual", "纯感谢句，两版空报告合理。"),
}


def main():
    report = load(OUT / "scored/report.json")
    records = lines(RUN / "responses.jsonl")
    requests = [r for r in lines(RUN / "requests.jsonl") if r["dataset"] != "dev"]
    scores = {(ds, r["id"], r["backend"]): r["score"] for ds in ("behavior", "physics")
              for r in report["datasets"][ds]["case_scores"]}
    reviews = []
    for request in requests:
        ds, identifier = request["dataset"], request["id"]
        category, finding = NOTES.get((ds, identifier), ("reviewed_no_additional_issue_flagged", "已核对原文、公开目标及引文，未额外标注问题；不构成作者金标或完整语义正确性证明。"))
        item = {"dataset": ds, "id": identifier, "category": category, "finding": finding,
                "reviewed": ["source", "answer", "predeclared_draft_target", "both_public_outputs", "nf_exclusions"], "variants": {}}
        for variant in ("pre_fix", "post_fix"):
            row = next(r for r in records if r["dataset"] == ds and r["id"] == identifier and r["variant"] == variant)
            score = scores[ds, identifier, variant]
            metric = {k: score[k] for k in ("expected_correct", "expected_label", "observed_label", "aligned_target_count")} if ds == "behavior" else {
                mode: {key: score["alignment_diagnostic"][mode][key] for key in ("correct_claim_count", "matched_claim_count", "gold_claim_count", "predicted_claim_count", "case_correct")}
                for mode in ("strict", "approximate")}
            telemetry = row["telemetry"]
            item["variants"][variant] = {"metrics": metric, "claims": row["prediction"]["claims"],
                "nf_exclusions": (telemetry.get("extraction") or {}).get("non_factual_spans", []),
                "fallback_exclusions": telemetry.get("fallback_exclusions", [])}
        reviews.append(item)
    groups = report["dual_parser_audit"]["groups"]
    forks = {key: value.get("records_with_transport_usable_parser_difference", 0)
             for key, value in groups.items() if key.startswith(("behavior/", "physics/"))}
    assert sum(forks.values()) == 0
    artifact = {"kind": "ai-supplementary-semantic-review-not-author-gold", "coverage": {
        "behavior_inputs": 48, "physics_inputs": 46, "paired_inputs_reviewed": len(reviews), "public_outputs_reviewed": 188,
        "all_supplementary_nf_and_empty_outputs_reviewed": True,
        "all_changed_scores_and_behavior_failures_reviewed": True,
        "deep_call_trace_review_ids": ["behavior-24/base/post_fix"],
        "limitation": "Public reports, original input, draft targets and NF ledgers were reviewed for all inputs. Detailed call traces were not exhaustively re-adjudicated."},
        "parser_difference_record_counts": forks,
        "findings": {"behavior_correct": [44, 46], "behavior_improved_cases": ["behavior-06/variant", "behavior-16/base", "behavior-16/variant"],
                     "behavior_regressed_cases": ["behavior-24/base"], "physics_strict_correct": [50, 48], "physics_approx_correct": [52, 52],
                     "physics_strict_change_breakdown": {"cphos28-q1-06": -3, "cphos28-q2-05": 1, "cphos28-q2-06": -3, "cphos28-q6-01": 1, "cphos28-q5-06": 2}},
        "causal_limit": "Zero observed parser differences across all supplementary records; independent sampled output changes are not attributable to the NF correction from these trajectories. No generalization claim.",
        "gold_or_score_changed": False, "reviews": reviews,
        "evidence_sha256": {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (RUN / "responses.jsonl", RUN / "requests.jsonl", RUN / "data/behavior/pairs.jsonl", RUN / "data/physics/cases.jsonl", OUT / "scored/report.json")}}
    path = OUT / "supplementary-semantic-audit.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(artifact, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"paired_inputs_reviewed": len(reviews), "public_outputs_reviewed": 188, "parser_difference_records": sum(forks.values())}))


if __name__ == "__main__":
    main()
