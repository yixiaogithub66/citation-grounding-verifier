# NF 修复实际评测：开发集有限范围语义审阅

这是 AI 对冻结轨迹的诊断，未经作者终审，不修改原生标签或正式分数。覆盖全部 35 个原生检测状态或完整性变化输入，另检查唯一的两版共同空输出，共 36/180 对；其余 144 对未做逐条语义审阅。没有新增空报告。

FP 73→69 的组成是 11 次 FP→TN、8 次 TN→FP，以及 1 次 FP→未决负例。TN 45→48还受到1次 TN→未决、1次未决→TN影响。另有1次 TP→未决正例；FN仍3不代表该正例被正常核查。完整报告总数相同，个例完成变化仍存在。

原生改善不能等同真纠错。15128 的电话输入字段、16773 的 neurotransmitters、7140 的 ample，都出现原生 FP→TN但引证未覆盖完整断言；5391 的个人/集团范围需单独审阅，17571 更直接丢掉 before-lungs 条件。15481 的 temporarily 虽然当前引证/推导不足，但完整材料含一次解锁经历，不能据引用不足断言全部来源不支持。17568 的指代消解和 4344 的合理概括有改善候选，但不能归因于 NF 规则。

14133 的报告从 partial→complete，却把球下坡势能事实排为非事实；其排除理由自己承认句中含事实。5278把问题当断言后判U；7020把‘两位顾客的投诉分别涉及两项’拆成‘两位都投诉每一项’。这些是可由通用语义独立解释的故障类型，不应演变成案例专用规则。

35 个状态/完整性变化中，14 个在至少一版实际 M1 payload 上有解析器差异标记，其中 3 个只有 NF 记账变化；21 个无标记。此条件取决于运行中生成的输出，不能用于因果消噪。

按冻结代码重建初始 M3 输入，39 对完全相同；其中原生决策不同的是 16772, 4344，完整性不同的是 16772, 5276, 10822。4344 是同输入下 U/S 变化；16772 是同输入下引用重判失败导致未决。这只能显示下游轨迹仍会不同，不能估算随机方差或其比例。

