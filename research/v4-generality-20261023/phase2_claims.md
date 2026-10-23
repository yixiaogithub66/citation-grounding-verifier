# Phase 2：原子事实提取、去语境化与拆分失真证据

日期：2026-10-23（Asia/Shanghai）。本文件是为 TabbyML v4 通用优化准备的定向证据扫描，不是系统综述，也不是实现方案、创新性证明或金标裁定。只采用论文作者/出版方的一手材料。检索结果中的相对发布日期不作为年份依据；最终记录以会议论文及 arXiv 版本信息为准。

本轮核对了 9 篇论文；重点阅读 Claimify、Decomposition Dilemmas、DnDScore 的方法、结果和局限相关全文章节，其他论文的精确已读范围见下表与配套 JSON。没有调用模型 API，也没有修改推理、Prompt、配置、测试标签。

## 项目约束与研究问题

已读 `AGENTS.md`、`grounding/prompts_v4.py` 和 `reports/V4_DEVELOPMENT_AUDIT.md`。当前 M1 要同时识别事实、拆分原子命题、补足明确指代并以原文 span 覆盖文字；同句冗余由统一语义 Prompt 处理，不能恢复运行时合并。开发报告记录 71 个降级块、涉及 70/180 例；句子骨架覆盖文字，但未保证原子粒度。

因此文献要回答的是：哪些机制能帮助区分“遗漏、改义、指代不足、过度拆分与执行失败”？哪些论文结果只是在改变分数计算方式？不能用它们授权针对 benchmark、模型身份或个别测试案例的规则。

## 已核验文献与阅读范围

作者全名、DOI、论文 URL、方法/结果/局限、检索索引和核验依据均在 [phase2_claims_sources.json](phase2_claims_sources.json)。以下页码指论文印刷页或 PDF 页，不声称读完全部附录。

