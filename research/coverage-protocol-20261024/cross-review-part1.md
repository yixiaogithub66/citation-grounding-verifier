# Part 1 争议项盲交叉审阅

审阅日期：2026-10-24。审阅者为本轮病例的 **AI 起草者**，不是人工作者或最终裁定者；起草意图不优先于实际文字与冻结规则。此次仅阅读 `PLAN.md` 和 `review-packets/blind-part1.json` 中下列八条记录，未读取私钥、analysis、臂映射或原始模型响应。未修改任何评分、病例或推理文件。下列 claim 索引均从 0 开始；全部建议按文字与统一契约作出。

冻结规则的关键区别是：整段可唯一回指可保住 `content_retained`；`standalone_retained` 要求单条表达必要主体和归属；`source_supported` 要求附带来源支持谓词、数值、条件和范围，只允许从原文补充明确共享先行词。明确的先行词补全不能扩大成任意上下文借用。忠实重复不是 FP，未解决歧义应给敏感性而非按臂挑选口径。

## 1. 双重所有格：r-60cc988af6222bcedaae7bc9

争议 claim 2：`Batch Kestrel's batch's cooling interval lasted 7.5 hours.` 附带来源为同时明确 Batch Kestrel 和 `the batch's cooling interval lasted 7.5 hours` 的原句。

**建议主判：f3 的 content=true、standalone=null、source=true；selection=true，strict=null。** 其余三个事实与本争议无关，均完整呈现。原回答只引入一个命名批次，没有第二批次或从属批次；整段阅读时，多出的 `'s batch's` 最自然地表现为替换先行词时留下的赘词。因而不宜将它报告为已证实的新实体或严重实体破坏。数值、单位和冷却区间未改变，附带原句完整支持这项在上下文中可恢复的事实。

但孤立读取时，双重所有格在字面上也能构成“Batch Kestrel 所属的另一个 batch”的嵌套结构。冻结的独立表达要求比“读者能猜出意思”严格；我不愿直接给该轴无疑义的 true，也不把这种并不自然的嵌套读法当作确定发生的 entity change。应在 uncertainty 记录语病及两种解读，不在主判追加确定的 `meaning_changed`。

敏感性：宽容语病读法将 standalone 与 strict 记 true；严格字面读法将 standalone 与 strict 记 false。后者若进一步将所属批次当作新实体，才会导致 content/source=false 和 selection=false；这是更强、较不自然的字面下界，应单独列出，不能冒充已证实错误。不要静默改写模型句子后宣称原输出完全正确。

## 2. “Two other entries belong on the handover card.”

涉及四条记录的 claim 2：

- r-4a7fee71cdd4324bb54c6d3b
- r-9fc42d5a313e8c9f2d311b59
- r-c509b5d1c132fb243b64e0c0
- r-dd1aee80592713eb349c6775

**建议主判：该句是编排建议，记 `non_factual_as_claim`；四个原有目标均保留，selection=false、strict=false。** 依据不是“金标只有四条”。这段在指导读者怎样编排交接材料：前面有 `For the margin note, use...`，后面紧接两项数据，再说 `I would place those entries on separate lines...`。这里 `belong on` 更接近“也应写进交接卡”，并未报告卡片已经含有两项，亦未引述一条外部规定。两个随后的事实仍是事实；建议它们应置于卡上并不是新的现实断言。

另一种读法确实存在：作者把下一段解释为交接卡文案的文档结构，句子就可被看作对拟议文档内容的概述。主判仍偏 NF，因为原文没有明确建立一个已完成文档或具有权威性的模板规则。对此应承认材料有语用边界，不把 AI 起草意图当作决定性证据。

敏感性：统一将这句作为可接受的文档结构元话语，不处罚这项额外输出，同时保持冻结的四个目标不变；这四条输出就争议项而言均可 selection=true、strict=true。它是“忽略边界性附加句”的容许性分析，**不是事后补第五个必提目标**。若真的把它新增为事实目标，还必须重新考虑其余输出是否遗漏该目标，并改变分母；那是另行报告的 fixture 修订，不能混入本轮主结果。

## 3. recorded route order 的来源范围

涉及 r-aa17b48d1ad5cbf16203aa97 与 r-5169b3d9b7b4d3eb95a9e0a2 的 claim 1 / f2。两条 claim 都写明 `in the recorded route order`，但唯一 attached source 是 `[141,179)`：`the mirror room follows the knot table`。`use the recorded route order:` 在附带范围之外。

