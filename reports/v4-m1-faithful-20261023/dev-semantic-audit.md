# M1-only 开发集变化案例语义审计

更新：2026-10-23T10:16:40.774244+00:00。运行状态：completed。完整日志 360/360 条；已成对 180/180 个；检测或完成状态变化 38 个；已审 38 个。

这是 AI 只读诊断，不是作者裁定。原生 labels、推理代码、评分与历史结果均未改变。只审检测结果或完成状态发生变化的配对案例；其余案例没有做全语义审计。不能据此估计全体误抽、漏核或真 FP，也不能把不触发回答级变动的 claim 错误视为不存在。

依据现有 _observe 口径：已完成部分有 C/U 为 positive；完整全 S 为 negative；all-S partial 或全失败为 unknown。成对只指两后端都有落盘记录，技术失败照样保留。最终模型完成不等于语义正确。

报告中的改善/退步若指原生检测，会明确标示；语义判断是诊断性解释。相同目标的判决变化不能单独归因于 M1 提示，因为只采样一次、下游模型仍有随机性。

## 最终数字与解释

全部360条记录已完成，所有38个检测/状态变化均已审阅；其中33个检测结果变化、12个完成状态变化、7个两者同时变化。其余142个回答未进行全语义审计。

| 指标 | 原 v4 | M1-only |
| --- | ---: | ---: |
| TP | 57 | 57 |
| 原生 FP | 74 | 64 |
| TN | 45 | 52 |
| FN | 3 | 2 |
| 阳性未决 | 0 | 1 |
| 阴性未决 | 1 | 4 |
| 完整报告 | 171 | 167 |
| Partial | 9 | 13 |
| 已决 F1 | 59.69% | 63.33% |

配对来源聚类bootstrap的F1差值为3.65个百分点，95%描述区间[-0.08, 7.30]个百分点，包含0。该区间不包含重复模型采样的不确定性。

逐条诊断支持以下有限结论：

- 本轮新版本原生FP74→64、FN3→2，但TP57不变，新增1个阳性未决；原生FP不是作者裁定真FP。
- 完整171→167，partial9→13；已决F1约59.69%→63.33%，配对来源bootstrap差异区间包含0，不能宣称确定性或未见泛化改善。
- 15485的FN→TP来自把建议直接抽为U，5278把疑问句抽为U；4345/4349等原生改善包含合句后身份或出处子命题漏核风险。
- 若干改善有合理自然语义解释，但关键目标文本相同或fallback一致，无法从单次生成把效果归因于M1提示。
- 7022原本可检出的营业时间冲突变为技术unknown；不可把unknown当阴性或零漏报证据。
- 审计覆盖全部38个检测/状态变化，未对其余142个回答进行全语义审计；也没有为每个claim建立作者金标。

从全部原始记录独立重算原生混淆矩阵、覆盖、F1及运行诊断，均与正式 report.json 一致；数据与当前/归档源文件均匹配冻结哈希。正式费用估计两版均为未完整统计（estimated_amount=null），不能只凭调用数下降推断费用下降。

## 覆盖与分类

