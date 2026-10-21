# Verifier benchmark

Run `dev-v3-final`; status **complete**; split `dev`.
Completed 72 / 72 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 18 | 100.0% | 33.3% | 27.6% | 33.3% | 100.0% | 11.1% | 0.0022 | 0.0023 | 0.0048 | 0 / 0 | 0.0000 USD |
| minimal | 18 | 100.0% | 89.8% | 91.2% | 89.8% | 100.0% | 88.9% | 2.5679 | 1.9100 | 8.2304 | 6285 / 8309 | 0.0111 USD |
| optimized-v2 | 18 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.9160 | 4.0533 | 12.4857 | 23627 / 14955 | 0.0202 USD |
| optimized-v3 | 18 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 5.7163 | 4.3008 | 10.7274 | 25057 / 18222 | 0.0245 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 11.1% | 11.1% | 9.1% | 0.0% | 0 | 0 | 0 |
| minimal | 88.9% | 88.9% | 68.2% | 40.9% | 2 | 0 | 0 |
| optimized-v2 | 100.0% | 100.0% | 95.5% | 22.7% | 0 | 0 | 0 |
| optimized-v3 | 100.0% | 100.0% | 95.5% | 40.9% | 0 | 0 | 0 |

## Recorded failures

| Approach | Case | Category | Diagnosis |
|---|---|---|---|
| baseline | cphos28-q1-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q1-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q1-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q3-01 | supported | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q3-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q3-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q3-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q3-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q4-01 | supported | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q4-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q4-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q4-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q4-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q1-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q3-05 | multi_passage_synthesis | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q4-03 | subtle_distortion | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q4-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q4-06 | mixed | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-q4-03 | subtle_distortion | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-q4-03 | subtle_distortion | gold_quote_anchor_not_covered_review_needed |

## baseline to minimal

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-03', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-06'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-q1-03', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-06'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## baseline to optimized-v2

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-03', 'cphos28-q1-05', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-05', 'cphos28-q4-06'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-q1-03', 'cphos28-q1-05', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-05', 'cphos28-q4-06'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## baseline to optimized-v3

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-03', 'cphos28-q1-05', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-05', 'cphos28-q4-06'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-q1-03', 'cphos28-q1-05', 'cphos28-q1-06', 'cphos28-q3-01', 'cphos28-q3-02', 'cphos28-q3-03', 'cphos28-q3-05', 'cphos28-q3-06', 'cphos28-q4-01', 'cphos28-q4-02', 'cphos28-q4-03', 'cphos28-q4-05', 'cphos28-q4-06'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## minimal to optimized-v2

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-05', 'cphos28-q4-05'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-q1-05', 'cphos28-q4-05'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## minimal to optimized-v3

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-05', 'cphos28-q4-05'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-q1-05', 'cphos28-q4-05'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## optimized-v2 to optimized-v3

Comparable completed cases: 18.
Strict complete-case improvements: [].
Strict complete-case regressions: [].
Approximate diagnostic improvements: [].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## Merge and contradiction-review accounting

| Approach | Merge calls | Merged groups | Claims removed | Review calls | Reviewed claims | Changed verdicts | Failed reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| minimal | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized-v2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized-v3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |


## Reproducibility and limitations

- Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.
- Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.
- Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.
- Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.
- Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.
- Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.
- Version comparisons use the same completed inputs and settings. A single paired run does not isolate sampling variation, component effects, or the cost of additional calls.
- Dataset SHA-256: `8f053e69982901852bd6f15382c15ba325a459aac9d2f8b37e5aac55a0ad71eb`.
- Implementation SHA-256: `db50902df43677543c447555044fb0dbb2e3c9c35b199fc9786dfe46c270e06e`.
- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.
- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.
