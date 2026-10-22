# CPHOS28 同来源、同题族新增确认集

这是在作者批准三个 pilot 和 v3.1 标注规则之后构造的正式确认集。共12个案例、42条 gold，使用Q2、Q6、Q7的新选录片段；没有使用Q5或把pilot转为正式样例。标签由AI构造并经过另一个只读AI审阅角色复核，**不声称作者逐条审阅了这42条标签**。

| 类型 | 案例数 | 声明数 | 设计 |
| --- | ---: | ---: | --- |
| density | 3 | 15 | 每例5句，覆盖正确关系、细微错误及无依据补充 |
| scope_distractor | 3 | 9 | 不同绳段、内部连接与固定端、特殊位置与一般坐标并置 |
| mixed_truth_compound | 3 | 9 | 同一句中的错误文字性质与正确公式分开判定，另含无依据陈述 |
| reformulation_calculation | 3 | 9 | 代入消元、递推求和/求差、双曲函数关系，需要真实多段证据 |

标签计数为 SUPPORTED 15、CONTRADICTED 13、UNSUPPORTED 14。新规则允许同一句中一致的局部性质描述与完整公式合并，但半对半错仍拆分。一般公式的声明明确按函数关系或恒等式判断，不把某个退化参数点的偶合当成全域等价；需要特定条件时写进待查声明，不默补物理参数。

## 文件与审阅

- `cases.jsonl`：正式、完整案例，统一 `split=confirmation`。
- `inputs.jsonl`：仅包含端点输入，不含gold。
- `gold.jsonl`、`manifest.jsonl`：标签与案例索引。
- `sources.json`、[来源核对](SOURCE_REVIEW.md)：原PDF位置、规范化证明和来源限制。
- [AI审阅记录](AI_REVIEW.md)：逐case结论、冻结前修订和全部42条声明。
- `construction.json`：构造时序、最初数据哈希及后续审查记录。
- `confirmation.freeze.json`：由统一runner在推理前写入的数据、代码和四路模型设置冻结记录。
- `review-history/draft-before-review.jsonl`：审阅前初稿，只用于追溯，不参与评分。

作者批准的是 [三个pilot与标注规则](../../reviews/cphos28/pilot-author-review.json)。正式数据采用的规则见 [ANNOTATION_POLICY_V3.md](../../docs/ANNOTATION_POLICY_V3.md)。三个pilot永久排除本集，即使它们未引起进一步修改。

## 构造与冻结时序

1. 首次v3.1实现于 `2026-10-22T02:53:51.501010+00:00` 冻结，数据代理随后构造新案例。
2. 数据初稿于 `2026-10-22T02:59:25.325949+00:00` 落盘，尚未提供给推理代码作者或主整合代理，也没有模型预测。
3. 独立的合成代码审查发现一个确定性合并边界问题：相同的较弱文字可能覆盖完整公式。代码修复来自合成复现，不来自本数据；提示语义、评分规则未改。最终代码于 `2026-10-22T03:02:20.670053+00:00` 冻结，见 [最终实现freeze](../../reports/v3.1-code-freeze-final.json)。
4. 独立数据审阅在任何模型推理前纠正一条范围断言的C/U边界、去除一处推导中不必要的非零假设，并澄清六条一般公式的量化范围。初稿保留，修订理由逐项记录。
5. 数据审查和结构校验完成后冻结本集，再由统一runner在相同输入上运行四路。冻结后不因预测或得分调整标签。

这份时序不声称“所有代码修改都发生在任何数据构造之前”。实际隔离条件是：最终边界修复未使用正式案例或预测，正式数据与设置均在模型推理前冻结。

## 校验与复现

```powershell
python scripts/validate_dataset.py --dataset dataset/cphos28-confirmation/cases.jsonl
```

原PDF在本机时可额外检查来源哈希：

```powershell
python scripts/validate_dataset.py --dataset dataset/cphos28-confirmation/cases.jsonl --check-local-sources
```

`scripts/build_confirmation_dataset.py` 保存构造逻辑。它检查作者批准和最终实现freeze的哈希，且拒绝覆盖现有确认集。使用已提交的数据即可复现输入，不需要原PDF或重新运行构造脚本。案例中的 `ai_review_status_at_construction` 只记录构造时状态，最终审阅状态见单独审阅与freeze记录。

## 解释范围

同一题在本集中有4例，部分片段跨类别重复使用，各例不是独立抽样。这是同来源、同题族的新增诊断确认，不能当作新的题目级独立测试集或通用物理能力基准。待查回答由AI控制构造，不是模型真实回答分布。结构校验不等于语义证明，AI复核也不是出题方认证。

四路应在同一正式 `cases.jsonl` 上比较，不把初稿、pilot或旧test混入本集统计。v2/v3.1和minimal/v3.1在同批数据上的比较都有效；跨新旧数据集的分数差异混入了难度变化。当前本目录只记录数据及其构造，不包含性能结论。
