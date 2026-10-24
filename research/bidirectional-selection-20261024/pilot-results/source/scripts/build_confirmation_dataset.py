#!/usr/bin/env python3
"""Build the frozen-policy CPHOS28 confirmation set without model inference."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from validate_dataset import check_dataset, export_dataset, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dataset/cphos28-confirmation"
POLICY = ROOT / "docs/ANNOTATION_POLICY_V3.md"
FREEZE = ROOT / "reports/v3.1-code-freeze-final.json"
APPROVAL = ROOT / "reviews/cphos28/pilot-author-review.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(key: str, pages: list[int], locator: str, text: str, proof: str) -> dict:
    return {
        "id": "confirmation_" + key, "document_id": "solutions", "pages": pages,
        "locator": locator, "text": text,
        "normalization": "AI视觉核对原页；希腊字母转ASCII名称，下标用_，分式用带括号的/，乘法用*，指数用exp，列向量用^T。删除页眉和评分说明，保留符号、条件与数值；引文以本text为逐字匹配对象。",
        "normalization_proof": proof,
        "review_status": "ai_text_and_page_visual_checked",
        "prior_transcription_status": "new_excerpt_not_in_historical_or_pilot_sources",
    }


SOURCES = [
    source("q2_slope_arc", [4], "二(1)，式(2)",
           "悬链线部分的定义为 tan(theta) = dy/dx，弧长微元为 ds = sqrt(dx^2+dy^2)。",
           "核对式(2)的tan、dy/dx及根号覆盖dx^2+dy^2；悬链线部分来自同页解答引导语。"),
    source("q2_horizontal", [4], "二(1)，式(3)",
           "参考解答对悬链线部分积分得到 T*cos(theta) = T_0。",
           "式(3)为T乘cos(theta)，没有sin或额外竖直自重项；保留其悬链线段适用范围。"),
    source("q2_integral", [4], "二(1)，式(5)",
           "悬链线部分再次积分得到 1/cos(theta)-C_0 = (lambda*g/T_0)*y。",
           "式(5)左侧为1/cos(theta)减C_0，右侧为lambda*g*y/T_0；显式括号只调整线性排版。"),
    source("q2_hanging", [5], "二(1)，自由悬挂部分标题及式(18)",
           "参考解答在自由悬挂部分列出的张力关系为 T_2 = m*g+lambda*g*l。",
           "标题明确自由悬挂部分，式(18)为mg+lambda*g*l；不从相邻式(17)复用pilot的T_1。"),
    source("q2_free_length", [5, 6], "二(1)，第5页自由悬挂部分l、第6页式(20)第一行",
           "参考解答给出的自由悬挂部分绳长数值为 l = 2.3932905*R。",
           "l的段落指代来自第5页自由悬挂部分；第6页式(20)第一行逐位为2.3932905R。未选录此前用过的式(21)。"),
    source("q2_energy", [6], "二(2)，圆周运动部分及式(22)",
           "圆周运动部分满足能量关系 0.5*M*v_0^2+M*g*R*(1-cos(phi)) = 0.5*M*v^2。",
           "式(22)两动能项系数均为1/2，重力项为1-cos(phi)，转写1/2为0.5。"),
    source("q2_normal", [6], "二(2)，式(23)第一个等号后的表达式",
           "圆周运动部分的支持力为 N = M*g*cos(phi)-M*v^2/R。",
           "只选录式(23)的第一种形式，负向心项为-M*v^2/R；不把同一行第二种已消去v的结果放进输入，以保留多段代数综合要求。"),
    source("q6_coefficient_b", [20], "六(3.2)，式(24)",
           "参考解答给出的有限长链矩阵幂系数为 B = (lambda_1^(N-1)-lambda_2^(N-1))/(lambda_1-lambda_2)。",
           "式(24)分子两个幂均为N-1，分母lambda_1-lambda_2；未添加原文未写的物理参数域。"),
    source("q6_coefficient_a", [20], "六(3.2)，式(28)",
           "参考解答给出的另一矩阵幂系数为 A = (lambda_1^N-lambda_2^N)/(lambda_1-lambda_2)。",
           "式(28)分子幂为N，不是N-1或N+1；分母保持特征根差。"),
    source("q6_root_sum", [20], "六(3.2)，式(25)",
           "参考解答按韦达定理写出 lambda_1+lambda_2 = exp(i*phi)*(1+i*q)+exp(-i*phi)*(1-i*q)。",
           "式(25)第一项相位正、括号为1+iq；第二项相位负、括号为1-iq；完整保留复数式。"),
    source("q6_continuity", [18], "六(2.1)，解答式(4)第一行",
           "相邻区间内部连接处的位移连续条件为 u_j(a) = u_(j+1)(0)。",
           "式(4)第一行是u_j在x=a和u_(j+1)在x=0的值相等；函数求值改用括号，不加等于零条件。"),
    source("q6_fixed_ends", [19], "六(3.1)，式(13)",
           "有限长链两端固定边界的位移条件为 u_0(0) = 0，u_N((1-tau)*a) = 0。",
           "式(13)左边界在第0段x=0，右边界在第N段x=(1-tau)*a；不是重复pilot的几何描述或初始传递矩阵。"),
    source("q6_eigenvectors", [19], "六(3.2)，式(18)",
           "参考解答给出的两个特征向量写作 p_(1,2) = [-exp(-i*phi)*i*q, exp(i*phi)*(1+i*q)-lambda_(1,2)]^T。",
           "式(18)列向量首项有前置负号，次项减相应lambda；(1,2)保留原文合写两个下标的记法，^T表示列向量。"),
    source("q6_recurrence_a", [19], "六(2.1)，式(6)第一行",
           "相邻区间振幅递推的第一式为 A_(j+1) = A_j*exp(i*k*a)+(i*m*k/(2*mu))*(A_j*exp(i*k*a)+B_j*exp(-i*k*a))。",
           "核对式(6)第一行：校正项前为+i*m*k/(2*mu)，括号内两项为相加。未用pilot的完整传递矩阵代替。"),
    source("q6_recurrence_b", [19], "六(2.1)，式(6)第二行",
           "相邻区间振幅递推的第二式为 B_(j+1) = B_j*exp(-i*k*a)-(i*m*k/(2*mu))*(A_j*exp(i*k*a)+B_j*exp(-i*k*a))。",
           "核对式(6)第二行：校正项前为负号，括号与第一行相同；B_j主项相位为-i*k*a。"),
    source("q7_velocity", [22], "七(1A)，解答式(4)",
           "恒固有加速度观者的速度为 v = c*tanh(g*tau/c)。",
           "式(4)使用tanh，不是此前t(tau)来源中的sinh；速度v前因子为c。"),
    source("q7_gamma", [22], "七(1A)，解答式(5)",
           "该观者的洛伦兹因子为 gamma = 1/sqrt(1-v^2/c^2) = cosh(g*tau/c)。",
           "式(5)根号内为1-v^2/c^2，第二种形式为cosh；没有引入额外速度条件。"),
    source("q7_clock_derivative", [22], "七(1A)，解答式(6)",
           "惯性系时间与固有时的微分关系为 dt/dtau = gamma。",
           "式(6)为dt/dtau而非反向导数，右边是gamma，不是倒数。"),
    source("q7_proper_acceleration", [22], "七(1A)，解答式(1)",
           "由固有加速度定义，g = dv_prime/dtau。",
           "原文v带撇，线性记为v_prime；导数分母是固有时tau。"),
    source("q7_origin_factor", [23], "七(1C)，式(13)",
           "在加速观者坐标 xi=0 处，度规共形因子的平方满足 Omega^2(c*tau,0) = 1。",
           "式(13)第二个坐标参数明确为0；这里只说明该位置，不能把0转成任意xi。"),
    source("q7_null_factor", [23], "七(1C)，式(16)",
           "一般加速类光坐标下的线元为 ds^2 = exp(-g*(u_tilde-v_tilde)/c^2)*du_tilde*dv_tilde。",
           "式(16)指数为-g*(u_tilde-v_tilde)/c^2；带波浪的u、v各记为u_tilde、v_tilde，保留一般坐标差。未复用旧式(17)的xi形式。"),
    source("q7_inverse_space", [23], "七(1C)，式(19)最后一个等号后的表达式",
           "由惯性坐标转回加速空间坐标的关系为 xi = (c^2/(2*g))*ln((g^2/c^4)*(x^2-c^2*t^2))。",
           "式(19)前因子为c^2/(2*g)，对数内为(g^2/c^4)*(x^2-c^2*t^2)；没有使用pilot式(18)的时间反变换。"),
]


def build_cases() -> list[dict]:
    text_by_key = {p["id"].removeprefix("confirmation_"): p["text"] for p in SOURCES}
    cases = []

    def add(category: str, problem: str, keys: list[str], answer: str, specs: list[tuple], note: str) -> None:
        identifier = f"cphos28-confirmation-{category}-{problem.lower()}"
        claims = []
        for i, (text, verdict, reason, evidence_keys) in enumerate(specs, 1):
            indices = [keys.index(k) for k in evidence_keys]
            claims.append({
                "claim_id": f"{identifier}-c{i}", "claim_text": text, "answer_quote": text,
                "verdict": verdict, "reasoning": reason,
                "citations": [{"index": index, "quote": text_by_key[key]} for index, key in zip(indices, evidence_keys)],
                "acceptable_evidence_sets": [sorted(indices)] if indices else [],
                "required_passage_indices": sorted(indices) if len(indices) > 1 else [],
            })
        cases.append({
            "id": identifier, "split": "confirmation", "category": category,
            "topic": "CPHOS28 同来源、同题族新增确认集", "problem_id": problem,
            "context_passage_ids": ["confirmation_" + k for k in keys],
            "input": {"context_passages": [text_by_key[k] for k in keys], "generated_answer": answer},
            "expected": {"claims": claims},
            "metadata": {
                "annotation_policy": "docs/ANNOTATION_POLICY_V3.md",
                "annotation_policy_sha256": digest(POLICY),
                "answer_origin": "代码与标注规则冻结后由AI构造，未查看被测模型输出；不是被测模型采样答案。",
                "author_review_status": "not_individually_reviewed",
                "ai_review_status_at_construction": "pending_independent_review", "construction_note": note,
                "source_scope": "same_source_same_question_family",
            },
        })

    t = [
        "悬链线段的切线斜率满足 tan(theta) = dy/dx。",
        "悬链线段在任意适用角度下的张力竖直分量恒为 T_0，即 T*sin(theta) = T_0。",
        "参考解答中悬链线积分公式的符号写法为 1/cos(theta)+C_0 = (lambda*g/T_0)*y。",
        "悬链线弧长微元满足 ds = sqrt(dx^2+dy^2)。",
        "这根绳的总质量为 2 kg。",
    ]
    add("density", "Q2", ["q2_slope_arc", "q2_horizontal", "q2_integral"], "".join(t), [
        (t[0], "SUPPORTED", "定义直接给出tan(theta)=dy/dx。", ["q2_slope_arc"]),
        (t[1], "CONTRADICTED", "来源保持的是T*cos(theta)，回答改成竖直分量T*sin(theta)；文字与其错误公式相互一致，按同句冗余规则保留一条。", ["q2_horizontal"]),
        (t[2], "CONTRADICTED", "同一积分关系中来源为减C_0，回答写加C_0，作为一般参数关系不等价。", ["q2_integral"]),
        (t[3], "SUPPORTED", "弧长定义完整一致。", ["q2_slope_arc"]),
        (t[4], "UNSUPPORTED", "输入没有绳总质量数值，也没有足以确定2 kg的数值参数。", []),
    ], "五句高密度回答，包含一致但错误的局部说明与完整公式。")

    t = [
        "在 lambda_1!=lambda_2 时，B 的分子指数为 N-1，即 B = (lambda_1^(N-1)-lambda_2^(N-1))/(lambda_1-lambda_2)。",
        "对任意 lambda_1!=lambda_2，矩阵幂系数的一般表达式为 A = (lambda_1^(N+1)-lambda_2^(N+1))/(lambda_1-lambda_2)。",
        "参考解答给出的特征根之和为 lambda_1+lambda_2 = exp(i*phi)*(1+i*q)+exp(-i*phi)*(1-i*q)。",
        "本例 N 的数值为 100。",
        "本例所有原子均由硅材料构成。",
    ]
    add("density", "Q6", ["q6_coefficient_b", "q6_coefficient_a", "q6_root_sum"], "".join(t), [
        (t[0], "SUPPORTED", "非零分母条件由回答显式给出；分子N-1的局部描述被完整公式蕴含，可以同句合并。", ["q6_coefficient_b"]),
        (t[1], "CONTRADICTED", "在回答已限定的不同特征根域内，来源分子幂是N，不是N+1；一般公式不同。", ["q6_coefficient_a"]),
        (t[2], "SUPPORTED", "两复指数项和括号符号与来源一致。", ["q6_root_sum"]),
        (t[3], "UNSUPPORTED", "N仅作为符号出现，未给100这个数值。", []),
        (t[4], "UNSUPPORTED", "矩阵幂和根关系不指定材料。", []),
    ], "五句回答；把适用域写进claim，未默认缺失的非零物理参数。")

    t = [
        "恒固有加速度观者的速度为 v = c*tanh(g*tau/c)。",
        "该观者的洛伦兹因子为 gamma = sinh(g*tau/c)。",
        "惯性时间对固有时的一般微分恒等式为 dt/dtau = 1/gamma。",
        "此次速度测量的相对误差为 1%。",
        "固有加速度的定义式为 g = dv_prime/dtau。",
    ]
    add("density", "Q7", ["q7_velocity", "q7_gamma", "q7_clock_derivative", "q7_proper_acceleration"], "".join(t), [
        (t[0], "SUPPORTED", "速度公式直接匹配。", ["q7_velocity"]),
        (t[1], "CONTRADICTED", "来源使用cosh而不是sinh。", ["q7_gamma"]),
        (t[2], "CONTRADICTED", "来源给dt/dtau=gamma，回答将其倒置。", ["q7_clock_derivative"]),
        (t[3], "UNSUPPORTED", "仅有理论关系，没有测量或误差数据。", []),
        (t[4], "SUPPORTED", "带撇速度对固有时的导数定义一致。", ["q7_proper_acceleration"]),
    ], "五句回答，跨相邻速度、洛伦兹因子、时钟和加速度关系。")

    t = [
        "在参考解答中，T*cos(theta) = T_0 被列为自由悬挂部分的张力关系。",
        "参考解答对自由悬挂部分给出 T_2 = m*g+lambda*g*l。",
        "自由悬挂部分的绳直径为 2 mm。",
    ]
    add("scope_distractor", "Q2", ["q2_horizontal", "q2_hanging"], "".join(t), [
        (t[0], "UNSUPPORTED", "第0段证明该式用于悬链线部分，第1段给自由悬挂部分另一关系，但二者并未排他地断言该式不可能也被列在自由悬挂部分；该额外归属缺少支持，不能把未说明当直接矛盾。", []),
        (t[1], "SUPPORTED", "自由悬挂部分的范围及完整自重项均保留。", ["q2_hanging"]),
        (t[2], "UNSUPPORTED", "两种张力关系都没有绳直径数据。", []),
    ], "并置同题不同绳段；判断的是明确来源归属，不凭额外力学推导断言两个张力永不相等。")

    t = [
        "任意内部连接点都具有额外的零位移约束 u_j(a) = 0。",
        "有限长链右侧固定边界满足 u_N((1-tau)*a) = 0。",
        "参考解答写出的左侧固定边界条件是 u_0(0) = 1。",
    ]
    add("scope_distractor", "Q6", ["q6_continuity", "q6_fixed_ends"], "".join(t), [
        (t[0], "UNSUPPORTED", "内部只给位移连续，零位移条件明确施加于两端固定边界；不能把两端约束推广到任意内部点。来源没有直接断言内部位移一定非零，故按证据不足处理。", []),
        (t[1], "SUPPORTED", "右侧边界的局部坐标和零值都正确。", ["q6_fixed_ends"]),
        (t[2], "CONTRADICTED", "同一个左侧固定端来源写0，回答写1。", ["q6_fixed_ends"]),
    ], "固定端条件作诱饵；保留缺乏支持与直接数值矛盾的区别。")

    t = [
        "在 xi=0 处，共形因子的平方满足 Omega^2(c*tau,0) = 1。",
        "不论 g 和加速类光坐标取何适用值，线元恒等式均为 ds^2 = du_tilde*dv_tilde。",
        "这一坐标系统使用的探测器质量为 1 kg。",
    ]
    add("scope_distractor", "Q7", ["q7_origin_factor", "q7_null_factor"], "".join(t), [
        (t[0], "SUPPORTED", "保留xi=0条件后直接得到因子为1。", ["q7_origin_factor"]),
        (t[1], "CONTRADICTED", "一般坐标线元含exp(-g*(u_tilde-v_tilde)/c^2)，不是任意坐标下都恒等于1；回答把特定位置的归一化推广为一般恒等式。", ["q7_null_factor"]),
        (t[2], "UNSUPPORTED", "度规关系没有给探测器质量。", []),
    ], "并置特殊位置与一般坐标的因子；不从缺失参数推断具体方向。")

    p = "参考解答列出的自由悬挂绳长系数为 2.4932905"
    f = "l = 2.3932905*R。"
    u = "该绳的热膨胀系数为 1.2e-5/K。"
    add("mixed_truth_compound", "Q2", ["q2_free_length"], p + "，即 " + f + u, [
        (p, "CONTRADICTED", "来源系数为2.3932905，文字部分改成2.4932905。", ["q2_free_length"]),
        (f, "SUPPORTED", "公式部分保留来源数值；与前面文字冲突，不能同句合并。", ["q2_free_length"]),
        (u, "UNSUPPORTED", "没有材料热膨胀系数信息。", []),
    ], "一条复合句中不一致的局部系数描述与公式必须拆分，另有独立无依据句。")

    p = "参考解答给出的特征向量 p_1 的第一分量是 exp(-i*phi)*i*q"
    f = "p_1 = [-exp(-i*phi)*i*q, exp(i*phi)*(1+i*q)-lambda_1]^T。"
    u = "这条链在实验室温度 300 K 下被测量。"
    add("mixed_truth_compound", "Q6", ["q6_eigenvectors"], p + "，即 " + f + u, [
        (p, "CONTRADICTED", "参考写法的首分量有前置负号，文字漏掉该符号；这里核对来源给出的写法，不声称特征向量的整体缩放唯一。", ["q6_eigenvectors"]),
        (f, "SUPPORTED", "取来源(1,2)中的第一组下标后，列向量两分量及符号一致。", ["q6_eigenvectors"]),
        (u, "UNSUPPORTED", "没有实验温度或实际测量条件。", []),
    ], "第一分量的错误描述与正确完整向量不合并；以来源写法避免特征向量整体倍数的争议。")

    p = "加速空间坐标 xi 的对数前因子为 c^2/g"
    f = "xi = (c^2/(2*g))*ln((g^2/c^4)*(x^2-c^2*t^2))。"
    u = "这里 g 的测量不确定度为 0.01 m/s^2。"
    add("mixed_truth_compound", "Q7", ["q7_inverse_space"], p + "，即 " + f + u, [
        (p, "CONTRADICTED", "来源前因子为c^2/(2*g)，文字省略分母2。", ["q7_inverse_space"]),
        (f, "SUPPORTED", "公式部分保留前因子与对数内全部项；文字与公式不一致应拆开。", ["q7_inverse_space"]),
        (u, "UNSUPPORTED", "来源只有符号坐标关系，没有g的测量不确定度。", []),
    ], "采用此前未转写的空间逆变换；不复用pilot的时间逆变换。")

    t = [
        "联立能量式与支持力式消去 v^2，得到 N = M*g*(3*cos(phi)-2)-M*v_0^2/R。",
        "同一消元中 v_0^2 项的系数为 +M/R，即 N = M*g*(3*cos(phi)-2)+M*v_0^2/R。",
        "圆柱材料的杨氏模量为 70 GPa。",
    ]
    add("reformulation_calculation", "Q2", ["q2_energy", "q2_normal"], "".join(t), [
        (t[0], "SUPPORTED", "能量式乘2得M*v^2=M*v_0^2+2*M*g*R*(1-cos(phi))，将整个M*v^2代入支持力式得到结果，不需要另加M非零假设；两段均必需。", ["q2_energy", "q2_normal"]),
        (t[1], "CONTRADICTED", "同样代入得到v_0^2项系数为-M/R，回答的一致文字与公式均写成正号。", ["q2_energy", "q2_normal"]),
        (t[2], "UNSUPPORTED", "运动关系不含材料弹性模量。", []),
    ], "来源只选支持力式的未消元形式，禁止用PDF同一行的答案式替代两个输入前提。")

    t = [
        "两条振幅递推相加后，A_(j+1)+B_(j+1) = A_j*exp(i*k*a)+B_j*exp(-i*k*a)。",
        "两条振幅递推相减恒等得到 A_(j+1)-B_(j+1) = A_j*exp(i*k*a)-B_j*exp(-i*k*a)。",
        "该链传递一个单元的实测时间为 0.01 s。",
    ]
    add("reformulation_calculation", "Q6", ["q6_recurrence_a", "q6_recurrence_b"], "".join(t), [
        (t[0], "SUPPORTED", "两式校正项大小相同、符号相反，相加恰好相消；两条递推都是必要前提。", ["q6_recurrence_a", "q6_recurrence_b"]),
        (t[1], "CONTRADICTED", "相减时校正项相加，尚有(i*m*k/mu)*(A_j*exp(i*k*a)+B_j*exp(-i*k*a))，回答的一般式漏项。", ["q6_recurrence_a", "q6_recurrence_b"]),
        (t[2], "UNSUPPORTED", "递推公式没有给单元传递的实测时间或数值参数。", []),
    ], "同一对公式对求和与求差给出不同校正项，必须真正合并两段证据。")

    t = [
        "由速度和洛伦兹因子公式相乘可得 gamma*v = c*sinh(g*tau/c)。",
        "由这两式还可得 gamma^2*(1-v^2/c^2) = 0。",
        "该观者时钟的漂移率实测为每天 0.1 ns。",
    ]
    add("reformulation_calculation", "Q7", ["q7_velocity", "q7_gamma"], "".join(t), [
        (t[0], "SUPPORTED", "gamma*v=c*cosh(z)*tanh(z)=c*sinh(z)，z=g*tau/c；两段分别给两个因子。", ["q7_velocity", "q7_gamma"]),
        (t[1], "CONTRADICTED", "第1段gamma=1/sqrt(1-v^2/c^2)已直接推出左侧为1而非0；其自身足以反驳，不伪造多源必要性。", ["q7_gamma"]),
        (t[2], "UNSUPPORTED", "理论速度和gamma关系没有实际时钟漂移测量。", []),
    ], "标准双曲恒等式及代数运算；只把真正必要的多源前提设为required。")
    return cases


def main() -> int:
    if DEST.exists() and any(DEST.iterdir()):
        raise SystemExit("Refusing to overwrite confirmation artifacts")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    if approval["decision"] != "approved" or approval["policy_sha256"] != digest(POLICY):
        raise SystemExit("Author-approved policy hash mismatch")
    if freeze["annotation_policy_sha256"] != digest(POLICY) or freeze["author_attestation_sha256"] != digest(APPROVAL):
        raise SystemExit("Implementation freeze does not bind current author approval")
    for name, expected in freeze["implementation_files_sha256"].items():
        if digest(ROOT / name) != expected:
            raise SystemExit("Frozen implementation mismatch: " + name)
    old = json.loads((ROOT / "dataset/cphos28/sources.json").read_text(encoding="utf-8"))
    pilots = json.loads((ROOT / "dataset/cphos28-review/sources.json").read_text(encoding="utf-8"))
    prior_passages = old["passages"] + pilots["passages"]
    assert not {p['id'] for p in SOURCES} & {p['id'] for p in prior_passages}
    assert not {p['text'] for p in SOURCES} & {p['text'] for p in prior_passages}
    document = next(p for p in old["documents"] if p["id"] == "solutions")
    if digest(Path(document["path"])) != document["sha256"]:
        raise SystemExit("Source PDF hash mismatch")
    DEST.mkdir(parents=True, exist_ok=True)
    sources = {
        "version": "confirmation-1", "documents": [document], "passages": SOURCES,
        "provenance_scope": "same_source_same_question_family_new_excerpts",
        "annotation_policy_sha256": digest(POLICY), "formal_human_label_review": False,
    }
    (DEST / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cases = build_cases()
    if len(cases) != 12 or set(Counter(c["category"] for c in cases).values()) != {3}:
        raise SystemExit("Expected twelve cases, three per planned category")
    write_jsonl(DEST / "cases.jsonl", cases)
    checked, report = check_dataset(DEST / "cases.jsonl", check_local_sources=True)
    if not report["valid"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    export_dataset(checked, DEST)
    (DEST / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    construction = {
        "created_at": datetime.now(timezone.utc).isoformat(), "implementation_freeze_path": str(FREEZE.relative_to(ROOT)).replace("\\", "/"),
        "implementation_freeze_sha256": digest(FREEZE), "implementation_frozen_at": freeze["frozen_at"],
        "author_policy_approval_sha256": digest(APPROVAL), "annotation_policy_sha256": digest(POLICY),
        "cases_sha256": digest(DEST / "cases.jsonl"), "sources_sha256": digest(DEST / "sources.json"),
        "historical_cases_sha256": digest(ROOT / "dataset/cphos28/cases.jsonl"),
        "pilot_cases_sha256": digest(ROOT / "dataset/cphos28-review/cases.jsonl"),
        "model_predictions_seen": False, "model_calls_made": 0,
        "author_review_scope": "Pilot and policy approval only; formal labels are AI-assisted.",
        "ai_independent_review_status": "pending",
    }
    (DEST / "construction.json").write_text(json.dumps(construction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "claims": sum(len(c['expected']['claims']) for c in cases), "categories": report['category_counts'], "verdicts": report['gold_verdict_counts'], "valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