| 分类 | 数量 |
| --- | ---: |
| technical_unknown_regression | 3 |
| same_target_judgment_variation | 1 |
| same_fallback_target_support_gap | 1 |
| same_target_one_step_entailment | 1 |
| additional_embedded_target_and_judgment_boundary | 1 |
| ambiguous_referent_preserved_then_resolved | 1 |
| repeated_summary_scope_judgment | 1 |
| same_target_qualifier_not_justified_by_citation | 1 |
| advice_promoted_to_factual_targets | 1 |
| coarser_claim_missing_causal_link_accepted | 1 |
| technical_partial_same_detection | 2 |
| same_target_attribution_and_outcome_boundary | 1 |
| same_target_cross_sentence_attribution | 1 |
| same_target_emotive_paraphrase_boundary | 1 |
| coarser_claim_entity_identity_conflation | 1 |
| coarser_claim_source_attribution_not_justified | 1 |
| same_target_organization_scope_boundary | 1 |
| identical_fallback_judgment_variation | 1 |
| coarser_claim_escalation_paraphrase_boundary | 1 |
| coarser_claim_attribution_support_gap | 1 |
| finer_claim_exposes_modality_strengthening | 1 |
| identical_targets_rhetorical_summary_boundary | 1 |
| question_promoted_to_factual_target | 1 |
| completion_gain_and_same_target_time_notation | 1 |
| completion_gain_with_review_attribution_regression | 1 |
| technical_partial_same_detection_and_target_switch | 1 |
| identical_fallback_completion_gain | 1 |
| time_notation_rejected_after_fallback | 1 |
| category_enumeration_scope_ambiguity | 1 |
| completion_gain_with_inconsistent_locality_judgment | 1 |
| identical_fallback_technical_unknown_regression | 1 |
| same_target_reviewer_context_resolution | 1 |
| technical_unknown_positive_regression | 1 |
| coarser_summary_resolves_locality_inconsistency | 1 |
| same_targets_reasonable_gloss_and_recommendation_boundary | 1 |

## 逐案例诊断

### 16772 · source 12287 · QA

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → unknown/partial。

新版本仍提取了传输机制对比，但该条引文重判耗尽（citation_requery_required），其余 7 条 S；原版 11 条均完成。原生 negative→unknown 是技术退步，不能算更少 FP，也不是事实被主动删除。

**M1 变化：** 原版把若干对比拆成两条；新版多保留对比，并新增泛化开场事实。

**证据与边界：** 新 c6 claim 保留 electrochemical pulses / hormones 两部分；errors 明确保留未完成项。

**诊断结论：** not_applicable。

### 16770 · source 12287 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

关键 critical 声明两版基本相同，原版因 critical 比 devoted to 更强判 U，新版接受为 S。其余事实未见因新版删除而漏核。可视为自然语义阈值差异，但不能证明 M1 保真改善。

**M1 变化：** 原版 4 条均为句切 fallback；新版成功提取 4 条并消解 They。

**证据与边界：** 源段 3 为 devoted to maintaining homeostasis；没有直接 critical 字样。

**诊断结论：** uncertain。

### 16773 · source 12287 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

两版均对 11 条句切骨架核查，最终同样 7 条事实输出。新版对含 neurotransmitters 的相同声明从 U 改 S；提供材料仅写 chemical messengers / hormones，没有明确给出 neurotransmitters 这一具体种类。原生 FP→TN 不能直接当语义纠错。

**M1 变化：** 两版都 fallback，相关 claim 文本相同；未观察到误抽减少。

**证据与边界：** 新版证据为段 3 chemical messengers 与段 1 electrochemical pulses/hormones；没有所加具体术语的引证。

**诊断结论：** not_established。

### 16774 · source 12287 · QA

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → unknown/partial。

原版完整全 S，新版 c2 引文重判耗尽，剩余 7 条 S，变为 unknown。传输机制事实仍在待完成 claim 中，不能把它当非事实排除或正确负例。

**M1 变化：** 两版均提取 8 条，无 fallback；主要区别是末尾总结措辞。

**证据与边界：** c2 对 electrochemical pulses / hormones 的证据修复失败，code=citation_requery_required。

**诊断结论：** not_applicable。

### 13717 · source 15206 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

两版均仅提取效率和火灾风险两条因果事实；原版拒绝从积绒导致火灾推出清除积绒降低风险，新版接受。按照允许显式一步推导的既有口径，新结论有支持，但这是相同目标的 M3 判断变化，并非新 M1 减少误抽。

**M1 变化：** 均排除操作步骤，保留同样两条后果；This thorough cleaning 改为 Thorough cleaning。

