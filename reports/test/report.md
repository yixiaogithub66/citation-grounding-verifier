# Three-approach benchmark

Run `test`; status **complete**; split `test`.
Completed 72 / 72 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 24 | 100.0% | 30.8% | 23.2% | 30.8% | 100.0% | 8.3% | 0.0007 | 0.0004 | 0.0015 | 0 / 0 | 0.0000 USD |
| minimal | 24 | 100.0% | 89.2% | 90.4% | 95.4% | 100.0% | 95.8% | 1.9977 | 1.7465 | 2.9110 | 8058 / 8552 | 0.0123 USD |
| optimized | 24 | 100.0% | 86.6% | 87.8% | 86.6% | 100.0% | 87.5% | 4.9498 | 4.1071 | 10.1021 | 31478 / 21271 | 0.0288 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 8.3% | 8.3% | 6.9% | 0.0% | 1 | 0 | 0 |
| minimal | 87.5% | 95.8% | 82.8% | 62.1% | 3 | 2 | 0 |
| optimized | 87.5% | 87.5% | 89.7% | 31.0% | 3 | 0 | 0 |

## Recorded failures

| Approach | Case | Category | Diagnosis |
|---|---|---|---|
| baseline | cphos28-q2-01 | supported | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q2-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q2-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q2-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q2-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q5-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q5-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q5-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q5-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q6-01 | supported | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q6-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q6-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q6-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q6-06 | mixed | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q7-01 | supported | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q7-02 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q7-03 | subtle_distortion | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q7-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-q7-06 | mixed | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q2-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q2-06 | mixed | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q5-03 | subtle_distortion | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q5-06 | mixed | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q7-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch |
| optimized | cphos28-q5-02 | subtle_distortion | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| optimized | cphos28-q5-03 | subtle_distortion | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| optimized | cphos28-q5-06 | mixed | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |

## Minimal to optimized comparison

Comparable completed cases: 24.
Strict complete-case improvements: ['cphos28-q2-05', 'cphos28-q7-05'].
Strict complete-case regressions: ['cphos28-q5-02', 'cphos28-q5-06'].
Approximate diagnostic improvements: [].
Approximate diagnostic regressions: ['cphos28-q5-02', 'cphos28-q5-06'].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## Reproducibility and limitations

- Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.
- Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.
- Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.
- Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.
- Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.
- Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.
- Dataset SHA-256: `8f053e69982901852bd6f15382c15ba325a459aac9d2f8b37e5aac55a0ad71eb`.
- Implementation SHA-256: `8f81865f5178f99e281a4d9fd2158942498c220340f16efd0c375502d26eb931`.
- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.
- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.
