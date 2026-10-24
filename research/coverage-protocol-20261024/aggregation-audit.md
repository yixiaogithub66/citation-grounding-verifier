# Coverage protocol 汇总审计

2026-10-24。这是 AI 只读汇总审计，不是人工终审或新的语义重评分。读取范围为离线汇总代码、最终语义汇总、两份最终 review、解盲 key、操作审计及本次修正保留的派生汇总副本。未调用模型，未修改最终评分、病例、冻结 run、Prompt 或推理代码；本代理唯一产物为本报告。费用部分从操作审计给出的 token 数独立重算，再对照语义汇总，没有重新审计 provider 原始轨迹。

**主汇总计数核对通过。** 以下明确保留共同有效子集的退步、技术无效的未知值，以及纯离线展示修正，不能把结构完成改善写成普遍语义改善。

## 身份、schema 与局部目标 ID

- 两份最终 review 合计 120 条且 review_id 全唯一，与 private-key 及 scored_records 一一对应。最终 review 的字段集合、类型、布尔/null、目标及 issue 枚举、非负整数索引与 claim_indices 去重符合评分 schema。动态索引上界由汇总代码针对盲包 claims 检查；此次未重新读取全部盲包来重做语义评分。
- 逐字段核对最终 review 和 key 合并后的 scored_records，全部一致；最终 review 文件哈希与 semantic-analysis.json 记录吻合。
- 每臂恰好 20 case × 2 repetition = 40 个唯一尝试、88 个目标机会、10 个 pure-NF 输出机会。不是 40 个独立回答；独立 case 数仍为 20。
- 逐 case 核对目标数量及 f1…fn 集合。事实数量序列为 3、2、0、3、4、3、0、2、2、4、0、3、3、2、0、4、4、3、0、2；没有跨 case 复用局部 f1 的身份。
- 配对 lookup 使用 `(case_id, repetition, arm)`，目标差集只在同 case/同 repetition 内比较；多事实子集先按 case_id 选其局部目标集合。未发现把所有 f1 合成一个全局事实的错误。
- 技术无效记录的 selection/strict 都是 null，standalone/source 目标也为 null。不可读输出所有目标 content 为 null 且不映射 claim。strict=true 的记录均 valid、selection=true、全部目标三轴为 true，且无 claim issues。
- 最终评分准确保留已采纳交叉裁定：双重 possessive 的 content/source=true、standalone=null；拆分规则的 f1→[1] 三轴 true，同时额外 claim 0 的独立归属 issue 令整条 strict=false。

## 全尝试主结果

下表每臂输出分母均为 40，目标分母均为 88；both-repeat case 分母为 20。

| 指标 | legacy | ledger_text | ledger_id |
| --- | ---: | ---: | ---: |
| 结构有效 | 33 | 37 | 40 |
| selection pass | 32 | 34 | 35 |
| strict joint pass | 23 | 28–29 | 30 |
| 两次均 strict 的独立 case | 8 | 10–11 | 14 |
| 已完成 content 目标 | 73 | 83 | 88 |
| 已完成 standalone 目标 | 64 | 73（另 1 未定） | 81 |
| 已完成 source-supported 目标 | 71 | 83 | 88 |
| 有效输出中的明确 content 遗漏 | 0 | 0 | 0 |
| 技术未服务目标 | 15 | 5 | 0 |
| 有效 false-claim 回答数 | 1 | 3 | 5 |

Text 的 strict 上下界只来自一条有效输出的独立措辞未定，不能当作两份不同重复抽样结果。主结果的 content 目标增加是“成功服务目标”的增加；legacy 可读 raw 中这些目标本来已经出现，不能据此声称首次事实提取召回从 73 提高到 88。

| Pure-NF，分母各 10 | legacy | ledger_text | ledger_id |
| --- | ---: | ---: | ---: |
| 正确且有效 | 7 | 9 | 9 |
| 有效但含错误 claim | 1 | 0 | 1 |
| 技术错误 | 2 | 1 | 0 |

## 无效 raw 分账

最终新增的 `invalid_only_diagnostic` 与独立计算吻合：

