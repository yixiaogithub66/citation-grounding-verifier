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

## Controlled development and held-out evaluation

Results and any further changes will be recorded here after the corresponding runs finish. No held-out predictions have been used to tune the initial implementations.
