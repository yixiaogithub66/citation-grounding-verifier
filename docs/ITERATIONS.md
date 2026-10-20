# Evaluation-driven iteration log

This log distinguishes changes motivated by observations from improvements demonstrated by a fresh controlled run. All core evaluation is end-to-end: gold claims, labels and evidence never enter verifier requests.

## Data preparation: version 1.0 to 1.1

The pre-existing single-model development run `20261020T093654.015646Z` used the earlier detailed prompt and dataset v1.0. It produced 24 claims on 18 development cases, with 23 matching labels. For `cphos28-q1-06`, the model treated the negative-angle claim as unsupported because the selected numeric snippet did not explicitly identify `delta` as the outgoing angle.

Review of the source location showed that the selection had omitted this definition. Dataset v1.1 restores the phrase identifying `delta` as the outgoing angle in `q1_sphere_result`, referring to solution PDF page 3. This affects only the development sample using that passage. Labels and held-out test inputs remain unchanged.

This is a source-selection repair, not evidence of model improvement. The old run is not the minimal baseline and is excluded from new comparison tables. Each new experiment records its actual dataset and source hashes.

## Initial implementations

- `baseline`: deterministic sentence splitting and IDF-weighted lexical retrieval, with restricted formula, numeric and negation contrast rules. It is intentionally unable to solve arbitrary algebra or synthesize all multi-passage claims.
- `minimal`: one model request with the task definition and output contract, no transport retry or output repair.
- `optimized`: answer decomposition with source spans, evidence verification for fixed extracted claims, deterministic validation and a bounded correction path. Its greater call budget is measured, not hidden.

The optimized design targets extraction omissions, unsupported facts falsely using external knowledge, invented quote spans and missing evidence across passages. Whether it improves this dataset is determined by the fresh runs recorded below.

## Pre-evaluation checks

Independent code review found that approximate claim matching could conflate a formula with its sign-mutated version. Matching must preserve formula operators, variable case and numerical values; approximate scores remain diagnostics. Review also separated passage-index coverage from actual quote-anchor coverage, since citing a valid but irrelevant word is not sufficient evidence.

The lexical baseline's comparison rules were tightened to avoid declaring a redundant unary plus or a signed zero term a contradiction.

## First controlled development run

`reports/dev-v1` completed all 54 case/backend records on 18 development cases. Strict claim+label F1 was 0.3333 for baseline, 0.8571 for minimal, and 0.3922 for optimized. The optimized approximate alignment diagnostic was 0.8627. The large strict/approximate gap came mainly from dropped sentence punctuation, not different verdicts.

Two actual decomposition problems were observed:

- `q1-05`: the optimized extractor turned the introductory phrase about substituting data into a standalone action claim, then marked it unsupported. The original sentence expressed one calculation result.
- `q4-01`: it promoted a model descriptor into a separate assertion and split coordinated subjects, with all results marked unsupported because the selected context omitted the one-dimensional model heading.

Minimal also shortened some statements and expanded the relational `q4-05` into two supported propositions. These are alignment/atomicity differences; they should not all be reported as semantic errors.

The original data snapshot is retained as `reports/dev-v1/dataset.snapshot.jsonl` and `sources.snapshot.json`; the initial implementation is Git commit `1548b17`.

## Version 2 changes, before held-out evaluation

Generic decomposition instructions now preserve terminal punctuation for a complete single-predicate sentence, keep computational framing attached to its result, avoid promoting descriptive noun phrases into new assertions, and allow coordinated subjects sharing one predicate to remain grouped. Grouped subjects require evidence for every subject. Distinct predicates still split. Explanations use the claim's language.

Dataset v1.2 also restores the original one-dimensional model heading in `q4_components`. This source selection correction affects development `q4-01`, `q4-03`, and `q4-06` only. No gold labels or held-out inputs change. It is explicitly a data repair, not an algorithm gain. Cross-version comparisons must restrict themselves to identical-input cases or identify this confound.

`reports/dev-v2` reruns all three backends against the same final dataset/settings. The minimal prompt text and lexical baseline are unchanged; the prompt-version metadata increments globally. Held-out evaluation uses the resulting frozen implementation, with no tuning from test predictions.

## Second development run and freeze

`reports/dev-v2` completed all 54 records with no contract/API errors. Strict claim+label F1: baseline 0.3333, minimal 0.9167, optimized 1.0000. Approximate diagnostic F1 was 1.0000 for both LLM methods. Minimal's two strict case mismatches were correct paraphrases, so the strict advantage is not evidence of two wrong minimal verdicts. Mean latency was 2.2432 s for minimal and 4.2873 s for optimized; standardized estimated costs were USD 0.009843324 and USD 0.018498180 for the respective 18-case runs.

For the 15 cases whose input hashes are identical between v1 and v2:

| Method | v1 strict joint F1 | v2 strict joint F1 | v1 approximate diagnostic F1 | v2 approximate diagnostic F1 |
| --- | ---: | ---: | ---: | ---: |
| Minimal, unchanged prompt | 0.8205 | 0.8947 | 0.8205 | 1.0000 |
| Optimized | 0.3077 | 1.0000 | 0.9231 | 1.0000 |

This isolates source-input changes but does not eliminate model sampling/run variation: even the unchanged minimal control varied. The clearest substantive fix is avoiding the spurious procedural action claim in `q1-05`; much of the strict gain is punctuation and wording preservation. No statistical significance or broad semantic superiority is claimed.

The frozen test implementation is commit `cfadeca` with prompt version `grounding-v2` and dataset v1.2. The held-out and edge records were checked byte-for-byte at the parsed JSON record level against the v1 snapshot and are unchanged. Final test and edge runs use this frozen code; subsequent documentation updates do not change inference.

## Held-out test and edge results

`reports/test` completed all 72 records: 24 cases per backend. Strict joint F1 was 0.3077 for baseline, 0.8923 for minimal, and 0.8657 for optimized. Both LLM methods were strictly correct on 21/24 whole cases. The optimized method took 4.9498 seconds per case on average versus 1.9977 seconds for minimal, with standardized estimated run costs of USD 0.028796952 and USD 0.012265848, respectively.

The development advantage did not generalize to this held-out split. Optimized duplicated prose and equivalent formulas in `q5-02` and `q5-06`; its direction verdict in `q5-03` also exposed an assumption about the drag coefficient's sign that the selected context did not explicitly state. Minimal's strict errors in `q2-05` and `q7-05` were correct paraphrases, but its `q2-05` citation omitted the physical time scale needed to support the computed duration. These are distinct granularity, annotation-boundary and evidence-coverage issues; the strict score alone cannot distinguish them.

All actual LLM citations were verbatim substrings with valid indices. This structural guarantee does not establish semantic sufficiency. Detailed observations are in `reports/test/AUDIT.md`. No prompts, inference code or test labels were changed after examining these results.

`reports/edge` completed all 12 records, with all four edge cases passing for each backend. Blank answers required no model calls; the nonfactual greeting and empty-context factual answer each required one call per LLM method. No real benchmark response triggered the repair path; malformed-output recovery was exercised by automated tests.

## Live HTTP check

The original assignment's SQLite request in `examples/sqlite.json` was sent through the actual optimized HTTP service using the configured live DeepSeek backend. It returned HTTP 200 and four claims with verdicts `CONTRADICTED`, `SUPPORTED`, `SUPPORTED`, `UNSUPPORTED`, matching the assignment example. Every quote passed deterministic validation. The observed end-to-end latency was 34.172 seconds; this single service smoke check is separate from the benchmark latency aggregates and used the service's configured model defaults. Its response and request hash are retained in `reports/service-smoke`.
