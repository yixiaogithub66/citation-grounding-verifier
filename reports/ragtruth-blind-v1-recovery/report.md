# RAGTruth response-level hallucination detection

180 responses × 3 backends = 540 expected prediction records.

Gold is positive when native `labels` is nonempty, including `implicit_true` and `due_to_null`. Prediction is positive when any valid claim is `CONTRADICTED` or `UNSUPPORTED`.

Primary F1 is a **pessimistic failure lower bound**, not an official score: positive failures add FN; negative failures add FP. End-to-end accuracy counts every failure as incorrect. Values show numerator/denominator; undefined ratios remain undefined.

| Backend | Successful / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| baseline | 180/180 | 0 | 50.00% (120/240) | 33.33% (60/180) |
| minimal | 171/180 | 9 | 56.70% (110/194) | 53.33% (96/180) |
| optimized-v3 | 170/180 | 10 | 58.89% (106/180) | 58.89% (106/180) |

## baseline

Answered confusion: TP 60, FP 120, TN 0, FN 0. Positive failures 0; negative failures 0; missing records 0.

Answered-only metrics condition on successful outputs:

precision: 33.33% (60/180); recall: 100.00% (60/60); f1: 50.00% (120/240); accuracy: 33.33% (60/180).

95% source-cluster percentile intervals (2000 draws, 30 source clusters, seed 20261022):

- detection_f1: [38.57%, 61.00%]; 2000 defined and 0 undefined draws.
- end_to_end_accuracy: [23.89%, 43.89%]; 2000 defined and 0 undefined draws.

Valid empty-claims outputs: 0; nonempty answer with empty claims: **0**; empty answer: 0; unknown answer length: 0. Empty claims predict negative; native detection does not assess extraction coverage.

Output verdict distribution (not three-class accuracy): SUPPORTED 34, CONTRADICTED 5, UNSUPPORTED 1453.

Recorded exact citation substring validity: 100.00% (39/39); 0 records lack citation diagnostics. This does not measure semantic citation quality.

Schema outcomes: {'valid': 180, 'invalid': 0, 'not_returned': 0}. Source-dependent validation recorded for 180/180 records.

| Task | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| Data2txt | 60/60 | 0 | 77.55% (76/98) | 63.33% (38/60) |
| QA | 60/60 | 0 | 30.99% (22/71) | 18.33% (11/60) |
| Summary | 60/60 | 0 | 30.99% (22/71) | 18.33% (11/60) |

| Generator | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| gpt-3.5-turbo-0613 | 30/30 | 0 | 23.53% (8/34) | 13.33% (4/30) |
| gpt-4-0613 | 30/30 | 0 | 12.50% (4/32) | 6.67% (2/30) |
| llama-2-13b-chat | 30/30 | 0 | 50.00% (20/40) | 33.33% (10/30) |
| llama-2-70b-chat | 30/30 | 0 | 57.14% (24/42) | 40.00% (12/30) |
| llama-2-7b-chat | 30/30 | 0 | 77.55% (38/49) | 63.33% (19/30) |
| mistral-7B-instruct | 30/30 | 0 | 60.47% (26/43) | 43.33% (13/30) |

Recorded usage: 0 calls, 0 input tokens, 0 output tokens; complete: True. Estimated cost: USD 0.000000.

Latency: 180 measured, 0 unknown; mean 0.01695555555828226 s; total recorded 3.052000000490807 s.

## minimal

Answered confusion: TP 55, FP 75, TN 41, FN 0. Positive failures 5; negative failures 4; missing records 0.

Answered-only metrics condition on successful outputs:

precision: 42.31% (55/130); recall: 100.00% (55/55); f1: 59.46% (110/185); accuracy: 56.14% (96/171).

95% source-cluster percentile intervals (2000 draws, 30 source clusters, seed 20261022):

- detection_f1: [45.30%, 66.67%]; 2000 defined and 0 undefined draws.
- end_to_end_accuracy: [45.00%, 61.67%]; 2000 defined and 0 undefined draws.

Valid empty-claims outputs: 0; nonempty answer with empty claims: **0**; empty answer: 0; unknown answer length: 0. Empty claims predict negative; native detection does not assess extraction coverage.

Output verdict distribution (not three-class accuracy): SUPPORTED 1878, CONTRADICTED 75, UNSUPPORTED 311.

Recorded exact citation substring validity: 100.00% (2443/2443); 0 records lack citation diagnostics. This does not measure semantic citation quality.

Schema outcomes: {'valid': 171, 'invalid': 9, 'not_returned': 0}. Source-dependent validation recorded for 180/180 records.

| Task | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| Data2txt | 54/60 | 6 | 75.00% (66/88) | 63.33% (38/60) |
| QA | 59/60 | 1 | 43.14% (22/51) | 51.67% (31/60) |
| Summary | 58/60 | 2 | 40.00% (22/55) | 45.00% (27/60) |

| Generator | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| gpt-3.5-turbo-0613 | 28/30 | 2 | 36.36% (8/22) | 53.33% (16/30) |
| gpt-4-0613 | 29/30 | 1 | 14.29% (2/14) | 60.00% (18/30) |
| llama-2-13b-chat | 27/30 | 3 | 45.71% (16/35) | 36.67% (11/30) |
| llama-2-70b-chat | 30/30 | 0 | 61.54% (24/39) | 50.00% (15/30) |
| llama-2-7b-chat | 28/30 | 2 | 75.00% (36/48) | 60.00% (18/30) |
| mistral-7B-instruct | 29/30 | 1 | 66.67% (24/36) | 60.00% (18/30) |

Recorded usage: 180 calls, 185866 input tokens, 1235354 output tokens; complete: True. Estimated cost: USD 1.507703.

