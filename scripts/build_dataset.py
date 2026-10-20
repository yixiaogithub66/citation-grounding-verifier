"""Build the curated CPHOS28 grounding benchmark from reviewed transcriptions."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset" / "cphos28"
PDF_ROOT = Path("D:/下载/CPHOS28/CPHOS28")
NORMALIZATION = (
    "由 AI 辅助选录并对照 PDF 页面核对；删除页眉、评分说明和重复题干；"
    "数学斜体、分式、上下标改写为 ASCII 变量及线性公式。"
    "此处为规范化转录，不声称与 PDF 二进制文本逐字相同；引用必须逐字匹配本 text。"
)


def document(doc_id, filename, pages, pdf_root):
    path = pdf_root / filename
    return {
        "id": doc_id,
        "title": filename.removesuffix(".pdf"),
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "page_count": pages,
        "copyright": "2025 CPHOS；原 PDF 版权归原作者，数据包未附原 PDF。",
    }


DOCUMENT_SPECS = [
    ("exam", "第28届CPHOS物理竞赛联考理论试题.pdf", 8),
    ("solutions", "第28届CPHOS物理竞赛联考理论试题解答.pdf", 24),
]
PASSAGES = {}


def passage(pid, doc, pages, locator, text):
    PASSAGES[pid] = {
        "id": pid,
        "document_id": doc,
        "pages": pages,
        "locator": locator,
        "text": text,
        "normalization": NORMALIZATION,
        "review_status": "text_and_page_visual_checked",
    }


passage("q1_setup", "exam", [1], "一(1)双透镜题干", "双透镜光具组中，入射方向透镜的焦距为 f_1，出射方向透镜的焦距为 f_2，两透镜之间的距离为 D。物方主面、像方主面到等效透镜的距离分别记为 u、v，等效焦距记为 f。")
passage("q1_focal", "solutions", [2], "一(1.1)，式(3)", "双透镜等效焦距：f = f_1*f_2/(f_1+f_2-D)。")
passage("q1_principal", "solutions", [2], "一(1.1)，式(4)(5)", "主面距离：u = f_2*D/(D-f_1-f_2)，v = f_1*D/(D-f_1-f_2)。")
passage("q1_afocal", "solutions", [2], "一(1.2)，式(7)(8)(9)", "使入射平行光 (r,0) 出射为 (k*r,0) 的配置满足 f_1 = -D/(k-1)，f_2 = k*D/(k-1)。该配置的光线矩阵为 M = [[k,D],[0,1/k]]。")
passage("q1_angular", "solutions", [2], "一(1.2)，式(11)(12)", "小偏角入射时，出射位置相对原出射位置的偏差为 Delta_r = D*theta，出射光相对光轴的夹角为 Delta_theta = theta/k。")
passage("q1_sphere_data", "exam", [1], "一(2.1)(2.2)球面例题", "球状光学面的半径为 R，右侧折射率为 n，左侧折射率为 1。例题数据为 u = 3 m，R = 4 m，n = 1.5，theta = pi/6；出射角 delta 以逆时针为正，数值用弧度表示并保留三位小数。")
passage("q1_sphere_formula", "solutions", [3], "一(2.1)，式(16)", "球面折射的出射角：delta = arcsin((u+R)*sin(theta)/(n*R)) - arcsin((u+R)*sin(theta)/R) + theta。")
passage("q1_sphere_result", "solutions", [3], "一(2.2)，式(17)及相邻出射角定义", "球面例题代入给定数据后，出射角为 delta = 0.081 rad。")

passage("q2_setup", "exam", [2], "二题干及(1)", "匀质不可伸长细绳的一端固定在 A，另一端跨过固定圆柱悬吊物块。A 与圆柱圆心等高。绳的质量线密度为 lambda，圆柱半径为 R，系统静止且悬链部分未绷直。给定 mu = 0.150，L/R = 16.0，d/R = 5.60，theta_0 = 10.0 deg。")
passage("q2_mass", "solutions", [6], "二(1)，式(21)", "参考答案给出的悬挂物块最大质量为 m_max = 6.66*lambda*R。")
passage("q2_track", "exam", [2], "二(2)轨道条件", "将悬挂物块质量取最大值时的细绳固化为光滑轨道。质点从圆柱顶端水平向左出发，要求恰好到达 A 且速度为零。所有可能的碰撞均为完全非弹性碰撞，不考虑直接平抛到轨道左侧末端的情况。")
passage("q2_speed", "solutions", [7], "二(2)，式(35)", "参考答案给出的所需初速度大小为 v_0 = 0.614*sqrt(g*R)。")
passage("q2_t1", "solutions", [7], "二(2)，式(36)", "圆周运动阶段用时 t_1 = 0.93008453*sqrt(R/g)。")
passage("q2_t2", "solutions", [6, 7], "二(2)，式(29)(34)及时间单位定义", "随后斜抛阶段的无量纲时长 t_2 = 2.3024461，对应实际时长 Delta_t_2 = 2.3024461*sqrt(R/g)。")
passage("q2_t3", "solutions", [7], "二(2)，式(43)", "碰撞后沿悬链线滑行的时长 t_3 = 3.7506261*sqrt(R/g)。")
passage("q2_total", "solutions", [7], "二(2)，式(44)", "首次到达 A 的总时间为 t_f = t_1 + Delta_t_2 + t_3 = 6.98*sqrt(R/g)。")

passage("q3_setup", "exam", [2, 3], "三题干及(2)给定数据", "圆筒内封闭氩气，可视为理想气体。活塞及筒壁绝热，活塞无摩擦且不漏气，圆筒放置在真空中。m = 0.64 kg，A = 80 cm^2，T_i = 293 K，y_i = 1 m，g = 9.81 m/s^2，R = 8.315 J/(mol*K)。计算终态时取扰动初速度 u_i = 5.0 m/s。")
passage("q3_model", "exam", [3], "三两部分气体模型", "气体分为主体部分和活塞表面层。主体部分是准静态的，温度和压强均匀；表面层体积很小，温度与主体相同。表面层对活塞造成曳引，最终使其停止。")
passage("q3_mass", "solutions", [8], "三(1)，式(3)(4)", "氩气总质量 m_Ar = mu*m*g*y_i/(R*T_i) = 1.03e-4 kg，其中 mu 为氩气摩尔质量。")
passage("q3_height_formula", "solutions", [9], "三(2)，式(7)", "最终平衡高度满足 y_f = y_i + u_i^2/(5*g)。")
passage("q3_temperature", "solutions", [9], "三(2)，式(10)(11)", "终态温度 T_f = T_i*(1+u_i^2/(5*g*y_i))，给定数据下 T_f = 442 K。")
passage("q3_entropy", "solutions", [9], "三(3)，式(13)(14)", "整个过程的气体熵增 Delta_S = (5*m*g*y_i/(2*T_i))*ln(1+u_i^2/(5*g*y_i))，给定数据下 Delta_S = 2.21e-2 J/K。")
passage("q3_pressure", "solutions", [9], "三(4)，式(21)", "近似到活塞速度 u 的一阶，表面层压强为 p_star = p*(1-2*u*sqrt(2*mu/(pi*R*T)))，其中 p、T 为主体压强、温度，mu 为摩尔质量。")
passage("q3_layer", "solutions", [10], "三(6)，式(36)前文字及公式", "表面层厚度大概是一个平均自由程，故其体积 delta_V = lambda_bar*A，其中 lambda_bar 为平均自由程，A 为活塞面积。")

passage("q4_normal", "exam", [3], "四引言，单边结构法向力", "单边直线感应弹射电动机除了产生电磁推力外，还产生与推力方向垂直的法向力；该法向力会影响轮轨摩擦力或磁悬浮气隙。")
passage("q4_double", "exam", [3], "四引言，双边结构法向合力", "为使次级受到的法向合力为零，可在次级两边各安装一套初级部件，形成双边直线感应弹射电动机。")
passage("q4_scaling", "exam", [3], "四引言，同线负荷下功率与推力比较", "在每侧电流线负荷与单边结构相同时，双边结构的输出功率和推力均为单边结构的两倍。")
passage("q4_geometry", "exam", [4], "四一维模型参数", "次级导电板电导率为 sigma，厚度为 2*d，速度为 v，长度为 2*p*tau；双边初级间距为 2*g_e，其中 p 是次级对应的极对数，tau 是极距。")
passage("q4_components", "exam", [4], "四假设I", "H 和 B 仅有 y 分量，J_1、J_2 和 E 仅有 z 分量。")
passage("q4_iron", "exam", [4], "四假设II、III、V", "场量仅依赖空间坐标 x，并随时间 t 正弦交变。初级铁芯与绕组沿纵向视为无限长。不计铁芯饱和和铁耗，取 mu_Fe = infinity，sigma_Fe = 0。")
passage("q4_ohm", "solutions", [12], "四(1.1)，式(2)", "次级导电板中的电流密度为 J_2_vec = sigma*(E_vec + v_vec cross B_vec)。")

passage("q5_model", "exam", [5], "五题干模型", "本题分析飞盘运动时不考虑重力。飞盘视为半径 r、厚度 h << r、质量 m 的圆柱体，其质量分布旋转对称。I_1 为垂直盘面的转动惯量，I_2 为沿盘面半径的转动惯量。初始速度沿 x 轴，主自旋沿 y 轴，小扰动满足 omega_0 << Omega_0。")
passage("q5_drag", "exam", [5], "五迎风面阻力假设", "对迎风面，即表面法向速度 v_n_vec 朝向面外的部分，单位面积阻力为 f_vec = -eta*v_n_vec。")
passage("q5_torque", "solutions", [15], "五(1)，式(5)", "相对质心的外力矩为 M_vec = -(pi/4)*eta*r^4*omega_vec，其中 omega_vec 为平行盘面的角速度分量。")
passage("q5_angular_decay", "solutions", [16], "五(2)，式(8)后文字", "在刚体本动系中，平行盘面的角速度分量的模长满足 omega(t) = omega_0*exp(-pi*eta*r^4*t/(4*I_2))。")
passage("q5_velocity", "solutions", [16], "五(3)，式(16)", "零阶平移速度为 v_vec(t) = v_0*exp(-pi*eta*r*h*t/(2*m))*x_hat。")
passage("q5_stability", "solutions", [16], "五(2)，式(14)后结论", "主自旋向量仅在 Omega_0*y_hat 周围小幅变动并逐渐趋于稳定值，因此盘面朝向趋于稳定。")

passage("q6_bare", "solutions", [18], "六(1)，式(2)(3)", "无限长裸弦的色散关系为 omega = +/-sqrt(T/mu)*k，波速为 v = sqrt(T/mu)。T 为张力，mu 为裸弦质量线密度。")
passage("q6_definitions", "exam", [6], "六(2.1)无量纲量定义", "弦球链相邻原子间距为 a，原子质量为 m，裸弦线密度为 mu，张力为 T。定义 phi = omega*a*sqrt(mu/T)，q = m*omega/(2*sqrt(T*mu))，假设传递矩阵可对角化。")
passage("q6_polynomial", "solutions", [19], "六(2.2)，式(9)", "传递矩阵特征值满足 lambda^2-2*(cos(phi)-q*sin(phi))*lambda+1 = 0。")
passage("q6_dispersion", "solutions", [19], "六(2.2)，式(11)", "弦球链色散关系为 cos(kappa*a) = cos(phi)-q*sin(phi)。")
passage("q6_modes", "exam", [6], "六(3.3)模式定义", "在题设模式分类中，特征值模长 abs(lambda) != 1 时对应局域模，abs(lambda) = 1 时对应传播模。")

passage("q7_t", "solutions", [22], "七(1A)，式(7)", "恒定正 x 方向固有加速度 g 的观者，用固有时 tau 表示的时间坐标为 t(tau) = (c/g)*sinh(g*tau/c)。")
passage("q7_x", "solutions", [23], "七(1A)，式(9)", "同一观者的空间坐标为 x(tau) = (c^2/g)*cosh(g*tau/c)。")
passage("q7_null", "exam", [6, 7], "七(1A)(1B)惯性系与类光坐标", "在惯性系中，ds^2 = (c*dt)^2-dx^2。定义类光坐标 u = c*t-x，v = c*t+x。")
passage("q7_metric", "solutions", [23], "七(1B)，式(10)", "类光坐标下的度规为 ds^2 = du*dv。")
passage("q7_rindler", "solutions", [23], "七(1C)，式(17)", "加速观者坐标下的度规为 ds^2 = exp(2*g*xi/c^2)*((c*dtau)^2-dxi^2)。")
passage("q7_ratio", "solutions", [24], "七(2B)，式(25)", "采用题目中空间频率 Omega 的约定，Bogoliubov 系数模方之比为 abs(alpha)^2/abs(beta)^2 = exp(2*pi*Omega*c^2/g)。")


CATALOG = [
    ("Q1", "光学", "dev", [1, 2], [1, 2, 3], "求双透镜等效参数、平行光配置和小偏角响应，并计算球面折射的数值。"),
    ("Q2", "悬链线与轨道动力学", "test", [2], [4, 5, 6, 7, 8], "求给定静态位形下的最大悬挂质量，以及固化光滑轨道上恰好到达 A 的初速度和时间。"),
    ("Q3", "绝热活塞", "dev", [2, 3], [8, 9, 10, 11], "分析真空中绝热氩气活塞的气体质量、扰动后终态、熵增与表面层模型。"),
    ("Q4", "直线感应电机", "dev", [3, 4], [11, 12, 13, 14], "在一维长初级模型下分析磁场、电场及电磁推力。"),
    ("Q5", "飞盘刚体运动", "test", [4, 5], [14, 15, 16, 17], "在薄盘和线性迎风面阻力模型下，求力矩、角速度与速度的一阶行为并讨论稳定性。"),
    ("Q6", "有限长弦球链", "test", [5, 6], [17, 18, 19, 20, 21], "由裸弦波动建立弦球链传递矩阵、色散关系并区分传播模与局域模。"),
    ("Q7", "盎鲁效应与加速坐标", "test", [6, 7], [21, 22, 23, 24], "分析恒固有加速度世界线、类光坐标、加速度规及 Bogoliubov 系数。"),
]
BY_PROBLEM = {item[0]: item for item in CATALOG}
CASES = []


def claim(text, verdict, reason, evidence=(), required=()):
    return {
        "claim_text": text,
        "answer_quote": text,
        "verdict": verdict,
        "reasoning": reason,
        "_evidence": list(evidence),
        "_required": list(required),
    }


def case(problem, number, category, pids, claims, mutation, question=None, answer=None):
    info = BY_PROBLEM.get(problem)
    case_id = f"cphos28-{problem.lower()}-{number:02d}"
    gold = []
    for i, item in enumerate(claims, 1):
        item = dict(item)
        evidence = item.pop("_evidence")
        required = item.pop("_required")
        citations = [{"index": pids.index(pid), "quote": quote} for pid, quote in evidence]
        indices = sorted({c["index"] for c in citations})
        item.update({
            "claim_id": f"{case_id}-c{i}",
            "citations": citations,
            "acceptable_evidence_sets": [indices] if indices else [],
            "required_passage_indices": sorted(pids.index(pid) for pid in required),
        })
        gold.append(item)
    CASES.append({
        "id": case_id,
        "split": info[2] if info else "edge",
        "category": category,
        "topic": info[1] if info else "接口边界",
        "problem_id": problem,
        "question": question or (info[5] if info else "验证空输入和非事实回答的边界行为。"),
        "context_passage_ids": pids,
        "input": {
            "context_passages": [PASSAGES[pid]["text"] for pid in pids],
            "generated_answer": answer if answer is not None else "".join(c["answer_quote"] for c in gold),
        },
        "expected": {"claims": gold},
        "metadata": {
            "answer_origin": "AI 辅助构造并固定的待验证回答，未经用户人工终审，并非从被测 LLM 采样",
            "mutation": mutation,
            "annotation_policy": "只依给定规范化上下文判断；可作短程代数代入和明确数值计算；不引入外部物理知识。",
        },
    })


S = "SUPPORTED"
C = "CONTRADICTED"
U = "UNSUPPORTED"

case("Q1", 1, "supported", ["q1_setup", "q1_focal"], [claim("双透镜等效焦距为 f = f_1*f_2/(f_1+f_2-D)。", S, "公式与等效焦距段落一致。", [("q1_focal", "f = f_1*f_2/(f_1+f_2-D)")])], "正确公式的自然语言重述")
case("Q1", 2, "subtle_distortion", ["q1_setup", "q1_focal"], [claim("双透镜等效焦距为 f = f_1*f_2/(f_1+f_2+D)。", C, "上下文分母为减 D，回答改为加 D。", [("q1_focal", "f = f_1*f_2/(f_1+f_2-D)")])], "分母符号 -D 改为 +D")
case("Q1", 3, "subtle_distortion", ["q1_afocal", "q1_angular"], [claim("该平行光配置的小偏角响应为 Delta_theta = k*theta。", C, "上下文给出 theta/k，回答将除以 k 改为乘以 k。", [("q1_angular", "Delta_theta = theta/k")])], "乘除互换")
case("Q1", 4, "extrinsic_hallucination", ["q1_setup", "q1_focal"], [claim("这两片透镜均由 BK7 玻璃制成。", U, "上下文只有焦距和间距，未说明玻璃材料。")], "添加未给出的镜片材料")
case("Q1", 5, "multi_passage_synthesis", ["q1_sphere_data", "q1_sphere_formula"], [claim("将球面例题给定数据代入折射公式，出射角约为正的 0.081 rad。", S, "数据与公式来自两段，代入得 0.0809895 rad，取三位小数为 0.081 rad。", [("q1_sphere_data", "u = 3 m，R = 4 m，n = 1.5，theta = pi/6"), ("q1_sphere_formula", "delta = arcsin((u+R)*sin(theta)/(n*R)) - arcsin((u+R)*sin(theta)/R) + theta")], ["q1_sphere_data", "q1_sphere_formula"])], "上下文未直接给出数值答案，需两段代入", "球面例题给定数据对应的出射角是多少？")
case("Q1", 6, "mixed", ["q1_angular", "q1_sphere_result", "q1_setup"], [claim("小偏角导致的位置偏差为 Delta_r = D*theta。", S, "位置偏差与来源一致。", [("q1_angular", "Delta_r = D*theta")]), claim("球面例题的出射角为 -0.081 rad。", C, "来源为正的 0.081 rad，回答反转了符号。", [("q1_sphere_result", "delta = 0.081 rad")]), claim("透镜表面镀有十层增透膜。", U, "上下文没有镀膜层数。")], "一条支持、一条数值符号反转、一条材料外推")

case("Q2", 1, "supported", ["q2_setup", "q2_mass"], [claim("在给定位形下，参考答案给出的最大悬挂质量为 6.66*lambda*R。", S, "最大质量与参考答案选录一致。", [("q2_mass", "m_max = 6.66*lambda*R")])], "正确最终数值；保持参考答案归属")
case("Q2", 2, "subtle_distortion", ["q2_setup", "q2_mass"], [claim("参考答案给出的最大悬挂质量为 6.67*lambda*R。", C, "给定有效数字下是 6.66，而非 6.67。", [("q2_mass", "m_max = 6.66*lambda*R")])], "最后一位有效数字加一")
case("Q2", 3, "subtle_distortion", ["q2_track"], [claim("该轨道模型中的碰撞均为完全弹性碰撞。", C, "上下文明确规定完全非弹性碰撞。", [("q2_track", "所有可能的碰撞均为完全非弹性碰撞")])], "反转碰撞条件")
case("Q2", 4, "extrinsic_hallucination", ["q2_setup", "q2_mass"], [claim("细绳的断裂张力为 20*lambda*g*R。", U, "只给出静态模型及最大悬挂质量，没有材料断裂张力。")], "添加未给出的绳强度")
case("Q2", 5, "multi_passage_synthesis", ["q2_t1", "q2_t2", "q2_t3"], [claim("将参考答案的圆周运动、随后斜抛和碰撞后滑行三个阶段的时长相加，结果约为 6.98*sqrt(R/g)。", S, "三个系数之和为 6.98315673，按三位有效数字约为 6.98。", [("q2_t1", "t_1 = 0.93008453*sqrt(R/g)"), ("q2_t2", "Delta_t_2 = 2.3024461*sqrt(R/g)"), ("q2_t3", "t_3 = 3.7506261*sqrt(R/g)")], ["q2_t1", "q2_t2", "q2_t3"])], "三个独立时长求和；未在上下文直接给总时长", "求参考答案中三个阶段时长之和。")
case("Q2", 6, "mixed", ["q2_setup", "q2_speed", "q2_total"], [claim("参考答案给出的初速度大小为 0.614*sqrt(g*R)。", S, "初速度数值与参考答案相同。", [("q2_speed", "v_0 = 0.614*sqrt(g*R)")]), claim("参考答案给出的首次到达时间为 6.89*sqrt(R/g)。", C, "来源为 6.98，回答交换了末两位。", [("q2_total", "t_f = t_1 + Delta_t_2 + t_3 = 6.98*sqrt(R/g)")]), claim("细绳由钢丝编织而成。", U, "没有给出绳材料。")], "正确速度、时间数字互换、材料无依据")

case("Q3", 1, "supported", ["q3_setup", "q3_mass"], [claim("封闭氩气的总质量为 1.03e-4 kg。", S, "气体质量数值与来源一致。", [("q3_mass", "1.03e-4 kg")])], "正确科学计数法")
case("Q3", 2, "subtle_distortion", ["q3_setup", "q3_height_formula"], [claim("最终高度满足 y_f = y_i + u_i^2/(4*g)。", C, "上下文分母为 5*g，不是 4*g。", [("q3_height_formula", "y_f = y_i + u_i^2/(5*g)")])], "分母整数减一")
case("Q3", 3, "subtle_distortion", ["q3_setup", "q3_entropy"], [claim("整个过程的氩气熵增为 -2.21e-2 J/K。", C, "来源给出正的 2.21e-2 J/K。", [("q3_entropy", "Delta_S = 2.21e-2 J/K")])], "熵增符号反转")
case("Q3", 4, "extrinsic_hallucination", ["q3_setup", "q3_model", "q3_mass"], [claim("本题采用的氩原子有效碰撞截面为 3.6e-19 m^2。", U, "上下文没有给出分子有效碰撞截面。")], "补入来源未给出的微观常数")
case("Q3", 5, "multi_passage_synthesis", ["q3_setup", "q3_height_formula"], [claim("给定扰动后，最终活塞高度约为 1.51 m。", S, "将 y_i=1、u_i=5、g=9.81 代入另一段公式，得 1.50968 m。", [("q3_setup", "y_i = 1 m，g = 9.81 m/s^2"), ("q3_setup", "u_i = 5.0 m/s"), ("q3_height_formula", "y_f = y_i + u_i^2/(5*g)")], ["q3_setup", "q3_height_formula"])], "题干数据和终态关系分段，需数值代入", "由初始数据和终态高度关系计算 y_f。")
case("Q3", 6, "mixed", ["q3_temperature", "q3_pressure", "q3_layer"], [claim("给定数据下的终态温度为 442 K。", S, "温度与来源一致。", [("q3_temperature", "T_f = 442 K")]), claim("一阶表面层压强为 p_star = p*(1+2*u*sqrt(2*mu/(pi*R*T)))。", C, "来源的一阶速度项前是负号。", [("q3_pressure", "p_star = p*(1-2*u*sqrt(2*mu/(pi*R*T)))")]), claim("表面层的平均自由程数值为 68 nm。", U, "来源仅给出体积量级关系，没有平均自由程的数值。")], "正确温度、曳引项符号错误、微观长度无依据")

case("Q4", 1, "supported", ["q4_components", "q4_geometry"], [claim("该一维模型中的 H 和 B 都只有 y 分量。", S, "与假设 I 完全一致。", [("q4_components", "H 和 B 仅有 y 分量")])], "模型分量正确重述")
case("Q4", 2, "subtle_distortion", ["q4_geometry"], [claim("次级导电板厚度为 d。", C, "上下文明确厚度为 2*d，回答少了系数 2。", [("q4_geometry", "厚度为 2*d")])], "厚度系数减半")
case("Q4", 3, "subtle_distortion", ["q4_components", "q4_iron"], [claim("本模型取铁芯磁导率为零。", C, "上下文取 mu_Fe = infinity，零对应的是电导率。", [("q4_iron", "mu_Fe = infinity，sigma_Fe = 0")])], "交换磁导率与电导率条件")
case("Q4", 4, "extrinsic_hallucination", ["q4_geometry", "q4_iron"], [claim("本题次级导电板由纯铜制成。", U, "只定义电导率 sigma，没有指明板材。")], "为导电板指定未给出的材料")
case("Q4", 5, "multi_passage_synthesis", ["q4_double", "q4_scaling", "q4_geometry"], [claim("在每侧线负荷与单边结构相同的比较条件下，用于消除次级法向合力的结构，其推力是单边结构的两倍。", S, "第一段将消除法向合力的方案识别为双边结构，第二段给出该结构的推力倍率；参数段落仅作干扰。", [("q4_double", "为使次级受到的法向合力为零，可在次级两边各安装一套初级部件，形成双边直线感应弹射电动机"), ("q4_scaling", "在每侧电流线负荷与单边结构相同时，双边结构的输出功率和推力均为单边结构的两倍")], ["q4_double", "q4_scaling"])], "先识别消除法向力的结构，再确定其条件性推力倍率", "用于消除法向合力的结构，在同线负荷条件下的推力倍率是多少？")
case("Q4", 6, "mixed", ["q4_scaling", "q4_components", "q4_ohm"], [claim("每侧线负荷相同时，双边结构的输出功率是单边结构的两倍。", S, "比较条件和输出功率倍率均在来源中。", [("q4_scaling", "在每侧电流线负荷与单边结构相同时，双边结构的输出功率和推力均为单边结构的两倍")]), claim("本模型的电场 E 仅有 x 分量。", C, "来源明确 E 仅有 z 分量。", [("q4_components", "J_1、J_2 和 E 仅有 z 分量")]), claim("这台电机的能量转换效率为 98%。", U, "上下文没有效率测量值或可据以计算的损耗。")], "正确倍率、分量交换、效率无依据")

case("Q5", 1, "supported", ["q5_model", "q5_torque"], [claim("相对质心的外力矩为 M_vec = -(pi/4)*eta*r^4*omega_vec。", S, "与力矩公式一致。", [("q5_torque", "M_vec = -(pi/4)*eta*r^4*omega_vec")])], "正确力矩")
case("Q5", 2, "subtle_distortion", ["q5_model", "q5_torque"], [claim("力矩的半径依赖为 r^3，即 M_vec = -(pi/4)*eta*r^3*omega_vec。", C, "来源半径幂次为 4。", [("q5_torque", "M_vec = -(pi/4)*eta*r^4*omega_vec")])], "半径指数减一")
case("Q5", 3, "subtle_distortion", ["q5_model", "q5_drag"], [claim("迎风面单位面积阻力与法向速度同向，f_vec = eta*v_n_vec。", C, "来源阻力公式含负号，方向与法向速度相反。", [("q5_drag", "f_vec = -eta*v_n_vec")])], "阻力方向反转")
case("Q5", 4, "extrinsic_hallucination", ["q5_model", "q5_torque"], [claim("本题飞盘的径向质量密度处处相同。", U, "旋转对称只说明无方位角差异，未给出径向均匀性。")], "将旋转对称擅自加强为均匀分布")
case("Q5", 5, "multi_passage_synthesis", ["q5_angular_decay", "q5_velocity"], [claim("在正的物理参数下，小扰动角速度模长的指数衰减率与零阶平移速率的指数衰减率之比为 m*r^3/(2*I_2*h)。", S, "两段负指数中 t 的正系数分别为 pi*eta*r^4/(4*I_2) 和 pi*eta*r*h/(2*m)，相除得到 m*r^3/(2*I_2*h)。", [("q5_angular_decay", "omega(t) = omega_0*exp(-pi*eta*r^4*t/(4*I_2))"), ("q5_velocity", "v_vec(t) = v_0*exp(-pi*eta*r*h*t/(2*m))*x_hat")], ["q5_angular_decay", "q5_velocity"])], "两类衰减率相除形成单个关系声明", "比较扰动角速度模长与零阶平移速率的指数衰减率之比。")
case("Q5", 6, "mixed", ["q5_stability", "q5_model", "q5_velocity"], [claim("该模型下盘面朝向趋于稳定。", S, "稳定性结论由上下文直接给出。", [("q5_stability", "因此盘面朝向趋于稳定")]), claim("零阶速度指数中的分母是 m，即 v_vec(t) = v_0*exp(-pi*eta*r*h*t/m)*x_hat。", C, "来源分母为 2*m，回答漏去 2。", [("q5_velocity", "v_vec(t) = v_0*exp(-pi*eta*r*h*t/(2*m))*x_hat")]), claim("飞盘在 20 m/s 时的阻力系数为 0.12。", U, "未给出实际速度下的阻力系数测量值。")], "稳定性、衰减系数细错、实验参数无依据")

case("Q6", 1, "supported", ["q6_bare"], [claim("无限长裸弦的波速为 sqrt(T/mu)。", S, "波速与来源一致。", [("q6_bare", "v = sqrt(T/mu)")])], "正确裸弦波速")
case("Q6", 2, "subtle_distortion", ["q6_bare"], [claim("无限长裸弦的波速为 sqrt(mu/T)。", C, "来源根号内是 T/mu，回答倒置。", [("q6_bare", "v = sqrt(T/mu)")])], "根号分子分母颠倒")
case("Q6", 3, "subtle_distortion", ["q6_definitions", "q6_dispersion"], [claim("弦球链的色散关系为 cos(kappa*a) = cos(phi)+q*sin(phi)。", C, "来源为减 q*sin(phi)。", [("q6_dispersion", "cos(kappa*a) = cos(phi)-q*sin(phi)")])], "色散关系符号反转")
case("Q6", 4, "extrinsic_hallucination", ["q6_definitions", "q6_dispersion"], [claim("本题采用的原子间距数值为 a = 0.30 nm。", U, "间距只以符号 a 定义，没有数值。")], "擅自指定晶格尺度")
case("Q6", 5, "multi_passage_synthesis", ["q6_definitions", "q6_dispersion"], [claim("代入无量纲定义后，cos(kappa*a) = cos(omega*a*sqrt(mu/T))-(m*omega/(2*sqrt(T*mu)))*sin(omega*a*sqrt(mu/T))。", S, "将第一段的 phi 和 q 代入第二段色散关系即可得到。", [("q6_definitions", "phi = omega*a*sqrt(mu/T)，q = m*omega/(2*sqrt(T*mu))"), ("q6_dispersion", "cos(kappa*a) = cos(phi)-q*sin(phi)")], ["q6_definitions", "q6_dispersion"])], "无量纲量定义跨段代入", "将 phi、q 的定义代入色散关系。")
case("Q6", 6, "mixed", ["q6_polynomial", "q6_modes", "q6_definitions"], [claim("传递矩阵特征值满足 lambda^2-2*(cos(phi)-q*sin(phi))*lambda+1 = 0。", S, "与来源特征方程相同。", [("q6_polynomial", "lambda^2-2*(cos(phi)-q*sin(phi))*lambda+1 = 0")]), claim("题设分类中，abs(lambda) != 1 的模式被称为传播模。", C, "来源将该类定义为局域模。", [("q6_modes", "特征值模长 abs(lambda) != 1 时对应局域模")]), claim("链中所有原子都带有相同的正电荷。", U, "仅指定原子质量，没有电荷信息。")], "正确方程、模式条件交换、电荷无依据")

case("Q7", 1, "supported", ["q7_null", "q7_metric"], [claim("在所定义的类光坐标中，度规为 ds^2 = du*dv。", S, "来源给出相同的度规。", [("q7_metric", "ds^2 = du*dv")])], "正确类光度规")
case("Q7", 2, "subtle_distortion", ["q7_t"], [claim("恒固有加速度观者的时间坐标为 t(tau) = (c/g)*cosh(g*tau/c)。", C, "时间坐标应含 sinh，而非 cosh。", [("q7_t", "t(tau) = (c/g)*sinh(g*tau/c)")])], "sinh/cosh 互换")
case("Q7", 3, "subtle_distortion", ["q7_rindler"], [claim("加速坐标度规为 ds^2 = exp(-2*g*xi/c^2)*((c*dtau)^2-dxi^2)。", C, "来源指数为正的 2*g*xi/c^2。", [("q7_rindler", "ds^2 = exp(2*g*xi/c^2)*((c*dtau)^2-dxi^2)")])], "共形因子指数符号反转")
case("Q7", 4, "extrinsic_hallucination", ["q7_t", "q7_x", "q7_rindler"], [claim("本题观者的固有加速度数值为 9.81 m/s^2。", U, "这里的 g 是符号参数，并未给定数值；其他题的数据不可移用。")], "将日常重力加速度外推到本题符号 g")
case("Q7", 5, "multi_passage_synthesis", ["q7_t", "q7_x"], [claim("联合时间和空间轨迹，观者世界线满足 x(tau)^2-c^2*t(tau)^2 = c^4/g^2。", S, "由两段公式和 cosh(z)^2-sinh(z)^2=1 化简得到。", [("q7_t", "t(tau) = (c/g)*sinh(g*tau/c)"), ("q7_x", "x(tau) = (c^2/g)*cosh(g*tau/c)")], ["q7_t", "q7_x"])], "两个坐标公式合成世界线不变量", "将同一观者的 t(tau)、x(tau) 合成不变量。")
case("Q7", 6, "mixed", ["q7_x", "q7_ratio", "q7_null"], [claim("该观者的空间轨迹为 x(tau) = (c^2/g)*cosh(g*tau/c)。", S, "与空间轨迹公式相同。", [("q7_x", "x(tau) = (c^2/g)*cosh(g*tau/c)")]), claim("题目空间频率约定下，系数模方比为 abs(alpha)^2/abs(beta)^2 = exp(-2*pi*Omega*c^2/g)。", C, "来源的指数为正号。", [("q7_ratio", "abs(alpha)^2/abs(beta)^2 = exp(2*pi*Omega*c^2/g)")]), claim("本题加速观者由电子构成。", U, "来源没有指定观者的物质组成。")], "正确轨迹、指数符号错、观者组成无依据")

case("EDGE", 1, "empty_context", [], [claim("裸弦波速为 sqrt(T/mu)。", U, "没有任何来源上下文，真实世界中是否正确不改变无依据判断。")], "真实但无上下文的事实", "没有上下文时验证一个物理事实。")
case("EDGE", 2, "empty_answer", ["q1_focal"], [], "空字符串回答", answer="")
case("EDGE", 3, "no_factual_claims", ["q3_setup"], [], "纯感谢用语，无可检验事实", answer="谢谢你的帮助！")
case("EDGE", 4, "withheld_evidence", ["q1_setup"], [claim("这份参考答案列出的球面例题出射角数值为 0.081 rad。", U, "只给出双透镜符号定义，没有球面题干或参考结果，不能验证参考答案写了什么。")], "选择性移除证据；答案在完整文档存在但输入中缺失", "仅凭给定片段能否确认参考答案列出的球面出射角？")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-root", type=Path, default=PDF_ROOT)
    args = parser.parse_args()
    documents = [document(*spec, args.pdf_root) for spec in DOCUMENT_SPECS]
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "sources.json", {"version": "1.1", "documents": documents, "passages": list(PASSAGES.values())})
    write_json(OUT / "problem_catalog.json", {
        "scope": "7 道大题的代表性文本/公式片段；不含完整图像题及完整推导。",
        "problems": [{
            "problem_id": pid, "topic": topic, "split": split,
            "exam_pages": exam_pages, "solution_pages": solution_pages,
            "question_summary": summary,
            "passage_ids": [key for key in PASSAGES if key.startswith(pid.lower() + "_")],
        } for pid, topic, split, exam_pages, solution_pages, summary in CATALOG],
    })
    (OUT / "cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in CASES), encoding="utf-8")
    print(f"Wrote {len(CASES)} cases, {sum(len(c['expected']['claims']) for c in CASES)} claims and {len(PASSAGES)} passages.")


if __name__ == "__main__":
    main()
