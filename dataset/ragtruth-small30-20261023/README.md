# RAGTruth 当前系统输入：其他来源 30 条

2026-10-23 固定取样，QA、Summary、Data2txt 各 10 条，每条来自一个不同来源，与此前登记的 33 个来源无重叠。原始版本为 ParticleMedia/RAGTruth `c103204b9ce28d6bbad859304bf30de72b8ed8fe`，许可保存在 `UPSTREAM_LICENSE`。

`inputs.jsonl` 每行包含 `id` 和 `input`。调用当前 `/verify` 时只提交 `input`，其中只有 `context_passages` 与 `generated_answer`；`id` 用于评测记账，不进入模型。

- `manifest.jsonl`：来源、任务、生成器、输入哈希及适配方式，仅供评测追溯。
- `native_gold.jsonl`：原生 hallucination spans 和回答级有无幻觉标记；与推理输入严格分离，不是人工裁定后的原子声明 S/C/U 金标。
- `preparation.json`：固定哈希取样与原始文件、输入文件绑定，不按标签或模型分数选样。

答案保持原文。QA 保留来源段落，问题不当作证据；Summary 保留原文；Data2txt 使用确定性 JSON 序列化，保留 null、布尔值及结构。本目录四份 JSON/JSONL 数据与 `results/ragtruth-small30-20261023/data/` 的冻结文件逐字节一致。

这是探索性小样本测试，已有少量文献曝光的来源映射未决，不能称严格未见验收。此批已登记曝光；未来若根据结果优化，不能继续把它当未见数据。正式 180 条 blind-v2 需另外执行原有流程并排除此批来源。

结果与限制见 [评测报告](../../reports/ragtruth-small30-20261023/README.md)。
