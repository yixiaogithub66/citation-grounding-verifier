# RAGTruth v4 partial-aware evaluation

Native labels are unchanged. Unknown outcomes never enter TN/FN. Conditional metrics require coverage.

| Backend | Complete | Partial | Error | TP / FP / TN / FN | Unknown + / - | Decision coverage | Resolved F1 | Legacy F1 lower bound |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| optimized-v4.0 | 171 | 9 | 0 | 57 / 74 / 45 / 3 | 0 / 1 | 99.44% (179/180) | 59.69% (114/191) | 54.84% (102/186) |
| optimized-v4-m1-faithful | 167 | 13 | 0 | 57 / 64 / 52 / 2 | 1 / 4 | 97.22% (175/180) | 63.33% (114/180) | 57.78% (104/180) |

Claim completion counts are not semantic extraction coverage. RAGTruth supplies no complete claim gold.
All technical partials remain whole-case failures in the legacy comparison. Full metrics, costs and uncertainty are in report.json.

Paired source-cluster differences and runtime details are in report.json. Native FP is not author-adjudicated true FP.

| Backend | Calls | Mean / P95 seconds | Reference USD | Mean quote characters |
| --- | ---: | ---: | ---: | ---: |
| optimized-v4.0 | 1471 | 18.81 / 44.89 | None | 85.35849056603773 |
| optimized-v4-m1-faithful | 1365 | 16.62 / 41.67 | None | 90.83888612630533 |
