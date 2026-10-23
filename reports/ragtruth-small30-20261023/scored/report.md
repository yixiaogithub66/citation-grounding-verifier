# RAGTruth v4 partial-aware evaluation

Native labels are unchanged. Unknown outcomes never enter TN/FN. Conditional metrics require coverage.

| Backend | Complete | Partial | Error | TP / FP / TN / FN | Unknown + / - | Decision coverage | Resolved F1 | Legacy F1 lower bound |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| optimized-v4.0 | 26 | 4 | 0 | 13 / 10 / 6 / 1 | 0 / 0 | 100.00% (30/30) | 70.27% (26/37) | 58.82% (20/34) |

Claim completion counts are not semantic extraction coverage. RAGTruth supplies no complete claim gold.
All technical partials remain whole-case failures in the legacy comparison. Full metrics, costs and uncertainty are in report.json.
