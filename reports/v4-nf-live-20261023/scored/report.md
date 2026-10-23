# NF occurrence repair: fresh paired evaluation

Fresh paired exposed-development diagnostic; all labels unchanged; supplementary labels are not author-adjudicated gold.

Only the NF occurrence parser changes. Prompt, model settings, M3 and review limits are shared. One generation per variant; differences include model and service variability.

| Dataset / variant | Complete / partial / error | Accuracy or correct / all gold | Extracted factual claim completion |
| --- | --- | --- | --- |
| dev / pre_fix | 168 / 12 / 0 | 102/180 (56.67%) | 1549/1578 (98.16%) |
| dev / post_fix | 168 / 12 / 0 | 104/180 (57.78%) | 1518/1540 (98.57%) |
| behavior / pre_fix | 48 / 0 / 0 | 44/48 (91.67%) | 46/46 (100.00%) |
| behavior / post_fix | 48 / 0 / 0 | 46/48 (95.83%) | 47/47 (100.00%) |
| physics / pre_fix | 46 / 0 / 0 | 50/58 (86.21%) | 62/62 (100.00%) |
| physics / post_fix | 46 / 0 / 0 | 48/58 (82.76%) | 61/61 (100.00%) |

Dev quality above counts correct native answer decisions over every input; unresolved is not counted as correct or as TN/FN. Physics is strict text-aligned correct / all predeclared claims, not all semantic claims.

| Dev variant | TP / FP / TN / FN | Unknown + / − | Decided accuracy | Decided F1 |
| --- | --- | --- | --- | --- |
| pre_fix | 57 / 73 / 45 / 3 | 0 / 2 | 102/178 (57.30%) | 114/190 (60.00%) |
| post_fix | 56 / 69 / 48 / 3 | 1 / 3 | 104/176 (59.09%) | 112/184 (60.87%) |

| Dev task / variant | Correct decisions / all | Decided accuracy | Decided F1 | Complete / partial / error |
| --- | --- | --- | --- | --- |
| Data2txt / pre_fix | 44/60 (73.33%) | 44/59 (74.58%) | 76/91 (83.52%) | 52 / 8 / 0 |
| QA / pre_fix | 29/60 (48.33%) | 29/60 (48.33%) | 16/47 (34.04%) | 59 / 1 / 0 |
| Summary / pre_fix | 29/60 (48.33%) | 29/59 (49.15%) | 22/52 (42.31%) | 57 / 3 / 0 |
| Data2txt / post_fix | 45/60 (75.00%) | 45/58 (77.59%) | 74/87 (85.06%) | 50 / 10 / 0 |
| QA / post_fix | 32/60 (53.33%) | 32/59 (54.24%) | 16/43 (37.21%) | 59 / 1 / 0 |
| Summary / post_fix | 27/60 (45.00%) | 27/59 (45.76%) | 22/54 (40.74%) | 59 / 1 / 0 |

| Dev paired delta (post − pre) | Point, percentage points | Source-cluster 95% interval |
| --- | ---: | ---: |
| resolved_accuracy | +1.79 | -4.05 to +7.34 |
| resolved_f1 | +0.87 | -2.81 to +4.19 |
| correct_decisions_per_all_cases | +1.11 | -5.00 to +6.67 |
| decision_coverage | -1.11 | -3.33 to +1.11 |
| complete_case_rate | +0.00 | -4.44 to +4.44 |
| claim_completion_known_cases | +0.41 | -0.65 to +1.57 |

| Dataset / variant | Calls / missing usage | Input / output / cached tokens | Mean / P95 seconds | Known reference USD / unpriced calls | All-miss standardized known USD |
| --- | --- | --- | --- | --- | --- |
| all / pre_fix | 1688 / 7 | 2563331 / 829228 / 2066985 | 14.79 / 40.80 | 1.156379 / 7 | 1.764073 |
| all / post_fix | 1674 / 3 | 2540552 / 723448 / 2057124 | 12.86 / 32.84 | 1.025509 / 3 | 1.630303 |
| dev / pre_fix | 1478 / 7 | 2398654 / 800434 / 1947330 | 20.55 / 48.73 | 1.107602 / 7 | 1.680117 |
| dev / post_fix | 1462 / 3 | 2373811 / 694154 / 1936319 | 17.59 / 36.70 | 0.975850 / 3 | 1.545128 |
| behavior / pre_fix | 104 / 0 | 75477 / 10703 / 54254 | 3.43 / 5.94 | 0.019536 / 0 | 0.035487 |
| behavior / post_fix | 105 / 0 | 76686 / 11076 / 55278 | 3.45 / 5.91 | 0.020045 / 0 | 0.036297 |
| physics / pre_fix | 106 / 0 | 89200 / 18091 / 65401 | 4.12 / 7.11 | 0.029241 / 0 | 0.048469 |
| physics / post_fix | 107 / 0 | 90055 / 18218 / 65527 | 4.17 / 7.52 | 0.029613 / 0 | 0.048878 |

Reference USD per million tokens: input 0.30, cached input 0.006, output 1.20. Missing usage is not zero cost; subtotals are not complete bills. All-miss standardized cost isolates cache accounting, not output-length or model variability.

| Variant / execution order | Records | Mean / P95 seconds | Cached / input tokens | Known USD / unpriced calls |
| --- | --- | --- | --- | --- |
| pre_fix / first | 137 | 14.89 / 43.12 | 1006032 / 1258309 | 0.589238 / 5 |
| pre_fix / second | 137 | 14.70 / 40.58 | 1060953 / 1305022 | 0.567142 / 2 |
| post_fix / first | 137 | 12.96 / 34.09 | 1053404 / 1301249 | 0.508380 / 3 |
| post_fix / second | 137 | 12.77 / 32.84 | 1003720 / 1239303 | 0.517128 / 0 |

No unseen data or adjudicated labels are used. Native score gains are not evidence of claim-level correction or generalization. JSON includes completion denominators, strict/approximate alignment, unknowns, transitions, usage gaps and all case scores.

Dual-parser audit: 57/548 observed records contain a transport-usable M1 payload whose validator result, NF ledger or rejection feedback differs; 0 ledger/chunk anomalies.

Both frozen validators are applied only to actual observed M1 payloads and exact recorded chunks. Changed rejection feedback may change later model responses, so later frozen responses are not a counterfactual rerun. Affected subsets are post-treatment descriptive diagnostics, not causal isolation from model variance.