**证据与边界：** 段 3 明说积绒堵塞 resulting in dangerous house fires，并紧接清除积绒方法；段 2 明说效率改善。

**诊断结论：** plausible_semantic_gain_not_M1_attributable。

### 15131 · source 15442 · QA

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

新版从建议中增加网站可用于寻人、可发 MC、点击 Trouver 的功能事实，并由第一条 U 触发原生 TN→FP。网站用途是潜在嵌入事实，不能一概认定为误抽；但段 1 明说 France people-search website could be helpful，新版 U 理由把 could be helpful 与 can be used 分开过严，具体命名是否对应实体也仍需裁定。

**M1 变化：** 6→9 条，无 fallback；更多建议被改写成功能性陈述。

**证据与边界：** 源段 1 为 website for people search in France could ... be helpful；第一条新版含 such as People Search France；其他新增功能均有直接来源。

**诊断结论：** uncertain。

### 12296 · source 14366 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版把 burning it 单独改写为焚烧整面旗帜并埋灰，给 U；新版保留完整并列句后给 S。原文 it 的指代存在蓝色区域/旗帜两读，保留结构避免了 M1 擅自固定主体，但新版 M3 仍选择有利读法；这不是已证明的语义纠错，也不是已证明的漏核。

**M1 变化：** 3 条改为 1 条，保留原文 it 和处置分支；有粒度变粗，但所有文字命题仍出现。

**证据与边界：** 段 1 明确焚烧并埋灰的主体是 blue field；段 3 才是整面旗帜的仪式焚烧。

**诊断结论：** ambiguous。

### 12299 · source 14366 · QA

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

新版把引导句 proper way 的范围带入每条，第四项与第二项重复；第三条从摘要式 Remove the blue field and burn it 得到 U，原版同摘要判 S。先前正文已经保留 bury the ashes，不能仅凭摘要删词断言整个回答遗漏步骤；相反也不能自动认为省略后仍是完整处置方法。属于指令/方法事实与摘要范围边界，非明确退步裁定。

**M1 变化：** 两版都 4 条；新版在重复摘要中传播 proper way，未丢弃前文完整版本。

**证据与边界：** 同一回答首个方法含 then bury the ashes，后文总结只说 remove/burn；来源描述先移除蓝色区再 collection，焚烧蓝区后埋灰。

**诊断结论：** ambiguous。

### 15481 · source 15501 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

新版仍保留 temporarily，但其 S 理由明确承认该词未被引用材料陈述，仍用 conditional locking 覆盖全句；这不是误抽消失，而是证据充分性检查放松。上下文段 1 有改密码后解锁的个人经历，可能支持“可能暂时”的另一推导，但新版没有引用或说明这一步，故不能认定已纠正。

**M1 变化：** 4→3 条，仅把警告和持续使用后锁定组合；关键含 temporarily 的 claim 未改变。

**证据与边界：** 新版只引段 2 may lock account，理由写 temporarily is not stated；段 1 的 unlock anecdote 未入该条证据。

**诊断结论：** not_established。

### 15485 · source 15501 · QA

原生标签：有标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

原生 FN→TP 的新增报警全部来自建议句：建议改密码、确保最新版、联系支持。新版把这些建议本身直接变成 claim 并判 U，未把它们限制为可核的嵌入事实前提。按已确定的 advice/non-factual 口径，这不是可靠的漏报修复。

**M1 变化：** 旧版 6 条句切骨架最终 4 条事实；新版成功提取 9 条，却保留 3 条明显建议作为事实。

**证据与边界：** 新 c7/c8 为 It is recommended to ...，c9 为 you may want to contact ...；来源未提该建议不等于建议本身是错误事实。temporarily 仍被以“不矛盾”理由接受，证据口径也未改善。

**诊断结论：** native_gain_with_extraction_contract_regression。

### 17569 · source 12423 · QA

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版把 This movement→胸腔容积增加作为独立待证环节判 U；新版保留整条因果长句并给 S，理由自己承认指代含糊，只说明后半链条相同。文本事实并未删除，但整句通过并不证明第一条因果边获得支持。

