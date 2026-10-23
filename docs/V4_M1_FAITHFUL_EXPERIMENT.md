# M1 answer-faithfulness experiment, 2026-10-23

## Registered before model calls

The user asked to try promising directions after review of the combined experiment.
This experiment changes only the original v4 decomposition system prompt. It asks
whether preserving the propositions actually asserted by the answer reduces
invented factual targets without dropping embedded or implicit factual assertions.
It does not test a new verification model, evidence protocol, semantic merge,
review policy, matcher, or resource budget.

The experimental backend is `optimized-v4-m1-faithful`, compared with a fresh run
of `optimized-v4.0`. Defaults and the earlier combined backend retain their meaning.
All requests use the same `configs/optimized-v4.0.json` and provider settings.

## Intervention and rationale

The new prompt retains the v4 claims/non_factual_spans schema and exact source-span
coverage contract. It makes answer-to-claim fidelity explicit: do not promote advice,
non-assertive illustrative wording, hypothetical antecedents, or attribution fragments into assertions; retain
asserted causal/numeric premises embedded in recommendations; preserve subject,
attribution, modality, scope and conditions. Resolve a reference only when the
answer determines its antecedent, and preserve ambiguity rather than inventing a
subject. Split according to independent truth conditions, not connective keywords.
Same-sentence semantic redundancy remains solely a prompt policy.

These requirements follow from extraction semantics and the user's prior decisions.
No benchmark identifiers, passages, labels, examples, generator identities or
dataset-specific parameters are added to inference. Source context is not supplied
to M1 to correct or complete the answer. This is one bundled M1 semantic-policy
intervention, not an ablation isolating each sentence of the prompt.

The subclass substitutes the prompt only during the decomposition phase. Original
v4 validators, chunking, coverage, skeleton fallback, M3 prompts, quotation repair,
numeric signals, review counts, retry limits and partial-report semantics remain
inherited. Synthetic isolation tests compare actual downstream request messages
under identical extracted claims, including a U review. They establish engineering
isolation, not the prompt's semantic accuracy.

## Fixed evaluation plan

Before any calls, freeze all grounding/scripts Python files, prompt metadata,
configuration, public model settings and selected existing inputs. Record source
snapshots, input hashes, usage and returned model fingerprints. Do not edit frozen
inference or evaluation code between the following runs:

1. Existing 24 behavior pairs (48 inputs), both backends, end-to-end only: 96 records.
   These are exposed AI-authored diagnostics, not author-approved gold. The fixed
   claim path is identical by construction and tested with byte-identical scripted
   downstream requests; do not spend extra model calls rerunning the same M3 policy.
2. Existing 46 physics cases, both backends: 92 records. Keep strict and approximate
   diagnostics unchanged. Read textual alignment coverage alongside label scores.
3. All old RAGTruth v1 development inputs (180, 30 source groups), both backends:
   360 records, deterministic per-input randomized backend order. Preserve native
   scoring and partial/unknown semantics. This is not an unseen evaluation.

Total planned new evaluation records: 548. Run the full registered comparisons
regardless of favorable or unfavorable semantic scores, unless a transport failure,
source-change invalidation or user interruption requires stopping. Retain every
failed attempt. Do not tune a prompt or select a subset after inspecting results.
Case concurrency is 4; internal stage workers and all budgets follow the unchanged
configuration. Cost uses the prior fixed reference prices (USD per million tokens:
input 0.30, cached input 0.006, output 1.20), explicitly not an actual bill.

## Outcomes and limits

Report native TP/FP/TN/FN, unknowns, complete/partial/error rates, completed-target
coverage, all-case correct decisions, source-cluster paired uncertainty, calls,
tokens, reference cost and mean/P95 latency. Native FP is not author-adjudicated
true FP. No true-FP or unseen-generality acceptance claim is possible here.
Each input/backend is sampled once. Backend-order randomization does not remove
model randomness; source-cluster intervals describe resampling of the observed
outputs and do not estimate variance across repeated generations.

Inspect extraction trace differences as AI diagnostic evidence, separating false
factual extraction, lost qualifiers/attribution/subject, missing facts, and purely
textual reformulations. Neither fewer claims nor fewer U decisions alone is an
improvement. Character coverage and lower fallback counts do not establish semantic
recall. Review changed native decisions in both directions and all behavior failures;
do not relabel gold. Record whether semantic audit coverage is partial or complete.

The prior frozen physics alignment audit is separate measurement work. It may
explain lexical mismatches but cannot alter historical scores, become author gold,
or explain native RAGTruth answer detection, which does not use claim matching.

An observed improvement is exploratory evidence on exposed development data. A
regression is retained and reported. Any subsequent semantic change needs another
registered experiment; the next unseen slice remains unselected, with exposure
mapping prerequisites intact.