| 仅技术无效输出 | legacy | ledger_text | ledger_id |
| --- | ---: | ---: | ---: |
| 回答数 | 7 | 3 | 0 |
| 可读 / 不可读 | 7 / 0 | 0 / 3 | 0 / 0 |
| 目标机会 | 15 | 5 | 0 |
| raw content 保留 | 15 | 0 | 0 |
| 明确遗漏 | 0 | 0 | 0 |
| content 未知 | 0 | 5 | 0 |
| 可读无效回答中的 false-claim 回答 | 2 / 7 | 0 / 0，不可评 | 不适用 |

Text 的三个不可读 raw 不能因 issue 数组为空而称为“零错误”。五个未知目标也不能称为“零遗漏已证实”。legacy 的 15/15 raw 保留仅属内容诊断，不给任何完成、standalone、provenance 或 joint 信用。

原有 `raw_diagnostic_*` 汇总的是所有输出中的可读内容，包括 valid 与 invalid；它不是 invalid-only。当前增加的 `raw_diagnostic_scope` 已明确范围，新增表将无效部分独立列出。原有全输出 content 保留计数 88 / 83 / 88 不应与本节 15 / 0 / 0 混用。

## 共同有效配对与严格增益来源

| 共同有效子集 | n | ID selection | 对照 selection | ID strict | 对照 strict |
| --- | ---: | ---: | ---: | ---: | ---: |
| ID vs Text | 37 | 32 | 34 | 27 | 28–29 |
| ID vs legacy | 33 | 28 | 32 | 23 | 23 |

这些数值均已独立重算。ID 相对 legacy 的全尝试 strict 净增 7，可分解为：原 7 个 legacy coverage-invalid 位置中 ID 全部 strict=true，贡献 +7；共同有效 33 条中净变化为 0。**净增全部来自这 7 个位置，不等于共同有效部分没有变化。** 后者实际有 3 获益和 3 退步相抵：

- ID 获益：cp011/r0、cp013/r0、cp013/r1。
- ID 退步：cp018/r1、cp002/r0、cp015/r0。

7 个 coverage-invalid 位置是 cp007/r0、cp005/r0、cp005/r1、cp015/r1、cp004/r1、cp002/r1、cp014/r1；其 private-key 原始错误均为 meaningful-source-text unaccounted coverage 拒绝，与 operational-audit 一致。它们涉及 6 个独立 case，不是 7 个独立回答。

ID/Text 的全尝试 strict 优势为 1–2 条，而共同有效部分为 ID 少 1–2 条。Text 三个 transport-invalid 对应位置中 ID 都 strict=true，这三个技术结果解释了由共同有效到全尝试的差异。不能把这一差异归因于已经观测到的 echo 错误；操作审计报告收到的 Text 输出没有 echo/schema 拒绝。

## 多事实单元与 masking

预定义三个 case 及目标为 cp001/{f1,f2}、cp005/{f2,f3}、cp017/{f2,f3}。每臂 3 个独立回答 × 2 个目标 × 2 次重复 = 12 个目标机会；逐 case 限定后计数，没有 f1/f2 跨 case 串联。

| 多事实单元目标 | legacy | ledger_text | ledger_id |
| --- | ---: | ---: | ---: |
| 机会 | 12 | 12 | 12 |
| 已完成保留 | 8 | 12 | 12 |
| 可读 raw 保留 | 12 | 12 | 12 |
| 有效输出中的明确遗漏 | 0 | 0 | 0 |

核对 80 对配对记录及全部局部目标后，本轮未观察到新候选有效遗漏，也未观察到同一遗漏由旧结构拒绝、新结构接纳的 masking。必须区分两类集合：

1. **新语义退步：** 对照 raw 明确保留的目标，与 candidate valid 明确 missing 的目标取同 case/rep 交集。
2. **同遗漏 masking：** candidate valid、control invalid，且双方 raw 对同一局部 fact 都明确 missing。

candidate unknown 对照 control retained 应另列未知，不能塞进明确遗漏集合。上述两类当前均为 0；所有可读输出的 content_missing 本来就为 0，因此这个结论不依赖宽松或精确化后的离线字段公式。对 Text 三条不可读控制输出，仍存在五个未知目标，不能把“未观察到”写成对未知内容的非劣证明。对 legacy 的 7 条无效 raw 均可读且 15 个目标全部保留，故本轮实际没有“旧 raw 真遗漏被拒绝”的正例来检验 masking 检出能力。