**M1 变化：** 6→2 条；新 claim 仍含 This movement，却没有说明它是收缩还是放松；两种运动都在前一句。

**证据与边界：** 段 1 写收缩时膈肌向下移动；段 3 从胸腔容积增加开始，未显式连接 This movement；需要明确推导该连接，不能只用后半链条覆盖。

**诊断结论：** not_established。

### 620 · source 15696 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → positive/partial。

两版仍有 FAA 时间归属 C 和 NTSB investigating U，原生 positive 不变；新版另有 Johnson 复述 dizziness 的 claim 引文重判失败，因此完整→partial。不能把原生检测不变当报告质量没有下降。

**M1 变化：** 旧版 11 条均句切骨架；新版 20 条正常提取，新增细分并保留原事实；1 条未完成，19 条已完成。

**证据与边界：** 新 c6 citation_requery_required；来源直接有 Johnson recalled the flight attendant saying 的原话。该项属于技术失败，不是无依据事实。

**诊断结论：** not_applicable。

### 622 · source 15696 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

关键两条声明在两版基本相同，新版把旅客自述眩晕/三人失去意识以及无人住院判 U；原版均 S。来源是空乘预告眩晕、护士本人 lightheaded、三人 reported loss of consciousness、无人 transported to hospital，确有归属/结局词边界，但不是 M1 找回丢失事实。

**M1 变化：** 旧版 6 条 fallback，新版 6 条正常提取；两条被判 U 的文本没有实质变化。

**证据与边界：** reported loss 与实际 loss、未送院与未住院不是字面等同；自然摘要是否许可应独立裁定，不由原生 negative 自动决定。双方对 fifteen others 是否额外十五人都未质疑，亦说明此审计不能替代全 claim 金标。

**诊断结论：** uncertain。

### 2466 · source 11877 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

关键 NSA concerns 声明在两版相同，新版接受由文章末尾 representatives of the National Sheriffs Association 接 our concerns 的跨句归属。材料支持这一自然读法，未见靠删除具体事实获得负例；但新版反而退回句切骨架，不能把改善归因于更好 M1。

**M1 变化：** 6 正常条→5 fallback 骨架；主要合并 Google 收购和拒绝讨论两事实，NSA 目标本身未删改。

**证据与边界：** 文中给出组织名称及其代表遭拒，再说 our concerns / offends our conscience；上下文一直论述执法受阻和警员危险。

**诊断结论：** plausible_semantic_gain_not_M1_attributable。

### 2471 · source 11877 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

关键 disappointment and offense 两版均保留；原版认为只支持 offense，新版只解释 offense 却把整句判 S。失望是否是合理情绪概括可讨论，但输出没有显式说明这一步，不能视为误抽减少。

**M1 变化：** 9→7 条，多项合句；末尾两种情绪完整保留，未遗漏事实词。

**证据与边界：** 原文 offends our conscience、refusal to dignify our concerns 可支持负面情绪概括；新版理由只覆盖 offense。

**诊断结论：** uncertain。

### 4345 · source 13895 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版拆出 Council 本身是 PAC 的同位语并判 U；新版将它包在贡献句内判 S，理由却用 Council 的 PAC 来支持 Council 即 PAC。这个身份等同没有被来源建立，原生 FP→TN 不是可靠语义改善。

**M1 变化：** 10→6 条；关键同位语没有从文本删除，但独立身份事实被包进复合 claim 后漏检。

**证据与边界：** 来源为 The political action committee for the Health Care Council of Illinois；答案是 The Health Care Council of Illinois, the industry political action committee。for 关系不能证明实体相等。

**诊断结论：** native_gain_with_support_gap。

### 4349 · source 13895 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

