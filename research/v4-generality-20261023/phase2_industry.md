# Phase 2：工业工程资料及可迁移边界

研究日期：2026-10-23（Asia/Shanghai）。本阶段仅调研，未修改推理代码、Prompt、配置、金标，也未调用模型 API。采用 deep-research 的来源核验与反证原则；官方工程博客和产品文档均属灰色文献，不能与独立同行评议实验等量计票。机器可读记录见 [phase2_industry_sources.json](phase2_industry_sources.json)。

## Checkpoint 1：先澄清研究对象

研究问题：在 context-only、固定 S/C/U 与精确 quote 契约下，怎样提高事实覆盖、判决质量和成本的跨表述/来源/领域稳健性？

审计中的三类成功必须分开：70/180 案例出现 M1 降级不等于事实被完整抽取；2,165 条精确子串不等于引文语义充分；303 次 U 复核中 39 次翻转不等于 39 次修正。执行完成率、提取覆盖与语义正确率应分别测量。1,457 次调用只能描述资源消耗，尚不能识别哪个阶段具有正的边际语义收益。[项目审计](../../reports/V4_DEVELOPMENT_AUDIT.md)

此外，纯建议排除、建议内事实保留、来源归属保真、显式一步推理、M1 独占原子粒度和执行失败不得转 U，均来自既有任务契约，不由检索到的资料重新定义。[作者决定](../../docs/V4_DECISIONS.md)

## 纳入与检索

纳入七条主来源，来自 Anthropic、Google、AWS、Microsoft 四家组织。选择标准是存在可定位的接口保证、工程机制、失败条件或评价方法；排除只宣称“更可靠”而没有机制的产品宣传。搜索使用官方域名加 citations、structured outputs、effective agents、context engineering、evals、contextual grounding、confidence grounding 等词。每条检索式、读取范围、日期与核验结果保存在 JSON。本文是定向机制调研，不是穷尽式系统综述。

Claimify 官方博客被检索并部分读取，其实现段由官方域名搜索摘录核验；重复抓取正文出现 502。它与 Claimify 论文是同一工作，本阶段不把博客另算独立效果证据，也不以二手转述补足全文。原文链接：[Microsoft Research Claimify](https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/)。

## 七条主来源

