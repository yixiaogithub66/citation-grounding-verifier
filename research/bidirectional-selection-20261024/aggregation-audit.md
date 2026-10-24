# Aggregation audit: bidirectional selection pilot

Audit date: 2026-10-24 (Asia/Shanghai). PASS for the recorded aggregation. This is a read-only mechanical/counting audit by the AI case author and controlled-output reviewer, not independent author gold or human adjudication. No model call, inference change, label change or original review edit was made. The mapping key was opened only for this authorized unblinded aggregation audit.

## Identity, schema and denominators

- All three review files pass the packet JSON Schema: 64 + 64 + 24 = 152 reviews, with unique review IDs and exact equality to the blinded packet/key/journal identity sets. Every expected fact is mapped once; claim indices are in range. Invalid outputs retain null semantic values and no fake zero-error semantic score. Review-file, response-journal and freeze hashes match the semantic summary.
- The natural design has 16 answers × 2 repetitions = 32 attempts per arm, 8 factual answers × 2 targets × 2 repetitions = 32 factual opportunities, and 8 pure-NF answers × 2 repetitions = 16 NF opportunities. Repetitions are not independent new answers.

| arm | attempts | valid | retained targets | valid semantic misses | technical unknown targets | NF correct /16 | NF wrong | NF technical error | complete /32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 32 | 24 | 18 | 0 | 14 | 11 | 4 | 1 | 20 |
| fresh | 32 | 24 | 18 | 0 | 14 | 10 | 5 | 1 | 19 |
| generic | 32 | 29 | 28 | 0 | 4 | 12 | 3 | 1 | 26 |
| bidirectional | 32 | 31 | 30 | 0 | 2 | 14 | 2 | 0 | 29 |

For every natural arm, retained + valid semantic misses + technical unknown = 32. All valid-output semantic-miss counts are zero. Thus the 28→30 target-service difference between generic and bidirectional is a technical-completion difference, not observed repair of natural semantic omission.

Each controlled arm contains exactly 4 omission, 4 spurious and 4 clean seeds; each subgroup has 4 valid semantic successes. The controlled probe therefore does not distinguish the two revision methods on these injected examples.

## Paired complete-success changes

Exactly three of the 32 generic/bidirectional pairs differ in complete semantic success; all three favor bidirectional. There are no opposite complete-success transitions in this sample.

| case / repetition | generic | bidirectional | interpretation |
|---|---|---|---|
| sel-02 / 1 | null | true | factual answer becomes technically scorable; 2 targets become served |
| sel-07 / 0 | null | true | pure-NF answer becomes technically scorable |
| sel-08 / 1 | false | true | both valid; question-as-fact error disappears |

This supports only one observed semantic NF-error correction over the generic revision, plus two protocol/completion improvements. It does not establish simultaneous natural omission reduction and advice-selection reduction.

## Cost and latency arithmetic

Token-level recomputation from the 152 recorded traces reproduces both analysis.json and the independent operational audit. Prices are fixed reference USD per million tokens: uncached input 0.30, cached input 0.006, output 1.20.

| accounting | cached reference USD | all-miss reference USD |
|---|---:|---:|
| base + generic (64 calls) | 0.020993892 | 0.030514200 |
| base + bidirectional (64 calls) | 0.021163908 | 0.031135800 |
| all 152 recorded calls | 0.051121620 | 0.076220400 |

The all-miss chain ratio is 1.020370843738, or +2.0371%. Chain mean and nearest-rank P95 latencies were independently recomputed from paired base+revision sums and match semantic-analysis.json. Each hypothetical chain includes the shared base; adding the two chain costs together would double-count that base in physical spending. The original interrupted run has one possibly unjournaled started attempt, so recorded cost remains a known subtotal rather than a confirmed complete bill. Separate reasoning usage is not reported; zero must not be called measured zero thinking cost.

## Clean-02 independent-subject diagnostic

- Generic: `r-ec1d863b8712705e7e91b904`, claim index 1, emits `Its technician log reports that recorder Morrow-6 does not write a backup track in mono mode.`.
- Bidirectional: `r-9fa0c98aeb0d6ef22e0fd53d`, claim index 1, emits `The Bracken sound archive's technician log reports that recorder Morrow-6 does not write a backup track in mono mode.`.
- The injected clean draft explicitly names the Bracken archive. Generic reintroduced the unresolved pronoun; bidirectional retained the full named source. Both preserve the uniquely resolvable proposition within the answer and therefore retain the pilot selection score. This is an additional standalone-claim regression for generic, not permission to claim full M1 contract success from selection-fidelity scores.

## Scope

The aggregation script was inspected without running its file-writing main. Counting and cost arithmetic were independently reconstructed, and all original review hashes remained unchanged. Scoped-assumption sensitivity is secondary to the fixed pure-NF primary score; this audit does not re-adjudicate that boundary or produce new semantic labels. The materials and reviews remain AI-authored supplementary diagnostics, and the interrupted/recovered pilot is not an untouched benchmark or proof of generalization.
