#!/usr/bin/env python3
"""Build three human-review pilots, never a formal confirmation dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validate_dataset import check_dataset, export_dataset, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dataset" / "cphos28-review"
POLICY = "docs/ANNOTATION_POLICY_V3.md"
NORMALIZATION = (
    "AI 对照 PDF 页面视觉核对后选录；删除页眉、评分信息和重复题干；"
    "分式用带括号的 /、乘法用 *、指数用 exp(...)、下标用 _，矩阵按逐行数组书写。"
    "保留数值、符号、上下标、适用条件；引用逐字匹配本规范化 text，不声称与 PDF 文本层逐字一致。"
)


def passage(identifier: str, pages: list[int], locator: str, text: str, proof: str) -> dict:
    return {
        "id": identifier, "document_id": "solutions", "pages": pages,
        "locator": locator, "text": text, "normalization": NORMALIZATION,
        "normalization_proof": proof,
        "review_status": "ai_text_and_page_visual_checked_awaiting_author",
        "selected_for": "review_pilot_only_excluded_from_confirmation",
    }


PASSAGES = [
    passage("review_q2_constants", [5], "二(1)，式(10)",
            "参考解答在给定数值代入后得到 C_0 = 5.5766696，lambda*g*R/T_0 = 1.0486773。",
            "式(10)花括号内两行依次是 C_0=5.5766696 和 lambda*g*R/T_0=1.0486773；仅把希腊字母与分式线性化，不改变精度。"),
    passage("review_q2_length", [5], "二(1)，式(12)标题、式(13)",
            "参考解答给出的悬链线部分绳长为 l_1 = 10.639650*R。",
            "从式(12)前的悬链线部分绳长标题确定量名；式(13)为 l_1=10.639650R，补显式乘号。"),
    passage("review_q2_tension", [5], "二(1)，式(17)",
            "圆柱上部分张力关系中，T_1 = T_0/sin(theta_0)。",
            "式(17)的分子为 T_0、分母为 sin(theta_0)；圆柱上部分的范围来自式(14)前标题。"),
    passage("review_q6_regular_transfer", [19], "六(2.1)，式(7)",
            "相邻等间距区间的振幅传递矩阵为 M = [[exp(i*phi)*(1+i*q), exp(-i*phi)*i*q], [-exp(i*phi)*i*q, exp(-i*phi)*(1-i*q)]]。",
            "逐个核对式(7)的四项：左上 exp(+i*phi)*(1+i*q)，右上 exp(-i*phi)*i*q，左下 -exp(+i*phi)*i*q，右下 exp(-i*phi)*(1-i*q)。未用存在疑点的式(10)。"),
    passage("review_q6_boundary_geometry", [18], "六(3)有限长链题干及图6.3上方文字",
            "有限长链有 N 个原子，最左端与最右端原子距离固定边界分别为 tau*a、(1-tau)*a，其中 tau 属于 [0,1]。固定边界处弦位移为零。",
            "保留原文两端距离与 tau 的闭区间；Greek tau 写为 tau，未从图形估计长度。"),
    passage("review_q6_initial_transfer", [19], "六(3.1)，式(16)",
            "有限长链最左端的初始振幅关系为 [A_1, B_1]^T = [[exp(i*tau*phi)*(1+i*q), exp(-i*tau*phi)*i*q], [-exp(i*tau*phi)*i*q, exp(-i*tau*phi)*(1-i*q)]]*[1, -1]^T*A_0。",
            "式(16)中的相位均含 tau*phi；右侧列向量为 [1,-1]^T，再乘 A_0。^T 是列向量排版的显式转置记号；没有将 tau 改成1或约去。"),
    passage("review_q7_inverse_time", [23], "七(1C)，式(18)",
            "参考解答中由惯性坐标转回加速观者时间坐标的关系为 tau = (c/(2*g))*ln((x+c*t)/(x-c*t))。",
            "式(18)第二个等号后的前因子是 c/(2*g)，对数分子 x+c*t、分母 x-c*t。仅转写该等号右侧；未使用式(27)-(28)的温度约定。"),
]


def gold(text: str, verdict: str, reason: str, citations: list[tuple[int, str]]) -> dict:
    indices = sorted({index for index, _ in citations})
    return {
        "claim_text": text, "answer_quote": text, "verdict": verdict,
        "reasoning": reason,
        "citations": [{"index": index, "quote": quote} for index, quote in citations],
        "acceptable_evidence_sets": [indices] if indices else [],
        "required_passage_indices": indices if len(indices) > 1 else [],
    }


def build_cases() -> list[dict]:
    lookup = {item["id"]: item["text"] for item in PASSAGES}
    cases = []

    def add(identifier: str, problem: str, category: str, ids: list[str], answer: str,
            claims: list[dict], purpose: str) -> None:
        for i, claim in enumerate(claims, 1):
            claim["claim_id"] = f"{identifier}-c{i}"
        cases.append({
            "id": identifier, "split": "review", "category": category,
            "topic": "CPHOS28 v3 人工审阅样例", "problem_id": problem,
            "context_passage_ids": ids,
            "input": {"context_passages": [lookup[key] for key in ids], "generated_answer": answer},
            "expected": {"claims": claims},
            "metadata": {
                "answer_origin": "AI 构造的审阅样例，未经作者终审，未采样被测模型",
                "annotation_policy": POLICY, "purpose": purpose,
                "author_review_status": "pending", "include_in_confirmation": False,
                "provenance_scope": "same_source_same_question_family_new_transcription",
            },
        })

    texts = [
        "在参考解答的给定数值代入下，C_0 = 5.5766696。",
        "同一次代入给出 lambda*g*R/T_0 = 1.0486773。",
        "参考解答给出的悬链线部分绳长为 l_1 = 10.639650*R。",
        "圆柱上部分的张力关系满足 T_1 = T_0*cos(theta_0)。",
        "所用绳材料的杨氏模量为 200 GPa。",
    ]
    add("cphos28-review-density-01", "Q2", "density",
        ["review_q2_constants", "review_q2_length", "review_q2_tension"], "".join(texts), [
            gold(texts[0], "SUPPORTED", "式(10)第一行直接给出该数值。", [(0, "C_0 = 5.5766696")]),
            gold(texts[1], "SUPPORTED", "式(10)第二行直接给出该无量纲比值。", [(0, "lambda*g*R/T_0 = 1.0486773")]),
            gold(texts[2], "SUPPORTED", "式(13)直接给出该绳长，保留参考解答归属。", [(1, lookup["review_q2_length"])]),
            gold(texts[3], "CONTRADICTED", "相同 T_1 的一般关系是除以 sin(theta_0)，不是乘以 cos(theta_0)；两者不是恒等的参数关系。", [(2, lookup["review_q2_tension"])]),
            gold(texts[4], "UNSUPPORTED", "给定三段只含静态结果和张力关系，没有材料杨氏模量，不能由这些式子确定数值。", []),
        ], "五句连续回答，保留全部事实并覆盖三种判决；不计入正式确认集。")

    texts = [
        "有限长链最左端的一般振幅关系为 A_1 = (exp(i*phi)*(1+i*q)-exp(-i*phi)*i*q)*A_0。",
        "有限长链最左端原子到固定边界的距离为 tau*a。",
        "有限长链的固定边界选用钛合金。",
    ]
    add("cphos28-review-distractor-01", "Q6", "scope_distractor",
        ["review_q6_regular_transfer", "review_q6_boundary_geometry", "review_q6_initial_transfer"], "".join(texts), [
            gold(texts[0], "CONTRADICTED", "取初始关系矩阵第一行乘 [1,-1]^T，得 A_1=(exp(i*tau*phi)*(1+i*q)-exp(-i*tau*phi)*i*q)*A_0。回答把最左端分段相位 tau*phi 换成等间距段的 phi；作为一般关系不成立，不能把 tau=1 的特殊情形当作全范围。", [(2, lookup["review_q6_initial_transfer"])]),
            gold(texts[1], "SUPPORTED", "有限链边界几何明确给出左端距离 tau*a，不能误用完整周期 a。", [(1, "最左端与最右端原子距离固定边界分别为 tau*a、(1-tau)*a，其中 tau 属于 [0,1]")]),
            gold(texts[2], "UNSUPPORTED", "固定边界和位移条件不确定边界材料；三段均未给出钛合金。", []),
        ], "并置完整等间距段和最左端非完整段，检验条件选择；不计入正式确认集。")

    part1 = "参考解答中 tau 的对数表达式前因子为 c/g"
    part2 = "tau = (c/(2*g))*ln((x+c*t)/(x-c*t))。"
    add("cphos28-review-mixed-01", "Q7", "mixed_truth_compound",
        ["review_q7_inverse_time"], part1 + "，即 " + part2, [
            gold(part1, "CONTRADICTED", "参考解答式(18)的对数前因子为 c/(2*g)，文字部分写成 c/g，漏去分母的2。", [(0, lookup["review_q7_inverse_time"])]),
            gold(part2, "SUPPORTED", "公式部分完整保留 c/(2*g) 和对数分式，与来源一致。文字和公式不等价，即字不能作为合并依据。", [(0, lookup["review_q7_inverse_time"])]),
        ], "同一句由即连接的不等价文字与公式须拆成两条，分别给 C/S；不计入正式确认集。")
    return cases


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    if any((DEST / name).exists() for name in ("cases.jsonl", "sources.json", "REVIEW.md")):
        raise SystemExit("Refusing to overwrite existing pilot files or author review. Use the checked-in artifacts.")
    historical = json.loads((ROOT / "dataset/cphos28/sources.json").read_text(encoding="utf-8"))
    document = next(item for item in historical["documents"] if item["id"] == "solutions")
    actual = hashlib.sha256(Path(document["path"]).read_bytes()).hexdigest()
    if actual != document["sha256"]:
        raise SystemExit("Source PDF hash mismatch")
    sources = {
        "version": "pilot-1", "review_status": "ai_review_complete_awaiting_author",
        "documents": [document], "passages": PASSAGES,
        "excluded_from_formal_confirmation": True,
    }
    (DEST / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cases = build_cases()
    write_jsonl(DEST / "cases.jsonl", cases)
    checked, report = check_dataset(DEST / "cases.jsonl", check_local_sources=True)
    if not report["valid"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    export_dataset(checked, DEST)
    (DEST / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 三条新样例：作者审阅表", "", "状态：AI 复核完成，待作者终审。三条均为 review pilot，永久排除正式确认集。",
             "", "请先审阅 [标注规则](../../docs/ANNOTATION_POLICY_V3.md)，逐项填写作者决定；空白不代表同意。"]
    for case in cases:
        lines += ["", "## " + case["id"], "", case["metadata"]["purpose"], "", "### 输入上下文", ""]
        for index, (pid, context) in enumerate(zip(case["context_passage_ids"], case["input"]["context_passages"])):
            source = next(item for item in PASSAGES if item["id"] == pid)
            lines += [f"{index}. `{pid}`，解答 PDF 第 {','.join(map(str, source['pages']))} 页，{source['locator']}：{context}", ""]
        lines += ["### 待验证回答", "", case["input"]["generated_answer"], "", "### AI 建议标注", "",
                  "| Claim | 建议判决 | 引用段 | 理由 | 作者决定 / 修改理由 |", "| --- | --- | --- | --- | --- |"]
        for claim in case["expected"]["claims"]:
            indices = ",".join(str(c["index"]) for c in claim["citations"]) or "无"
            lines += [f"| {claim['claim_text']} | {claim['verdict']} | {indices} | {claim['reasoning']} | 待填写 |"]
        lines += ["", "作者确认：待填写；日期：待填写。"]
    (DEST / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "cases": len(cases), "claims": sum(len(c['expected']['claims']) for c in cases), "split": "review", "author_review": "pending"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
