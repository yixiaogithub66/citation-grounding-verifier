#!/usr/bin/env python3
"""Materialize manually authored AI review notes; never adjudicate for the author."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent

# These are case-specific review observations, not inferred from model predictions.
NOTES = {
    "q1-01-c1": "等效焦距的分子、分母及减 D 均与唯一给定焦距公式一致；所引公式足以支持。",
    "q1-02-c1": "回答把分母 -D 改成 +D；这是一般焦距关系的变化，不是等价代数重排。",
    "q1-03-c1": "给定响应是 theta/k，回答写 k*theta；对一般 k 不是同一函数。个别参数偶然相等不使一般关系成立。",
    "q1-04-c1": "逐段检查只给符号、焦距和间距；BK7 材料既未给出也不能从焦距唯一确定，应保留无依据。",
    "q1-05-c1": "对给定角度和长度作数值代入得 0.0809895445 rad，三位小数为 +0.081；两条引文分别覆盖参数与运算式，计算引导语不另拆。",
    "q1-06-c1": "Delta_r=D*theta 与位置偏差段完全一致，回答未引入新的条件。",
    "q1-06-c2": "来源已将 delta 解释为球面出射角，+0.081 与回答 -0.081 直接冲突；可引用整句增强量名可读性。",
    "q1-06-c3": "三段均没有镀膜或层数资料；不从常见光学器件制造方式推断十层。",
    "q2-01-c1": "回答明确归属参考答案，数值 6.66*lambda*R 与摘录一致；不把它升级为整道力学题的独立正确性证明。",
    "q2-02-c1": "相同参考答案和有效数字下，摘录是 6.66 而回答是 6.67；没有证据支持额外容差覆盖此差异。",
    "q2-03-c1": "完全弹性与上下文的完全非弹性为互斥的模型约定，完整碰撞条件已被引用。",
    "q2-04-c1": "静态最大悬挂质量不能在缺少强度模型时推出断裂张力；所给数值不是来源结果。",
    "q2-05-c1": "三个实际时长的共同量纲因子均为 sqrt(R/g)，系数和 6.98315673 支持 6.98；gold 特意引用 Delta_t_2 的带单位形式，未误用无量纲 t_2。",
    "q2-06-c1": "参考答案初速度数值 0.614*sqrt(g*R) 一致，归属表述避免声称重做整个运动过程。",
    "q2-06-c2": "6.89 与来源的 6.98 冲突。gold 引用包括整个求和式，但仅带量名的 t_f 和最终值即可构成充分反证；不应把未包含中间求和项自动解释为语义证据不足。",
    "q2-06-c3": "上下文规定匀质不可伸长但没有材料或编织工艺；钢丝结论仍无依据。",
    "q3-01-c1": "氩气质量 1.03e-4 kg 在上下文中明确给出，标签成立；但 gold 引用仅有数值和单位，未含 m_Ar 或氩气质量量名，作为独立引文过短。",
    "q3-02-c1": "当前输入已给 u_i=5.0 m/s，非零扰动下分母 4*g 和 5*g 产生不同终态高度，直接反驳充分。",
    "q3-03-c1": "来源的给定数据熵增为正，回答改成相反数；不需借助外部热力学定律也可判矛盾。",
    "q3-04-c1": "两部分气体模型和总质量没有给有效碰撞截面或可反演所需量，不能填入外部氩气经验值。",
    "q3-05-c1": "1+5.0^2/(5*9.81)=1.5096839959 m，四舍五入到 1.51 m；gold 两个参数引文加高度公式覆盖全部前提。",
    "q3-06-c1": "T_f=442 K 是来源对给定数据的明确结果，未要求另行获得上下文未给的初始参数。",
    "q3-06-c2": "相同一阶速度展开中，来源线性项为 -2*u*sqrt(...)，回答换成加号；一般一阶关系不等价。",
    "q3-06-c3": "平均自由程只以符号 lambda_bar 出现；体积关系不能给出 68 nm 的绝对数值。",
    "q4-01-c1": "当前 v1.2 上下文明确一维简化模型，H 和 B 共同受仅 y 分量的同一谓词约束；按已公布联合主语约定可保持一条。",
    "q4-02-c1": "同一次级板的厚度来源为 2*d，回答为 d；不是半厚度变量的重新定义。",
    "q4-03-c1": "mu_Fe=infinity 已足以反驳磁导率为零；sigma_Fe=0 描述电导率。gold 同时包含后者，可能过度约束引用锚点，但标签无误。",
    "q4-04-c1": "电导率 sigma 和铁芯近似未指定次级板为纯铜，不能由导电性质确定材质。",
    "q4-05-c1": "先用第0段识别消除法向合力的双边结构，再用第1段在同线负荷条件下得到推力倍率；是单个带结构限定的综合结论，需要两段。",
    "q4-06-c1": "每侧线负荷相同这个比较条件保留，功率两倍是来源明确子结论，未混入总线负荷固定的新条件。",
    "q4-06-c2": "同一模型中 E 被限制为 z 分量，回答将方向改为 x；对应分量约定直接冲突。",
    "q4-06-c3": "所给功率倍率不是绝对效率，损耗未给，不能推出98%的能量转换效率。",
    "q5-01-c1": "外力矩公式的负号、pi/4、eta 和 r^4 均与来源一致；没有要求补充 eta 数值或方向推断。",
    "q5-02-c1": "文字 r^3 与回答公式中的 r^3 是同一错误幂次的两种表述，按原粒度保留一条；来源为 r^4，反证充分。",
    "q5-03-c1": "公式 +eta*v_n_vec 与来源 -eta*v_n_vec 作为一般符号关系不一致，但同向/反向解读依赖 eta>0 且速度非零。来源称其为阻力，却未显式给 eta 的符号域；若严格拒绝外部惯例，文字与公式不一定可视为等价命题。须作者裁决，不能把模型拆分后的 UNSUPPORTED 简单认定为错误。",
    "q5-04-c1": "旋转对称只限制方位角依赖，不保证径向密度均匀；两段没有补足径向分布，保留无依据。",
    "q5-05-c1": "claim 已显式限定正的物理参数，排除了 eta=0 的0/0边界；两衰减率相除约掉 pi*eta*r，得 m*r^3/(2*I_2*h)，两个引文充分。",
    "q5-06-c1": "来源直接写盘面朝向趋于稳定；无需引用前面的具体进动描述才可支持这一较弱结论。",
    "q5-06-c2": "文字分母 m 与回答指数公式中的 m 等价，来源分母为 2*m；完整指数可直接展示少掉的系数2。",
    "q5-06-c3": "来源的 eta 没有给数值，20 m/s 测量或系数0.12均未出现，不能把符号模型当测量表。",
    "q6-01-c1": "来源明确裸弦波速 v=sqrt(T/mu)，同一系统和量名一致。",
    "q6-02-c1": "回答倒置根号中的 T/mu，一般函数与来源不等价；无需从外部物理量纲规则补证。",
    "q6-03-c1": "相同 phi、q 定义下色散关系的 -q*sin(phi) 被改为 +q*sin(phi)，不是恒等式。",
    "q6-04-c1": "原子间距只有符号 a，没有任何长度数值；色散关系不能唯一确定0.30 nm。",
    "q6-05-c1": "将两条明确无量纲定义代入色散式，保留减号和 q 的分母2；两个引用正好覆盖全部代入前提，仍为一个等价公式结论。",
    "q6-06-c1": "特征多项式完整保留中间项系数2及常数1；未引用原解答有疑点的另一个式(10)。",
    "q6-06-c2": "题设直接将 abs(lambda)!=1 定义为局域模，回答称传播模；引用包含被误命名的一类，证据充分。",
    "q6-06-c3": "上下文只定义质量和链参数，未赋予原子任何电荷值或符号；不从原子名称推断正电荷。",
    "q7-01-c1": "来源给出所定义类光坐标的 ds^2=du*dv；引用虽短但包含完整度规关系。",
    "q7-02-c1": "原时间函数为 sinh，回答改成 cosh，两函数不恒等；原函数直接构成反证。",
    "q7-03-c1": "同一 xi 和 g 约定下，共形因子的指数从 +2*g*xi/c^2 改成负号；作为全坐标关系不一致。",
    "q7-04-c1": "给定上下文中的 g 为一般加速度参数，没有9.81的数值定义；不可挪用第三题的数据或日常重力常数。",
    "q7-05-c1": "两轨迹代入 x^2-c^2*t^2 后得到 (c^4/g^2)*(cosh^2-sinh^2)，恒等式给出 c^4/g^2；两个坐标引用必需。",
    "q7-06-c1": "空间轨迹的前因子 c^2/g 和 cosh 函数与来源一致。",
    "q7-06-c2": "保留来源的空间频率约定后，模方比指数仍应为正；回答负号反转一般系数比。没有用存在量纲疑点的最终温度式判标签。",
    "q7-06-c3": "轨迹与坐标没有规定观者组成，电子结论无来源支持。",
    "edge-01-c1": "输入上下文为空，不能用真实世界中常见的裸弦公式冒充来源支持；无引用是正确行为。",
    "edge-04-c1": "输入仅有双透镜符号说明，球面数值虽在完整PDF另处存在但未提供，不能跨输入补入来源。",
}

FLAGS = {
    "q2-06-c2": ("citation_anchor_overrestriction", "CONTRADICTED", "历史标签保留；作者判断是否在后续版本或语义审计中接受只含 t_f 与6.98的充分短引文。历史结果和gold不回写。"),
    "q3-01-c1": ("citation_sufficiency", "SUPPORTED", "历史标签保留；建议未来版本引用含氩气总质量/m_Ar与数值的整句，并单独披露锚点修订，当前数据不改。"),
    "q4-03-c1": ("citation_anchor_overrestriction", "CONTRADICTED", "历史标签保留；mu_Fe=infinity 可单独反驳磁导率为零，不要求同时引 sigma_Fe=0。作者确认未来引文评价边界。"),
    "q5-03-c1": ("parameter_domain_and_claim_granularity", None, "建议保留历史快照的 CONTRADICTED 以维持复现，同时明确标为争议。作者裁决阻力一词是否足以限定 eta>0、是否拆开方向与公式；任何新裁决另存，不静默替换旧标签或给v3补分。"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if (DEST / "review.json").exists() or (DEST / "REVIEW.md").exists():
        raise SystemExit("Refusing to overwrite review notes or pending author decisions")
    data_path = ROOT / "dataset/cphos28/cases.jsonl"
    source_path = ROOT / "dataset/cphos28/sources.json"
    cases = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()]
    sources = json.loads(source_path.read_text(encoding="utf-8"))
    lookup = {item["id"]: item for item in sources["passages"]}
    records = []
    for case in cases:
        for claim in case["expected"]["claims"]:
            key = claim["claim_id"].removeprefix("cphos28-")
            note = NOTES[key]
            flag = FLAGS.get(key)
            refs = []
            for index, passage_id in enumerate(case["context_passage_ids"]):
                source = lookup[passage_id]
                quotes = [entry["quote"] for entry in claim["citations"] if entry["index"] == index]
                refs.append({
                    "passage_id": passage_id, "input_index": index,
                    "document_id": source["document_id"], "pages": source["pages"],
                    "locator": source["locator"], "context": source["text"],
                    "gold_quotes": quotes,
                    "role": "gold_evidence" if quotes else "screened_context_without_gold_citation",
                })
            records.append({
                "case_id": case["id"], "claim_id": claim["claim_id"],
                "problem_id": case["problem_id"], "split": case["split"],
                "claim_text": claim["claim_text"], "gold_verdict": claim["verdict"],
                "ai_review_status": "requires_author_adjudication" if key == "q5-03-c1" else "retain_with_evidence_note" if flag else "retain",
                "ai_suggested_verdict": flag[1] if flag else claim["verdict"],
                "ai_reasoning": note, "source_references": refs,
                "gold_citations": claim["citations"],
                "acceptable_evidence_sets": claim["acceptable_evidence_sets"],
                "required_passage_indices": claim["required_passage_indices"],
                "dispute_type": flag[0] if flag else None,
                "recommendation": flag[2] if flag else "建议维持原标签及粒度；待作者抽查确认。",
                "author_decision": None, "author_comment": None, "author_reviewed_at": None,
            })
    if len(records) != 58 or len(NOTES) != 58:
        raise SystemExit("Expected exactly 58 independently annotated review rows")
    result = {
        "review_version": "1", "review_date": "2026-10-22", "reviewer_type": "AI",
        "status": "ai_review_complete_awaiting_author",
        "historical_dataset_sha256": sha(data_path), "historical_sources_sha256": sha(source_path),
        "historical_dataset_unchanged": True, "reviewed_claim_count": 58,
        "flagged_claim_count": len(FLAGS),
        "ai_status_counts": dict(Counter(row["ai_review_status"] for row in records)),
        "scope": "逐条核对原始给定上下文、gold标签、引用充分性及粒度；不引用待测模型输出来决定标签。q5原题第5页额外视觉复核。其他原来源页面检查沿用SOURCE_REVIEW记录，本次不声称重新独立求解整卷。",
        "author_review_method_planned": "作者逐条裁决4个标出项并抽查其他项；未收到作者实际确认。",
        "zero_claim_case_checks": [
            {"case_id": "cphos28-edge-02", "ai_conclusion": "空字符串没有事实声明，claims=[]合理。", "author_decision": None},
            {"case_id": "cphos28-edge-03", "ai_conclusion": "纯感谢没有可检验事实，claims=[]合理。", "author_decision": None},
        ],
        "claims": records,
    }
    (DEST / "review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# CPHOS28 原58条 gold：AI 逐项复核表", "",
             "复核日期：2026-10-22。状态：**AI 复核完成，待作者终审**。这里没有修改原数据、旧报告或任何标签。",
             "", "作者需逐条裁决下方4个标出项，并抽查其余条目。请在作者决定栏写结论、理由和日期；待填写不是同意，也不构成人工终审。",
             "", "## 优先裁决项", "", "| Claim | 问题 | 建议 |", "| --- | --- | --- |"]
    for row in records:
        if row["dispute_type"]:
            lines.append(f"| `{row['claim_id']}` | {row['ai_reasoning']} | {row['recommendation']} |")
    lines += ["", "## 逐项审阅", "", "S=SUPPORTED，C=CONTRADICTED，U=UNSUPPORTED。页码均为 PDF 的1-based页码；题=试题PDF，解=参考解答PDF。",
              "", "每行的出处列列出 gold 引文对应段；U 行列出排查过的输入上下文。完整逐字引文、输入片段与证据索引见 [review.json](review.json)。"]
    for problem in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "EDGE"]:
        lines += ["", "### " + problem, "", "| Claim / 原文 | Gold | AI结论与理由 | 出处 | 争议 / 建议 | 作者决定 |", "| --- | --- | --- | --- | --- | --- |"]
        for row in records:
            if row["problem_id"] != problem:
                continue
            refs = [ref for ref in row["source_references"] if ref["gold_quotes"]] or row["source_references"]
            source_text = "；".join(("题" if ref["document_id"] == "exam" else "解") + "p" + ",".join(map(str, ref["pages"])) + " " + ref["locator"] + " (`" + ref["passage_id"] + "`)" for ref in refs) or "输入上下文为空"
            verdict = {"SUPPORTED": "S", "CONTRADICTED": "C", "UNSUPPORTED": "U"}[row["gold_verdict"]]
            title = "待裁决" if row["ai_review_status"] == "requires_author_adjudication" else "保留标签，引用待审" if row["dispute_type"] else "建议维持"
            lines.append(f"| `{row['claim_id']}`<br>{row['claim_text']} | {verdict} | {title}：{row['ai_reasoning']} | {source_text} | {row['recommendation']} | 待填写 |")
    lines += ["", "## 零声明案例补查", "", "`cphos28-edge-02` 为空回答、`cphos28-edge-03` 为纯感谢，二者零 gold 合理，不计入58条声明。作者抽查：待填写。",
              "", "## 复核边界与证据", "",
              "本次逐条阅读的是各案例实际提供的规范化上下文，而不是用完整PDF给缺失上下文补证。物理结果以来源忠实性判断；一般公式不因某个退化参数取值偶然相等就自动视为等价。方向推断中的参数符号边界仍明确列为争议。",
              "", "q5-03 已额外视觉核对试题PDF第5页：原文写空气阻力及 f_vec=-eta*v_n_vec，但没有显式 eta>0 不等式。q5-05 的回答自带正参数条件，不能把前一例的边界争议照搬到它。",
              "", "其余原选录公式的页面核对记录沿用 [SOURCE_REVIEW](../../dataset/cphos28/SOURCE_REVIEW.md)。本次没有重新独立解完整卷，也没有把AI复核称为作者或专家认证。",
              "", f"原 cases.jsonl SHA-256：`{sha(data_path)}`", "", f"原 sources.json SHA-256：`{sha(source_path)}`", "",
              "作者终审确认：待填写；实际抽查 claim_id：待填写；日期：待填写。"]
    (DEST / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"reviewed_claim_count": len(records), "flagged_claim_count": len(FLAGS), "author_review": "pending"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
