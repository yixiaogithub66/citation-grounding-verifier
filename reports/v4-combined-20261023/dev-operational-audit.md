# 通用组合实验：完整运行结构审计

审计时间：2026-10-23T13:14:37+08:00。主运行已结束，**360/360 条记录、180 个完整配对案例**；运行状态中的 `source_unchanged=true`、`data_unchanged=true` 均通过。本稿核查错误链、M1残留与降级、协议门禁及调用预算。未读取原生金标或作者裁定文件，未调用模型，未修改推理、Prompt、配置、测试或数据。

最终日志：`dev/predictions.jsonl`；字节数 `27583730`；SHA-256 `eb0db6fba626b76b73f53d39fbde63d34c06cd2dc6f3a72ab4aacf94fb707102`。运行代码冻结为 `07d6034`。298条记录时的临时稿已原样保留为 [dev-operational-audit-298-draft.md](../../results/v4-combined-20261023/dev-operational-audit-298-draft.md)。

## 结构结果与分母

| 指标 | v4.0 | combined |
| --- | ---: | ---: |
| 运行记录 | 180 | 180 |
| complete | 170 | 179 |
| partial | 10 | 1 |
| 整例error | 0 | 0 |
| 提取目标（含降级骨架） | 1718 | 1813 |
| 完成事实核查目标 | 1602 | 1812 |
| 未完成目标 | 17 | 1 |
| M3排除的纯非事实骨架 | 99 | 0 |
| M1原始块 | 204 | 204 |
| M1最终降级块 | 70 | 14 |
| 含骨架案例 | 67 | 14 |
| 最终保留降级骨架 | 562 | 32 |

claim完成覆盖率按已提取且未被判为纯非事实的目标计算：v4.0为1602/(1718−99)=98.9500%；combined为1812/1813=99.9448%。这一分母不包含被M1漏提或错排除的事实，因此不能叫事实召回率。两版目标粒度与非事实分流位置不同，1813对1718的目标数也不能单独证明召回改善。

## 全部不完整输出

| backend | 日志案例ID | 状态 | 未完成目标 | 代码 / 阶段 | 完成 / 未完成 |
| --- | --- | --- | --- | --- | --- |
| optimized-v4.0 | 2466 | partial | c2 | citation_requery_required / review | 4 / 1 |
| optimized-v4.0 | 5388 | partial | c4,c5,c6 | invalid_model_output / verify_batch | 6 / 3 |
| optimized-v4.0 | 6277 | partial | c13 | citation_requery_required / verify | 18 / 1 |
| optimized-v4.0 | 6276 | partial | c7 | citation_requery_required / verify | 8 / 1 |
| optimized-v4.0 | 6280 | partial | c7,c10 | citation_requery_required / verify | 9 / 2 |
| optimized-v4.0 | 6281 | partial | c7 | citation_requery_required / verify | 13 / 1 |
| optimized-v4.0 | 10069 | partial | c1,c2,c3 | invalid_model_output / verify_batch | 18 / 3 |
| optimized-v4.0 | 7780 | partial | c8 | citation_requery_required / verify | 12 / 1 |
| optimized-v4.0 | 7144 | partial | c1,c2,c3 | invalid_model_output / verify_batch | 15 / 3 |
| optimized-v4.0 | 7781 | partial | c5 | citation_requery_required / verify | 7 / 1 |
| optimized-v4-combined | 6142 | partial | c10 | invalid_model_output / verify | 13 / 1 |

v4.0的17个未完成目标分为三种直接机制：

- 9个目标：3个初判批在唯一 `verify_batch_retry_1` 后仍为 `Completion is not strict JSON.`，对应5388的c4–c6、10069的c1–c3、7144的c1–c3。整个失败批留空，其他批保留；未把执行错误转换成U。
- 7个目标：初判和唯一单条重问的引文仍触发 `quote_requires_rejudgment`，最终是 `citation_requery_required / verify`。门禁保留未完成，没有把内容差异静默修成原文。
- 1个目标：2466/c2初判U附引文时已消耗共享定向重问，修复出有效U；随后U复核提出S，但新的引用需要重判，剩余额度为0，最终是 `citation_requery_required / review`。

