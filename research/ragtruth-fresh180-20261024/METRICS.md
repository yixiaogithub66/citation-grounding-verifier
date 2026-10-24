# 新 180 条三方案比较：预登记评分约定与审计清单

2026-10-24。只读检查既有评分代码和旧 small30 报告后形成；本文件编写时未读取本轮待选原文、回答或标签，未选数据，未调用模型，未改生产推理。最终生效版本须随本轮推理前冻结清单一起绑定。

## 比较对象和范围

- 固定同一批 180 个回答，30 个来源，每来源 6 个生成模型回答；QA / Summary / Data2txt 各 10 个来源、60 个回答。每个回答分别运行 `baseline`、`minimal`、`optimized-v4.0`，预期 540 条唯一的回答 × 后端记录。
- 这是三套既定系统的端到端比较，不是同计算量的算法消融。冻结并公开 minimal 的 thinking / 输出预算与 v4 的分阶段配置；不得在结果出现后调整预算求公平或挑选更好版本。
- 同一来源的 6 条回答不是 6 个独立来源。样本数为 180 个回答、30 个来源，不能称为 180 个独立来源。生成模型身份只能用于抽样规格核验、结果分层，不能进入推理策略。
- 原生指标无需等待作者裁定即可计算；本轮不得据此宣称通过“裁定后真 FP”的正式验收。

## 原生回答级判定规则

主评分直接复用冻结的 `scripts/score_v4.py::score_records`，每次明确传入三个 backend、全部 manifest、native_gold 和实际 inputs，以共享公有契约检查引用。原生阳性严格定义为 `bool(labels)`，保留 `implicit_true`、`due_to_null` 等原始标注，不按我们自己的任务偏好筛除标签。

| 公有输出 | 回答级预测 | 执行状态 |
| --- | --- | --- |
| 合法 complete，至少一条有效 C/U | 阳性 | complete |
| 合法 complete，全 S | 阴性 | complete |
| 合法 complete，空 claims | 阴性，并单列空报告 | complete |
| 合法 partial，已完成部分至少一条 C/U | 阳性 | partial |
| 合法 partial，已完成部分全 S | unknown | partial |
| 执行错误、无输出、缺失记录、公有契约不合法 | unknown | error |

unknown 按原生正负分别报告，不进入 TP / FP / TN / FN。合法完整空报告不能在看到标签后改为 unknown；它可能是恰当拒答，也可能漏掉事实，因此必须同时报告空 claims 数、非空回答对应的空 claims 数，语义原因只能另作诊断。

## 主要表格及分母

每个方案必须同时列出：

1. **正确决策 / 全部 180 条**：`(TP + TN) / 180`。这是端到端正确决策产出率；unknown 不算正确，但不被伪装成 FN 或 FP。
2. **完整报告率**：`complete / 180`，以及 complete / partial / error 数。partial 中出现有效 C/U 可以完成回答级检测，却仍不是完整报告。
3. **决策覆盖率**：`(TP + FP + TN + FN) / 180`，unknown positive / negative 数。
4. 已决 accuracy、precision、recall、F1，明确标为条件指标，并提供原始 TP / FP / TN / FN。不同方案已决分母可能不同，不凭条件 F1 单独排名。
5. 已完成 claim 数、已知未完成 claim 数、未知 claim 总数的回答数、`completed/(completed + known_failed)`。这只是被系统提取且可记账目标的执行完成率，不是事实提取召回率。
6. 原生正负总数、按任务（每类 60 条）及生成模型分层的计数。先看类别比例，避免把全报阳性方案的高 recall 或某类 accuracy 当作区分能力。
7. 引用逐字合法数 / 实际检查数，并注明这只验证索引、子串、偏移等机械契约；无引用时分母为 0，比例为 null，不是 100%。

原生 RAGTruth 不提供完整原子 claims、S/C/U 判决及证据金标，因此不得据此报告“三分类准确率”、完整 claim 召回率或语义引用正确率。原生 FP 只表示对原生回答级标签的误报，不能直接叫“作者裁定真 FP”。

保留 `legacy_whole_case_failure` 原样作为历史对照：所有 partial 均按整条失败处理；旧检测 F1 是将正类失败计 FN、负类失败计 FP 的**悲观下界**，不是 RAGTruth 官方分数，也不能与新的已决 F1 混写。

## 配对比较与区间

