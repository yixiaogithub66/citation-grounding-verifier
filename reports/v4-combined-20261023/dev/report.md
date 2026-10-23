# RAGTruth v4 partial-aware evaluation

Native labels are unchanged. Unknown outcomes never enter TN/FN. Conditional metrics require coverage.

| Backend | Complete | Partial | Error | TP / FP / TN / FN | Unknown + / - | Decision coverage | Resolved F1 | Legacy F1 lower bound |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| optimized-v4.0 | 170 | 10 | 0 | 58 / 66 / 52 / 2 | 0 / 2 | 98.89% (178/180) | 63.04% (116/184) | 56.98% (102/179) |
| optimized-v4-combined | 179 | 1 | 0 | 60 / 76 / 44 / 0 | 0 / 0 | 100.00% (180/180) | 61.22% (120/196) | 61.22% (120/196) |

Claim completion counts are not semantic extraction coverage. RAGTruth supplies no complete claim gold.
All technical partials remain whole-case failures in the legacy comparison. Full metrics, costs and uncertainty are in report.json.

Paired source-cluster differences and runtime details are in report.json. Native FP is not author-adjudicated true FP.

| Backend | Calls | Mean / P95 seconds | Reference USD | Mean quote characters |
| --- | ---: | ---: | ---: | ---: |
| optimized-v4.0 | 1509 | 17.45 / 43.12 | 1.1277086459999999 | 88.59105286940805 |
| optimized-v4-combined | 1620 | 31.86 / 71.27 | 2.39595852 | 97.3038567493113 |
