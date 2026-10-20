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

`reports/dev-v2` reruns all three backends against the same final dataset/settings. The minimal prompt text and lexical baseline are unchanged; the prompt-version metadata increments globally. Held-out evaluation will use the resulting frozen implementation, with no tuning from test predictions.
