# Three-approach benchmark

Run `dev-v2`; status **complete**; split `dev`.
Completed 54 / 54 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 18 | 100.0% | 33.3% | 27.6% | 33.3% | 100.0% | 11.1% | 0.0016 | 0.0010 | 0.0054 | 0 / 0 | 0.0000 USD |
| minimal | 18 | 100.0% | 91.7% | 92.6% | 100.0% | 100.0% | 100.0% | 2.2432 | 1.7157 | 6.5098 | 6285 / 7196 | 0.0098 USD |
| optimized | 18 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.2873 | 3.4924 | 9.0864 | 23627 / 12958 | 0.0185 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 11.1% | 11.1% | 9.1% | 0.0% | 0 | 0 | 0 |
| minimal | 88.9% | 100.0% | 90.9% | 45.5% | 2 | 2 | 0 |
| optimized | 100.0% | 100.0% | 100.0% | 31.8% | 0 | 0 | 0 |

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
| minimal | cphos28-q1-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch |
| minimal | cphos28-q3-05 | multi_passage_synthesis | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q4-03 | subtle_distortion | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-q4-05 | multi_passage_synthesis | strict_text_or_verdict_mismatch |

## Minimal to optimized comparison

Comparable completed cases: 18.
Strict complete-case improvements: ['cphos28-q1-05', 'cphos28-q4-05'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: [].
Approximate diagnostic regressions: [].
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
