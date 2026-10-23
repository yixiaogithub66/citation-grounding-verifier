# 跨来源综合与可证伪猜想

本稿在试验前整理。论文机制不等于本地效果，组合来源不等于算法首创；本轮所有收益判断等待小试。来源详细阅读范围与限制见三个 sources.json 文件，累计22条记录，包括同厂商的多份文档，不能视作22次独立效力实验。

## 先排除已有反证的方向

本地combined与M1-faithful实验已说明，格式完整、claim数量或标签翻转的改善不足以证明语义改进；同批30条的共同已决28条中minimal与v4各17正确。本轮不再整套叠加指针、盲化复核和更复杂拆分，不增加推理预算来掩盖结构问题。[本地反证](local-diagnosis.md)

分解噪声具有外部依据：Hu等分析了分解方法、输入粒度、验证器之间的交互；MiniCheck在其设置中也未发现拆分/去语境化稳定有益。两者并不证明所有分解都应取消，也没有授权改变M1承担粒度的既定契约。[Decomposition Dilemmas](https://aclanthology.org/2025.naacl-long.320/) [MiniCheck](https://par.nsf.gov/servlets/purl/10631137)

## 假设A：把“丢弃事实”的风险单独作为审计对象

Claimify分别讨论提取蕴含、元素覆盖和去语境化；AFaCTA强调表达形式的主观性与可核查事实不等价。结合本地“合法NF吞掉事实”的日志，我们推测：仅审计拟排除文字，要求给出原回答中的事实见证，可能比再加长全局M1提示更直接。这是对这些来源的联合推断，不是论文已验证的当前系统算法。[Claimify](https://aclanthology.org/2025.acl-long.348/) [AFaCTA](https://aclanthology.org/2024.acl-long.104/)

反证是同模型审计可能重复错误或创造事实。无外部反馈的推理自改在一些实验中会退化，所以必须与同样多一次原M1提取比较；不能把“审计有意见”当证据。[Huang等](https://openreview.net/forum?id=IkmD3fKBPQ)

本轮P2只做影子检查：看原回答、拟NF文字和已有原文跨度，不看context事实证据或初判理由。纯建议、试探、假设和拒答仍允许无事实输出。返回候选不直接并入M3。评分先固定事实目标分母，分别看漏提、错误新增、限定/归属保真，而非输出条数；这借鉴了ACU的固定内容单元思想，但不把其重要性评价当作事实真值。[ACU](https://aclanthology.org/2023.acl-long.228/)

与Gemini讨论后增加base+fresh的离线目标集合对照，防止“保留再补漏”天然胜过替换初判。该集合只用于评测，不是运行时拼句或语义合并。

## 假设B：在一次判决中明确必要关系和限定的证据责任

ACL2026的test-taking方法将核查看成有指导的阅读理解；Alignment Bottleneck提示细粒度命题必须与相关证据可靠对齐；NLI诊断说明整体与有效原子命题的一致性只是必要条件。联合这些来源，我们推测：保持完整claim、完整context、标签和预算，仅要求按主体/归属→关系→限定→一步蕴含顺序核对，并在原derivation字段指出关键证据或缺失部分，可能降低局部匹配造成的误判。[Test-Taking](https://aclanthology.org/2026.acl-long.1468/) [Alignment Bottleneck](https://arxiv.org/html/2602.10380v1) [NLI under the Microscope](https://aclanthology.org/2025.naacl-long.130/)

不能迁移二分类、两跳推理或弃权U含义；本项目的U是缺证并计入回答级检测。顺序核对可能只重申当前提示，也可能增加字面主义或格式错误。因此P1是简短提示强化的小试，不称新架构。正常同义和既定一步推导必须保留；全部24次/臂作为分母，另审阅证据与解释，不能靠淘汰格式失败样本提高条件准确率。

FAE/REAL启发了证据删除诊断：若删除唯一支持及所有替代支持、且没有反证，期望转U。但本轮只借其评测思想，不复现训练方案，也不把标签正确自动等同于证据依赖。所有删除输入同时给两臂，不能只测试候选。[FAE/REAL](https://arxiv.org/abs/2609.08943)

## 假设C：把序列化可靠性当独立工程问题

Datadog讨论rubric、格式约束与语义质量的取舍；JSONSchemaBench将约束覆盖、效率和任务质量分开；厂商文档进一步区分JSON对象输出、严格schema和原生引文指针。这些证据支持先做能力探针，不能证明强schema会更准确。[Datadog](https://www.datadoghq.com/blog/ai/llm-hallucination-detection/) [JSONSchemaBench](https://arxiv.org/abs/2501.10868) [Google文档](https://ai.google.dev/gemini-api/docs/structured-output)

当前系统已开启Chat JSON mode，安全引用直修也已存在；不能把它们重提为新优化。DeepSeek当前Chat文档与Responses文档的schema支持不同，迁移还涉及返回格式、失败状态与用量解析。该能力尚未在本项目实测，本轮暂不迁移API。[Chat API](https://api-docs.deepseek.com/api/create-chat-completion/) [Responses API](https://api-docs.deepseek.com/api/create-response/)

原生引文机制保证位置不代表保证蕴含；模型间功能也不能直接互换。多层重试会放大开销，成本路由又需要可靠校准，不能按benchmark设阈值。故优先两个低范围语义机制probe，严格协议探针、已知字段回填和薄层single-call护栏另作未来独立工程实验。[Anthropic citations](https://platform.claude.com/docs/en/build-with-claude/citations) [AWS重试工程](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) [FrugalGPT](https://arxiv.org/abs/2305.05176)

## 与Gemini的分歧如何处理

| 议题 | Gemini建议或反驳 | 最终处理 |
| --- | --- | --- |
| 优先机制 | 单次M3优先，NF独立诊断 | 两项分别小试，不组合部署 |
| thinking预算 | 第一轮提议统一开启16384 | 拒绝；保持当前初判disabled/8192，减少混杂 |
| 证据删除 | 第一轮只给候选删除臂 | 拒绝；同一原/反/删除输入在两臂全交叉 |
| NF审计信息 | 不能隐藏已有事实跨度，否则重复捞回 | 提供原文跨度，不给改写claim或初判理由；重复不计恢复 |
| 等预算控制 | 单调补漏与fresh替换算子不对称 | 接受；增加零调用的base+fresh离线事实目标集合对照 |
| 格式修复 | 提议确定性直修 | 说明已有生产M2，避免改名重做；不放宽validator |
| 当前失败解释 | 曾推测尾部截断 | 拒绝；当前相关日志为正常stop，不能据此加预算 |
| 小试采用标准 | 提出量化筛选阈值 | 在PLAN中预登记更保守的“值得扩大验证”条件，绝非自动生产采用 |

两轮原始CLI输出和纠偏均保留。Gemini没有自己检索网页；一手检索由主代理与文献代理承担，它负责基于材料的综合和反证。其措辞与结论经过主代理核对，不能代替作者裁定。

本轮保留的“创新”是工程假设与实验控制的组合：区分合法排除风险、成分证据责任、输出协议负担，并用同预算和证据干预分别证伪。尚未证明新算法或普遍收益，也没有把某篇论文的数字搬到本系统。
