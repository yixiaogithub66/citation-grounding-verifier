# 正式确认集：独立AI审阅记录

完成状态：12例、42条声明已由另一个只读AI审阅角色逐项检查，受影响8条修订后再次核对，无剩余阻断问题。未读任何被测模型输出，未调用被测模型API；并非作者逐条终审或专家认证。

## 冻结前修订

1. `scope_distractor-q2-c1` 从CONTRADICTED改为UNSUPPORTED，清空全部证据字段：来源将公式用于悬链线并给出自由悬挂另一式，没有排他性，不能把额外归属直接判反驳。
2. `reformulation_calculation-q2-c1` 的推导改为将整个M*v^2代入，避免无必要地除以M；标签及必需证据不变。
3. 六条claim明确一般恒等式、任意适用参数或来源书写形式，区分一般式不同和某个参数点巧合相等。没有新增context物理参数。

修订均发生在模型推理前，仅基于源片段和标注规则；原始初稿保留在 `review-history/draft-before-review.jsonl`，逐字段差异见 `ai_review.json`。最终标签计数S15/C13/U14。

## 逐case结论

| Case | 独立审阅结论 |
| --- | --- |
| `cphos28-confirmation-density-q2` | 5条粒度正确；两处错误公式已明确任意适用角度或来源符号写法，避免退化参数歧义。 |
| `cphos28-confirmation-density-q6` | 5条粒度正确；错误A式已明确对任意不同特征根的一般表达式，保留不同特征根条件。 |
| `cphos28-confirmation-density-q7` | 5条粒度正确；gamma倒数错误明确按一般微分恒等式判断。 |
| `cphos28-confirmation-scope_distractor-q2` | 第一条来源归属并无排他性，冻结前从C改为U并清空证据；其余S/U正确。 |
| `cphos28-confirmation-scope_distractor-q6` | U/S/C正确；未把内部连续当作内部必非零，未将固定端约束扩展到内部。 |
| `cphos28-confirmation-scope_distractor-q7` | S/C/U正确；一般线元错误明确量化所有适用g与坐标，没有默补特定正参数。 |
| `cphos28-confirmation-mixed_truth_compound-q2` | C/S/U正确；数值说明与公式冲突，拆分正确。 |
| `cphos28-confirmation-mixed_truth_compound-q6` | C/S/U正确；核对来源给出的特征向量写法，避免整体缩放歧义。 |
| `cphos28-confirmation-mixed_truth_compound-q7` | C/S/U正确；空间反变换前因子说明与公式不一致，拆分正确。 |
| `cphos28-confirmation-reformulation_calculation-q2` | S/C/U正确；用M*v^2整体代入，消除不必要的M非零假设，两段证据必需。 |
| `cphos28-confirmation-reformulation_calculation-q6` | S/C/U正确；求差错误明确按一般恒等式判断，两条递推均是必要前提。 |
| `cphos28-confirmation-reformulation_calculation-q7` | S/C/U正确；乘法结果需要两段，恒等值1的反证只需gamma段，没有夸大多源必要性。 |

## 全部声明

下表反映最终输入及gold，原文引用、可接受段集合与必需段索引保存于cases.jsonl。

### cphos28-confirmation-density-q2

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 悬链线段的切线斜率满足 tan(theta) = dy/dx。 | SUPPORTED | 定义直接给出tan(theta)=dy/dx。 | [] |
| 悬链线段在任意适用角度下的张力竖直分量恒为 T_0，即 T*sin(theta) = T_0。 | CONTRADICTED | 来源保持的是T*cos(theta)，回答改成竖直分量T*sin(theta)；文字与其错误公式相互一致，按同句冗余规则保留一条。 | [] |
| 参考解答中悬链线积分公式的符号写法为 1/cos(theta)+C_0 = (lambda*g/T_0)*y。 | CONTRADICTED | 同一积分关系中来源为减C_0，回答写加C_0，作为一般参数关系不等价。 | [] |
| 悬链线弧长微元满足 ds = sqrt(dx^2+dy^2)。 | SUPPORTED | 弧长定义完整一致。 | [] |
| 这根绳的总质量为 2 kg。 | UNSUPPORTED | 输入没有绳总质量数值，也没有足以确定2 kg的数值参数。 | [] |