combined唯一未完成目标为 **6142/c10：协议版本字面值复制错误**。模型在初判、唯一 `verify_claim_requery`、一次 `verify_claim_requery_repair_1` 中连续写出 `source-evidence-points-v1`，而版本要求是 `source-evidence-pointers-v1`。三个IR转换均记录 `Unknown evidence protocol version.`；该案14个目标中其余13个完成。这不是输出截断、传输超时或长请求预算耗尽；该记录的 `failed_calls` 为空。未经语义审查不能据此断言它的S判决本来正确。

协议版本错误保留为未完成，未做案例例外、静默接纳版本别名或运行中改Prompt。可泛化的协议常量管理问题应作为未来独立设计项检验；本次冻结结果保持原样。

`targeted_reasks[*].error` 可能保留最初诊断，不能仅凭该字段计最终失败；本审计以 `prediction.errors` 和 `verdict_chains.status` 为最终口径。

## H1：85次补提取，14个降级块

combined有204个初始块、27次初始格式修复、85次残留补提取及2次残留格式修复。85次残留请求中，72次文字记账清空，13次仍有残留后降级；另1块在初始提取与修复后仍有分类跨度重叠，直接降级。最终14个降级块、14个案例、32条原句骨架。所有combined最终 `residual_ranges_after_fallback` 均为空。

剩余初次结构失败位于7140/d1，错误为 `Factual, non-factual, ambiguous and unprocessed categories must not overlap substantive text.`；该块7条原句骨架全部完成核查。由此可见complete并不等于M1原子提取完全成功。

| combined提取格式修复阶段 | 结构原因 | 次数 |
| --- | --- | ---: |
| decompose | `Completion is not strict JSON.` | 1 |
| decompose | `Factual, non-factual, ambiguous and unprocessed categories must not overlap substantive text.` | 19 |
| decompose | `Source reference is outside the designated target token ranges.` | 1 |
| decompose | `Source references need an existing unit ID and integer token indices.` | 1 |
| decompose | `background_refs must contain only existing answer unit IDs.` | 4 |
| decompose | `background_refs must not repeat an answer unit ID.` | 1 |
| decompose_residual | `Factual, non-factual, ambiguous and unprocessed categories must not overlap substantive text.` | 1 |
| decompose_residual | `Source reference is outside the designated target token ranges.` | 1 |

旧v4的70个分块降级由以下最终错误触发：

- `unaccounted_answer_text`：63块。
- `Extraction source spans must be exact answer substrings in answer order.`：5块。
- `Each non-factual span needs exactly nonempty text and reason.`：1块。
- `Extraction must contain exactly claims and non_factual_spans.`：1块。

这些结果只支持结构层面的观察，不能推出完整事实覆盖：

1. source_refs绑定原始文字，但模型可给整句挂范围而只表达其中一条事实。`parse_decomposition`不拥有原子事实全集，无法证明遗漏为零。
2. claim_text是否忠于原答案、指代是否正确、条件及来源归属是否完整、是否强化语义，仍需模型判断和独立语义评价。
3. 非事实范围由模型分类。完整文字记账不能证明没有把事实错放进non_factual_spans；本轮combined还保留2条歧义、14条未处理的历史跨度记录，最终由补提取或显式骨架继续处理，历史记录不是额外的已完成事实。
4. 原句降级会取代相交的提取结果并记录superseded轨迹，不拼接模型命题；它保证保留原句文字，不能保证原子粒度。
5. 全答案背景重复输入每个块/补提取请求，背景始终不充当证据。它的输入token开销必须计入总成本。

## H2：减少自由引文失败，并未消除U证据角色错误

