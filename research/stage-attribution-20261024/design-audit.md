# Design audit — stage attribution pilot

Audit date: 2026-10-24 (Asia/Shanghai). Read-only audit of PLAN.md, protocol.py, the production v4 validation/review code and prompts. No model calls, benchmark reads, or production changes. This is AI methodological review, not author adjudication.

## Decision before inference

The design can diagnose the three requested components, subject to the small corrections and explicit attribution boundaries below. None requires adapting an inference rule to new cases.

## Required correction

1. In `protocol.validate_m3`, counting `unexpected_rows` currently evaluates `r.get("id") not in expected` without checking the ID type. An array/object ID raises TypeError instead of recording an incomplete model output. Require a string ID before set membership, and add an offline malformed-ID test. Every planned call must remain represented when malformed output is observed.

## Required scoring clarifications / checks

- Report `public_valid` separately from `rows`: the former is the common public contract; the latter additionally requires the arm's output protocol. Current rows need derivation/conflict, so only scoring `rows` would silently change the common-gate endpoint. Common-contract correct counts can use an identifiable row that fails internal schema; review eligibility cannot.
- A malformed C conflict may enter review only when `_validate_row` admits the row. An internally altered quote requiring semantic requery is excluded by this protocol, as are absent derivation/required fields. The result therefore estimates bounded finishing/review among admitted initial rows, not the complete production recovery pipeline. Preserve the excluded-row counts and reasons.
- Record unexpected rows and reordered expected rows independently of per-target success. If a case is called “complete,” specify whether this means all requested targets complete or exact response-envelope adherence; do not silently award unknown extra factual assertions strict compliance.
- Audit semantic evidence sufficiency separately from exact-quote validity for both arms and both before/after states. Correct labels with unrelated/incomplete quotes are not usable grounded-correct responses. Show label-only and evidence-sufficient endpoints without substituting one for the other.
- For review, the main usable-correct net should be checked directly as after-usable-correct minus before-usable-correct on the same planned opportunities. The label transition formula alone does not capture quote-evidence deterioration or repair when the label stays unchanged. Retain C structural repair separately from evidence semantic sufficiency.
- Blind M1 audit must include unexpected factual assertions outside the 45 targets, so the reference is not a closed vocabulary scorer. Source spans can overlap and retained compound claims count toward content retention, but strict success still requires independently understandable atomic assertions and no factual premise classified as NF.

## Attribution boundaries already handled well

The concise M1 arm is a task-matched control, not deployed minimal. Fixed M3 uses equal inputs/settings but unequal output protocols. Review starts from exactly persisted current-M3 responses with production triggers, not a new initial sample; numeric-conflict-triggered S reviews are included. Review has its existing higher budget and is not an equal-budget retry control. M1 has one attempt and no fallback, so it measures initial extraction rather than production completion. Two repetitions are clustered within original cases. All labels are AI draft references and any post-run ambiguity requires retained sensitivity bounds.

## Scope limitations to retain

Twenty authored synthetic cases and forty-five fixed claims can expose mechanisms but cannot establish broad generalization, stable superiority to minimal, or long-answer behavior. Balanced S/C/U is a diagnostic construction, not natural production prevalence. Sparse natural C-review triggers are an inconclusive stratum; do not manufacture trigger cases after seeing outputs. A future failed result can justify a task-level generic hypothesis, but these cases then become exposed development material.
