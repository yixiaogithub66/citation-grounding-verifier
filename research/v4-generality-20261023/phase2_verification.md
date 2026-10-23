# Phase 2：证据核查、证据充分性与复核机制的来源档案

日期：2026-10-23。范围：TabbyML optimized-v4.0 通用优化的文献调查子任务。本文只登记证据与迁移边界，不构成最终优化方案、代码变更、金标修订或作者裁定。

已核对项目的 AGENTS.md、docs/V4_DESIGN.md、docs/V4_DECISIONS.md；应用 deep-research 的来源验证、阅读范围和局限标注规则。项目要求统一推理契约、禁止 benchmark 特调，M1 独占原子粒度，不恢复运行时语义合并；隐含断言仅允许由引用前提作明确一步推导。论文中的多跳任务不能自动扩大这一契约。

## 检索与纳入范围

采用定向叙述性证据搜集，不声称系统综述或穷尽检索。纳入可核实的作者论文，优先 ACL Anthology、ICLR 正式论文与 arXiv 全文；未把搜索摘要、博客转述或排行榜作为方法证据。共纳入 9 篇，其中 8 篇读取了正文方法或实验相关章节，至少 RefChecker、MiniCheck、RT4CHART、FactCG 读到方法和结果及其局限边界；QAFactEval 仅作摘要级补充。全文相关章节阅读不等于逐页阅读所有附录。

实际检索式（引号中的文本是检索输入）：

1. Q1: “RefChecker Reference-based Fine-grained Hallucination Checker EMNLP 2024 paper”
2. Q2: “MiniCheck Efficient Fact-Checking of LLMs on Grounding Documents 2024 EMNLP paper”
3. Q3: “AlignScore Evaluating Factual Consistency Unified Alignment Function ACL 2023”
4. Q4: “Chain-of-Verification Reduces Hallucination in Large Language Models ACL 2024 paper”
5. Q5: “Large Language Models Cannot Self-Correct Reasoning Yet ICLR 2024 paper”
6. Q6: “2025 sufficient context retrieval augmented generation fact checking evidence sufficiency paper”
7. Q7: “TRUE Re-evaluating Factual Consistency Evaluation ACL 2022”
8. Q8: “QAFactEval Improved QA-Based Factual Consistency Evaluation ACL 2022”
9. Q9: “2025 FactCG complex claims graph fact checking EMNLP”
10. Q10: 主代理提供 arXiv:2603.27752，定向打开 v1 方法、实验与局限。

Q7 找到 TRUE，未进一步精读，未计入九篇核心档案。Sufficient Context 的 OpenReview PDF 被浏览器验证页阻断，转读作者 arXiv v3（2025-04-23），并用 Google Research/ICLR 页面核实发表信息。搜索结果中的“几年前”等相对时间不用于年代判定，以论文正式出版年和版本日期为准。

## 逐篇证据记录

### V01 — RefChecker / Knowledge-Centric Hallucination Detection