| ID | 来源、日期、实际读取范围 | 支持的机制 | 已确认的边界 |
|---|---|---|---|
| I01 | Erik S.、Barry Zhang，Anthropic，2024-12-19；架构区分、链式流程、路由、复核、停止条件及附录接口设计。[Building effective agents](https://www.anthropic.com/research/building-effective-agents) | 固定任务优先简单流程；只有可测收益才增加复核与复杂度。 | 客户/内部经验，非本项目受控实验；当前页面提醒工具生态已变化。 |
| I02 | Anthropic 文档，无首发日期；2026-10-23 访问；引用机制、索引、分块、费用和兼容性。[Citations](https://platform.claude.com/docs/en/build-with-claude/citations) | 输出文档位置，再由服务取回文字，可减少自由复制错误。 | 保证引用指针有效不等于蕴涵正确；当前原生 citations 与 strict structured outputs 不能同用。 |
| I03 | Google 文档，更新于 2026-10-21；介绍、JSON Schema 支持、最佳实践及限制。[Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) | 结构约束用于字段类型与枚举，客户端继续校验。 | 合法 JSON 仍可能语义错误；Schema 只支持子集，部分关键字不执行，复杂 Schema 可被拒绝。 |
| I04 | Rajasekaran、Dixon、Ryan、Hadfield，Anthropic，2025-09-29；上下文原则、检索及压缩/子代理章节。[Effective context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) | 每阶段提供足够且高相关的信息；防止规则堆积。 | 压缩可丢关键细节；长程代理经验不能直接证明核查器裁剪上下文有益。 |
| I05 | Grace、Hadfield、Olivares、De Jonghe，Anthropic，2026-01-09；评分器、研究代理、重复试验、平衡测试、留痕及人工评价章节。[Demystifying evals](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | 拆开程序、模型与人工评分；记录轨迹和结果；检查应该触发与不应触发两面。 | 模型评分需人工校准；案例经验不是独立泛化估计，不能把开发回归集再次称未见。 |
| I06 | AWS 活文档，无页面日期；2026-10-23 访问；定义、聚合、阈值和输入限制段。[Contextual grounding checks](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html) | grounding 与 relevance 是不同维度；服务公开长度与聚合边界。 | 多来源合并评估、相关性按 chunk 聚合；这些产品口径不等于本项目 S/C/U、来源归属或精确引文契约。 |
| I07 | Joe Filcik、Colin Murphy，Microsoft，2026-10-14；完整正文、校准步骤、生产结果及公开实验说明。[Grounding and confidence](https://devblogs.microsoft.com/foundry/content-understanding-confidence-grounding-hitl/) | 来源证据、独立置信模型、人工校准和留出验证分工；看漏过错误和复核覆盖。 | 厂商自报：留出集重点复核字段少 41%，仍包含 >80% 已知错误；所有字段仍经人工检查，不能解读为等比例省时或无人自动化。 |

## 联合推导：可研究，但仍待本项目验证

以下是跨源推导，不是上述厂商对 TabbyML 效果的声明。

1. **证据定位与语义裁决分层。** I02/I03/I06 分别限定了指针、结构和 grounding 产品的保证范围。可研究给模型稳定来源 ID 与局部位置，让程序回填原文，然后单独检验该证据是否覆盖完整命题。位置正确不能自动赋 S；不能把自由 paraphrase 当精确 quote。[I02](https://platform.claude.com/docs/en/build-with-claude/citations) [I03](https://ai.google.dev/gemini-api/docs/structured-output) [I06](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html)
2. **先测 M1 的保真与覆盖，再决定是否扩充推理链。** I01 的复杂度约束和 I05 的分维评价支持把“格式有效、事实是否遗漏、限定/归属是否保留、原子性”分别测量；它们不证明现有 M1 应换成哪套实现。不得用下游语义合并补回原子性，不得把 fallback 骨架当已认证事实。[I01](https://www.anthropic.com/research/building-effective-agents) [I05](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
3. **复核应按净收益验收。** I01/I05/I07 联合支持同时统计错误纠正、正确改错、未变、执行失败、额外 tokens 与延迟。对已校准的通用信号才讨论有限级联；M3 自报 confidence、复核一致或更长理由均不能直接充当校准。不得照搬 I07 的按来源/表单设阈值形成 benchmark 分支。[I01](https://www.anthropic.com/research/building-effective-agents) [I05](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) [I07](https://devblogs.microsoft.com/foundry/content-understanding-confidence-grounding-hitl/)
4. **减少无关上下文需要对称测风险。** I04 提供信息选择动机，I06 暴露合并来源的边界。若研究局部候选证据，应保留原始来源身份、必要邻域和原文回查能力；删掉限定句可能把 U/C 错变 S。只有跨位置、长度、表述和领域的冻结验证才可说明裁剪有用。[I04](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) [I06](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html)

## 反证与禁止的外推

- 原生 citation 与结构化输出各有价值，但 I02 的当前接口明确冲突；研究可比较两条实现路径，不能声称它们已可无损组合。
- I07 的重点复核减少并不是不检查剩余字段；若只统计被触发项，就可能漏掉未触发项的错误。其数字与训练模型不为本项目可复用阈值。
- I04 的压缩、记忆、子代理主要面向长程代理；context-only 核查不能引入外部知识补证，也不能让压缩摘要替代精确原文。
- I06 的阻断阈值并未提供本项目 C 与 U 的可验证语义分界；不能按它的分数直接映射固定标签。
- 七条主来源有四条来自 Anthropic，属于同一组织的相关意见；Claimify 博客与论文也同源。组织数量与文献数量不能冒充独立实验数量。

## 证据限度与下一阶段

接口约束有直接文档依据；跨任务收益仍是假设。七条材料均未在 TabbyML 当前模型、中文/英文混合物理与系统文本、固定 S/C/U、既有预算条件下提供受控结果。未运行任何方案，未据此选择最优参数。下一阶段应以论文证据和代码实况交叉审阅上述推导，并把语义质量、覆盖/执行错误及成本一起列入冻结实验协议。

本报告由 AI 辅助检索、读取与归纳；人工作者尚未对建议、金标或数据集作出终审。