| 输入 | 原生状态；完整性 | 解析器差异 | AI 审阅 |
| --- | --- | --- | --- |
| 1728 | tn→fp；complete→complete | 无 | 新版把 routine check-ups、critics argue regulation/education 均判 U。来源本身是批评过度检测的文章，明确对健康者常规检测、监管和教育提出相同观点；这些 U 显示概括与作者归属边界不稳定，不能把批评作者机械排除于 critics 概括之外。 |
| 1732 | fp→fp；partial→complete | 无 | 旧首批三项 JSON 失败，新版恢复；两版仍因‘only effective and safe tests’这一额外监管目标而 U。没有证据表明完整性变化是 NF 规则直接带来的语义纠正。 |
| 1733 | fp→tn；complete→complete | acceptance_changed | 旧 U 分别针对‘false alarms 导致进一步检测治疗’及‘available 不代表 necessary/useful’。后者可由全文反过度检测论点合理概括；前者的治疗因果范围更有歧义。新版合为 fallback 长句并全 S，可能减少过严判决，也可能掩盖因果限定，不能把两项一并标真纠错。 |
| 4218 | tn→fp；complete→complete | 无 | 新版仅把 growing tensions in the Middle East 判 U；来源写持续展开的冲突可能引发地区战争。一般新闻概括可读为紧张升级，但 growing 的时间趋势没有独立字面陈述。应保留语义边界待裁定，不能据 TN→FP断言发现真实错误。 |
| 4219 | tn→fp；complete→complete | 无 | 新版同一答案中，‘Pentagon expressed concerns’在核弹头子项判 U、在导弹井子项判 S；两项均来自同一句 Pentagon report offers causes of concern。该内部不一致比原生分数更能说明归属判定不稳定，无法把一个 U 直接认作正确纠错。 |
| 4344 | fp→tn；complete→complete | acceptance_changed | 两版相同提取目标和初始 M3 输入；旧 U 拒绝把 Pritzker 对税收转移的批评概括为 Critics argue，新版 S 接受同一政策/人群语境下的概括。属于合理概括改善候选，不能据此声称解析器消除了随机波动。 |
| 5274 | tn→fp；complete→complete | accepted_nf_ledger_changed | 旧把 Fans are left wondering 整句排 NF；这是观众心理状态的陈述，不是单纯问句。新版保留后，对 motives 判 S、forgiveness 判 U，虽然两者均由文章向读者发问改写而来，边界不一致。新版还未单独保留括号中的演员名。标签退步不等同于所有语义变差，但整体仍不稳定。 |
| 5276 | tp→tp；partial→complete | 无 | 相同初始 M3 输入下，旧引用重判失败的 She wants ... 恢复；但新版把 RJ does not want to tell Eric 判 S，来源说 tell his dad、担心 Eric（祖父）被背叛，收信人混淆没有解决。Alzheimer's 未说明仍 U，TP 掩盖该退步。 |
| 5278 | tn→fp；complete→complete | 无 | 新版直接将 Will RJ forgive Luna? 作为 claim，再因问题未得到回答判 U。疑问句并不声称已经或不会原谅，应区分问题本身与隐含前提；该 TN→FP是明确的事实性分类错误信号。 |
| 5391 | fp→tn；complete→complete | 无 | 新版用整个 scheme 涉及多州且损失数十万美元，支持 She stole ... in six states；源文只把本人明确盗窃金额归于 Mississippi 的 $108,000。团体事件范围转成个人范围缺一步证据。duress 的 claimed/admitted表述另有歧义，不能用原生 FP→TN作全句正确证明。 |
| 5739 | tp→tp；partial→complete | 无 | 旧首批三项 JSON 失败恢复；两版都识别营业时间及 third reviewer 来源绑定问题。新版另将 business_stars:4.0 的 average/out of 5 判 U，体现结构化字段解释过严，但 TP 保持，不能仅用完成率认定语义全面改善。 |
| 6276 | tp→tp；complete→partial | acceptance_changed | 新版用品抱怨复合目标因 citation_requery_required 失败；WiFi/Music:null 与 generous portions 的 U 仍检测到问题。旧版‘无停车设施’U变新版S属于字段范围边界变化；完成率下降主要来自已记录的引用重判失败。 |
| 6279 | tp→tp；complete→partial | 无 | 新版 utensils 目标因引用重判失败未完成；其余未说明的价格区间、现代传统融合等仍 U。'4.0 based on 3 reviews' 从 S→U有合理 basis 警惕，intimate 的 C仍在；不能把局部合理变化抵销未完成项后宣称整体收益。 |
| 6632 | tp→tp；complete→partial | rejection_feedback_changed | 新版首批地点、品类、营业时间 JSON 失败，包含旧版由每日相同 hours 反驳 varying hours 的直接冲突。剩余 popular U使回答仍 TP；回答级召回掩盖重要冲突目标未完成。 |
| 6635 | tp→tp；partial→complete | 无 | 旧首批三项 JSON 失败恢复；新版明确保留未说明 delivery 和不同评论者内容拼接的 U。另一方面把 rating 3.0 based on 3 reviews 判 S，源数据三条展示评论不能证明总评分由这三条计算。完成改善不代表所有归属/数量范围正确。 |
| 7020 | tn→fp；complete→complete | rejection_feedback_changed | 答案说两位顾客不满，投诉涉及 fish/chips 与 Thanksgiving；新版拆成‘两位都投诉 fish/chips’及‘两位都投诉 Thanksgiving’，将集合分布变为每人全覆盖后判 U。原文分别来自两条评论；此 TN→FP体现 M1 量词/归属强化，不是发现原答案新增事实。 |
| 7022 | tp→unknown_positive；complete→partial | 无 | 新版首批三项 JSON 失败，包含错误统一11am–11pm营业时间；原文各日时段不同，旧 C有直接证据。剩余全 S形成未决正例，不能称 FN仍3而无召回损失。 |
| 7024 | tp→tp；partial→complete | 无 | 旧评论末批 JSON 失败恢复，营业时间、停车、预约冲突仍正确检出。新版把末尾建议 exercise caution 和事实概括合成目标，以建议无依据为由 U；检测不变掩盖建议事实化。 |
| 7140 | fp→tn；complete→complete | 无 | 新版对 ample lot parking 的 S 理由明确写 ample 只是‘不矛盾的修饰’；引用只有 lot:true，没有容量。由存在停车位推到充足停车位缺少证据，FP→TN不应算真纠错。 |
| 7776 | fp→unknown_negative；complete→partial | 无 | 旧 U 对 10:30–0:0 不愿解释成上午至午夜过严；新版没有把该声明纠正为 S，而是首批三项 JSON 失败，原有 U恰好未完成，最终未决负例。FP减少1不能记语义收益。 |
| 7779 | tp→tp；complete→partial | 无 | 新版价格取货抱怨因引用重判失败未完成；虚构正面评价和 mixed reviews 仍 U，所以 TP保持。旧/新粒度不同不改变这一技术完成退步。 |
| 10068 | fp→fp；partial→complete | 无 | 三条首批目标从 JSON 失败恢复完成，回答仍被检测到。新输出把 Music:null 正确视为未说明，但又把 2013 年的恢复评价概括成 recent reviews 已改善；完成不等于语义全对。 |
| 10069 | unknown_negative→tn；partial→complete | rejection_feedback_changed | 旧版末批三项因 JSON 失败未决，新版完成后全 S。新增把 It may be worth trying 的建议抽为事实并判 S；recently relocated 的时间范围仍需谨慎。未决→TN主要是完成恢复，不能当作纠正旧语义误报。 |
| 10819 | fp→tn；complete→complete | accepted_nf_ledger_changed | 旧 U 针对 food lacked flavor；新版整句 S 引用 not very sweet / not very memorable。它可被理解为口味概括，也可理解为新增味道强度，属于自然语义边界，不认定为已裁定纠错。 |
| 10822 | tp→tp；complete→partial | rejection_feedback_changed | 两版提取目标及初始 M3 输入相同；新版首批（包含开场片段、地点品类、营业时间）JSON 失败。WiFi 冲突及未说明 delivery 仍被发现，因此 TP不变而完成性下降。 |
| 13717 | tn→fp；complete→complete | 无 | 新版 U 的火灾风险声明忽略原文‘堵塞导致危险火灾’与清理堵塞的一步关系；另把‘材料足够回答’元说明当事实核查。原文的工具/拆卸能力前提可以核查，但整段不能因是步骤就全排除。该 TN→FP 不能解释为发现真实新错误。 |
| 13718 | 两版同为空报告 | 无 | 两版都把纯清洁步骤列为 NF并返回空 claims。按既有‘步骤本身非事实’口径这是可解释的处理；隐含工具用途等前提是否已构成独立断言需另行任务定义。此例两版共同存在，没有新增空输出或由空报告制造的分数改善。 |
| 14133 | tp→tp；partial→complete | acceptance_changed | 新版河流运动目标从旧引用重判失败恢复，但把‘球下坡因高度具有重力势能’整条放入 fallback_exclusions；排除理由自己承认有 factual claim，随后以原文没有该例为由排掉。未获支持与非事实混淆，完整报告增加掩盖事实排除。橡皮筋示例仍 U，TP不变。 |
| 15128 | fp→tn；complete→complete | accepted_nf_ledger_changed | 旧 U 指出 phone number 可作为搜索输入没有依据。新版仍保留该子命题，却用仅说 first name / address 的引文判整条 S；原文 phone number 是搜索结果字段。FP→TN含明确证据覆盖不足，不能算纠错。 |
| 15131 | fp→tn；complete→complete | 无 | 旧 U 把 People Search France 作为专名存在性要求；新版用一般‘people search in France’支持带该名称的推荐。来源文字本身含 people search France 描述，是否独立品牌名称需作者口径，不能据原生 TN直接裁为真纠错。字段映射等其余事实有来源。 |
| 15481 | fp→tn；complete→complete | 无 | 新版引用段未说明 temporarily，理由却以‘不矛盾、核心条件支持’放行，这不是有效蕴含论证。但完整材料的另一段有改密码后曾解锁的个人经历，可能支持 may temporarily 的弱存在性解读。因此这里只确认所给引证/推导不足，不把最终 S裁为必错；需作者审阅其归纳范围。 |
| 16772 | tn→unknown_negative；complete→partial | rejection_feedback_changed | 两版相同提取目标和初始 M3 输入。新版关于 electrochemical pulses / hormones 的完整事实因 citation_requery_required 未完成，其余全 S→未决负例；不能计为新 FN/TN或语义标签改善。 |
| 16773 | fp→tn；complete→complete | acceptance_changed | 新版将含 neurotransmitters and hormones 的整句判 S，而引文只写 chemical messengers、electrochemical pulses 和 hormones，未给 neurotransmitters 这一名称。旧 U 对缺失子命题的诊断有依据；新版 FP→TN不能当作无条件收益。 |
| 16879 | tn→fp；complete→complete | 无 | 原答案是种植步骤；新版抽成‘A sprouted potato should ...’，再以未覆盖 every sprouted potato 判 U。原文对 large sprouted potatoes 与 small potatoes 有区别，条件确应保留；但抽取先把步骤升为普遍规范后再否定，未能证明报告在正确核查原断言。 |
| 17568 | fp→tn；complete→complete | 无 | 旧 fallback 的 This is part of ventilation 被以缺少指代为由 U；新版显式指代到膈肌运动并引用原文呼吸/通气定义，恢复可追踪的一步含义。是合理改善候选；两版该例均无可用 payload 的解析器分歧，不能归因于 NF 修复。 |
| 17571 | fp→tn；complete→complete | acceptance_changed | 新版把两个‘before it reaches the lungs’列表引导语排为非事实，子项因此丢失 before-lungs 范围；旧版对‘肺内气体交换发生在到肺之前’的 C 消失。还将‘Expansion ... decrease air pressure ... inhalation’整条因片段形式排 NF。FP→TN伴随事实范围/目标丢失。 |

机器文件保存每项普通输入、两版完整报告、提取/NF/fallback排除账本、解析器差异、初始 M3 消息指纹和明确审阅范围。引用存在、接口完成及原生标签一致都不构成完整语义证明。所有补充解释保持 AI 诊断状态；歧义项未被强制收敛为作者金标。
