# Citation Grounding & Faithfulness Verifier

## Overview

A Python 3.11+ HTTP service that decomposes generated answers into factual claims, checks them against supplied passages, and enforces exact-source citations. The repository includes a 46-case CPHOS28 benchmark, deterministic and single-call baselines, an optimized verifier, recorded model outputs, and reproducible tests.

| Historical frozen test (24 cases) | Strict claim + verdict F1 | Mean latency | Estimated run cost |
| --- | ---: | ---: | ---: |
| Non-LLM baseline | 30.77% | 0.0007 s | USD 0 |
| Minimal LLM | 89.23% | 1.9977 s | USD 0.012266 |
| Optimized v2 | 86.57% | 4.9498 s | USD 0.028797 |

These are the original `grounding-v2` results, including its negative comparison with minimal. V3 adds answer-only merging and contradiction-evidence review. The author has reviewed three pilot examples and approved the v3.1 same-sentence redundancy rule; confirmation performance must be established on frozen new data with all four backends. See [v3 design](docs/V3_DESIGN.md) and [annotation policy](docs/ANNOTATION_POLICY_V3.md). Costs above use the recorded reference tariff, not a billing statement.

接收来源段落和生成答案，拆成事实声明，返回 `SUPPORTED`、`CONTRADICTED` 或 `UNSUPPORTED`，并附来源中的逐字引用。本项目实现了 [任务说明](https://gist.github.com/wsxiaoys/849522ee389e0ce359ef444653084484) 要求的 HTTP 服务和三方案评测入口。

Python **3.11+**，仅使用标准库，无需安装依赖。默认使用 DeepSeek `deepseek-flash`，也可连接 Chat Completions 兼容接口。程序化校验保证响应结构、引用下标和原文匹配；语义判断依赖对应验证方法。

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

新服务和 `benchmark.py` 自动读取 `.env`，优先级为显式参数 > 进程环境变量 > `.env` > 默认值。文件仅解析为文本配置，不执行其中内容。`api-default` 沿用模型服务端默认思考模式；比较时两个 LLM 使用同一模型设置。

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
| `optimized-v3`（`optimized`） | 拆分后筛选等价复述候选，按需批量合并；验证时记录矛盾证据，对证据不充分的矛盾按需批量复核 | 保留三种判决的改判方向，新增调用全部计入耗时和费用；确认集收益尚待验证 |

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

新增确认集需先完成三条示例及标注规则的作者审阅，再构造正式数据并冻结。`--split confirmation` 会验证冻结清单、代码与数据哈希、模型设置、四路后端和示例审阅凭证；缺失时在任何模型调用前报错。示例仅用 `review` 划分，排除出正式确认集。详细顺序见 [v3 设计](docs/V3_DESIGN.md)。

原 `scripts/evaluate_llm.py` 保留为单模型诊断工具，其 `fixed-claims` 模式会提供标准拆分文字，因此不与这里的端到端三方案分数混用。

## 数据集

CPHOS28 数据集共 **46 条案例、58 条标准声明**，来自 7 道物理竞赛题的选录题干和解答；开发集 18 条、测试集 24 条、边界集 4 条。覆盖完全支持、细微篡改、外部幻觉、真正需要多段证据的关系推理，以及混合标签回答。按整道题分组，避免同题变体跨开发/测试集。

主文件为 `dataset/cphos28/cases.jsonl`，`inputs.jsonl` 不含标签，`gold.jsonl` 单独保存标准答案。来源页码、公式定位和规范化方式存于 `sources.json`。[数据说明](dataset/cphos28/README.md) 和 [来源审查记录](dataset/cphos28/SOURCE_REVIEW.md) 说明了原解答疑点及排除范围。

数据版本 **1.2** 补全了开发集来源中的出射角定义和一维模型标题，均来自原文相邻定义；标签和测试集输入未改变。历史运行保留原数据快照，不混入当前版本的三方案对照。完整变更记录见 [迭代记录](docs/ITERATIONS.md)。

原 58 条标签已于 2026-10-22 经作者终审：AI 逐项复核，作者裁决四个标出项，并报告抽查其余条目无问题。该记录不等同于独立领域专家逐条认证；历史数据与成绩保持原样，引用改进意见单独登记，见 [作者审阅记录](reviews/cphos28/REVIEW.md)。该小规模中文公式数据主要诊断忠实度，不代表通用 RAG 性能。公式已规范化为线性文本，未测试图像理解。原 PDF 版权归 CPHOS，本仓库未附原 PDF 或宣称其内容采用开放许可。

作者已批准 [三条新样例](dataset/cphos28-review/REVIEW.md) 和 [标注规则](docs/ANNOTATION_POLICY_V3.md)，并明确允许同句内一致的冗余说明与完整公式合并；[审阅凭证](reviews/cphos28/pilot-author-review.json) 绑定实际样例、规则及用户确认。三条样例永久排除正式确认集；作者批准不代表已人工审核后续新增确认标签。

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
- 优化方案 `q5-03` 将方向判断标为 `UNSUPPORTED`，理由是片段未明确 `eta` 的符号；原标签按阻力系数正值理解。此项同时暴露上下文假设与标签边界，保留原测试记录供复核。
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

134 项测试通过；干净克隆在无密钥条件下通过测试、数据校验、离线评测和 HTTP 检查。真实 v3 服务已通过任务中的 SQLite 示例，见 [HTTP 记录](reports/service-smoke-v3/run.json)。这些检查验证实现与回归，正式效果结论仍需新增确认集。

初版冻结后对旧 test 作了一次诊断回归：24/24 响应有效，严格 F1 **86.57%**，整例正确 21/24，原三处粒度问题仍在。两次合并调用找到了目标候选，但模型认为“局部性质”与“完整公式”不严格等价而拒绝合并，因此该版未实现预期的过拆修复。作者据此明确批准“同句内一致的冗余说明可合并”的规则，v3.1 单独实现并冻结；旧数据和旧成绩不回写。详见 [初版回归报告](reports/test-v3-regression/report.md) 和 [失败复核](reports/test-v3-regression/AUDIT.md)。

## 复现检查

```powershell
python -m unittest discover -s tests -v
python scripts/validate_dataset.py
```

测试使用本地模拟上游，无需密钥，覆盖合法/非法引用、布尔下标、空输入、模型输出修复、上游错误、HTTP 契约、评分遗漏惩罚等。GitHub Actions 同时检查 Windows/Linux 和 Python 3.11/3.12。

数据导出可用 `python scripts/validate_dataset.py --export` 重建。只有重新生成选录主文件或使用 `--check-local-sources` 时才需要本机原 PDF；服务、常规校验和 benchmark 均不需要 PDF 读取依赖。
