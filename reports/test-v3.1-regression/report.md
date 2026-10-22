# Verifier benchmark

Run `test-v3.1-regression`; status **complete**; split `test`.
Completed 24 / 24 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| optimized-v3 | 24 | 100.0% | 95.4% | 96.0% | 95.4% | 100.0% | 95.8% | 6.0549 | 5.2450 | 10.1714 | 38000 / 25165 | 0.0332 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| optimized-v3 | 95.8% | 95.8% | 96.6% | 51.7% | 1 | 0 | 0 |

## Recorded failures

| Approach | Case | Category | Diagnosis |
|---|---|---|---|
| optimized-v3 | cphos28-q5-03 | subtle_distortion | strict_text_or_verdict_mismatch, unresolved_alignment, missing_passage_or_unaligned_claim, gold_quote_anchor_not_covered_review_needed |

## Merge and contradiction-review accounting

| Approach | Merge calls | Merged groups | Claims removed | Review calls | Reviewed claims | Changed verdicts | Failed reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| optimized-v3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |


## Reproducibility and limitations

- Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.
- Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.
- Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.
- Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.
- Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.
- Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.
- Version comparisons use the same completed inputs and settings. A single paired run does not isolate sampling variation, component effects, or the cost of additional calls.
- Dataset SHA-256: `8f053e69982901852bd6f15382c15ba325a459aac9d2f8b37e5aac55a0ad71eb`.
- Implementation SHA-256: `0ba6f98f65c1a82605282b6956362d7e2a54452dc4dcc548289287411d985984`.
- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.
- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.
