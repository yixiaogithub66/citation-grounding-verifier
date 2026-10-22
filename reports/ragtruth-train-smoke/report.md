# RAGTruth response-level hallucination detection

18 responses × 1 backends = 18 expected prediction records.

Gold is positive when native `labels` is nonempty, including `implicit_true` and `due_to_null`. Prediction is positive when any valid claim is `CONTRADICTED` or `UNSUPPORTED`.

Primary F1 is a **pessimistic failure lower bound**, not an official score: positive failures add FN; negative failures add FP. End-to-end accuracy counts every failure as incorrect. Values show numerator/denominator; undefined ratios remain undefined.

| Backend | Successful / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| baseline | 18/18 | 0 | 56.00% (14/25) | 38.89% (7/18) |

## baseline

Answered confusion: TP 7, FP 11, TN 0, FN 0. Positive failures 0; negative failures 0; missing records 0.

Answered-only metrics condition on successful outputs:

precision: 38.89% (7/18); recall: 100.00% (7/7); f1: 56.00% (14/25); accuracy: 38.89% (7/18).

95% source-cluster percentile intervals (100 draws, 3 source clusters, seed 20261022):

- detection_f1: [50.00%, 66.67%]; 100 defined and 0 undefined draws.
- end_to_end_accuracy: [33.33%, 50.00%]; 100 defined and 0 undefined draws.

Valid empty-claims outputs: 0; nonempty answer with empty claims: **0**; empty answer: 0; unknown answer length: 0. Empty claims predict negative; native detection does not assess extraction coverage.

Output verdict distribution (not three-class accuracy): SUPPORTED 8, CONTRADICTED 0, UNSUPPORTED 173.

Recorded exact citation substring validity: 100.00% (8/8); 0 records lack citation diagnostics. This does not measure semantic citation quality.

Schema outcomes: {'valid': 18, 'invalid': 0, 'not_returned': 0}. Source-dependent validation recorded for 18/18 records.

| Task | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| Data2txt | 6/6 | 0 | 50.00% (4/8) | 33.33% (2/6) |
| QA | 6/6 | 0 | 50.00% (4/8) | 33.33% (2/6) |
| Summary | 6/6 | 0 | 66.67% (6/9) | 50.00% (3/6) |

| Generator | Success / total | Errors | F1 lower bound | End-to-end accuracy |
| --- | ---: | ---: | ---: | ---: |
| gpt-3.5-turbo-0613 | 3/3 | 0 | 0.00% (0/3) | 0.00% (0/3) |
| gpt-4-0613 | 3/3 | 0 | 50.00% (2/4) | 33.33% (1/3) |
| llama-2-13b-chat | 3/3 | 0 | 80.00% (4/5) | 66.67% (2/3) |
| llama-2-70b-chat | 3/3 | 0 | 50.00% (2/4) | 33.33% (1/3) |
| llama-2-7b-chat | 3/3 | 0 | 50.00% (2/4) | 33.33% (1/3) |
| mistral-7B-instruct | 3/3 | 0 | 80.00% (4/5) | 66.67% (2/3) |

Recorded usage: 0 calls, 0 input tokens, 0 output tokens; complete: True. Estimated cost: USD 0.000000.

Latency: 18 measured, 0 unknown; mean 0.015777777783417452 s; total recorded 0.28400000010151416 s.

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
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\tmp\\ragtruth-train-smoke\\native_gold.jsonl",
    "sha256": "9ecfd87133a1086fd4cd249d0b7ed2306aa36cde0c9456892230be5fcc088eb1"
  },
  "manifest": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\tmp\\ragtruth-train-smoke\\manifest.jsonl",
    "sha256": "1ffe30561e09dfcd75182f63e440caf1363c20830b25e4fee44db3e0c189a8bd"
  },
  "predictions": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\reports\\ragtruth-train-smoke\\predictions.jsonl",
    "sha256": "32eaf3e18600dcd8517801b7fcb23064763949f2108163a8a485b9fa5e44cbb3"
  },
  "run_config": {
    "path": "D:\\HuaweiMoveData\\Users\\yixiao\\Desktop\\TabbyML\\reports\\ragtruth-train-smoke\\config.json",
    "sha256": "1d54450dfd9305a5e1c0c48985d85dbb38ca05925cadf552ad91e5db83a4281c"
  }
}
```