### cphos28-confirmation-density-q6

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 在 lambda_1!=lambda_2 时，B 的分子指数为 N-1，即 B = (lambda_1^(N-1)-lambda_2^(N-1))/(lambda_1-lambda_2)。 | SUPPORTED | 非零分母条件由回答显式给出；分子N-1的局部描述被完整公式蕴含，可以同句合并。 | [] |
| 对任意 lambda_1!=lambda_2，矩阵幂系数的一般表达式为 A = (lambda_1^(N+1)-lambda_2^(N+1))/(lambda_1-lambda_2)。 | CONTRADICTED | 在回答已限定的不同特征根域内，来源分子幂是N，不是N+1；一般公式不同。 | [] |
| 参考解答给出的特征根之和为 lambda_1+lambda_2 = exp(i*phi)*(1+i*q)+exp(-i*phi)*(1-i*q)。 | SUPPORTED | 两复指数项和括号符号与来源一致。 | [] |
| 本例 N 的数值为 100。 | UNSUPPORTED | N仅作为符号出现，未给100这个数值。 | [] |
| 本例所有原子均由硅材料构成。 | UNSUPPORTED | 矩阵幂和根关系不指定材料。 | [] |

### cphos28-confirmation-density-q7

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 恒固有加速度观者的速度为 v = c*tanh(g*tau/c)。 | SUPPORTED | 速度公式直接匹配。 | [] |
| 该观者的洛伦兹因子为 gamma = sinh(g*tau/c)。 | CONTRADICTED | 来源使用cosh而不是sinh。 | [] |
| 惯性时间对固有时的一般微分恒等式为 dt/dtau = 1/gamma。 | CONTRADICTED | 来源给dt/dtau=gamma，回答将其倒置。 | [] |
| 此次速度测量的相对误差为 1%。 | UNSUPPORTED | 仅有理论关系，没有测量或误差数据。 | [] |
| 固有加速度的定义式为 g = dv_prime/dtau。 | SUPPORTED | 带撇速度对固有时的导数定义一致。 | [] |

### cphos28-confirmation-scope_distractor-q2

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 在参考解答中，T*cos(theta) = T_0 被列为自由悬挂部分的张力关系。 | UNSUPPORTED | 第0段证明该式用于悬链线部分，第1段给自由悬挂部分另一关系，但二者并未排他地断言该式不可能也被列在自由悬挂部分；该额外归属缺少支持，不能把未说明当直接矛盾。 | [] |
| 参考解答对自由悬挂部分给出 T_2 = m*g+lambda*g*l。 | SUPPORTED | 自由悬挂部分的范围及完整自重项均保留。 | [] |
| 自由悬挂部分的绳直径为 2 mm。 | UNSUPPORTED | 两种张力关系都没有绳直径数据。 | [] |

### cphos28-confirmation-scope_distractor-q6

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 任意内部连接点都具有额外的零位移约束 u_j(a) = 0。 | UNSUPPORTED | 内部只给位移连续，零位移条件明确施加于两端固定边界；不能把两端约束推广到任意内部点。来源没有直接断言内部位移一定非零，故按证据不足处理。 | [] |
| 有限长链右侧固定边界满足 u_N((1-tau)*a) = 0。 | SUPPORTED | 右侧边界的局部坐标和零值都正确。 | [] |
| 参考解答写出的左侧固定边界条件是 u_0(0) = 1。 | CONTRADICTED | 同一个左侧固定端来源写0，回答写1。 | [] |

### cphos28-confirmation-scope_distractor-q7

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 在 xi=0 处，共形因子的平方满足 Omega^2(c*tau,0) = 1。 | SUPPORTED | 保留xi=0条件后直接得到因子为1。 | [] |
| 不论 g 和加速类光坐标取何适用值，线元恒等式均为 ds^2 = du_tilde*dv_tilde。 | CONTRADICTED | 一般坐标线元含exp(-g*(u_tilde-v_tilde)/c^2)，不是任意坐标下都恒等于1；回答把特定位置的归一化推广为一般恒等式。 | [] |
| 这一坐标系统使用的探测器质量为 1 kg。 | UNSUPPORTED | 度规关系没有给探测器质量。 | [] |

### cphos28-confirmation-mixed_truth_compound-q2

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 参考解答列出的自由悬挂绳长系数为 2.4932905 | CONTRADICTED | 来源系数为2.3932905，文字部分改成2.4932905。 | [] |
| l = 2.3932905*R。 | SUPPORTED | 公式部分保留来源数值；与前面文字冲突，不能同句合并。 | [] |
| 该绳的热膨胀系数为 1.2e-5/K。 | UNSUPPORTED | 没有材料热膨胀系数信息。 | [] |

