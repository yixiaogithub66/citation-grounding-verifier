# RAGTruth v4 partial-aware evaluation

Native labels are unchanged. Unknown outcomes never enter TN/FN. Conditional metrics require coverage.

| Backend | Complete | Partial | Error | TP / FP / TN / FN | Unknown + / - | Decision coverage | Resolved F1 | Legacy F1 lower bound |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| baseline | 180 | 0 | 0 | 60 / 120 / 0 / 0 | 0 / 0 | 100.00% (180/180) | 50.00% (120/240) | 50.00% (120/240) |
| minimal | 171 | 0 | 9 | 55 / 75 / 41 / 0 | 5 / 4 | 95.00% (171/180) | 59.46% (110/185) | 56.70% (110/194) |
| optimized-v3 | 170 | 0 | 10 | 53 / 63 / 53 / 1 | 6 / 4 | 94.44% (170/180) | 62.35% (106/170) | 58.89% (106/180) |
| optimized-v4.0 | 170 | 10 | 0 | 57 / 66 / 52 / 3 | 0 / 2 | 98.89% (178/180) | 62.30% (114/183) | 56.98% (102/179) |

Claim completion counts are not semantic extraction coverage. RAGTruth supplies no complete claim gold.
All technical partials remain whole-case failures in the legacy comparison. Full metrics, costs and uncertainty are in report.json.

Exposed-v1 development comparison: historical baseline/minimal/v3 logs plus newly executed v4. Not a contemporaneous controlled rerun, independent test, or component ablation.