**建议主判：f2 content=true、standalone=true、source=false；claim 1 记 `source_misaligned`；selection=true、strict=false。** 原回答的记录范围被正确写入 claim，因此内容与独立表达没有问题；来源却只携带一个未限定关系。“recorded route order”是关系的记录/路线范围，不能当作 mirror room 或 knot table 的缺失姓名来套用先行词例外。该 clause 没有指向这个范围的 `it/this/that order` 等明确替代成分。

这是来源缺范围，不能描述为凭空捏造路线关系。也不要把两条 output 当作原回答说错了该事实。允许所有直接前缀或整句共享范围进入来源，可以给 source=true、strict=true 的探索性上界，但它扩大了冻结 allowance，不能作为本轮主判。

病例的 `source_quote` 本身也只保留该短 clause，而 `required_semantic_elements` 要求 recorded route order。这是 AI fixture 的说明弱点：引用锚点比完整目标窄，容易让人误以为它是充分来源模板。冻结 PLAN 已独立规定 source 轴，故不能用这项锚点不足覆盖评分规则；应公开保留这一材料局限。

## 4. 卡上规则拆分：r-e63edc1edb52c658c997fe77

该记录的前两项为：

0. `标记为“薄片”的试件采用 18 分钟保温`；来源 `[8,28)` 为这段文字本身。
1. `标记为“薄片”的试件采用 18 分钟保温这一条是卡上的适用规则`；来源 `[29,40)` 为 `这一条是卡上的适用规则`。

**content/selection：f1 内容保留，selection 可以 true。** 整个输出明确把条件、18 分钟与卡上规则连接起来，没有丢失条件、制造已完成保温事件，或把所有试件都纳入规则。并且实际的 claim 1 已展开先行词并包含完整规则及卡上归属，并非只有“这一条”四个字；不必仅靠两个不完整命题的拼合来证明内容存在。

**对 claim 1 的 source：建议 true。** `这一条` 是紧接前一条规则的明确命题指代。将其展开为刚刚陈述的规则，是冻结文本允许的明确先行词恢复；其 attached source 自己就含有此 claim 的判断谓词 `是卡上的适用规则`。这与第 3 项额外导入未被来源指代的 recorded-route 范围不同。这里规则内容是被指代对象的身份，并未额外断言它已实施。若把既有 allowance 限定为人名或实体名、排除命题先行词，才会使本条 source=false；PLAN 未明示这种限定，宜作为较严敏感性，不宜临时加入主规则。

**独立性与整条 strict：claim 0 仍有问题，建议 strict=false。** claim 0 单独出现时没有“卡规定/卡上规则”的来源归属，需要后一项才知道说的是卡的适用规则，而非无归属的普遍操作断言。可用 `unresolved_reference` 记录这种依赖相邻 claim 才恢复的归属，reason 应明确它是独立性不足，不是整体 content 丢失或虚构事件；不要把该项标成确定的 `meaning_changed` 后又不加解释地给 selection=true。

建议目标映射优先用 f1→[1]：在这个完整映射下 content/standalone/source 均可 true。claim 1 已写出条件、数值及“卡上规则”的文档归属；“卡”是原文明确给出的泛称，不应另要求虚构卡片专名。claim 0 的独立归属缺失作为额外 claim 的 strict issue 保留，不能被完整重复项掩盖。因此“目标被完整覆盖”和“每条输出都独立忠实”可以得到不同结果。

如果现有评分已把 f1 映射为 [0,1]，则联合 content 仍 true，而对“每一个映射 claim 均独立表达完整目标”的 aggregate standalone 应为 false。不要未经声明就在“存在一个完整 claim”与“所有相关重复 claim 都完整”之间切换目标指标。来源轴也应先保留逐 claim 的上述解释，不把别的 claim 的附件自动并入 claim 0。建议主结果采用一个完整 claim 的目标覆盖，加逐 claim 的严格问题；另一种目标聚合口径作为敏感性说明，整条 strict=false 的结论不受影响。

f2 的 claim 2/3 是同一红色试件标记的忠实重复；claim 3 从 `它` 展开红色试件属于明确先行词恢复。它们不应因为可合并却未合并而被计 FP，也不应仅因 claim 3 来源片段没有再次写出红色试件而判 source 错。

## 交叉意见的稳定性

我对第 2 项的主语用判断和第 3 项按冻结来源规则的失败判断较有把握，但第 2 项仍需保留元话语敏感性。第 1 项应明确保留语病恢复的不确定性，不能报告为已证实严重实体错误。第 4 项最关键的是区分实际已经展开的 claim 1 与仍依赖相邻归属的 claim 0，并把明确命题先行词恢复与任意全文补来源区分开。

这些是 AI 交叉意见，不改变病例来源、原评分记录或冻结规则，也不为任何臂预先决定汇总结果。
