# Three-approach benchmark

Run `edge`; status **complete**; split `edge`.
Completed 12 / 12 case/backend records.
Model `deepseek-flash`. All LLM backends share the saved model and generation settings.

| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 4 | 100.0% | 100.0% | 100.0% | 100.0% | n/a | n/a | 0.0007 | 0.0002 | 0.0020 | 0 / 0 | 0.0000 USD |
| minimal | 4 | 100.0% | 100.0% | 100.0% | 100.0% | n/a | n/a | 1.0314 | 0.8675 | 1.7083 | 856 / 341 | 0.0006 USD |
| optimized | 4 | 100.0% | 100.0% | 100.0% | 100.0% | n/a | n/a | 1.3883 | 1.1025 | 2.7331 | 2399 / 701 | 0.0011 USD |

*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.

## Evidence and alignment audit

| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | n/a | n/a | n/a | n/a | 0 | 0 | 0 |
| minimal | n/a | n/a | n/a | n/a | 0 | 0 | 0 |
| optimized | n/a | n/a | n/a | n/a | 0 | 0 | 0 |

## Recorded failures

| Approach | Case | Category | Diagnosis |
|---|---|---|---|
| All | - | - | No scored failures in completed records |

## Minimal to optimized comparison

Comparable completed cases: 4.
Strict complete-case improvements: [].
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
