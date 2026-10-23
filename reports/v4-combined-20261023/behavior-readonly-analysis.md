# H4 已冻结行为实验：只读结果分析

分析对象：`behavior-r2` 的 24 对、48 个输入，分别运行旧 v4 与 combined 的端到端和固定 claim 模式，共 192 条记录。全部完成。数据为明确标记的 AI 起草诊断集，未经作者终审，也不是未见集。本分析未修改标签、Prompt、推理代码或运行配置，未新增模型调用。

旧 v4 两种模式均为 **48/48** 符合草案标签、**24/24** 对满足预期关系；combined 两种模式均为 **47/48** 和 **23/24**。两种模式都错在同一输入，因此不是两个独立失败案例。这组结果没有显示组合收益。[汇总](../../results/v4-combined-20261023/behavior-r2/report.json)

## 唯一差异：来源编号的语义解释

`behavior-06/variant` 的输入是：index 0 说费用恰为 **7 credits**，index 1 说费用恰为 **9 credits**；回答是 `Passage 1 states that the quoted fee is exactly 7 credits.`。原始草案按零基索引约定给 `CONTRADICTED`，要求引用 index 1。该标签和计分原样保留。[冻结样本](../../results/v4-combined-20261023/behavior-r2/pairs.jsonl)

| 环节 | 端到端 combined | 固定 claim combined |
| --- | --- | --- |
| 待核查命题 | M1 完整保留原句，包括 `Passage 1`，无降级 | 评测器直接提供同一原句，跳过 M1 |
| 初判 | `SUPPORTED` | `SUPPORTED` |
| 考察位置 | `p0u1`、`p1u1` | `p0u1`、`p1u1` |
| 判决位置 | `p0u1` | `p0u1` |
| 代码回填 | index 0 原文的 7 credits | index 0 原文的 7 credits |
| 后续复核 | 无 C/U 复核，无数值信号 | 无 C/U 复核，无数值信号 |

原始模型推导明确把来源称为 `Passage 1 (p0u1)`；固定 claim 推导进一步写出 `p0u1 is the content of Passage 1 (index 0)`。这支持“把自然语言 Passage 1 读成第一段”的解释，不能解释为代码把正确的 `p1u1` 错换成 `p0u1`。两个合法 ID 均被考察而仍选错归属，也说明指针有效性不能保证语义正确。[原始轨迹](../../results/v4-combined-20261023/behavior-r2/responses.jsonl)

**结论应分两层：** 按预注册的零基映射，这是来源归属判错，必须保留为一次退步；但 `Passage 1` 在单个请求正文中没有显式声明零基，普通语言又允许“第一段”的一基读法，因而此题同时暴露了编号表达歧义。冻结输入虽提供 `index:0/1`，combined Prompt 并未明确规定回答中的 `Passage N` 必须对应这个零基字段。不能事后改标签来抹去失败，也不能把这一例包装成毫无歧义、足以证明总体泛化退步的样本。

旧 v4 的固定 claim 轨迹初判即 C；端到端轨迹为 U→C，U 复核最终引用 index 1 的 9 credits。combined 初判 S 且未触发任何复核。因此，本例不构成“盲化复核把正确答案改错”的证据，也不能据此识别 H3 的因果效应。完整 M1 提取与固定 claim 重现则排除了“此例只因拆分丢掉来源归属”的解释。

## 固定 claim 复核净变化

按报告中的 `groups.*.review_audit_ai_draft`，两后端各触发 **9 次复核：5 次 C、4 次 U**；全部前后标签不变，且这 9 条在草案标签下前后均正确。

| 后端 | 错→对 | 对→错 | 标签未变 | 失败 | 净修正 |
| --- | ---: | ---: | ---: | ---: | ---: |
| optimized-v4.0 | 0 | 0 | 9 | 0 | 0 |
| optimized-v4-combined | 0 | 0 | 9 | 0 | 0 |

这里的净修正是“错→对减去对→错”，只描述这些已触发复核、具有 AI 草案标签的固定目标；不覆盖未触发的 S，也不是 H3 单因素对照。唯一失败正是未触发复核的 S。[复核审计与计分限制](../../results/v4-combined-20261023/behavior-r2/report.json)

证据绑定：`responses.jsonl` SHA-256 为 `62e31f09bb2f6c48279b17a943fe149900d3ed4a1e3cd8a3f52938cf56501608`；`config.json` SHA-256 为 `cdc3c4821ba8740fb5ec86708c359b44514ad043a1f97bd9617f8303bc0a777a`。本分析只解释这次已曝光诊断结果，不作跨数据集或未见泛化结论。