Latency: 180 measured, 0 unknown; mean 27.57662222222231 s; total recorded 4963.792000000016 s.

## optimized-v3

Answered confusion: TP 53, FP 63, TN 53, FN 1. Positive failures 6; negative failures 4; missing records 0.

Answered-only metrics condition on successful outputs:

precision: 45.69% (53/116); recall: 98.15% (53/54); f1: 62.35% (106/170); accuracy: 62.35% (106/170).

95% source-cluster percentile intervals (2000 draws, 30 source clusters, seed 20261022):

- detection_f1: [47.67%, 68.37%]; 2000 defined and 0 undefined draws.
- end_to_end_accuracy: [50.56%, 66.11%]; 2000 defined and 0 undefined draws.

Valid empty-claims outputs: 2; nonempty answer with empty claims: **2**; empty answer: 0; unknown answer length: 0. Empty claims predict negative; native detection does not assess extraction coverage.

Output verdict distribution (not three-class accuracy): SUPPORTED 1441, CONTRADICTED 59, UNSUPPORTED 230.

Recorded exact citation substring validity: 100.00% (2473/2473); 0 records lack citation diagnostics. This does not measure semantic citation quality.

Schema outcomes: {'valid': 170, 'invalid': 10, 'not_returned': 0}. Source-dependent validation recorded for 180/180 records.

| Task | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| Data2txt | 52/60 | 8 | 78.05% (64/82) | 70.00% (42/60) |
| QA | 59/60 | 1 | 40.82% (20/49) | 51.67% (31/60) |
| Summary | 59/60 | 1 | 44.90% (22/49) | 55.00% (33/60) |

| Generator | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| gpt-3.5-turbo-0613 | 27/30 | 3 | 27.27% (6/22) | 46.67% (14/30) |
| gpt-4-0613 | 29/30 | 1 | 30.77% (4/13) | 70.00% (21/30) |
| llama-2-13b-chat | 27/30 | 3 | 47.06% (16/34) | 40.00% (12/30) |
| llama-2-70b-chat | 29/30 | 1 | 58.82% (20/34) | 53.33% (16/30) |
| llama-2-7b-chat | 28/30 | 2 | 77.27% (34/44) | 66.67% (20/30) |
| mistral-7B-instruct | 30/30 | 0 | 78.79% (26/33) | 76.67% (23/30) |

Recorded usage: 398 calls, 570840 input tokens, 3654904 output tokens; complete: True. Estimated cost: USD 4.456020.

Latency: 180 measured, 0 unknown; mean 86.8227000000033 s; total recorded 15628.086000000592 s.

## Paired differences

All manifest responses remain paired, including failures. Differences are candidate minus minimal using identical source-cluster draws.

| Comparison | Metric | Difference | 95% interval | Defined draws |
| --- | --- | ---: | ---: | ---: |
| optimized-v3_minus_minimal | detection_f1 | 2.19 pp | [-2.64, 7.50] pp | 2000 |
| optimized-v3_minus_minimal | end_to_end_accuracy | 5.56 pp | [0.00, 12.22] pp | 2000 |

## Limitations

- This is response-level hallucination detection on RAGTruth native labels, not an official span-localization score or atomic-claim accuracy. No complete atomic-claim gold is available.
- Native gold is positive exactly when labels is nonempty, including implicit_true and due_to_null annotations. Unmarked answer text is never converted into SUPPORTED claim gold.
- A valid response predicts positive if any claim is CONTRADICTED or UNSUPPORTED. A valid empty claims array predicts negative, including for a nonempty answer. Native detection does not measure claim extraction coverage.
- Answered-only precision, recall, F1 and accuracy condition on successful outputs. Request errors, malformed outputs and missing records remain in all-case coverage and end-to-end denominators; they are never treated as clean responses.
- The primary detection_f1 is an explicit pessimistic lower bound, not an official score: positive failures add false negatives and negative failures add false positives. Every failure is incorrect for end_to_end_accuracy.
- SUPPORTED / CONTRADICTED / UNSUPPORTED counts are an output distribution, not three-class classification accuracy. Exact citation substring validity is a mechanical check, not semantic citation quality.
- Scoring checks output structure independently. Source-dependent schema and exact-substring checks use runner-recorded diagnostics; absent diagnostics are reported as unknown and cannot be reconstructed without source text.
- Confidence intervals use percentile bootstrap resampling of whole source_id clusters, retaining all responses and backends for a sampled source. They do not isolate model sampling or API variation; undefined F1 replicates are reported and excluded from its percentile interval.
- Usage and latency include recorded failed attempts. Missing telemetry is unknown, not zero. Cost uses explicitly supplied prices and recorded usage, not provider billing.

## Input hashes

```json
{
  "gold": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\dataset\\ragtruth-blind-v1\\recovery\\native_gold.jsonl",
    "sha256": "1a8bc7681b5fbd86a53dd8cafe8b0dad8df3939159f0a9ebc2af137a177231db"
  },
  "manifest": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\dataset\\ragtruth-blind-v1\\recovery\\manifest.jsonl",
    "sha256": "d3b2f0eea2fac1ec55f4436863b5836db5e4269fd47a206989e0a2920bf2b430"
  },
  "predictions": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\reports\\ragtruth-blind-v1-recovery\\predictions.jsonl",
    "sha256": "648b2518f19127665d667babd300ee318780c2508159ec3ea0d739b4e0a68f7c"
  },
  "run_config": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\reports\\ragtruth-blind-v1-recovery\\config.json",
    "sha256": "c8b6fd5acea5621dd11594ec68e9847a62dd84f240e98397c7a033acd892aaba"
  }
}
```
