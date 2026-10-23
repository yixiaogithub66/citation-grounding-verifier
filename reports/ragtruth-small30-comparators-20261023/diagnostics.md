# Baseline / minimal 补测结构诊断

本诊断在补测 `progress.status=completed` 后进行。只读检查既有预测、逐次调用记录、原输入及统一评分结果；未重跑模型、修复输出、修改代码或标签。这里的结构观察和原生标签关联均不是作者裁定，也不证明声明判决在语义上正确。

## Minimal 的两条失败

Minimal 共 30 条，一次调用一条，28 条返回有效完整报告，2 条因引文不满足精确子串契约而整条失败。两次失败均为 Data2txt，服务返回 HTTP 200、`finish_reason=stop`，各只有 `attempt=1`，模型均为 `deepseek-flash`。现有记录不支持将它们归因为超时、预算截断或 JSON 解析失败。

| 记录 ID | 原始 JSON 中声明数 | 引用总数 | 精确引用 / 不精确引用 | 输入 Token | 输出 Token | 其中 reasoning Token | 调用时延 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 9526 | 31 | 26 | 25 / 1 | 1,112 | 11,072 | 9,372 | 50.875 秒 |
| 9586 | 19 | 26 | 15 / 11 | 1,116 | 9,547 | 8,235 | 45.578 秒 |

输出 Token 已包含 reasoning Token，不应重复相加。两条失败的原始调用 Token 仍保存在 telemetry 中并进入费用汇总；输出预算为 16,384，两条均未触及上限。原始声明数与精确引用数只用于定位故障，不当作有效报告完成数。

两条错误码均为 `invalid_model_output`，状态码为 502，具体检查是 `Must be an exact substring of the indexed passage`。因此预测 journal 中 `prediction=null`、`schema_valid=false`。journal 的公开引用计数均为 0，表示没有接纳公开报告，不能据此说模型没有尝试输出引用。

- **9526**：`claims[6].citations[0]` 输出的引用为 `"Ice Cream & Frozen Yogurt"`，内容两侧多了双引号字符。原索引为 0；没有其他段落含有这个完整引用。仅在离线诊断中去掉两侧双引号后，剩余文字在原索引段落中逐字存在。
- **9586**：11 处不精确引用均多出一个前导双引号字符。举例，`claims[9].citations[0]` 为 `"pretty pricy`。仅在离线诊断中去掉该字符后，11 处剩余文字均在原索引 0 段落中逐字存在。不存在“原引用逐字存在于另一个段落”的索引错配。

9586 的完整故障位置（下标从 0 开始）为：`9/0`、`10/0`、`10/1`、`10/2`、`13/0`、`14/0`、`15/0`、`15/1`、`17/1`、`18/0`、`18/1`，格式为“声明下标 / 引用下标”。异常正文只展示前 8 个校验错误，完整扫描原始 JSON 后发现 11 个；不是后续新增错误。

边界字符去除仅用于说明可定位的差异，没有执行引文修复、重新核查或重新评分。字符存在性也不说明引用能够支持相应声明。Minimal 保留其既有单次、无修复契约。

按统一评分文件，两条原生标签均为阳性：minimal 对两条均记 `unknown_positive`，不能记为 TN 或 FN，也不能据此把其已决 FN=0 解释为“全部阳性均检出”。作为同输入对照，baseline 对两条均为 TP；v4 对 9526 返回部分有效报告、对 9586 返回完整报告，两条均检出。

## 成功空输出对照

| 后端 | 成功空 `claims` 数 | 样本 ID |
| --- | ---: | --- |
| baseline | 0 | 无 |
| minimal | 1 | 16452 |
| optimized-v4.0 | 2 | 16452、16421 |

三个成功空输出对应的输入答案均非空。这是输出形态统计，不能单凭空数组判断遗漏事实。

- **16452**：minimal 与 v4 的共同空输出。答案为 `Unable to answer based on given passages.`；原生标签为阴性，两者在回答级评分中均为 TN。Baseline 输出一条被标为 C/U 的声明，原生口径为 FP。这里只陈述原生评分，不重新裁定拒答句是否含有可核查断言。
- **16421**：只有 v4 为空。Minimal 返回 16 条声明，全部为 `UNSUPPORTED`；baseline 也检出。答案包含 GeoGebra 操作建议和说明，原生标签为阳性，因此 minimal / baseline 均为 TP，v4 为 FN。这个差异定位到事实提取/非事实处理边界；本诊断不逐条裁定其 16 条声明是否都是恰当原子事实。

## 证据绑定

| 文件 | SHA-256 |
| --- | --- |
| `results/ragtruth-small30-comparators-20261023/predictions.jsonl` | `a2f79416a71757a95674315b488f3c408e15f8d68a09fa8332dd22fe348d5f1c` |
| `results/ragtruth-small30-20261023/predictions.jsonl` | `cd805d809995dcf33ebe8fd7598c29ce873cde1d6f794d6a6d8d745bb362fd72` |
| `results/ragtruth-small30-20261023/data/inputs.jsonl` | `445ec4e93e9bf930ab5c3b3b9963fa2c6a39c8ecfa689c8e087971d23dbe643d` |
| `results/ragtruth-small30-comparators-20261023/scored/report.json` | `9d9e37555f68cd3d10d54ebea8bc52e1ac1ca274399b10773af5fbe70b0aa8a4` |