### cphos28-confirmation-mixed_truth_compound-q6

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 参考解答给出的特征向量 p_1 的第一分量是 exp(-i*phi)*i*q | CONTRADICTED | 参考写法的首分量有前置负号，文字漏掉该符号；这里核对来源给出的写法，不声称特征向量的整体缩放唯一。 | [] |
| p_1 = [-exp(-i*phi)*i*q, exp(i*phi)*(1+i*q)-lambda_1]^T。 | SUPPORTED | 取来源(1,2)中的第一组下标后，列向量两分量及符号一致。 | [] |
| 这条链在实验室温度 300 K 下被测量。 | UNSUPPORTED | 没有实验温度或实际测量条件。 | [] |

### cphos28-confirmation-mixed_truth_compound-q7

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 加速空间坐标 xi 的对数前因子为 c^2/g | CONTRADICTED | 来源前因子为c^2/(2*g)，文字省略分母2。 | [] |
| xi = (c^2/(2*g))*ln((g^2/c^4)*(x^2-c^2*t^2))。 | SUPPORTED | 公式部分保留前因子与对数内全部项；文字与公式不一致应拆开。 | [] |
| 这里 g 的测量不确定度为 0.01 m/s^2。 | UNSUPPORTED | 来源只有符号坐标关系，没有g的测量不确定度。 | [] |

### cphos28-confirmation-reformulation_calculation-q2

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 联立能量式与支持力式消去 v^2，得到 N = M*g*(3*cos(phi)-2)-M*v_0^2/R。 | SUPPORTED | 能量式乘2得M*v^2=M*v_0^2+2*M*g*R*(1-cos(phi))，将整个M*v^2代入支持力式得到结果，不需要另加M非零假设；两段均必需。 | [0, 1] |
| 同一消元中 v_0^2 项的系数为 +M/R，即 N = M*g*(3*cos(phi)-2)+M*v_0^2/R。 | CONTRADICTED | 同样代入得到v_0^2项系数为-M/R，回答的一致文字与公式均写成正号。 | [0, 1] |
| 圆柱材料的杨氏模量为 70 GPa。 | UNSUPPORTED | 运动关系不含材料弹性模量。 | [] |

### cphos28-confirmation-reformulation_calculation-q6

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 两条振幅递推相加后，A_(j+1)+B_(j+1) = A_j*exp(i*k*a)+B_j*exp(-i*k*a)。 | SUPPORTED | 两式校正项大小相同、符号相反，相加恰好相消；两条递推都是必要前提。 | [0, 1] |
| 两条振幅递推相减恒等得到 A_(j+1)-B_(j+1) = A_j*exp(i*k*a)-B_j*exp(-i*k*a)。 | CONTRADICTED | 相减时校正项相加，尚有(i*m*k/mu)*(A_j*exp(i*k*a)+B_j*exp(-i*k*a))，回答的一般式漏项。 | [0, 1] |
| 该链传递一个单元的实测时间为 0.01 s。 | UNSUPPORTED | 递推公式没有给单元传递的实测时间或数值参数。 | [] |

### cphos28-confirmation-reformulation_calculation-q7

| Claim | 标签 | AI理由 | 必需段 |
| --- | --- | --- | --- |
| 由速度和洛伦兹因子公式相乘可得 gamma*v = c*sinh(g*tau/c)。 | SUPPORTED | gamma*v=c*cosh(z)*tanh(z)=c*sinh(z)，z=g*tau/c；两段分别给两个因子。 | [0, 1] |
| 由这两式还可得 gamma^2*(1-v^2/c^2) = 0。 | CONTRADICTED | 第1段gamma=1/sqrt(1-v^2/c^2)已直接推出左侧为1而非0；其自身足以反驳，不伪造多源必要性。 | [] |
| 该观者时钟的漂移率实测为每天 0.1 ns。 | UNSUPPORTED | 理论速度和gamma关系没有实际时钟漂移测量。 | [] |

## 核对方式与边界

独立角色视觉核对了解答PDF第4、5、6、18、19、20、22、23页，未发现所选数字、符号、下标或页码转录错误。所有answer_quote均为答案原文子串；引用索引与quote逐字匹配。另作三类代数结果的确定性数值交叉检查。

独立AI角色指分工后的只读复核，不意味着误差统计独立。来源材料、题族和部分片段在案例间相关；评测结论应保持这一范围。
