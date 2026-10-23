# v4 claim regression

Conditional label accuracy only uses completed text-aligned claims. Read with gold alignment coverage and unmatched predictions; not semantic accuracy of every paraphrase.

| Backend | Complete / partial / error | Aligned label accuracy | Gold alignment coverage | All-gold strict F1 diagnostic | Mean seconds |
| --- | --- | --- | --- | --- | --- |
| optimized-v4.0 | 10 / 0 / 0 | 100.00% | 92.31% | 88.89% | 2.48 |