新版保留 Campaign finance records show，但把数额合在大 claim 后仅以 amounts and contributor match 判 S；原版单独对来源归属无依据给 U。原文提供金额，却未说信息来自 campaign finance records。此变化属于来源归属核查放松，不是更少误抽。

**M1 变化：** 12→7 条；金额、时间、归属文字仍存在，关键源归属只是与其他金额事实同条。

**证据与边界：** 来源首段说 it is revealed / accepted nearly $2 million，没有 campaign finance records；不能用金额一致替代出处证据。

**诊断结论：** native_gain_with_support_gap。

### 1729 · source 11400 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

同一开场复合声明中 individuals and organizations advocating regular testing，旧版 S、新版因 organizations 无依据而 U。来源列出个人倡导和实验室商业推广，但是否等同组织倡导“定期”检测有范围差异。核心声明两版均来自相同 fallback，不能把原生 TN→FP 直接算 M1 退步或真误报。

**M1 变化：** 21→19 条，但开场同一 fallback 骨架未变；减少主要来自后文合句。

**证据与边界：** 原文 Mark Cuban 每三月、Taylor Swift 提醒筛查、州长立法；实验室段写服务和市场机会，未直接说 organizations advocating regular testing。

**诊断结论：** uncertain。

### 4338 · source 13894 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → unknown/partial。

新版本最后一批三条严格 JSON 失败，已完成前三条都是 S，故 negative→unknown。日期与医学救援归属仍存在于未完成 claim，不能按真阴性计分，也不能解释为语义删减。

**M1 变化：** 两版均 6 条正常提取；3 条 batch-level invalid_model_output。

**证据与边界：** c4 November 13、c5 November 7、c6 administration medical aid；来源分别直接支持，未完成原因均 Completion is not strict JSON。

**诊断结论：** not_applicable。

### 5391 · source 13554 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

两版 5 条 fallback 骨架相同；新版把 admitted ... under duress 判 U，原版视作对辩护说法的概述而 S。源文既有 guilty plea，又有她自述受胁迫；组合为 admitted under duress 是否造成法律/话语姿态变化需语义裁定。可以确认变化不来自 M1 抽取内容。

**M1 变化：** 两版提取和公开目标完全相同；仅 M3 标签/理由变化。

**证据与边界：** 来源写 pled guilty 和 In her defense, she claimed ... coerced，答案写 admitted ... under duress。

**诊断结论：** uncertain。

### 4218 · source 13874 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版单独把 growing tensions 判 U；新版将其与台湾担忧同句后判 S。来源有 ongoing conflict 与 potential outbreak of regional war，“紧张增长”是解释性概括而非直接词面；新版未解释这一趋势推导，不能把合句后通过当误抽修复。

**M1 变化：** 8→5 条；Middle East growing tensions 保留在复合声明，未删除。

**证据与边界：** 原文 potential for outbreak of regional war / conflict continuing to unfold，未直接使用 growing；合理概括边界需作者裁定。

**诊断结论：** uncertain。

### 4223 · source 13874 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版独立核查 US 对台湾 rhetoric 的 concern 并给 U；新版把 military developments 和 rhetoric 合并后 S。原文有美军 likely observing closely，以及作者说 rhetoric should be taken seriously，但没有清楚把后一评价归给美国。合句未解决出处归属，原生改善可能来自忽略该子命题。

**M1 变化：** 13→6 条；US views rhetoric with concern 从单独目标进入合句，文字仍保留。

**证据与边界：** 来源末句规范性 should be taken seriously 的说话者是文章叙述；新版理由把 concern 归于 Pentagon report，不能自动把 rhetoric 评价也归给 US。

**诊断结论：** not_established。

### 4222 · source 13874 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

新版将末句事实部分和台湾建议分开，核到从 might explore possibility of developing 升成实际 development poses a threat 的模态加强，给 U。这个 U 有来源差异依据，原生 TN→FP 不一定是语义退步。原版把事实与建议留在一条而全部 S。

