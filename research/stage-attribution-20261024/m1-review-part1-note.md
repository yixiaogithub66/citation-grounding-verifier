# M1 part1 盲审说明

仅阅读本 part 的 m1-part1.json、PLAN.md 与 case-audit.md。未读取 private-key、arm 映射、候选 Prompt、其他实验输出、成本或分数。40 份 raw 均可读，全部逐条语义审阅；本审核未把可读等同于协议合格，也未查看结构评分或据此排除输出。它是辅助 AI 语义审核，不是作者终审。

## 判定原则与观察

- 内容覆盖按完整答案可恢复的实际断言判断；不要求与参考字符串完全相同。多条忠实输出可联合覆盖，例如北侧训练区已检查与签字前不得开放。
- source_sufficient 可以使用原答案中明确的共同先行词。此处诸如 source 只写 then/that value/one/it 的条目，在同句已有午夜后/二十/头盔/东侧横移区时均可判来源充分。
- standalone 单独要求输出不依赖可在原答案展开却未展开的指代。本 part 出现 Setting four 未说 gain、“该组”“这套设备”“场馆”“这个干燥流程”、未标 D4 范围的浸泡容器及 that ratio 未解开的情况；这些输出仍可能 content_retained=true。
- this observatory 原答案没有专名先行词，允许局部站点称谓保留，不从 evidence context 补专名，也不因材料未给专名扣分。
- 红灯校准而非故障按同一指示含义的对照定义判原子性合理；K6 的有序维护链按有序流程处理，不强制拆。两种做法都不拿固定目标数当作输出条数要求。
- 把请求/偏好改写成 should、is to be、the speaker prefers 仍是误纳；缺少客观前提时，第三人称包装不改变 NF 身份。尤其纯 NF 回答中出现多个这类 claims 时，no_false_claims 和 all_claims_well_formed 为 false。
- 两份输出将含真实事实前提的整句划进 NF，尽管又正确提取了相同事实：m-7ad251ad1c5ee13826fc（公共阅听室耳机），m-3c2cdf70f11f37c41d6b（D4 湿润检查）。两者 no_fact_in_nf=false，不能由 reason 里声称“只指建议部分”抵消实际 span。
- 忠实重复不单独算 FP。本 part 额外动作行的错误依据是将明确 NF 请求/偏好变成核查声明或改变局部条件，不是仅因为字面重复。

## 冻结参考歧义：保留敏感性而不改标注

以下四份的 t3 均逐字保留明确事实理由：R2 bench procedure requires cleaning while the connector is energized。冻结目标另要求 connected to an energized port；port 只在前面的 Please leave... 请求中。狭义事实前提读法认为抽取完整；严格参考读法认为缺少连接 port。故 content_retained/faithful=null，保留两种解释，不确定计为遗漏或通过，不改冻结目标：

- m-614d3d2b2a2ececc9760
- m-69d2d01956b878a9ab2a
- m-746bfc9662f174e3cf71
- m-d6ce56a42c963f024749

其中第一份还有额外请求动作行；这些误纳独立判定，不用来替事实理由补 port。最终汇总应对所有臂统一应用这一双读边界。

JSON 已检查 40 个唯一 review_id、与盲包顺序一一对应、目标数一致、claim_indices 全部合法，每条目标和异常均给出具体原文依据。未计算或比较臂间结果。