## 费用与操作审计对照

按冻结参考价：输入 USD 0.30/百万、缓存输入 0.006/百万、输出 1.20/百万。独立使用 operational-audit 的各臂输入、输出、cache hit/miss token 数进行十进制计算，结果与 semantic-analysis.json 一致：

| 臂 | usage 已知 / 尝试 | 已知 cache-aware USD | 已知 all-miss USD | 全部成本 |
| --- | ---: | ---: | ---: | --- |
| legacy | 40 / 40 | 0.014891946 | 0.0195198 | 已知 |
| ledger_text | 37 / 40 | 0.023446668 | 0.0300699 | 未知 |
| ledger_id | 40 / 40 | 0.019025148 | 0.0260982 | 已知 |

已知 token 总计 98,289 input + 38,501 output，与操作审计吻合。Text 保留 `complete=false`、`priced_calls=37`、`unpriced_calls=3`，两个总成本字段均为 null；三个 transport 错误的 usage 没有当作零。其原始错误和 case/rep 与操作表一致。

ID/legacy all-miss 比为 **1.337011649709526**，即高 **33.7011649709526%**，超过预注册 1.30×。ID 的完整 40-call 成本低于 Text 已知的 37-call 小计；Text 的完整成本及相对完整总价的精确降幅仍未知。本审计没有将参考价格当作实际账单，也没有因 thinking-disabled 请求设置而报告测得零 reasoning token。

semantic-analysis 所记 freeze 与 responses 哈希和 operational-audit 的完整性表吻合。冻结、调用身份、durable 文件及 HTTP 时序的底层完整性结论来自该操作审计，本次未将阅读操作报告冒称为重新逐个核验所有 provider 文件。

## 离线报告修正及审计边界

审计发现并由 root 仅在派生分析中修正：

- `per_repeat.*.both_repeats_strict_case_interval` 原为 [0,0]，实际是单次切片不适用；现为 null。顶层 8、10–11、14 不变。
- 新增 invalid-only 诊断与全输出 raw 范围声明，避免将原有 raw 汇总误读为仅无效输出。
- 将新遗漏、同遗漏 masking 及 candidate-unknown 分开定义和记录，不把 unknown 算成明确 missing。该字段精确化不改变本轮零遗漏/零 observed masking 的结果。

旧派生文件被保留以供核对。已确认展示修正前后 120 条 scored_records、两份最终评分及其哈希、全尝试主计数、费用和多事实子集不变。这些是报告计算的澄清，不是看结果后修改推理、Prompt、实验输入或语义裁定。

主数值通过并不建立泛化或生产有效性。尤其须同时报告：共同有效子集的 selection/strict 未改善、ID false-claim 回答更多、Text 三个 transport 不可知，以及 ID 对 legacy 成本超阈值。

## 审计时最终哈希

最后一轮核对确认：80 对配对的三个集合字段均与逐对、逐局部 fact 重算相同；旧派生汇总与当前版本的 scored_records、最终 review 哈希、费用、多事实子集及原有全尝试主字段完全一致。所有数值修正仅限上述报告口径。

| 文件 | SHA-256 |
| --- | --- |
| summarize_reviews.py | `7e3caa31591ddca592ea5935ab467da198ec6d7f2766a273ca3b1f75d3649d02` |
| semantic-analysis.json | `955f97ba255401dfa6a9ecda5366b547c224cb6649661cc543aafeec1b0fedb8` |
| semantic-analysis-initial.json | `d7dbe3a7beb4106b7d5a5fd37d44eb09c6b8b54ce22c56bb0486398672df9808` |
| semantic-analysis-pre-mask-audit.json | `a7d5f4e2afa3363018463857cb304176ddccf0e1c76e450c2c38cc9e0741ec4b` |
| review-part1.json | `bc32522233af399349c84e55fd4ae83b8982043d99824060cd976107cedd8545` |
| review-part2.json | `c8dbc0efe60363e3aa42c971505b265cef173f46cd46abdb56184c7a8d7169e6` |
| review-packets/private-key.json | `0b2b6834916f9c90a88e0133129d4e59b9b268f415ca004b8d6e8cb4e543e473` |
| operational-audit.md | `37333bd129f41e3ea11e1e84a99f103f8df1913613512fd28633cc49f17507be` |