| ID | 论文与作者 | 出版信息 | 已读范围 |
| --- | --- | --- | --- |
| C01 | [Towards Effective Extraction and Evaluation of Factual Claims](https://aclanthology.org/2025.acl-long.348/) — Dasha Metropolitansky、Jonathan Larson | ACL 2025；DOI 10.18653/v1/2025.acl-long.348 | §2 概念/覆盖/去语境化；§3 全部提取阶段；§4 数据与比较设置；§5.2–5.3、§6 消融、§9 相关局限 |
| C02 | [FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation](https://aclanthology.org/2023.emnlp-main.741/) — Sewon Min 等 9 人 | EMNLP 2023；DOI 10.18653/v1/2023.emnlp-main.741 | §3.1 定义与假设、§4.2、局限、附录 B.2 |
| C03 | [VeriScore: Evaluating the factuality of verifiable claims in long-form text generation](https://aclanthology.org/2024.findings-emnlp.552/) — Yixiao Song、Yekyung Kim、Mohit Iyyer | Findings EMNLP 2024；DOI 10.18653/v1/2024.findings-emnlp.552 | §2.1 提取、§3.1 人工评价、局限；未完整阅读微调实验 |
| C04 | [Long-form factuality in large language models](https://arxiv.org/abs/2403.18802) — Jerry Wei 等 12 人 | NeurIPS 2024；arXiv DOI 10.48550/arXiv.2403.18802 | 正文 §2–4、§8；附录 A.3、C.4–C.8、C.10 开头；72 页中定向阅读 |
| C05 | [Decontextualization: Making Sentences Stand-Alone](https://aclanthology.org/2021.tacl-1.27/) — Eunsol Choi 等 6 人 | TACL 2021, 9:447–461；DOI 10.1162/tacl_a_00377 | §2 定义、§3.4 范围、§5.2 自动评价与表4–5；未完整读下游研究 |
| C06 | [A Closer Look at Claim Decomposition](https://aclanthology.org/2024.starsem-1.13/) — Miriam Wanner、Seth Ebner、Zhengping Jiang、Mark Dredze、Benjamin Van Durme | *SEM 2024；DOI 10.18653/v1/2024.starsem-1.13 | §3 评价、结论与局限、附录表3–6；未逐条读所有示例 Prompt |
| C07 | [Decomposition Dilemmas: Does Claim Decomposition Boost or Burden Fact-Checking Performance?](https://aclanthology.org/2025.naacl-long.320/) — Qisheng Hu、Quanyu Long、Wenya Wang | NAACL 2025；DOI 10.18653/v1/2025.naacl-long.320 | §3.2、§4 与表1–3、§5、§6 的权衡/复杂度实验、§8 局限 |
| C08 | [DnDScore: Decontextualization and Decomposition for Factuality Verification in Long-Form Text Generation](https://aclanthology.org/2025.emnlp-main.1205/) — Miriam Wanner、Benjamin Van Durme、Mark Dredze | EMNLP 2025；DOI 10.18653/v1/2025.emnlp-main.1205 | §3.3–4.2、§5.2–5.3、§6 相关分析、局限、附录 C.3 人工评价及表8–9 |
| C09 | [Harmful Factuality: LLMs Correcting What They Shouldn't](https://aclanthology.org/2026.findings-eacl.46/) — Mingchen Li、Hanzhi Zhang、Heng Fan、Junhua Ding、Yunhe Feng | Findings EACL 2026；DOI 10.18653/v1/2026.findings-eacl.46 | PDF 896–904 页的方法、结果、提示干预与局限；900 页部分提取输出截断，不宣称完整读完 |

FActScore 的作者显示有一处元数据差异：ACL 页面显示 Pang Koh，PDF 首页写 Pang Wei Koh；JSON 采用 PDF 姓名。SAFE 的 DOI 是核验过的 arXiv DOI，未伪称会议 DOI。

## 可以支持联合推导的证据

### 1. 覆盖、忠实性与原子性必须分开测

Claimify 把原文能否蕴涵提取项、元素覆盖、去语境化分别评价。其句子级 macro-F1 为 91.2%，元素级为 83.7%；后者只在自动元素标签与人工句子标签相符的 81% 句子上计算。单句“提取到了内容”无法证明其中每个事实及限定都被保留。[C01，§2.2、§5.2](https://aclanthology.org/2025.acl-long.348.pdf)

DecompScore 改用原句作“证据”，测量提取项是否忠实；这与拿外部证据检验事实真伪是两个问题。它也展示同一批回答仅换拆分器就得到不同的 FActScore，且作者明确提醒分数更大不代表拆分更好。[C06，§3、表4](https://aclanthology.org/2024.starsem-1.13.pdf)

**对 v4 的推论，而非论文实测结果：** exact substring 和字符覆盖只能证明可检查的文字不变量。一个错误改写的命题仍可绑定正确 source_span；一个覆盖整句的骨架也可能漏掉关系或把多个断言绑成一条。因此当前 70 例降级不能仅以“字都覆盖了”视为语义恢复成功，也不能据此认定所有降级项都错。

### 2. 去语境化可以帮助理解，也可以改变被核查对象

Choi 等将去语境化约束为保留真值条件的上下文消解；其数据刻意偏向容易以简单编辑处理的英语 Wikipedia 句子，技术与叙事语篇更难。它支持“补足指代要保义”，不支持“只要读起来独立完整就正确”。[C05，§2、§3.4](https://aclanthology.org/2021.tacl-1.27.pdf)

DnD 在一次调用中保留子命题及其上下文化形式，核查时区分“要判的部分”与“用于理解的部分”。其 100 项人工研究**只选判断发生翻转的 LFQA 样本**：足够信息比例由 54% 升至 88%，DnDScore 人工一致率 76%，上下文化后的 FActScore 为 77%。这些结果支持补足上下文的重要性，不能写成 DnDScore 普遍准确率优于基线。[C08，§3.3–4.2、附录C.3](https://aclanthology.org/2025.emnlp-main.1205.pdf)

**对 v4 的推论：** 若以后考虑保存更多原句/指代上下文，应明确其来自待核查回答，只负责解释目标，不能自动成为支持证据；实体身份、时间、条件也不能在“补上下文”时被悄悄放宽。此处提出的是语义边界，未建议加运行时合并或取消当前原子化责任。

### 3. 先辨识事实内容有依据，静默删掉困难句子没有依据

VeriScore 使用邻句窗口，在提取时处理指代并排除不可核查内容。其 120 段文本、三名评者形成的 360 个偏好中，SAFE 仅被优选 26 次；但比较只用了 SAFE 的提取和改写阶段，不含相关性过滤。偏好不是逐事实完整召回。[C03，§2.1、§3.1](https://aclanthology.org/2024.findings-emnlp.552.pdf)

Claimify 消融中，去掉 selection 阶段造成最大退步；不过只要歧义不能解决，它会排除整句，即使句中还包含清楚的事实。这一设计必须与其单数据集和人工评价限制一起看。[C01，§3.3、§6、§9](https://aclanthology.org/2025.acl-long.348.pdf)

**对 v4 的推论：** 事实性筛选可以作为独立诊断维度，但“难核查”“没有证据”“执行失败”“纯建议”不可混为同一排除状态。文献对 advice 的排除也不能覆盖用户规定的“保留建议中嵌入的事实前提”。长列表前言/标题缺失是通用上下文风险，不应变成领域词表。

### 4. 拆得越细越好并不成立

Decomposition Dilemmas 同时观察到正、负效应：WICE/MiniCheck 的基线 BAcc 80.01、F1 72.32，经 FactScore 拆分后变为 71.11、59.90；FELM/MiniCheck 配 VeriScore 的 F1 由 48.10 升到 67.56，而 FELM/GPT-4o-mini 配 FactScore 的 F1 从 71.56 降到 54.34。论文用信息遗漏、关系丢失、歧义、冗余碎片和改义描述失败。研究限于二分类，且没有直接测量全部拆分噪声与检索噪声。[C07，§4–6、§8](https://aclanthology.org/2025.naacl-long.320.pdf)

**对 v4 的推论：** 通用原子性的依据应是能独立判断的完整断言，同时保留关系和限定；不能以条数最大化或某个数据集分数最大化为目标。该论文也不能给 v4 推出一个通用“最多拆 N 条”阈值，其开放检索和聚合流程不同于当前固定上下文。

### 5. 对宣传性数字要还原分母与评价阶段

FActScore 的“误差小于 2%”指聚合事实精度的估计误差。论文明确展示聚合误差和逐项判决质量可以排序相反；不是“每条事实判断准确率超过 98%”。[C02，§4.2、附录B.2](https://aclanthology.org/2023.emnlp-main.741.pdf)

SAFE 的 16,011 个事实、72% 人工一致率采用人工预拆分事实，从去语境化阶段开始；其附录另测自动拆分，但主要是回答级事实数量相关：Pearson .798、Spearman .846，未作逐命题对齐。因此不能用前一个数字证明 M1，也不能说 SAFE 完全没测拆分。[C04，§4、附录C.4](https://papers.neurips.cc/paper_files/paper/2024/file/937ae0e83eb08d2cb8627fe1def8c751-Paper-Conference.pdf)

**对 v4 的推论：** 完成率、提取忠实性、命题覆盖、逐条判决、回答级举报质量和成本应分别呈现。提取项数量改变后，条件在“成功且被提取项”上的准确率不能单独证明整条流程改进。

### 6. 不纠正待提取文本是独立任务要求

HFH 用实体扰动检验模型是否把上下文改回世界知识。在其 GEP 摘要设置中，限制只用源文本的提示使 GPT-4.1/GPT-4o 的此类纠错率约减半；范围是 WikiEntities 和所测模型，并非所有任务。该研究评价生成行为，不是直接证明某个提取器的召回。[C09，§3、§4.4、§6、§8](https://aclanthology.org/2026.findings-eacl.46.pdf)

**对 v4 的推论：** M1 忠实性检查应能发现常识纠错，尤其在源文本与模型记忆冲突时。但 v4 已明确要求不验证、不纠正；本文不能作为继续加长提示一定有收益的证据。

## 联合推导时仍需保留的未知项

- 这些研究没有证明 v4 在中文、公式、代码/配置、条件句和长列表上会有同样收益。
- 没有一篇直接验证当前 source_span/覆盖修复/降级机制，因此不能把文献结果转写成 70 个降级案例的根因比例。
- 文献的人工偏好、计数相关、模型裁判覆盖分数和条件样本一致率不等于完整人工金标事实召回。
- 这里的表示区分、上下文解释与独立度诊断可参与后续联合构思；是否实现、如何控制调用成本、是否改善未见表现，仍需独立冻结与验证。
- 同一论文的 Prompt 示例、benchmark 内容和标签只作为理解方法的材料，不得复制到 v4 推理路径作为答案提示；本轮未做此类修改。

## 实际检索与筛选记录

执行了 11 个检索 query，完整字符串、域名限制及每篇关联索引见 JSON：

1. Claimify 标题与年份；FActScore 标题；VeriScore 标题；SAFE/LongFact 标题。
2. claim decomposition + factuality evaluation + distortion + DecompScore + 2025/2026。
3. Decontextualization Making Sentences Stand-Alone Choi 2021 TACL。
4. fact decomposition evaluation atomicity faithfulness 2025 2026。
5. VeriScore Song 2024 EMNLP 2024。
6. claim decomposition decontextualization factuality 2026。
7. atomic claim extraction evaluation faithfulness 2026 decomposition。
8. “claim extraction” “2026” “coverage”。

初筛也出现了 AtomEval（2026）、Optimizing Decomposition（ACL 2025）、Claim Extraction for Fact-Checking（2025）、Core、VeriFastScore、FaStFact。它们未完整阅读，不计入本文件的核心证据；具体原因写在 JSON。2026 的 PROBE、GAVEL 等线索已转交其他研究分支。二手摘要站、论坛与 Wikipedia 只出现在搜索结果，未用来支持方法或效果；重复的预印本/会议稿优先采用最终出版稿。

工具边界：可用工具中未发现技能所述 academic-search MCP，因此使用 web 发现与出版方全文核验。HFH 的 web PDF find 出错后，改为直接读取公开出版方 PDF；首次终端编码失败，UTF-8 重试成功。没有把检索覆盖描述为穷尽，也未宣称未纳入的工作不存在。
