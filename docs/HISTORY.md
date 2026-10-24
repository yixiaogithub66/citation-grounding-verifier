# 版本与实验索引

发布目录聚焦服务、测试、可运行评测和代表性结果。完整研究、审阅草案、多轮运行和源码快照保留于 [develop的固定归档提交bd51922](https://github.com/yixiaogithub66/citation-grounding-verifier/tree/bd51922)，无需改写Git历史。历史记录中的绝对路径、版本别名和默认值描述当时环境，不代表当前启动要求。

| 阶段 | 实现/问题 | 证据与采用判断 |
| --- | --- | --- |
| baseline / minimal | 规则方法与单调用对照 | 统一公共输入和响应契约；不把启发式召回当语义能力 |
| optimized-v2 | 两阶段拆分、核查及程序化引用校验 | 旧CPHOS测试严格F1 86.57%，低于minimal 89.23%；负结果保留 |
| optimized-v3 / v3.1 | 尝试通过拆分与冗余边界改善粒度 | 同来源12条确认中严格F1 97.62%；合并实际0次，不能将收益归因于合并阶段 |
| optimized-v4.0 | 取消运行时合并；分块、降级、分批、引用重判、C/U有界复核、partial | 当前主线。旧180用于开发，新来源180上正确产出103/180 vs minimal88/180；F1差区间仍跨零 |
| combined | 同时组合多项通用假设 | 旧180完整报告170→179，但已决F1 63.04%→61.22%，费用约2.12倍，未采用 |
| M1-faithful | 单独改事实拆分提示 | 旧180已决F1 59.69%→63.33%，完整171→167，存在事实/条件丢失，未采用 |
| NF发生处修复 | 每条非事实片段只认领其一次出现 | 修复通用记账缺陷；旧180正确102→104，差值区间跨零，不能宣称稳定泛化收益 |

`optimized` 在当前发布入口指向v4.0；复现旧版本应使用 `optimized-v2` 或 `optimized-v3`，不要依赖历史别名。冻结v2文件继续按原始字节哈希核验。实验后端没有被提升为默认。

## 代表性历史报告

- [v2开发迭代与负向结果](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/docs/ITERATIONS.md)
- [v3.1同来源确认及审计](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/confirmation-v3.1/AUDIT.md)
- [首轮RAGTruth blind-v1](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/ragtruth-blind-v1-recovery/AUDIT.md)
- [combined配对实验](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/v4-combined-20261023/README.md)
- [M1-faithful配对实验](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/v4-m1-faithful-20261023/README.md)
- [NF发生处修复的实测](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/v4-nf-live-20261023/README.md)
- [small30三方案比较](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/ragtruth-small30-comparators-20261023/README.md)
- [新来源180条：当前结果导览](../reports/ragtruth-fresh180-20261024/README.md)

这些表来自不同样本、运行和评分层级，不能将各列最大值拼成统一排行榜。v4在small30的70.27% F1与新180的59.89%也不是同样本版本退步。

## 组件实验怎样解释复杂度

[M1/M3/复核对照](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/stage-attribution-pilot-20261024.md)使用20条新虚构回答、45个AI标注目标，每输入重复两次。它是诊断实验，不是自然RAGTruth或作者终审金标。

- M1：简短对照严格完成且保真18/40，当前16/40；当前对纯非事实和误纳有局部改善，未形成整体优势。18份结构失败中13份涉及文字覆盖记账。
- 固定claim的M3：公共契约有效且标签正确84/90与85/90；可读raw正确标签均87/90，简单版另3错、当前版另3未知。局部语义改进被协议失败抵消，不能称显著优势。
- 复核：85个符合入口的初判标签都正确，实际触发27次，标签翻转0；修复1条内部conflict结构。没有错误初判机会，所以零净纠错既不证明复核有效，也不证明复核无用。

[双向选择](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/bidirectional-selection-pilot-20261024.md)与[覆盖账本](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/coverage-protocol-pilot-20261024.md)只测局部提取协议，未升级当前推理。发布收口不追加研究实验，不将更复杂的设计自动称为更好的系统。

## 归档边界

历史源码快照和原始评测结果不重新格式化、不更新其中的哈希或金标。本发布树只增加交付导览和必要的通用工程修复；对旧报告进行离线复算应使用其冻结源码。已曝光数据只用于回归，新未见评测需先冻结当前推理再按来源排重取数。作者裁定状态与AI草案各自保留，不能由AI审阅冒充作者终审。