**M1 变化：** 旧版 5 骨架最终 3 条事实；新版 4 条正常提取，把 threat 事实与 should take ... seriously 建议分开。

**证据与边界：** 来源只有 might well be exploring the possibility ... would allow strikes；尚未陈述实际开发。两版仍把台湾 should 建议保留为可判事实，故不能声称 advice 分流已经解决。

**诊断结论：** plausible_semantic_gain_despite_native_regression。

### 5274 · source 13535 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

两版相同 4 条目标，唯一变化是 Fans are left wondering... 从 U 到 S。来源把动机和原谅作为悬念直接向 B&B fans 提问，“观众留下疑问”可作篇章概括，但并非实际观众心理调查。合理概括边界需裁定，不能归因于 M1 误抽减少。

**M1 变化：** 两版均 4 条正常提取，关键 claim 相同。

**证据与边界：** 文章末尾直接向 B&B fans 发问；原版要求明示粉丝心理，新版按悬念表达解释。

**诊断结论：** plausible_semantic_gain_not_M1_attributable。

### 5278 · source 13535 · Summary

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

新版把纯疑问句 Will RJ forgive Luna? 抽为事实并给 U，造成原生 TN→FP。该问题没有断言 RJ 会或不会原谅，不应因来源未给答案而成为无依据事实。旧版正确列为 non-factual；这是明确的提取契约退步。

**M1 变化：** 旧版 5 条事实、排除问题和 Tune in 建议；新版 4 条，其中前3条是合句事实，第4条却是原样疑问句。

**证据与边界：** 来源同样把 forgiveness 留作开放悬念，不能把开放问题本身判成 unsupported assertion。

**诊断结论：** semantic_regression_in_extraction。

### 6276 · source 13713 · Data2txt

原生标签：有标注幻觉；原 v4 → M1-only：positive/complete → positive/partial。

两版都正确区分 null 与 false，对 WiFi/Music 缺失而断言无服务给 U，原生 TP 不变。新版将餐具评价合成一条后引文重判失败，完整→partial；这条事实仍被提取但未核完。

**M1 变化：** 10→9 条；把失望和具体餐具合句，c7 未完成。

**证据与边界：** 结构化源 WiFi/Music=null；餐具评论原文直接有 small plastic spoon / disposable wooden chopsticks；新错误 citation_requery_required。

**诊断结论：** not_applicable。

### 5737 · source 13614 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/partial → negative/complete。

原版营业时段 claim 因未明示24小时格式而 U；新版对同一时段接受 11:0-21:0 为 11AM-9PM，同时补齐原版末条引用失败。两项改善都有可解释依据，未见通过漏掉营业时间得到负例；但时段目标两版同为 fallback，不能归因于新 M1 语义规则。

**M1 变化：** 旧版18条均fallback，末条未完成；新版19条、前14条fallback，末尾评论摘要拆成两条且完成。

**证据与边界：** 源 hours Tuesday-Saturday=11:0-21:0 / Sunday=12:0-20:0，常规时间读法直接支持；原 c18 报 citation_requery_required，新版相关两条均S。

**诊断结论：** plausible_semantic_and_completion_gain_not_M1_attributable。

### 5739 · source 13614 · Data2txt

原生标签：有标注幻觉；原 v4 → M1-only：positive/partial → positive/complete。

新版补齐旧版 3 条 JSON 批失败，原生 TP 仍由营业时间等事实维持。但新版把“第三位评论者提到 toppings/free delivery”判 S，实际这是第二位评论者，第三位只说20年光顾、价格和街机；旧版该条 C 更符合提供数据。完整率改善不能遮住出处错判。

**M1 变化：** 15→12 条；部分属性/时段被合并，旧版未完成的评分、差评和第二位好评新版本均完成。

**证据与边界：** review_info[1] 有 toppings/free delivery；review_info[2] 无此内容。新版还把 majority customers 解释为全体顾客而U，属于范围边界，未改变最终 positive。