| 定向重问起因 | v4.0 | combined |
| --- | ---: | ---: |
| `Citation content needs a new semantic judgment.` | 20 | 0 |
| `Each evidence row must use the versioned pointer schema with considered_evidence_ids and decision_evidence_ids; legacy citations are not accepted.` | 0 | 5 |
| `Every decision evidence ID must also occur in considered_evidence_ids.` | 0 | 5 |
| `Only provisional fallback skeletons may be excluded as non-factual, with a reason.` | 4 | 0 |
| `SUPPORTED and CONTRADICTED require nonempty decision_evidence_ids.` | 0 | 1 |
| `UNSUPPORTED must have citations:[]; never silently remove an invalid citation.` | 157 | 0 |
| `UNSUPPORTED must have decision_evidence_ids:[]; invalid decision evidence is never silently removed.` | 0 | 105 |
| `Unknown evidence protocol version.` | 0 | 1 |
| `Verification must preserve supplied id and exact claim_text.` | 1 | 1 |
| `considered_evidence_ids must not contain duplicate IDs.` | 0 | 1 |
| `response.claims[0].citations: This verdict requires evidence` | 2 | 0 |

combined仍有105次初判U携带非空decision_evidence_ids而触发定向重问。角色拆分没有让模型天然遵守该规则；校验器仍拒绝错误对象，没有靠删除结论证据隐藏问题。指针生成精确引用排除了自由抄写漂移这一入口，却不能证明所选证据有关、完整或足以支持结论。

## H3与调用预算：界限被保留，整体调用并未减少

| 指标 | v4.0 | combined |
| --- | ---: | ---: |
| U复核触发 | 316 | 467 |
| U复核标签翻转 | 36 | 150 |
| C复核触发 | 2 | 3 |
| C复核标签翻转 | 0 | 1 |
| 全部模型调用 | 1509 | 1620 |

此处的150次U翻转和1次C翻转不是151次已证纠错。没有完整claim金标时，不能区分错→对与对→错；组合同时改变提取对象、初判与触发集合，也不能把整体变化单独归因给H3。

| 阶段调用 | v4.0 | combined |
| --- | ---: | ---: |
| contradiction_review | 2 | 3 |
| decompose | 204 | 204 |
| decompose_repair_1 | 127 | 27 |
| decompose_residual | 0 | 85 |
| decompose_residual_repair_1 | 0 | 2 |
| unsupported_review | 316 | 467 |
| unsupported_review_repair_1 | 1 | 3 |
| verify | 638 | 705 |
| verify_batch_retry_1 | 19 | 0 |
| verify_claim_requery | 184 | 119 |
| verify_claim_requery_repair_1 | 18 | 5 |

只看M1（包含残留与格式修复）为331对318次，但combined初判批与U复核更多，使全部调用从1509增至1620。最终费用与延迟以独立评分报告为准，不能用拆分修复下降代替总成本下降。

| 审计到的最大值 | v4.0 | combined | 契约含义 |
| --- | ---: | ---: | --- |
| 单目标C复核 | 1 | 1 | ≤1 |
| 单目标U复核 | 1 | 1 | ≤1 |
| 单目标全链定向重问 | 1 | 1 | 共享≤1 |
| 单批重试 | 1 | 0 | ≤1 |
| 单块残留补提取 | 0 | 1 | combined固定≤1 |
| 格式修复attempt字段 | 1 | 1 | ≤1 |
| 传输attempt字段 | 1 | 1 | 从1起，当前均未发生传输重试 |

逐记录、逐claim检查未发现C/U逻辑复核或共享定向重问超过一次；已验证复核链未出现U后再开C复核。逐批重试和逐块残留次数均在界限内。全部3129条调用记录的phase、thinking与max_output_tokens均与各自记录配置一致。格式修复attempt最大为1；旧telemetry没有独立格式请求ID，不能仅靠全局同名stage次数恢复每个格式请求的分组，本项依据attempt字段和冻结实现共同审计。

## 范围与后续解释

主运行的配对完整性和source/data不变标记已核对。原生标签、来源级置信区间、费用和延迟由 [独立评分报告](../../reports/v4-combined-20261023/dev/report.md) 汇总；本稿未对这些语义指标重新裁定，也不将运行完成率当作泛化结论。作者人工审核仍是独立版本。

案例ID仅用于追溯日志，未进入Prompt、运行时条件、参数或例外规则。本次是固定通用规则在已曝光开发集上的组合观察，不是未见确认，也不是四个假设各自的因果消融。
