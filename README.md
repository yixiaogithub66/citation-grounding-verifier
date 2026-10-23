# Citation Grounding & Faithfulness Verifier

新增实验后端 **`optimized-v4-combined`**：组合答案位置与覆盖记账、证据角色/指针协议、初判盲化复核，并配套离线行为测试。原 v4 保留作配对对照；启动与实验边界见 [组合实验说明](docs/V4_COMBINED_EXPERIMENT.md)。

组合实验已完成：旧 RAGTruth 180 条配对中，完整报告 170→179、原生 FP 66→76、FN 2→0，已决 F1 63.04%→61.22%，参考费用为 2.12 倍。FN 改变含非事实片段被事实化的问题，不能作为语义修复证明；物理回归和 AI 草案行为测试也未显示整体优势。**结构完整性改善，尚未获得整体通用性优化。** 377 项测试通过；详见 [完整实测与审计](reports/v4-combined-20261023/README.md)。

独立后端 **`optimized-v4.0`**：分块拆分与句子骨架降级、保守引文修复、分批核查、C/U 有界复核和部分结果返回。当前处于开发验证及作者裁定阶段，尚未宣称通过未见测试验收。启动、配置、评测与冻结流程见 [v4 说明](docs/V4_DESIGN.md)；[341 条 AI 裁定草案](reviews/ragtruth-v4-dev-adjudication-v1/ai-draft/README.md)的作者审核已提交，剩余细节暂缓处理，尚未导入为最终裁定版本。`optimized` 别名继续指向历史 v3。

v4 已完成旧 180 条开发评测：170 条完整、10 条部分、0 条整例执行失败，平均 14.80 秒；原生口径 FP=66、FN=3，尚未达成语义验收目标。坏引用七例恢复 6 条完整报告；318 项测试通过。详细回归、开销和未完成项见 [v4 开发审计](reports/V4_DEVELOPMENT_AUDIT.md)。新未见切片尚未取数。

最新的 [RAGTruth 外部盲测](reports/ragtruth-blind-v1-recovery/AUDIT.md) 已完成：优化版失败计入 F1 为58.89%，minimal为56.70%，差值区间跨零；原有CPHOS高分不足以证明通用泛化优势。下方保留全部历史结果。

## Overview

A Python 3.11+ HTTP service that decomposes generated answers into factual claims, checks them against supplied passages, and enforces exact-source citations. The repository includes the original 46-case CPHOS28 benchmark, 12 new confirmation cases, deterministic and single-call baselines, separately versioned v2/v3.1 verifiers, recorded model outputs, and reproducible tests.

| Historical frozen test (24 cases) | Strict claim + verdict F1 | Mean latency | Estimated run cost |
| --- | ---: | ---: | ---: |
| Non-LLM baseline | 30.77% | 0.0007 s | USD 0 |
| Minimal LLM | 89.23% | 1.9977 s | USD 0.012266 |
| Optimized v2 | 86.57% | 4.9498 s | USD 0.028797 |

These are the original `grounding-v2` results, including its negative comparison with minimal. After author approval of three excluded pilots and the v3.1 annotation policy, a frozen same-source, same-question-family confirmation run completed on 2026-10-22:

| New confirmation (12 cases / 42 gold claims) | Strict claim + verdict F1 | Whole cases correct | Mean latency | Estimated run cost |
| --- | ---: | ---: | ---: | ---: |
| Non-LLM baseline | 36.14% | 0/12 | 0.0013 s | USD 0 |
| Minimal LLM | 58.14% | 3/12 | 5.1554 s | USD 0.018439 |
| Frozen optimized v2 | 90.70% | 9/12 | 13.5279 s | USD 0.046071 |
| Optimized v3.1 | **97.62%** | **11/12** | 15.8928 s | USD 0.053769 |

