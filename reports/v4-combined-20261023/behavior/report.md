# v4 offline behavioral diagnostics

AI-draft expected labels, exploratory diagnostic evidence only. Same-label consistency counts stable mistakes; read both-expected-correct separately. No cross-dataset or unseen-generalization claim.

| Backend / mode | Complete / partial / error | Expected accuracy | Both correct pairs | Relation consistency | Stable wrong pairs | Target alignment coverage | Mean s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| optimized-v4-combined/end_to_end | 48 / 0 / 0 | 97.92% | 95.83% | 95.83% | 0 | 95.83% | 3.04 |
| optimized-v4-combined/fixed_claim | 48 / 0 / 0 | 97.92% | 95.83% | 95.83% | 0 | 100.00% | 1.97 |
| optimized-v4.0/end_to_end | 48 / 0 / 0 | 100.00% | 100.00% | 100.00% | 0 | 95.83% | 3.66 |
| optimized-v4.0/fixed_claim | 48 / 0 / 0 | 100.00% | 100.00% | 100.00% | 0 | 100.00% | 1.85 |

Required source-index presence is not a semantic citation audit. Fixed-claim costs exclude M1. All expected labels are AI-authored drafts; no formal acceptance or unseen status is implied.
