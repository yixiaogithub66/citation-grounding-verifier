# Antigravity High 辅助审查与主代理复核

用户已授权 Antigravity 辅助当前工作，并明确指定 High；后来又指定后续任务优先从桌面端委派。本次既有审查在偏好切换前通过插件所用 CLI 发起，没有重复从桌面端派发。

最终审查成功返回。它基于直接提供的 12 份带行号静态源码与报告，未调用任何工具、未修改项目、未运行新 benchmark。Antigravity 的原始意见是 AI 辅助审阅，不是作者终审；其中有可复核发现，也有不能采纳的推断。

## 调用是否成功

使用本机 `C:\Users\yixiao\.gemini\bin\agy.exe` 1.4.6。

1. 最初按 CLI 全局 `max` 尝试，默认 `gemini-4-argon` 拒绝该档（支持 low/medium/high），0 推理轮次。
2. 用户明确改为 `high` 后，首次文件读取被 headless 的 RunCommand 权限拒绝。尽管 exit 0、status SUCCESS，response 为空，不能算审查完成。另外，同时使用 `--mode plan` 与 `--disable-slash-commands` 会使 plan 不生效，此组合不再使用。
3. 最终通过标准 stdin NDJSON 直接提供材料，以 `--mode plan --effort high --input-format stream-json --output-format stream-json` 完成任务。没有使用 `--dangerously-skip-permissions`，没有扩大权限。最终 SUCCESS、正文非空（24,043 字符）、无 denied_actions、stderr 为空。流中只有 user_input 和 agent_response，没有工具调用。

最终一次调用约 291.48 秒；CLI 返回 usage 为 input 49,373、output 24,225、thinking 12,253、total 73,598。thinking 字段单独保留，不能再加到 total 上。它们是 CLI 提供的计量，不是已核对账单。前一次权限失败的调用也有用量，原始日志保留，不能当作零成本。

原始记录保留在 `results/antigravity-review-20261023T113053Z/`。本目录的 `raw-response.txt` 保留原始回复，含未采纳的观点；`review-metadata.json` 保存请求、返回及材料哈希信息。

## 采纳的发现：非事实排除自动扩展至所有同文位置

`grounding/verifiers_v4.py` 的 `extract_claims` 对一条 `non_factual_spans.text` 使用循环寻找块内全部同文出现位置，并给所有位置套用同一个 reason。事实 claim 的重复出现则要单独覆盖。这可能把一个语境里的非事实判断带到另一个语境。

用现有代码、无模型调用的合成输入复现：

| 输入与 M1 输出 | 当前确定性校验行为 |
| --- | --- |
| `Please wait. Please wait.`；仅一条 NF `Please wait.` | 自动生成两个排除跨度并通过 |
| `The lamp is on. The lamp is on.`；仅提取第一处事实 | 拒绝：第二处未覆盖 |
| `Say "The lamp is on." The lamp is on.`；没有 claims，NF 为 `Say` 与一条 `The lamp is on.` | 通过，独立事实所在的第二处文本也被自动排除 |

这是可独立于 benchmark 解释的位置记账问题，值得单独修复和验证。尚未量化本轮真实数据触发频率，也不能据此解释所有事实遗漏。修复需要处理同文不同语境及重叠跨度；不能将更严格的文字覆盖冒充事实召回保证。此轮没有改生产代码。

## 修正 unknown 与 FP/FN 的因果解释

独立配对本轮完整 360 条评分记录后确认：

| 转移 | 次数 |
| --- | ---: |
| FP → TN | 18 |
| TN → FP | 8 |
| FP → unknown | 0 |
| TN → unknown_negative | 4 |
| unknown_negative → TN | 1 |
| TP → unknown_positive | 1 |
| FN → TP | 1 |
| FN → unknown | 0 |

因此 **FP 净少 10 全部来自已决结果之间的净转移，并不是 FP 转为 unknown**。未决增加是另一项并存的完成性退步。主代理此前进度表述“部分 FP 减少与未决增加有关”过强，在此纠正。

`7022` 从 TP 变为未决正例，不解释 FN 下降；FN 下降来自 `15485` 的原生 FN→TP，该例通过把建议误抽为事实报警，语义合法性另有问题。保留原生矩阵，不将 AI 诊断覆盖原标签。

## 未采纳或仅保留为假设的建议

- **拒绝 6/41 外推到其余约 20 次翻转。** 相同提取对象的 41 例不是其他 138 例的随机代表样本；其他例的 M3 输入也改变了。来源组 bootstrap 不能估计重复生成方差，不能据此断言全部收益落在“随机噪声范围”。
- **不把源码结构当作提示诱发错误的因果证明。** 条件/来源误排与提示措辞的联系是有根据的假设，但尚未通过独立干预证明；`thinking: disabled` 本身也不能证明错误成因。
- **不改变 unknown 主评分口径。** 将 unknown 改算 FP/FN 与用户已定契约冲突；如需保守敏感性分析，应另列并清晰命名，不能替换原矩阵。
- **不采用事后指定的样本门槛。** `≥56/58`、固定 `171/180`、特定案例必须修好等不能升格为作者要求或未见验收门槛。AI 草案原子目标不是作者批准的事实召回金标。
- **不直接删除 `source_span`。** 它含原答案语义信息，并非纯定位噪声。载荷投影、分批变化与 token 成本须分别验证。
- **不直接重分配 retry 预算。** 当前批次行错误会使用共享定向重问额度，但尚未证明其解释本轮未完成目标增加。配置数字相同不代表总调用上限相同，不能把语义重判包装成格式修复，也不能放宽 C/U 上限。
- **不把有限审查子集换算为总体语义召回。** 原生标签、AI 审阅、作者裁定及未见评测仍须区分。

## 后续协作方式

已通过 Windows `computer-use` 接口打开并观察到 Antigravity 桌面端 2.25.0，当前项目为 TabbyML，模型选择为 Gemini 4 Argon High。没有在桌面端重复发送本轮审查，也没有改变其权限设置。

后续适合委派独立审查、明确范围的实现子任务或测试分析，由主代理核对证据、代码与结果。新建议先成为可证伪实验，不因来自另一 AI 而自动采用。禁止 benchmark 特调和作者终审边界继续生效。
