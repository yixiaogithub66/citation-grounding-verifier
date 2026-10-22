# Verifier benchmark

Run `confirmation-v3.1`; status **complete**; split `confirmation`.
Completed 48 / 48 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 12 | 100.0% | 36.1% | 21.5% | 36.1% | 100.0% | 3.6% | 0.0013 | 0.0006 | 0.0045 | 0 / 0 | 0.0000 USD |
| minimal | 12 | 100.0% | 58.1% | 57.9% | 76.7% | 100.0% | 75.0% | 5.1554 | 4.5077 | 8.8663 | 4297 / 14323 | 0.0184 USD |
| optimized-v2 | 12 | 100.0% | 90.7% | 90.8% | 90.7% | 100.0% | 92.9% | 13.5279 | 11.8844 | 25.9635 | 17702 / 36288 | 0.0461 USD |
| optimized-v3 | 12 | 100.0% | 97.6% | 97.5% | 97.6% | 100.0% | 100.0% | 15.8928 | 14.0205 | 26.6890 | 23795 / 42653 | 0.0538 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3.6% | 3.6% | 3.0% | 3.0% | 4 | 0 | 0 |
| minimal | 64.3% | 75.0% | 9.1% | 9.1% | 7 | 8 | 0 |
| optimized-v2 | 92.9% | 92.9% | 27.3% | 27.3% | 2 | 0 | 0 |
| optimized-v3 | 100.0% | 100.0% | 30.3% | 30.3% | 0 | 0 | 0 |

## Recorded failures

| Approach | Case | Category | Diagnosis |
|---|---|---|---|
| baseline | cphos28-confirmation-density-q2 | density | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-density-q6 | density | strict_text_or_verdict_mismatch, unresolved_alignment, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-density-q7 | density | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-scope_distractor-q2 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-scope_distractor-q6 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-scope_distractor-q7 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-mixed_truth_compound-q2 | mixed_truth_compound | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-mixed_truth_compound-q6 | mixed_truth_compound | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-mixed_truth_compound-q7 | mixed_truth_compound | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-reformulation_calculation-q2 | reformulation_calculation | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-reformulation_calculation-q6 | reformulation_calculation | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| baseline | cphos28-confirmation-reformulation_calculation-q7 | reformulation_calculation | strict_text_or_verdict_mismatch, aligned_verdict_error, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-density-q2 | density | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-density-q6 | density | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-density-q7 | density | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-scope_distractor-q2 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error |
| minimal | cphos28-confirmation-scope_distractor-q6 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-scope_distractor-q7 | scope_distractor | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-mixed_truth_compound-q2 | mixed_truth_compound | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-mixed_truth_compound-q6 | mixed_truth_compound | strict_text_or_verdict_mismatch, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-mixed_truth_compound-q7 | mixed_truth_compound | strict_text_or_verdict_mismatch, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-reformulation_calculation-q2 | reformulation_calculation | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-reformulation_calculation-q6 | reformulation_calculation | gold_quote_anchor_not_covered_review_needed |
| minimal | cphos28-confirmation-reformulation_calculation-q7 | reformulation_calculation | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-density-q2 | density | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-density-q6 | density | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-density-q7 | density | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-scope_distractor-q2 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error |
| optimized-v2 | cphos28-confirmation-scope_distractor-q6 | scope_distractor | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-mixed_truth_compound-q2 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-mixed_truth_compound-q6 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-mixed_truth_compound-q7 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-reformulation_calculation-q2 | reformulation_calculation | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-reformulation_calculation-q6 | reformulation_calculation | gold_quote_anchor_not_covered_review_needed |
| optimized-v2 | cphos28-confirmation-reformulation_calculation-q7 | reformulation_calculation | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-density-q2 | density | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-density-q6 | density | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-scope_distractor-q2 | scope_distractor | strict_text_or_verdict_mismatch, aligned_verdict_error |
| optimized-v3 | cphos28-confirmation-scope_distractor-q6 | scope_distractor | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-scope_distractor-q7 | scope_distractor | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-mixed_truth_compound-q2 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-mixed_truth_compound-q6 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-mixed_truth_compound-q7 | mixed_truth_compound | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-reformulation_calculation-q2 | reformulation_calculation | gold_quote_anchor_not_covered_review_needed |
| optimized-v3 | cphos28-confirmation-reformulation_calculation-q7 | reformulation_calculation | gold_quote_anchor_not_covered_review_needed |

## baseline to minimal

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q7', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-scope_distractor-q7'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q7', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-scope_distractor-q7'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## baseline to optimized-v2

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q7', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6', 'cphos28-confirmation-scope_distractor-q7'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q7', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6', 'cphos28-confirmation-scope_distractor-q7'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## baseline to optimized-v3

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q6', 'cphos28-confirmation-density-q7', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q2', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6', 'cphos28-confirmation-scope_distractor-q7'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q6', 'cphos28-confirmation-density-q7', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q2', 'cphos28-confirmation-reformulation_calculation-q6', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6', 'cphos28-confirmation-scope_distractor-q7'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## minimal to optimized-v2

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## minimal to optimized-v3

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q6', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-mixed_truth_compound-q6', 'cphos28-confirmation-mixed_truth_compound-q7', 'cphos28-confirmation-reformulation_calculation-q2', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q2', 'cphos28-confirmation-density-q6', 'cphos28-confirmation-mixed_truth_compound-q2', 'cphos28-confirmation-reformulation_calculation-q2', 'cphos28-confirmation-reformulation_calculation-q7', 'cphos28-confirmation-scope_distractor-q6'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## optimized-v2 to optimized-v3

Comparable completed cases: 12.
Strict complete-case improvements: ['cphos28-confirmation-density-q6', 'cphos28-confirmation-reformulation_calculation-q2'].
Strict complete-case regressions: [].
Approximate diagnostic improvements: ['cphos28-confirmation-density-q6', 'cphos28-confirmation-reformulation_calculation-q2'].
Approximate diagnostic regressions: [].
These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.

## Merge and contradiction-review accounting

| Approach | Merge calls | Merged groups | Claims removed | Review calls | Reviewed claims | Changed verdicts | Failed reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| minimal | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized-v2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized-v3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |


## Reproducibility and limitations

- Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.
- Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.
- Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.
- Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.
- Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.
- Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.
- Version comparisons use the same completed inputs and settings. A single paired run does not isolate sampling variation, component effects, or the cost of additional calls.
- Dataset SHA-256: `2a2fefb97d8344f5dbdf126672de498d87fc8695b719b9479095b98b6b4165ea`.
- Implementation SHA-256: `383a8787791bc28e1ad5db3596654ccae8da85a88a10b509335dc9f1f50ceec4`.
- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.
- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.