V3.1 gains 6.92 percentage points over v2 on the same inputs, chiefly by avoiding two prose/formula over-splits during extraction. It takes 17.5% longer and costs 16.7% more at the fixed reference tariff. Three merge checks correctly retain mixed-truth assertions; no successful merge or contradiction re-review occurs. All LLM methods still misclassify one unsupported scope attribution as contradicted. Minimal's approximate-alignment F1 is 76.74%, so its strict gap must not be interpreted as an equivalent semantic-accuracy gap.

All 48 responses are structurally valid. The 12 related, constructed cases use Q2/Q6/Q7 excerpts; formal labels are AI-assisted with independent AI-role review, not individually author-reviewed. This single run is not a component ablation or an independent-question generalization result. Code, data, settings and labels were frozen before inference and were not retuned from these outputs. Costs are standardized estimates, not billing statements. See [full results](reports/confirmation-v3.1/report.md), [outcome audit](reports/confirmation-v3.1/AUDIT.md), [v3.1 design](docs/V3_DESIGN.md) and [annotation policy](docs/ANNOTATION_POLICY_V3.md).

接收来源段落和生成答案，拆成事实声明，返回 `SUPPORTED`、`CONTRADICTED` 或 `UNSUPPORTED`，并附来源中的逐字引用。本项目实现了 [任务说明](https://gist.github.com/wsxiaoys/849522ee389e0ce359ef444653084484) 要求的 HTTP 服务和三方案评测入口。

Python **3.11+**，仅使用标准库，无需安装依赖。默认使用 DeepSeek `deepseek-flash`，也可连接 Chat Completions 兼容接口。程序化校验保证响应结构、引用下标和原文匹配；语义判断依赖对应验证方法。

## RAGTruth 外部评测

新增的 RAGTruth 入口使用外部自然生成回答和人工幻觉标签，独立于上述 CPHOS 公式数据。首轮按任务分层抽取 **30 个来源、180 条回答**，比较冻结的 `baseline / minimal / optimized-v3`。原推理代码和提示词保持原样；原始数据固定到上游 commit，转换、评分和运行设置在首次正式调用前冻结。

这里的主任务是**回答级幻觉检测**：原生标签非空为正例，系统输出任何 `CONTRADICTED` 或 `UNSUPPORTED` 为预测正例。它不使用旧的声明精确文本 F1，也没有把未标注文字自动转换成 SUPPORTED gold。原子声明三分类、完整提取召回和引用语义充分性尚无独立金标，首轮不报告这些能力的准确率。

<!-- RAGTRUTH_RESULTS_START -->
2026-10-22 已完成 **180 条回答 × 3 方案 = 540 条记录**，输入来自 30 个来源，三类任务各 60 条。按原始标签有幻觉 60 条、未标幻觉 120 条。所有失败均保留。

| 方案 | 成功输出 F1 | 失败计入 F1 下界 | 端到端准确率 | 技术失败 | 平均耗时/例 | 180例参考费用 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 50.00% | 50.00% | 33.33% | 0/180 | 0.02 s | USD 0.0000 |
| minimal | 59.46% | 56.70% | 53.33% | 9/180 | 27.58 s | USD 1.5077 |
| optimized-v3 | 62.35% | 58.89% | 58.89% | 10/180 | 86.82 s | USD 4.4560 |

**当前优化版只比 minimal 高 2.19 个百分点**（失败计入 F1），来源整组 bootstrap 的95%差值区间为 **[-2.64, +7.50] 个百分点**，尚不能确认稳定优势；平均耗时约 **3.15 倍**、参考费用约 **2.96 倍**。baseline 对全部180条回答都报出C/U，等同于恒阳性参考。按原生标签，两种LLM的主要问题是误报较多；优化版另有长输出预算耗尽的问题。

失败计入 F1 是预注册保守下界：阳性失败记FN、阴性失败记FP；成功输出指标条件于180/171/170条成功返回，不能隐去失败。费用采用既有固定参考单价，不是实际账单。三类输出分布和逐字引用合法率都不是语义准确率。

原生标签与Gist在“步骤/建议是否需要核验”上存在边界差异，少量案例也发现原标注覆盖疑点；已单独记录，未据此改写标签或首轮分数。这是回答级外部诊断，不能与旧CPHOS的97.62%声明文本对齐F1直接比较。

本轮记录器曾发生本地权限错误，原84条完整记录（含2条失败）按字节保留；仅补跑456个缺失配对。原推理、提示词、评分器、输入与标签均未改变。完整[结果与审计](reports/ragtruth-blind-v1-recovery/AUDIT.md)、[自动报告](reports/ragtruth-blind-v1-recovery/report.md)、[原始预测](reports/ragtruth-blind-v1-recovery/predictions.jsonl)、[恢复记录](reports/ragtruth-recorder-recovery/README.md)均已保存。独立重算与离线重评分一致，**200项测试通过**。
<!-- RAGTRUTH_RESULTS_END -->

离线下载和准备入口（输出目录必须不存在）：

```powershell
python scripts/fetch_ragtruth.py --output-dir tmp/ragtruth-upstream
python scripts/ragtruth_data.py --raw-dir tmp/ragtruth-upstream --output-dir results/ragtruth-prepared-copy --split test --sources-per-task 10
```

`--sources-per-task 0` 准备全部合格 test 回答。原始数据和测试标签不进入验证器；推理仅接收两个请求字段，完成后由独立脚本评分。API/格式失败保留在总体分母中，并同时报告成功输出上的指标和计入失败的保守 F1。置信区间按来源整体重采样，不能把同源六个回答当作六个独立来源。

以下首轮复现命令需在历史提交 `5fc6c40` 的独立 checkout 中运行；v4 开发目录会被旧冻结校验正确拒绝。使用已冻结的首轮选择复现时，同一工作区已有来源曝光需 `--replicate`，始终使用新输出目录：

```powershell
python scripts/benchmark_ragtruth.py run --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/ragtruth-reproduction --thinking enabled --workers 4
python scripts/ragtruth_score.py --run-dir results/ragtruth-reproduction --data-dir dataset/ragtruth-blind-v1/recovery
```

无需 API 的重新计分：

```powershell
python scripts/ragtruth_score.py --run-dir reports/ragtruth-blind-v1-recovery --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/ragtruth-rescore
```

完整的首次 freeze 命令、与上游输入的差异、费用参考和泛化边界见 [协议](docs/RAGTRUTH_PROTOCOL.md)。RAGTruth 项目与论文出处记录在 [数据目录](dataset/ragtruth-blind-v1/README.md)。

## 配置与启动

在仓库根目录的 `.env` 填写以下内容；密钥文件已加入 `.gitignore`：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=你的密钥
LLM_TIMEOUT=180
LLM_MAX_OUTPUT_TOKENS=16384
LLM_JSON_MODE=true
LLM_THINKING=api-default
LLM_REPAIR_ATTEMPTS=1
LLM_UPSTREAM_RETRIES=1
```

新服务和 `benchmark.py` 自动读取 `.env`，优先级为显式参数 > 进程环境变量 > `.env` > 默认值。文件仅解析为文本配置，不执行其中内容。`api-default` 沿用模型服务端默认思考模式；比较时各 LLM 后端使用同一模型设置。

启动优化验证器：

```powershell
python -m grounding.server --backend optimized
```

服务地址为 `http://127.0.0.1:8000/verify`。`optimized` 是当前 `optimized-v3` 的别名；`--backend optimized-v2` 使用冻结的旧版。`--backend minimal` 使用单次 LLM；`--backend baseline` 完全离线且无需密钥。可通过 `--port` 更改端口。

在另一个 PowerShell 窗口发送任务说明中的 SQLite 示例：

```powershell
$body = Get-Content -Raw -Encoding UTF8 examples/sqlite.json
Invoke-RestMethod -Uri http://127.0.0.1:8000/verify -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 10
```

## HTTP 契约

`POST /verify` 的请求只包含：

```json
{
  "context_passages": ["The service retries at most three times."],
  "generated_answer": "The service retries at most four times."
}
```

成功响应只包含 `claims`，每项具有 `claim_text`、`verdict`、简短 `reasoning` 和 `citations`。每条 citation 包含合法的 0-based `index` 和对应 passage 的非空精确子串 `quote`。前两类判断需要非空引用，`UNSUPPORTED` 必须为 `[]`。可选偏移采用 Unicode 字符位置和 `[start_char,end_char)` 区间，须成对提供并精确截取 quote。

| 情况 | 行为 |
| --- | --- |
| 空答案或无事实断言 | `200 {"claims":[]}` |
| 空上下文且答案有事实 | 仍拆分声明，每条为 `UNSUPPORTED`、无引用 |
| JSON/字段/类型不合法 | `400` JSON 错误 |
| 请求过大 | `413` |
| 不是 `application/json` | `415` |
| 模型输出经有限修复后仍不合法 | `502`，不会伪装成 `UNSUPPORTED` |
| 上游超时 | `504` |
| 配置缺失或并发槽位耗尽 | 启动时配置报错，或 `503` |

错误响应为 `{"error":{"code":"...","message":"..."}}`。`GET /health` 用于检查服务状态。每个请求最多 64 个来源段落、每段 32,000 字符、答案 20,000 字符、总输入 200,000 字符、JSON body 1 MiB；最多返回 64 条声明。服务默认只绑定本机，最多 4 个并行验证请求，HTTP body 读取超时 15 秒。

## 方法与版本

| 方法 | 处理流程 | 优势与限制 |
| --- | --- | --- |
| `baseline` | 句子切分、IDF 加权词/中文字符特征检索、保守的公式/数值/否定规则 | 无 API 成本、确定性；不能可靠处理改写和跨段代数推理 |
| `minimal` | 最简任务及输出契约提示词，单次 LLM 请求，再校验返回值 | 实现简单；无模型输出修复、无传输重试 |
| `optimized-v2` | 原冻结两阶段方案：拆分事实及原答案片段，再逐声明验证，校验结构与逐字引用，有限修复 | 保留历史对照；运行前校验推理文件的原始字节哈希 |
| `optimized-v3`（`optimized`，提示版本 v3.1） | 拆分后筛选等价复述或同句一致的冗余说明，按需批量合并并保留完整公式；验证时记录矛盾证据，对缺少有效结构记录的矛盾按需批量复核 | 保留三种判决的改判方向，新增调用全部计入耗时和费用；结构检查不能证明语义正确 |
| `optimized-v4.0`（`optimized-v4`） | 分块拆分、保守引用定位、按预算分批、C/U 有界复核与部分结果；无独立合并阶段 | 分阶段配置与逐条干预审计；部分报告需要读取 `status/errors`，作者裁定与未见验收尚待完成 |

HTTP 与 benchmark 调用相同的后端实现。推理模块只接收两个请求字段，不能访问数据集标签。优化方案的原文覆盖检查能发现字面遗漏，不能证明所有事实都已正确拆分；被模型判为非事实的片段仍需语义审阅。详细实现与测试位于 `grounding/` 和 `tests/`。

## 统一评测

无需先启动 HTTP 服务。统一脚本直接调用与 HTTP 相同的后端：

```powershell
python scripts/benchmark.py --split dev --output-dir results/comparison-dev
python scripts/benchmark.py --split test --output-dir results/comparison-test
python scripts/benchmark.py --split edge --output-dir results/comparison-edge
```

默认比较 `baseline / minimal / optimized-v3`。四路开发集比较可运行：

```powershell
python scripts/benchmark.py --split dev --backends baseline minimal optimized-v2 optimized-v3 --thinking enabled --output-dir results/v3-dev
```

离线检查可运行：

```powershell
python scripts/benchmark.py --backends baseline --split dev --output-dir results/baseline-dev
```

历史 v2 先用开发集迭代，再冻结代码与提示词运行测试集。旧 test 现已用于 v3 的诊断设计，后续仅作回归；v3 的正式比较改用新增确认集。输出目录须为新目录或空目录，以保留既有实验。每次保存配置、代码/提示词/数据哈希、原始预测、调用追踪、结构错误、token 用量及 `report.json` / `report.md` 对照报告。所有调用和修复都计入延迟与用量。

关键指标包含：成功率、严格文本对齐下的声明+标签 P/R/F1、宏 F1、整例正确率、漏答/多答、近似对齐诊断、合法引用率、证据段落覆盖、标准证据文字包含率、平均/P50/P95 延迟、输入/输出及缓存 token。严格匹配不会把含义不同但字面相近的公式自动视为正确；近似对齐也只是诊断，需要检查匹配审计。

证据文字包含率允许模型引用比标准片段更长的原文，解决“引用整句而标准只取公式”被精确匹配计零的问题。原文子串或段落命中均不能单独证明语义蕴含。

费用估算需要显式提供输入和输出单价，缓存输入单价可选；未提供缓存价时全部输入按普通输入价估算。提供缓存价但缓存计数缺失、或总用量缺失时会标注不完整。价格、币种和计费假设记录在结果中。报告不把未运行、失败或缺少密钥的 LLM 结果填成零成本或满分。

复现本次测试采用的统一峰时参考价格估算：

```powershell
python scripts/benchmark.py --split test --backends baseline minimal optimized-v2 --thinking enabled --input-price-per-million 0.30 --cached-input-price-per-million 0.006 --output-price-per-million 1.20 --currency USD --output-dir results/test-priced
```

计费来源与限制见 [价格说明](reports/PRICING.md)。这只是统一价格下的估算，非实际扣费账单。

新增确认集已完成三条示例及标注规则的作者审阅、正式数据构造、独立 AI 复核与冻结。`--split confirmation` 会验证冻结清单、代码与数据哈希、模型设置、四路后端和示例审阅凭证；缺失时在任何模型调用前报错。示例仅用 `review` 划分，永久排除出正式确认集。详细顺序见 [v3 设计](docs/V3_DESIGN.md)。

在历史提交 `5fc6c40` 的独立 checkout 中使用原冻结清单，可在新目录复现四路确认评测。当前 v4 目录将其作为回归材料时，使用 `scripts/benchmark_v4_claims.py`，不冒充新的确认实验：

```powershell
python scripts/benchmark.py --dataset dataset/cphos28-confirmation/cases.jsonl --split confirmation --backends baseline minimal optimized-v2 optimized-v3 --thinking enabled --input-price-per-million 0.30 --cached-input-price-per-million 0.006 --output-price-per-million 1.20 --currency USD --output-dir results/confirmation-reproduction
```

同一工作区已有该批输入的运行登记时，须额外加 `--confirmation-replicate`，明确记录为重复实验。新克隆的本地登记为空，不表示这些数据在全球从未运行过；复现也不是新的未见确认。无需重新生成或覆盖冻结清单，模型设置须与清单一致。

原 `scripts/evaluate_llm.py` 保留为单模型诊断工具，其 `fixed-claims` 模式会提供标准拆分文字，因此不与这里的端到端三方案分数混用。

## 数据集

CPHOS28 数据集共 **46 条案例、58 条标准声明**，来自 7 道物理竞赛题的选录题干和解答；开发集 18 条、测试集 24 条、边界集 4 条。覆盖完全支持、细微篡改、外部幻觉、真正需要多段证据的关系推理，以及混合标签回答。按整道题分组，避免同题变体跨开发/测试集。

主文件为 `dataset/cphos28/cases.jsonl`，`inputs.jsonl` 不含标签，`gold.jsonl` 单独保存标准答案。来源页码、公式定位和规范化方式存于 `sources.json`。[数据说明](dataset/cphos28/README.md) 和 [来源审查记录](dataset/cphos28/SOURCE_REVIEW.md) 说明了原解答疑点及排除范围。

数据版本 **1.2** 补全了开发集来源中的出射角定义和一维模型标题，均来自原文相邻定义；标签和测试集输入未改变。历史运行保留原数据快照，不混入当前版本的三方案对照。完整变更记录见 [迭代记录](docs/ITERATIONS.md)。

原 58 条标签已于 2026-10-22 经作者终审：AI 逐项复核，作者裁决四个标出项，并报告抽查其余条目无问题。该记录不等同于独立领域专家逐条认证；历史数据与成绩保持原样，引用改进意见单独登记，见 [作者审阅记录](reviews/cphos28/REVIEW.md)。该小规模中文公式数据主要诊断忠实度，不代表通用 RAG 性能。公式已规范化为线性文本，未测试图像理解。原 PDF 版权归 CPHOS，本仓库未附原 PDF 或宣称其内容采用开放许可。

作者已批准 [三条新样例](dataset/cphos28-review/REVIEW.md) 和 [标注规则](docs/ANNOTATION_POLICY_V3.md)，并明确允许同句内一致的冗余说明与完整公式合并；[审阅凭证](reviews/cphos28/pilot-author-review.json) 绑定实际样例、规则及用户确认。三条样例永久排除正式确认集；作者批准不代表已人工审核后续新增确认标签。

[正式确认集](dataset/cphos28-confirmation/README.md) 包含 **12 条案例、42 条声明、22 个新片段**，来自 Q2/Q6/Q7，四种题型各 3 例，标签 S/C/U 为 15/13/14。标签采用 AI 辅助构造与独立 AI 角色复核；它是**同来源、同题族的新增确认集**，样例相关且部分片段复用，不是题目级独立测试。代码修复、数据审阅和冻结的真实时序见 [构造记录](dataset/cphos28-confirmation/construction.json)。

## 实测比较

<!-- BENCHMARK_RESULTS_START -->
以下保留 2026-10-20 的历史 `grounding-v2` 结果：`deepseek-flash`，显式启用思考模式，数据 v1.2。该轮开发阶段结束后冻结代码与提示词，测试集为 **24 条案例、32 条标准声明**；该轮测试后未修改 v2。三种方法均完成 24/24 次验证，返回结构全部有效。后续 v3 已利用这些失败作诊断，不能再将旧 test 称为 v3 的未见测试。

| 方法 | 严格声明+标签 F1 | 严格宏 F1 | 近似对齐诊断 F1 | 平均耗时/例 | P95 | 24 例估算费用 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 30.77% | 23.20% | 30.77% | 0.0007 s | 0.0015 s | USD 0.000000 |
| `minimal` | 89.23% | 90.44% | 95.38% | 1.9977 s | 2.9110 s | USD 0.012266 |
| `optimized` | 86.57% | 87.78% | 86.57% | 4.9498 s | 10.1021 s | USD 0.028797 |

费用按统一峰时参考单价及实际缓存 token 估算，非实际账单。近似对齐列是诊断，不是语义准确率；严格分数会惩罚正确改写和不同拆分。最简与优化方案的严格整例正确率均为 **21/24**，但优化方案的额外拆分降低了声明 F1。

测试集的每条实际引用均通过逐字子串校验，但覆盖并非都充分：最简/优化方案的近似对齐证据段落覆盖为 95.8% / 87.5%，标准证据文字包含率为 82.8% / 89.7%。这些指标均需结合具体引文审阅。

此次优化方案平均耗时约为最简方案的 2.48 倍，标准化费用约为 2.35 倍，未取得更高的测试分数。优化是实现方案名称，并不代表在这份数据上胜出。纯规则基线速度快，但改写、细微公式差异与跨段推导多数被保守判为无依据。

关键失败与评分差异：

- 最简方案 `q2-05`、`q7-05` 的求和/世界线结论正确，但改写了声明，导致严格匹配失败；`q5-03` 把同一符号错误的文字说明和公式分成两条。
- 优化方案 `q5-02`、`q5-06` 将文字解释和等价公式重复拆分，未与单条标准声明对齐。这是声明粒度问题，不能一概称为物理判断错误。
- 优化方案 `q5-03` 将方向判断标为 `UNSUPPORTED`，理由是片段未明确 `eta` 的符号；作者于 2026-10-22 裁决阻力系数为正，维持整句 `CONTRADICTED`，该方向片段属于真实判决错误。历史记录与成绩不回写，争议已关闭。
- 最简方案 `q2-05` 引用了无量纲 `t_2` 的数值，却没有引用同段的实际时长单位关系；合法子串并不自动等于充分证据。

开发集最终严格 F1：baseline 33.3%、minimal 91.7%、optimized 100%。两个 LLM 的开发集近似诊断 F1 均为 100%，不应把文字对齐优势解释成等量语义收益。4 条边界案例由三种方法全部通过；没有真实调用触发格式修复，其恢复路径由模拟上游测试验证。

完整结果：[首轮开发](reports/dev-v1/report.md)、[最终开发](reports/dev-v2/report.md)、[测试集](reports/test/report.md)、[边界集](reports/edge/report.md)。每个目录保存配置、原始预测、分阶段调用、数值分母及 JSON 汇总。[迭代记录](docs/ITERATIONS.md) 与 [评测协议](docs/EVALUATION_PROTOCOL.md) 说明了数据修复、提示改进与指标局限。

另用任务说明中的 SQLite 示例实际请求本机 HTTP 服务，得到 `200` 及预期的四条判断：`CONTRADICTED / SUPPORTED / SUPPORTED / UNSUPPORTED`，逐字引用校验通过。[响应记录](reports/service-smoke/sqlite.response.json) 与 [运行记录](reports/service-smoke/run.json) 单独保存；本次服务检查耗时 34.172 秒，不计入上表。
<!-- BENCHMARK_RESULTS_END -->

## v3 初版验证记录

以下保留初版 `grounding-v3`（严格等价规则）的验证记录。作者随后已批准样例、旧标签终审及冗余说明合并边界，当前实现更新为 `grounding-v3.1`，其新评测单独记录。初版开发集四路回归共 72 条运行记录，全部结构有效：

| 方法 | 开发集严格 F1 | 平均耗时/例 | 18 例参考价估算 |
| --- | ---: | ---: | ---: |
| `baseline` | 33.33% | 0.0022 s | USD 0 |
| `minimal` | 89.80% | 2.5679 s | USD 0.011066 |
| `optimized-v2` | 100% | 4.9160 s | USD 0.020181 |
| `optimized-v3` | 100% | 5.7163 s | USD 0.024533 |

v2/v3 均为 18/18 整例正确。该开发集已饱和，不能据此证明 v3 的泛化提升；本轮没有触发额外合并或矛盾复核调用。完整记录见 [四路开发回归](reports/dev-v3-final/report.md)。早期 JSON 模式兼容失败与修复过程也保留在 [迭代记录](docs/ITERATIONS.md)，未用失败后的重跑覆盖原记录。

当时 134 项测试通过；干净克隆在无密钥条件下通过测试、数据校验、离线评测和 HTTP 检查。真实 v3 服务已通过任务中的 SQLite 示例，见 [HTTP 记录](reports/service-smoke-v3/run.json)。这些是初版实现与回归检查，当前 v3.1 的确认结果另行记录。

初版冻结后对旧 test 作了一次诊断回归：24/24 响应有效，严格 F1 **86.57%**，整例正确 21/24，原三处粒度问题仍在。两次合并调用找到了目标候选，但模型认为“局部性质”与“完整公式”不严格等价而拒绝合并，因此该版未实现预期的过拆修复。作者据此明确批准“同句内一致的冗余说明可合并”的规则，v3.1 单独实现并冻结；旧数据和旧成绩不回写。详见 [初版回归报告](reports/test-v3-regression/report.md) 和 [失败复核](reports/test-v3-regression/AUDIT.md)。

## v3.1 正式确认结果

2026-10-22 在冻结的 12 例、42 条声明上完成四路一次性实测：`deepseek-flash`、`thinking=enabled`，共 **48/48** 条结构有效记录，无 API 失败、格式修复或传输重试。代码、数据、规则、作者样例审阅凭证及模型设置均在调用前绑定哈希。

| 方法 | 严格 F1 | 近似对齐 F1 | 严格整例正确 | 正确 / 预测 / gold | 平均耗时/例 | 12 例估算费用 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 36.14% | 36.14% | 0/12 | 15 / 41 / 42 | 0.0013 s | USD 0 |
| `minimal` | 58.14% | 76.74% | 3/12 | 25 / 44 / 42 | 5.1554 s | USD 0.018439 |
| `optimized-v2` | 90.70% | 90.70% | 9/12 | 39 / 44 / 42 | 13.5279 s | USD 0.046071 |
| `optimized-v3`（v3.1） | **97.62%** | **97.62%** | **11/12** | **41 / 42 / 42** | 15.8928 s | USD 0.053769 |

主要对照是同卷 v2 → v3.1：严格 F1 提高 **6.92 个百分点**，两例改善、无整例退步。`density-q6` 的 B 系数指数说明和完整公式、`reformulation_calculation-q2` 的系数符号说明和完整公式，在 v2 被多拆；v3.1 在初始提取时保留整句，消除 4 条 extra 和 2 条 missing。新增合并阶段没有执行实际合并，不能把这两例收益归因于合并调用。

minimal 的失分包含缩写、改写和过拆；近似对齐后从 25 条正确增加到 33 条，但仍有粒度差异和范围判断错误。不能把 58.14% 的严格分数直接当成语义准确率，也不能用新旧数据的分差证明能力变化。

三个 LLM 都把 `scope_distractor-q2-c1` 的额外来源归属由 gold 的 `UNSUPPORTED` 判成 `CONTRADICTED`。片段给出某公式用于悬链线，并未排他地证明其不能出现在自由悬挂部分；缺乏支持不等于直接矛盾。v3.1 的结构化矛盾记录通过检查，没有触发复核，说明该门控仍不能保证语义正确。原标签与全部预测保留。

调用数为 minimal **12**、v2 **24**、v3.1 **27**。v3.1 的 3 次额外调用均检查半对半错句，保留分开的命题；实际合并数、矛盾复核数、改判数均为 0。相对 v2，平均延迟增加 **17.5%**、参考价费用增加 **16.7%**；四路合计估算 USD **0.118279**。该轮按固定顺序逐例执行，延迟与缓存费用并非随机化实验。

v3.1 的证据段落覆盖为 28/28、多段必需证据覆盖为 5/5，但标准引文完整包含仅 10/33；许多短引文没有覆盖 gold 的整段锚点。这些指标度量不同，不能把段落覆盖 100% 写成语义引用准确率 100%。详细引文复核与剩余问题见 [结果审计](reports/confirmation-v3.1/AUDIT.md)，完整数值和调用记录见 [报告](reports/confirmation-v3.1/report.md) 与 [原始记录](reports/confirmation-v3.1/responses.jsonl)。

本轮确认集来自同来源、同题族，12 例之间相关，正式 42 条标签经过 AI 构造与独立 AI 复核；作者审批限于先前的样例与规则。一次运行支持本批数据上的改善，不能证明通用优越性，也不能单独证明额外合并或复核阶段的收益。看到结果后未修改代码、评分或标签。

另保留 v3.1 在旧数据上的 [开发回归](reports/dev-v3.1/report.md)（100%）和 [旧 test 回归](reports/test-v3.1-regression/report.md)（95.38%，23/24 整例）。它们使用独立合成审查修复前的代码快照，仅属已见数据回归，不替代本次确认。最终实现 **143 项测试通过**，干净克隆在无密钥下通过离线测试、数据校验、baseline benchmark 和 HTTP 检查。

## 复现检查

```powershell
python -m unittest discover -s tests -v
python scripts/validate_dataset.py
```

测试使用本地模拟上游，无需密钥，覆盖合法/非法引用、布尔下标、空输入、模型输出修复、上游错误、HTTP 契约、评分遗漏惩罚等。GitHub Actions 同时检查 Windows/Linux 和 Python 3.11/3.12。

数据导出可用 `python scripts/validate_dataset.py --export` 重建。只有重新生成选录主文件或使用 `--check-local-sources` 时才需要本机原 PDF；服务、常规校验和 benchmark 均不需要 PDF 读取依赖。
