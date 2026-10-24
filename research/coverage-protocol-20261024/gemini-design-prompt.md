你是本机 Antigravity CLI High 辅助方法学/协议审查者。本次只审给定设计：禁止调用工具、浏览、终端、文件写入。用户要求处理覆盖协议问题，换新样本实测完成率、事实保真、成本；绝对禁止benchmark特调。不要提出针对案例的提示例子/关键词/例外。

现状：M1输入原answer，输出atomic claims[{claim_text,source_span逐字子串}]与non_factual_spans[{text逐字子串,reason}]。代码按两个列表各自来源顺序逐字匹配 occurrence，检查所有有意义字符在claim来源或NF片段并集中；失败则此初次输出invalid。模型不能静默把遗漏文本转NF。步骤建议本身NF，但其中已断言事实前提要提取；保留条件/否定/数值/归属/模态，去指代；M1独管atomicity，无runtime合并。

前一批已曝光诊断：152调用里20个结构失败（18覆盖缺口+2NF来源顺序错误）。新只读细查18缺口：17仅是连接/组织文字未记账，但1个raw确实漏整项事实。旧报告“所有有效输出无漏提”成立，但不应推断所有无效输出都是纯格式错。我们不把旧具体文本放进新prompt。上一轮双向复查多数收益来自二次生成救结构，成本约单次2.53倍，暂未合入production。

拟做20条全新独立角色AI起草诊断回答，5新领域、中英各10，15 factual/mixed（每条2–4目标）+5NF，长度<=1200，长短/标点/重复出现/跨句事实均有。作者不看候选实现，另角色预审目标；非作者金标、非真实分布泛化证明。每个回答2重复×3臂=120单次调用，模型deepseek-flash/thinking disabled/8192/JSON/no retry/no fallback/no M3，轮换顺序，全部事先冻结，原production不改。

三臂：
1 legacy：当前prompt+原answer+当前精确substring/coverage validator。
2 ledger_text：来源单元账本+逐字原文source寻址。
3 ledger_id：同一来源单元账本，仅用ID寻址。
主要归因比较2vs3；1vs2/3只是整体协议替换比较，不能把其增益单独归给ID。

共同来源单元由纯标点/换行边界确定，保持原始字符串逐字符拼回，无Unicode/数字/字母归一化。所有单元按序显示{id,text}；两ledger臂输入完全相同，只显示完整单元列表不重复整段answer。单元仅为地址，不代表句子完整/事实原子性，允许一单元有多事实、一个事实跨多个单元、同一文本不同occurrence有不同ID。模型仍负责atomic claims和完整保真。

ledger统一输出JSON：
{"claims":[{"claim_id":"c1","claim_text":"standalone asserted proposition"}],
 "coverage":[{"source":"...","kind":"factual|non_factual|mixed","claim_ids":["c1"],"reason":null}]}
text臂source必须等于对应输入单元完整text；ID臂source必须等于对应id。coverage严格与全部输入单元逐个同序一一对应，无遗漏/重复/自动补全；kind F需要至少1有效claim_id且reason=null，NF必须空claim_ids且非空reason，mixed需claim_id和非空NF reason。所有claim必须被至少一单元引用，claim数组按首个来源单元顺序；同一claim可挂多单元，多claim可挂同一单元，不进行字符串拼接生成claim或语义合并。

代码只重建每条claim对应的精确原文unit范围列表。为与旧输出诊断兼容，可附连续包围source_span，但该包围范围只作显示，语义来源核对必须用真实referenced unit列表；不把包围范围内未引用文字自动算claim或NF。mixed单元的NF标志只说明同时含两类内容，不能把整个单元都贴作non_factual_spans。报告明确新protocol覆盖更粗，不能宣称与旧字符覆盖约束等价，也不以100% unit ID覆盖证明事实全部提取。

新实验必须人工式AI盲审每条输出：固定事实目标保留/缺失、错误claim、source association正确、独立自足（Its/该室等未展开单列严格轴）、必要/充分条件/范围/归属损伤。技术失败不当NF或零FP。除了“结构有效且事实保真”固定全分母，额外审阅可解释raw claims的语义覆盖（diagnostic-only，绝不把无效输出升级成功），以识别新协议是否只是藏住旧validator本可暴露的语义遗漏。展示同样单次预算的token与参考成本，不把改变schema后的通过率说成生产完成率或总体准确率。

请用中文约800–1200字审查：
1 哪些设计缺陷会让完成率成为“放宽校验”的假改善？如何最小改动地限制它？
2 schema是否有不必要负担/可避免歧义（尤其mixed、跨单元、重复文本、来源包围范围）？可以建议更简洁的、可直接实现的schema，但不要增加新的语义判决代码。
3 三臂是否足够区分记账粒度和source复制/ID效果，哪些结论仍不能作因果归因？
4 运行前如何定通过门槛/停止条件，才能同时公开退步、成本和机会不足？
本轮方案尚未实跑；不要编造结果。所有建议由主代理核对，不能冒充作者终审。
