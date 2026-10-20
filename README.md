# Citation Grounding & Faithfulness Verifier

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

服务地址为 `http://127.0.0.1:8000/verify`。`--backend minimal` 使用单次 LLM；`--backend baseline` 完全离线且无需密钥。可通过 `--port` 更改端口。

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

## 三种方法

| 方法 | 处理流程 | 优势与限制 |
| --- | --- | --- |
| `baseline` | 句子切分、IDF 加权词/中文字符特征检索、保守的公式/数值/否定规则 | 无 API 成本、确定性；不能可靠处理改写和跨段代数推理 |
| `minimal` | 最简任务及输出契约提示词，单次 LLM 请求，再校验返回值 | 实现简单；无模型输出修复、无传输重试 |
| `optimized` | 单独拆分事实及原答案片段，逐声明对照来源验证，校验结构与逐字引用，有限修复 | 提高覆盖和证据约束，但增加调用量；不存在语义正确性的硬保证 |

HTTP 与 benchmark 调用相同的后端实现。推理模块只接收两个请求字段，不能访问数据集标签。优化方案的原文覆盖检查能发现字面遗漏，不能证明所有事实都已正确拆分；被模型判为非事实的片段仍需语义审阅。详细实现与测试位于 `grounding/` 和 `tests/`。

## 统一评测

无需先启动 HTTP 服务。统一脚本直接调用与 HTTP 相同的后端：

```powershell
python scripts/benchmark.py --split dev --output-dir results/comparison-dev
python scripts/benchmark.py --split test --output-dir results/comparison-test
python scripts/benchmark.py --split edge --output-dir results/comparison-edge
```

默认比较全部三种方法。离线检查可运行：

```powershell
python scripts/benchmark.py --backends baseline --split dev --output-dir results/baseline-dev
```

先用开发集迭代，再冻结代码与提示词运行测试集。输出目录须为新目录或空目录，以保留既有实验。每次保存配置、代码/提示词/数据哈希、原始预测、调用追踪、结构错误、token 用量及 `report.json` / `report.md` 对照报告。所有调用和修复都计入延迟与用量。

关键指标包含：成功率、严格文本对齐下的声明+标签 P/R/F1、宏 F1、整例正确率、漏答/多答、近似对齐诊断、合法引用率、证据段落覆盖、标准证据文字包含率、平均/P50/P95 延迟、输入/输出及缓存 token。严格匹配不会把含义不同但字面相近的公式自动视为正确；近似对齐也只是诊断，需要检查匹配审计。

证据文字包含率允许模型引用比标准片段更长的原文，解决“引用整句而标准只取公式”被精确匹配计零的问题。原文子串或段落命中均不能单独证明语义蕴含。

费用仅在显式提供每百万输入、缓存输入和输出 token 单价时估算；缓存或用量缺失会标注不完整。价格、币种和计费假设记录在结果中。报告不把未运行、失败或缺少密钥的 LLM 结果填成零成本或满分。

原 `scripts/evaluate_llm.py` 保留为单模型诊断工具，其 `fixed-claims` 模式会提供标准拆分文字，因此不与这里的端到端三方案分数混用。

## 数据集

CPHOS28 数据集共 **46 条案例、58 条标准声明**，来自 7 道物理竞赛题的选录题干和解答；开发集 18 条、测试集 24 条、边界集 4 条。覆盖完全支持、细微篡改、外部幻觉、真正需要多段证据的关系推理，以及混合标签回答。按整道题分组，避免同题变体跨开发/测试集。

主文件为 `dataset/cphos28/cases.jsonl`，`inputs.jsonl` 不含标签，`gold.jsonl` 单独保存标准答案。来源页码、公式定位和规范化方式存于 `sources.json`。[数据说明](dataset/cphos28/README.md) 和 [来源审查记录](dataset/cphos28/SOURCE_REVIEW.md) 说明了原解答疑点及排除范围。

数据版本 **1.1** 补全了开发集 `q1_sphere_result` 中 `delta` 的出射角定义，来自原解答同页定义；标签和测试集输入未改变。旧单模型运行基于版本 1.0，只作为发现材料歧义的历史证据，不能混入新的三方案对照。

标签由 AI 辅助构造并复核，仍待用户/领域专家终审。该小规模中文公式数据主要诊断忠实度，不代表通用 RAG 性能。公式已规范化为线性文本，未测试图像理解。原 PDF 版权归 CPHOS，本仓库未附原 PDF 或宣称其内容采用开放许可。

## 实测比较

<!-- BENCHMARK_RESULTS_START -->
正在生成统一三方案实测结果。此位置不会用单模型历史记录或模拟响应替代真实对照。
<!-- BENCHMARK_RESULTS_END -->

## 复现检查

```powershell
python -m unittest discover -s tests -v
python scripts/validate_dataset.py
```

测试使用本地模拟上游，无需密钥，覆盖合法/非法引用、布尔下标、空输入、模型输出修复、上游错误、HTTP 契约、评分遗漏惩罚等。GitHub Actions 同时检查 Windows/Linux 和 Python 3.11/3.12。

数据导出可用 `python scripts/validate_dataset.py --export` 重建。只有重新生成选录主文件或使用 `--check-local-sources` 时才需要本机原 PDF；服务、常规校验和 benchmark 均不需要 PDF 读取依赖。
