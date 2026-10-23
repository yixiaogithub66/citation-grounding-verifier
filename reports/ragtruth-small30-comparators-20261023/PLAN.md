# 同一批 RAGTruth 30 条：补跑 baseline 与 minimal

用户于 2026-10-23 要求在刚完成的同一批 30 条上测试 baseline 和 minimal。本轮不再抽样，不修改推理、Prompt、金标或输入，也不重新运行已经完成的 v4。它是已曝光集合上的固定实现比较，不称新的盲测确认。

## 实现与运行冻结

- 原运行：`results/ragtruth-small30-20261023`，30 个来源、QA / Summary / Data2txt 各 10 条，当前 v4 已运行一次。本轮直接复用其中的输入与 v4 预测，不择优挑选预测。
- baseline 为项目现有的无 LLM 词法启发式实现；minimal 为现有的一次模型调用实现。两者及公共 client / contracts / prompts / scoring 均已包含在原运行的 49 文件源码快照中，执行和评分从该快照导入。
- 模型和设置沿用原冻结全局配置：`deepseek-flash`、thinking enabled、max_output_tokens 16384、JSON mode、timeout 180 秒、max_claims 64。minimal 按其既有实现强制 upstream_retries=0，无格式重试；不把 v4 核查阶段的 disabled/8192 配置移植给它。
- v4 沿用自身原有的分阶段预算与重试策略；比较的是三个现有系统，不是相等 token 预算下的受控算法消融。
- 新 wrapper、计划、运行设置、输入/manifest/gold、原 preselection/binding 和 v4 预测均绑定 SHA-256。运行前后核验冻结副本；不得覆盖原运行文件或新日志。
- 新增 baseline 30 条、minimal 30 条，共 60 条。模型只收到普通请求的 `context_passages` 和 `generated_answer`；ID、任务、生成器、金标仅用于日志和离线评分。
- 4 案例并发，固定哈希顺序，各后端各运行一次。技术失败保留并记录用量，不能因失败重跑或替换输出；写入逐条耐久日志和进度。

## 统一评分与比较边界

- 新 60 条与原 v4 30 条共同使用原冻结 `score_v4` 的回答级原生标签评分。保留 TP/FP/TN/FN、unknown、完整/部分/错误率、决策覆盖率、已决准确率与正确决策/全部30条、Precision/Recall/F1，以及旧整条失败口径对照。
- 有效 C/U 即检测到；只有 S 的 partial 和执行/契约失败记 unknown，不能计 TN/FN。完整空 claims 按原规则为阴性，另报空输出数量。
- baseline/minimal 没有 v4 的分阶段 completion 台账。合法完成的输出可以统计其返回的 claims；失败时未知提取总数必须保留未知，不制造“100%事实覆盖率”。原生标签不提供 claim 级准确率。
- 每任务仅 10 条，分层报告包含原生类别比例；不将 Data2txt 的高阳性比例下检测分数直接推广到其他分布。不裁定“真 FP”，不改原生标签。
- 每后端分别报告调用、输入/输出/缓存用量、缺失用量、总参考费用、平均/P95时延。使用原固定单价 USD 0.30/百万非缓存输入、0.006/百万缓存输入、1.20/百万输出；缺失用量不算零。另报统一缓存全未命中估算。baseline 的模型 token 和模型费用为 0，不表示本地计算没有资源成本。
- 质量结果可按同一来源做配对描述及 bootstrap 区间，但 v4 与新增后端不是同时随机交错运行。成本/延迟受缓存、负载、时间以及算法调用结构影响；不得将差值视为控制了这些因素的因果结论。供应商返回 model/fingerprint 均记录核对。
- 本轮不修复系统或挑选新的 Prompt。若之后据此优化，需将其视为曝光开发证据，并在其他来源验证通用改动。
