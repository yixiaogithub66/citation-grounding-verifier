# v4 四个假设的组合实现与开发实验

状态：2026-10-23 用户授权直接组合落地。独立后端为 `optimized-v4-combined`；`optimized-v4.0` 保留作对照，默认 `optimized` 仍指向 v3。人工裁定剩余事项暂缓，实验不将未定稿审核当作最终 gold。

## 实现边界

- H1：代码给原答案建立不可变位置单元和 token 范围，M1 决定原子命题及目标/背景关系。按精确跨度记事实、非事实、歧义和残留；有界补提取失败后保留原句骨架。位置覆盖不等于事实召回，背景不属于来源证据。不增加运行时拼句或语义合并。
- H2：新的内部 `source-evidence-pointers-v1` 协议分开 `considered_evidence_ids` 和 `decision_evidence_ids`。从原始来源位置生成逐字引用。U 的结论证据必须为空；非法非空、未知 ID、失败调用仍报错或走有界重试。完整 context 保留，代码不判断证据的语义充分性。
- H3：现有 C/U 复核采用同一个初判盲化提示，不给模型初判标签、理由、已选证据或触发诊断。保留原 claim、范围和完整 context。触发器、C→U 次序、C≤1/U≤1、全链共享 targeted 重问≤1 均沿用 v4。一次复核自身的格式修复可以看到自身输出，不代表看到初判。
- H4：离线行为及变形测试，不加入生产推理调用链。分别跑固定 claim 和完整流程，检查预声明关系与两侧正确性，AI 草拟标签不冒充作者终审。

`/verify` 的完整/部分/全失败契约不变。所有推理输入共用相同任务定义、长度策略和资源配置；推理不接收数据集身份、样本 ID、原生 gold、生成器信息或变形家族。

## 调用前确定的比较方案

主比较为旧 RAGTruth blind-v1/recovery 的全部 180 条、30 个来源组：两个后端重新运行同一输入，按固定种子的逐例随机后端顺序配对，来源和 gold 元数据只留在评测器。阶段 thinking、输出预算、最大 claims、批大小、重试次数均用相同 `configs/optimized-v4.0.json`。H1 的残留调用属于新增机制，实际调用及成本单列，不将同上限冒充同总成本。

冻结推理、提示词、配置、评测代码和数据哈希后才调用；每个结果落盘并保留原始 telemetry。推理时仅对 gold 文件做字节哈希，评分在推理后单独读取。前后代码或数据变化会将本轮标为无效。模型返回名称与 fingerprint 按实际记录报告。统一参考价使用输入 USD 0.30、缓存输入 USD 0.006、输出 USD 1.20 / 百万 token，与既有开发报告一致，非实际账单或现价声明。

结果完整列出：

1. 原生回答级 TP/FP/TN/FN、部分全 S 的未知项、完整/部分/失败数、完成覆盖率与条件 F1，历史全例失败口径并列。原生 FP 不称作者裁定的真 FP。
2. 配对回答改变：错→对、对→错、未知转移；按完整来源组 bootstrap 2,000 次，报告 F1、全例正确决策率、决策覆盖率与完整率差值的 95% 描述区间。暴露开发集区间不构成独立确认。
3. M1 降级、格式修复、targeted 重问、C/U 复核及翻转、实际 token、均值/P95 延迟、参考价费用。RAGTruth 无完整 claim gold，翻转不可直接称纠错；已完成 claims 占比不称事实召回。
4. H4 预先固定的 24 对 AI 草拟原/变体（48 输入），覆盖多个领域和错误族，两个后端均跑固定 claim 与端到端模式。报告原/变体双项正确率、关系一致率、空结果与错误，不因结果不利而删除样例或重写期望。

这次仅识别**组合版本相对原 v4 的效果**，不归因于某一个假设。一次开发实验不能证明跨数据集、跨模型或未见来源泛化。已有验收条件维持；语义目标未达成时如实报告。不会根据本轮已知案例添加特例，也不会因分数好看便将组合版提升为默认。

## 运行

```powershell
python -m grounding.server --backend optimized-v4-combined --v4-config configs/optimized-v4.0.json
python scripts/benchmark_v4_combined.py --output-dir results/v4-combined-dev --v4-config configs/optimized-v4.0.json --price-input 0.3 --price-cached-input 0.006 --price-output 1.2
python scripts/summarize_v4_combined.py --run-dir results/v4-combined-dev --output-dir reports/v4-combined-dev
python scripts/benchmark_v4_behavior.py --help
```

复现需使用新输出目录，不覆盖上一轮日志。正式未见 v2 不在本轮取数；文献展示案例的来源映射和作者裁定余项仍按此前要求在正式验收前处理。

研究依据及各机制的反证条件见 [跨来源研究报告](../research/v4-generality-20261023/REPORT.md) 和 [组合假设](../research/v4-generality-20261023/phase3_synthesis.md)。