Hu et al., EMNLP 2024。正式发表题名为 **Knowledge-Centric Hallucination Detection**；RefChecker 是方法名及早期预印本题名，不是两篇独立证据。[正式论文](https://aclanthology.org/2024.emnlp-main.395/)

阅读：§3–6、Limitations，PDF pp.4–9；另核对首页作者、实验表5/6。

证据：将回答抽取为 claim-triplets，再依据 reference 判 Entailment / Contradiction / Neutral；Neutral 对应证据不足。§6.1 的粒度比较以回答级三类 macro-F1 聚合，§6.3 的显著数字则是相关系数增益，两者不可混称 claim 准确率。作者报告三元组在其任务设置中优于其他粒度。

局限：作者明确承认三元组难保留时间及复杂语义、偏局部上下文；模型内在知识可把 Neutral 误判为 E/C；源归因仍初步。[author-acknowledged, Limitations a/c/d, p.9] 本项目不能据此把自然语言原子命题强制改成三元组，或将其相关系数当作通用三标签可靠性保证。[reader-inferred，迁移判断未验证]

### V02 — MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents

Tang, Laban & Durrett, EMNLP 2024。[正式论文](https://aclanthology.org/2024.emnlp-main.499/)

阅读：§2–7、Limitations、附录A.2/A.3/B.1–B.2相关表；重点 pp.2–10、15–17。

证据：C2D/D2C 合成数据针对多事实核查和跨句组合；§3.3 把 ANLI contradiction 与 neutral 合并为 unsupported。主表固定 0.5 阈值，十集合平均 BAcc 为 FT5 74.7、GPT-4 75.3；“400倍低成本”绑定当时模型、13K测试及GPU价格口径。§7.1 分解并未一致提升句级判定：FT5 下降1.4点；这不推翻本项目输出原子断言的契约。

局限：作者承认其基准未要求显著远距或跨文档证据组合，且模型训练仅英文、不提供可靠解释。[author-acknowledged, Limitations, pp.9–10] 二分类分数不能推出 C/U，低支持度也不是矛盾证明。[reader-inferred，任务映射限制]

### V03 — AlignScore: Evaluating Factual Consistency with A Unified Alignment Function

Zha, Yang, Li & Hu, ACL 2023。[正式论文](https://aclanthology.org/2023.acl-long.634/)

阅读：§3、§4.1–4.2 与主结果表开头，PDF pp.2–6；未完整审阅余下结果/附录。

证据：用七类任务训练统一对齐模型，包含三类、二类和回归头；最终 AlignScore 使用三类头的 ALIGNED 概率。其聚合为每个回答句取最高上下文块分数，再对回答句求平均；上下文块约350 tokens。§3.2 明确说明平均是为了避免单个不一致句支配全文分数。

局限：max-over-chunks 无法独自合成跨块前提，mean-over-sentences 的目标也不同于“任一 C/U 即标记回答”；这是从聚合定义推出的迁移限制，非作者实验证明其必然失效。[reader-inferred, §3.2 Eq.3] 不能称 AlignScore “本身只有二分类模型”，也不能把最终标量直接当 S/C/U。[reader-inferred]

### V04 — QAFactEval: Improved QA-Based Factual Consistency Evaluation for Summarization

Fabbri, Wu, Liu & Xiong, NAACL 2022。[正式论文及摘要](https://aclanthology.org/2022.naacl-main.187/)

阅读：正式页面元数据与摘要，abstract_only。

摘要报告：QA评价中的问题生成和可回答性分类会影响效果，QA与蕴含信号可互补。此条只支持存在替代验证信号的背景，不支撑将其组件直接移植到 v4，也不引用摘要性能数字作本项目收益预估。方法弱点：**not assessed (read scope: abstract_only)**。没有从摘要推断其采样偏差、错误类型或统计缺陷。

### V05 — Chain-of-Verification Reduces Hallucination in Large Language Models

Dhuliawala et al., Findings ACL 2024。[正式论文](https://aclanthology.org/2024.findings-acl.212/)

阅读：§3、§4.1–4.2、表1–2，PDF pp.2–6；未完整阅读后续结果与所有附录。

证据：CoVe 先写答案、生成核查问题、独立回答核查问题、再修订答案。factored 版本让回答核查问题的调用不看原始草稿，以减少直接复述；方法没有使用外部检索工具。表2的闭卷MultiSpanQA中，Llama65B few-shot F1 0.39，joint 0.46，factored 0.48。

局限：本实验是生成修订与闭卷事实问答，原文用任务对应 few-shot 示例；不能把它当固定context三标签核查的直接证据。[reader-inferred, §3.3、§4.1–4.2] 调用分开不等于错误统计独立；本项目也不能复制 benchmark 对应演示或用模型重新回答代替原文证据。[reader-inferred]

### V06 — Large Language Models Cannot Self-Correct Reasoning Yet

Huang et al., ICLR 2024。[正式论文](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8b4add8b0aa8749d80a34ca5d941c355-Abstract-Conference.html)

阅读：§2–5、§6开头，PDF pp.2–8；表2–8。

证据：研究明确限于无外部反馈的 intrinsic self-correction。去掉利用金标停止修改的 oracle 后，测试模型在所测推理任务上未获净增益，出现正确答案改错；也比较了等响应数的 self-consistency 和 debate。§5发现把任务要求提前写入初始提示可消除一些“自纠错收益”。

局限：作者承认 HotpotQA 样本过小，未做细粒度转移统计。[author-acknowledged, §3.3脚注1, p.5] 测试的是2023模型与特定推理任务，不能推出2026模型永远无法纠错，也不能推出有原始context的定向证据复核无效。[reader-inferred] 与CoVe表面结论不同，不是同一设置的直接冲突。

### V07 — Sufficient Context: A New Lens on Retrieval Augmented Generation Systems

Joren et al., ICLR 2025；读取 arXiv v3。[作者全文](https://arxiv.org/html/2411.06037v3)；[发表信息](https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/)

阅读：§3–6，含表1–2和选择性生成结果段。

证据：sufficiency 判断“是否存在可由context回答该问题的答案”，而非“给定候选答案是否受支持”；判定不需金标答案。Gemini1.5Pro 1-shot autorater 在115个人工标签样本上准确率93%。选择性生成同时使用充分性与自报置信度，报告 accuracy–coverage 曲线，部分设置没有额外收益。

局限：作者限于QA，未充分探索检索策略变化。[author-acknowledged, §6 Limitations] 其正确性评价允许参数知识补足回答；本项目要求context-grounded，因此“context不足但答对”不能转成SUPPORTED。[reader-inferred, §3.1、§4.3] 115例autorater准确率不是开放域充分性判断的保证。[reader-inferred]

### V08 — FactCG: Enhancing Fact Checkers with Graph-Based Multi-Hop Data

Lei et al., NAACL 2025。[正式论文](https://aclanthology.org/2025.naacl-long.258/)

阅读：§3–7.3，PDF pp.3–8；表1–5及CoRe定义/结果说明。

证据：CG2C由上下文图构造多前提训练样本，破坏证据关系形成负例；CoRe同时要求原样本支持、删除必要证据后不支持。其推理仍是块分数取max及grounded/ungrounded二分类。主表DBT平均BAcc77.2，高于同表GPT-4o75.9，但§6.2明确逐数据集调阈值，统一校准留待未来。

局限：作者说明每个实验只运行一次；CoRe分析仍有约一半被归为 disconnected reasoning。[author-acknowledged, §6.3、§7.3] 其主表不能直接证明统一阈值收益；图抽取与文档改写仍依赖LLM，按构造贴标签不等于语义真值有确定性保证。[reader-inferred, §5.1–5.2] 不移植逐benchmark阈值或运行时图推理。

### V09 — Retromorphic Testing with Hierarchical Verification for Hallucination Detection in RAG

Yu, Zhang, Lin, Briand & Muñoz，arXiv v1，2026-03-29，**预印本，未核实同行评审接收**。[全文](https://arxiv.org/html/2603.27752v1)

阅读：§2–4.6、§5；工具展开额外显示§4.7前三个案例，见曝光记录。

证据：RT4CHART已有原子claim、E/C/Nic、回答span回映、context证据与局部—全局核查；全局阶段将局部结论只作为搜索提示并重抽证据。表6全局复核在一集合F1 +0.036、另一集合0.000；表7同时移除了分解和局部核查，不能单独识别局部核查的因果贡献。

局限：作者承认模态强弱、冲突/冗余context及英文RAGTruth派生样本范围限制。[author-acknowledged, §5.1–5.2] 两个集合源自同一数据家族；不能据此宣称广泛跨域泛化。[reader-inferred] 方法是v4的直接近邻，不能把“三标签+分解+证据+复核”重命名后视为新颖贡献。[reader-inferred]

## 跨来源一致点与不宜直接移植点

| 问题 | 可确认的证据 | 不能直接推出 |
|---|---|---|
| 支持、矛盾、缺证 | RefChecker、RT4CHART明确三标签；MiniCheck/FactCG合并C与U。[V01,V02,V08,V09] | localNLI的低支持度就是C，或二分类准确率等于S/C/U准确率 |
| 多前提 | MiniCheck训练跨句组合；FactCG检查必要证据删除；RT4CHART承认局部Nic并不等于全局Nic。[V02,V08,V09] | 某块得分最高便覆盖所有前提，或用复杂推理替代v4明确一步推导契约 |
| 复核收益 | CoVe在闭卷生成中有效；Huang等发现无外部反馈可改错；RT4CHART全局复核收益不一致。[V05,V06,V09] | 更多轮数必定改善，或分角色/分调用意味着独立错误 |
| 输出粒度 | RefChecker支持细粒度；MiniCheck句级任务中分解收益不一致。[V01,V02] | 原子输出契约可以取消，或更细的字符串一定是更好的原子语义 |
| 泛化口径 | MiniCheck主表统一阈值；FactCG主表按数据集调阈值。[V02,V08] | 不同协议的分数可直接排名，或某个benchmark增益就是通用优化 |
| 充分性与真值 | Sufficient Context区分“存在答案”与给定答案蕴含；RT4CHART固定context为证据。[V07,V09] | 可回答问题意味着候选答案被支持，或世界知识可覆盖给定来源 |
| 证据可追溯 | RT4CHART要求证据回映，RefChecker承认归因不足。[V01,V09] | 精确引用/合法索引本身证明语义蕴含或矛盾 |

以上是来源间可比性判断，不是对 v4 实施收益的实验证明。没有运行模型API、代码测试或任何benchmark；没有修改推理代码、Prompt、配置、金标和现有评测结果。

## 阅读与审查边界

每篇的 empirical criteria 覆盖见JSON中的 method_weakness_checklist，固定检查维度为：Research hypothesis clarity、Variable operational definitions、Internal validity、External validity、Statistical reporting completeness、Conclusion conservatism。checked: found 表示在指定范围内发现了对应局限；not checked 表示未对该维度完成审核，不能解释为没有问题。本次只做与迁移有关的有限方法检查，不构成正式同行评审。

未复现任何论文结果，未重新核查所有基准标签，未审计发布模型权重/训练污染；未读取 QAFactEval 正文，因而不对其方法作批评。2026文献的覆盖是定向近期扫描，不代表该年全部成果。来源报告的成本、版本与性能只属于原论文设置。

本文件由AI辅助检索、阅读与归纳；来源和推理判断已分开标注，人工审核细节按任务要求暂缓。

## 来源曝光记录

仅访问论文、出版元数据和作者页面，没有打开/下载RT4CHART标注数据或样本文件。打开其§4实验时，浏览工具自动扩展到§4.7，显示了RAGTruth示例ID **879、587、25** 的原文内容；已即时通知主代理。本记录仅用于后续排除未见评测来源，绝不能进入推理Prompt或规则。其原始source-group映射尚未核实，不在此擅自修改项目正式曝光清单或选择数据。

其他论文含公开示例亦属于本次文献阅读曝光；本报告不把任何论文中的benchmark样例复制成推理演示。
