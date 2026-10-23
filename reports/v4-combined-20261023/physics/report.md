# v4 claim regression

Conditional label accuracy only uses completed text-aligned claims. Read with gold alignment coverage and unmatched predictions; not semantic accuracy of every paraphrase.

| Backend | Complete / partial / error | Aligned label accuracy | Gold alignment coverage | All-gold strict F1 diagnostic | Mean seconds |
| --- | --- | --- | --- | --- | --- |
| optimized-v4-combined | 46 / 0 / 0 | 97.78% | 77.59% | 73.33% | 3.98 |
| optimized-v4.0 | 46 / 0 / 0 | 100.00% | 91.38% | 89.08% | 3.34 |