- 主差值为 `v4 - minimal` 的全部 180 条正确决策产出率、完整报告率、决策覆盖率；同时列 `minimal - baseline` 和 `v4 - baseline`。已决 F1 差值保留，但注明各自可能条件于不同样本。
- 同时给出全 180 条 correct / wrong / unknown 的 3 × 3 配对转移表，用于区分技术恢复与已有判定的改进、退步。再给共同已决子集的双向胜负计数和子集大小；此子集是结果后定义的描述性分析，不能替代全 180 条主比较或单独证明语义因果收益。
- 为兼容历史，主区间复用 **whole-source pooled percentile bootstrap，2,000 次，95% 区间**，并在冻结清单指定 seed。一次抽取一个 source_id 时，必须保留该来源全部 6 条回答和全部 3 个后端，三个后端使用相同来源抽样。
- 不按 180 条回答独立重抽。只有 30 个来源，区间仍可能较宽；单次生成不能估计相同请求重复调用的模型随机性，bootstrap 也不能消除服务时间变化。
- 既有 `score_v4` 的 pooled bootstrap 可能改变三任务的抽样比例。这是历史口径，保留即可。如增补“每任务分别重抽 10 个来源”的分层区间，应在冻结前声明、同时保留历史 pooled 区间，不能按结果挑更窄的一种。
- 0 分母指标维持 null；bootstrap 中未定义重复次数单列，不强置 0。按任务、生成模型和各 pair 的结果主要作为描述性诊断，不开展结果后选择的显著性宣称。

## 成本、时延和调用总账

复用 `scripts/analyze_v4_nf.py::runtime_summary` / `reference_cost` 的逐调用累计方式。计入初判、修复、复核、失败尝试及运输重试；不得只汇总成功输出。

- 同时报输入、输出、reasoning、缓存命中 token，调用数，缺 usage 调用数，缺缓存账调用数，返回 model / fingerprint 分布。reasoning token 是 completion token 的组成部分，不重复加入总 token 或费用。
- 两种费用并列：实际记录缓存份额对应的固定参考价估算；**统一按所有输入未缓存计价**的标准化参考费用。后者便于比较缓存命中不同的系统，但仍不是账单，也不消除输出长度和模型随机性。
- 可沿用历史固定参考单价：输入 0.30、缓存输入 0.006、输出 1.20 USD / million token。若采用此价必须明确为冻结的比较参考，不声称是当日供应商正式价格。
- 某次调用 usage 缺失时，显示已知小计和未计价调用数，总额为 unknown；缺 usage 不等于零费用。每条记录应有 telemetry.calls 列表，避免整条 telemetry 缺失被误当 0 次调用。baseline 的零模型调用与零模型费用单独验证。
- 报全 180 条的单回答 mean / P50 / P95 wall latency（含其失败和重试），同时记录外层并发、v4 内层并发、运行顺序和全轮 wall time。单回答时延之和不等于并发运行总时长。费用 / 回答使用固定 180 分母；共同成功子集仅可补充。
- 三后端应使用冻结且与标签无关的调度顺序，不按难度动态选择先后；记录执行位置以检查缓存/服务时间偏差。

## 已发现的复用边界与非生产修补建议

1. `score_v4._partial_bootstrap` 仅生成 v4 对 minimal / v3 的配对区间，当前三方案比较缺 baseline 配对及 complete rate 差值。可在新外层报告补全，勿修改历史评分定义。
2. `runtime_summary` 的执行顺序分层只遍历 index 0 / 1，原本用于双方案实验。三方案若赋 index 2，应在外层补全第三位置，或明确没有记录该分层；总 token、总费用、总体时延累计本身不受这点影响。
3. `runtime_summary` 默认每条记录有 latency，且 `usage_summary` 将缺 telemetry 视为没有 calls。新 wrapper 必须先验证 540 条完整唯一记录、每条 telemetry.calls 与非负有限 latency，再汇总；对缺失不得默认为零。既有 `ragtruth_score` 单独有 records_missing_telemetry 诊断，可作为交叉检查。
4. `score_v4` 在提供 inputs 时按实际 context 重新验证公有报告。应强制提供 inputs，不能只依赖 journal 中的 schema_valid。引用重验证不证明支持关系。
5. 后端输出的 completed claims 数本来可能不同；不能用“v4 返回更少 claims”推导更精准，也不能由更高已提取 claim 完成率推导遗漏更少。

## 完成后独立核对

离线独立重算不调用模型、不改预测、不重标金标。核对 180 inputs / manifest / native_gold ID 和哈希一致、30 来源每组 6 条、每任务 60 条、540 回答 × 后端唯一槽位；冻结推理源与配置未变；逐条公有契约、空输出、partial、unknown；逐后端/逐任务混淆矩阵、全部分母、历史对照；逐调用 usage 与费用、引用子串/偏移、时延；bootstrap 来源单位和共享抽样。输出审计 JSON，任何差异先报告并定位，不以静默重跑替换结果。

本文件只约定可机械复核的评测与会计规则，不构成作者语义裁定，也不预先承诺 v4 优于 minimal。
