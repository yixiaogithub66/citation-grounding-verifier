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

## Version 3: mechanism-driven revision (2026-10-22)

The author supplied an updated design after reviewing the negative v2 test result. V3 uses that old test for diagnosis; it cannot claim those cases remain unseen. The existing v2 files and historical reports stay unchanged. `optimized-v2` verifies the original inference-file hashes, while `optimized-v3` is a new implementation and `optimized` selects v3.

The diagnosis separates matched-label counts from judgment accuracy: both historical LLM systems had 29 strictly aligned correct claims, but their extra predictions differed. That fact does not establish equal semantic judgment ability. The old negative result belongs to `grounding-v2`.

| Observation / design concern | V3 change | Intended check |
| --- | --- | --- |
| Equivalent prose and formulas became duplicate claims | Preserve one proposition per sentence; merge only equivalent extracted assertions before verification | Synthetic equivalent and inconsistent restatements, compound mixed-truth claims, development regressions |
| Merging can erase independent assertions | Candidate detection is separate from semantic approval; preserve source coverage and unrelated clauses | Partial-sentence merges, different conditions, shared subjects, unsupported invented spans |
| A contradicted verdict needs auditable conflicting evidence | Internal claim anchor, evidence and explanation; batch re-review only when that record is unusable | Three-way review outcomes, multi-passage calculations, no error-to-unsupported fallback |
| Extra reasoning stages have real cost | Record every merge/review/repair call and verdict-change direction | Usage totals, stage counts and same-set backend comparisons |

These are design motivations, not measured gains. A deterministic quote/anchor check is a structural check; it does not prove that the explanation establishes a contradiction. Multiple v3 changes are bundled, so a paired v2/v3 difference is not a component-level ablation.

The full protocol is in `docs/V3_DESIGN.md`. Three pilot examples are reserved for author review and excluded from final confirmation scores. After pilot annotation-policy review, the planned 12-case same-source, same-question-family confirmation set will compare baseline, minimal, frozen v2 and v3 with locked inputs, settings and code. No confirmation results or human-review completion are claimed before those steps occur.

### Provider compatibility check

The first real v3 development attempt (`reports/dev-v3`) exposed an HTTP 400 at verification, despite passing offline tests. A small direct request confirmed DeepSeek's JSON-object mode requires the literal word `json` in a message; v3's merge and verify prompts described an object but omitted that word. The run was stopped and its 46 completed records retained as an interrupted compatibility run, not a quality comparison. In-flight usage at interruption may be unreported.

The fix adds only explicit JSON-output wording to those two prompts and a transport-level regression covering all four stages. It does not change semantic rules, historical labels or the scorer. All 134 tests then passed. The actual v3 HTTP service returned 200 for the assignment's SQLite example with the four expected verdicts, using two model calls (29.705 seconds); this check is separate from benchmark timing. See `reports/service-smoke-v3`.

The original implementation snapshot is retained in `reports/v3-code-freeze.json`; the corrected snapshot is `reports/v3-code-freeze-final.json`. The integrator read the excluded pilot examples after the first snapshot; the subsequent change was the independently confirmed JSON-mode compatibility correction. The formal confirmation dataset has not been constructed or evaluated.

### Corrected four-backend development regression

`reports/dev-v3-final` completed all 72 records on the original 18 development cases without API or schema errors. Strict joint F1 was 0.3333 for baseline, 0.8980 for minimal, and 1.0000 for both frozen v2 and v3. V2/v3 each produced 24/24 correctly aligned claims and passed all 18 whole cases. This is a saturated development set, not new confirmation evidence.

Minimal shortened the correct calculation in `q1-05` and separated the structure description from the correct thrust relation in `q4-05`. Its two strict case failures are wording/granularity differences; the strict gap is not evidence of two incorrect semantic verdicts.

Mean latency was 4.9160 seconds for v2 and 5.7163 seconds for v3; standardized estimated costs were USD 0.020180748 and USD 0.024532500. Both used 36 model calls. No merge or contradiction-review stage was triggered in this development run, so its result does not demonstrate those recovery mechanisms on live failures. Their behavior is exercised by transport/behavioral tests; any later regression evidence must be labeled separately.

A fresh local clone of implementation commit `d72453c` passed all 134 tests, both dataset validators, the offline development benchmark, and actual baseline HTTP health/verify requests without a `.env` file or provider credentials. New pilot source validation additionally matched the local original PDF hash. The author review fields remain pending.

### Frozen old-test regression: remaining granularity mismatch

`reports/test-v3-regression` ran the frozen corrected v3 once on the 24 previously inspected test cases, solely as regression evidence. All outputs were valid; strict and approximate F1 were 0.8657, with 29 correct gold claims, 35 predictions, 6 extras, 3 missing and 21/24 correct whole cases. Two merge calls were made, but neither approved a merge; no contradiction review was triggered. The historical `q5-02`, `q5-03` and `q5-06` mismatches remained.

For `q5-02` and `q5-06`, the candidate detector found the intended pair. The model then applied the strict-equivalence instruction: a radius-power or denominator statement asserts less than the corresponding complete formula, so it retained two claims. This exposes a mismatch between strict equivalence and the intended annotation grouping of a consistent partial description with a fuller formula. The new stage is implemented, but it has not solved that issue. No further prompt or label changes were made from this run. See `reports/test-v3-regression/AUDIT.md` for the evidence and the author policy decision still needed.