**诊断结论：** mixed_completion_gain_and_semantic_regression。

### 10068 · source 14778 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → positive/partial。

两版同样9条fallback，新版前3条核查批失败（包括原版因Music=null而U的服务声明），另把搬家影响服务速度判U，因此回答positive不变但未完成项增加。不能把最终同为positive解读为同一错误已稳定核出。

**M1 变化：** 两版提取完全相同；新版原c1-c3未完成，其余6条完成。

**证据与边界：** 评论写新址后 still getting the hang of how to serve so many people，以及 apologizing for slow service, when it is actually about the same as other places。是否能推出搬迁导致速度变化有边界；两版核查目标未变。

**诊断结论：** not_applicable。

### 10069 · source 14778 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：unknown/partial → negative/complete。

两版同样12条fallback；原版搬迁/服务/食物改善那条引文重判失败导致all-S partial unknown，新版完成该条并S。来源评论直接描述新址、服务调整和最近食物改善，未见通过删除事实得到negative；这是完成恢复，不是提取改进。

**M1 变化：** 两版同样目标，末尾建议 It may be worth trying 均不作为事实。

**证据与边界：** 原 c11 citation_requery_required；新版对应搬迁评论被完整核查，原材料 review3 包含 moved/new place、service adjustment 和 back on their game。

**诊断结论：** completion_gain_not_M1_attributable。

### 7776 · source 14169 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → positive/complete。

新版把营业时段合句并退回句切后，因来源没有显式定义 AM/midnight 而 U；来源 hours 为常规10:30-0:0/1:0，原版按24小时读法正确核查。这与5737相反方向显示相同M3政策对时间表达不稳定，并非答案缺少来源。

**M1 变化：** 旧12正常条→新6fallback；时间事实保持完整，只是两类日期合句。

**证据与边界：** source hours Monday-Thursday/Sunday=10:30-0:0，Friday/Saturday=10:30-1:0；不能因未写AM而一概视为无依据。

**诊断结论：** semantic_regression_in_judgment。

### 7140 · source 14060 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版将不流畅的 supplier of ... delis ... 枚举分配为 supplier of delis，判U；新版保留完整类别枚举后S。按自然业务类别读法，新版可能避免了机械展开产生的奇怪命题；按严格语法，supplier关系本来又在答案中。没有独立作者裁定，不能把23→7条直接当漏核或纠错。

**M1 变化：** 旧版23条将各类别/三明治赞誉/属性分别拆开，新版7条保留枚举与复合句；没有直接删除列出的类别。

**证据与边界：** 结构化 categories 包含 Restaurants, Hunting & Fishing Supplies, Delis, Sporting Goods, Automotive, Car Wash 等；它提供类别归属，而不是明确 suppliers-of-delis 关系。

**诊断结论：** ambiguous。

### 7141 · source 14060 · Data2txt

原生标签：有标注幻觉；原 v4 → M1-only：positive/partial → positive/complete。

新版补齐旧版最初3条JSON批失败，保持对 locals and visitors popularity 的U。与此同时同一新版第1条支持 local business，第12条却以 local business 未被证明判U；这是下游判决不一致，完整率改善不能证明语义全面提升。

**M1 变化：** 旧14条含10fallback、前三条未完成；新15条正常提取且完整。末尾更粗的popular复合句仍保留关键范围。

**证据与边界：** 来源地址字段与评论 Support local businesses 可支持当地商户；新版自己的首条已经认可同一主体local身份。旧版staff great service U→新版S也是相同事实的解释差异。

**诊断结论：** mixed_completion_gain_and_semantic_instability。

### 10818 · source 14908 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：negative/complete → unknown/partial。

两版均8条相同fallback，原版完整全S，新版营业时间条目未完成，其余7条S，故negative→unknown。没有删除营业时间事实，也不是新M1修复或新语义判断。

**M1 变化：** 两版提取目标相同；新c2失败。

**证据与边界：** 源hours七天均11:0-16:0，breakfast/brunch来自categories。新版 errors 保留该条核查失败，不能把未完成当S或U。

**诊断结论：** not_applicable。

### 10819 · source 14908 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

关键 different customer 目标两版相同；原版把上下文中第三条负面评论与前两位的区别判为缺依据，新版依据独立评论条目和正负体验接受。正常篇章读法下有合理支持，未见通过漏掉Groupon或反复关门事实得到negative；但不能单独归因于M1。

**M1 变化：** 两版19条、14fallback，末段抽取结构亦相同；关键U→S文本未变。

**证据与边界：** review_info中依次为失望的碗体验、juice fast正面体验、Groupon无法使用负面体验；新版利用了完整评论结构，原版只认局部负面经历。

**诊断结论：** plausible_semantic_gain_not_M1_attributable。

### 7022 · source 14038 · Data2txt

原生标签：有标注幻觉；原 v4 → M1-only：positive/complete → unknown/partial。

旧版用营业时间直接反证给C；新版同样目标的首批JSON失败，营业时间c3未完成，其余6条均S，成为unknown_positive。原生漏报计数虽不增加，但不能宣称FN=0验收达标；这里确有原生阳性未决，不能算TN或FN。

**M1 变化：** 两版10条fallback完全相同，末尾建议被排除；新版前三条未完成，未靠删除错误营业时间变成negative。

**证据与边界：** source hours weekday12:0-20:0、Friday12:0-21:0、weekend11:0起，直接反驳每天11AM-11PM。新版对oysters known-for从U转S有概括边界，但不能代替未完成的营业时间检测。

**诊断结论：** technical_regression_on_positive_case。

### 7033 · source 14040 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版首条已经把当地地址支持为local business，末尾独立local restaurant又判U，内部不一致；新版保留当地地址与评论总结后S，正常地域语义下有依据。未见为了negative丢掉原事实，但变粗合句与下游随机性同时存在，不能只据该例认定新M1有效。

**M1 变化：** 21正常条→12条（1 fallback）；主要合并同一评论内的子事实，末尾local身份仍在总结内。

**证据与边界：** 来源name/address/city/categories明确该餐馆位于Goleta；原版自己的首条S已接受这一当地含义。

**诊断结论：** plausible_semantic_gain_not_M1_attributable。

### 6139 · source 13688 · Data2txt

原生标签：未标注幻觉；原 v4 → M1-only：positive/complete → negative/complete。

原版的三个U涉及高度推荐、4星代表正面体验和local business；新版相同目标全S。local身份与4星正面概括有常规语义支持，原版甚至首条local已S而末尾U。highly recommended从really enjoyed/prefer推导仍是推荐强度边界，应与前两项区分，不把整例直接认证为全真纠错。

**M1 变化：** 两版15条，原版3fallback、新版0；关键三个含争议词的目标均保留，未发现删除事实换取negative。

**证据与边界：** 评论明确 really enjoyed Beef Thai Tom Yum、prefer Thai one，字段business_stars=4.0，地址Goleta；没有逐字 highly recommended，但强烈个人喜好可构成合理推荐读法。

**诊断结论：** plausible_gain_with_residual_semantic_ambiguity。

## 可复核材料

本目录 dev-semantic-audit.json 保留全部变化案例的原答案、所有上下文、原生 span、两版公开输出、提取轨迹、完成记账与逐条诊断。原始日志在项目 results/v4-m1-faithful-20261023/dev/predictions.jsonl；原生标签来自 dataset/ragtruth-blind-v1/recovery/native_gold.jsonl。

日志快照 SHA-256：951f9bbaa6c28231ad9dda85da6be52416f0225e0aa2347683db82cf3ab91538。运行中快照会更新；只有最终 completed 快照覆盖全部已登记案例。
