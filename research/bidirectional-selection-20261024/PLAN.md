# Bidirectional factual-selection fidelity: preregistered M1 pilot

Date: 2026-10-24. This is a new, fictional, AI-authored diagnostic batch, not RAGTruth, author-adjudicated gold, a held-out benchmark result, or evidence of production-wide generalization. The production verifier is unchanged. The question is whether explicitly reviewing both claim-to-answer fidelity and answer-to-claim completeness helps **both** omission and advice-to-fact errors beyond an equally funded generic revision.

## Intervention and isolation

The current M1 DECOMPOSE_PROMPT is the base. Generic and bidirectional revision receive the exact same answer, base raw draft, structural status and validator diagnostic. All semantic standards are shared: preserve attribution, modality, conditions, quantities and other asserted meaning; keep factual premises inside advice; exclude mere advice/questions/refusals and imagined outcomes; ordinary paraphrases are allowed. The candidate differs only in the two-direction review procedure. No examples, case identities, benchmark text, expected labels, metadata, seed fault kinds, or evidence passages enter inference.

Each revision returns a complete extraction in the existing schema. There is no union, best-of selection, runtime merging or other semantic postprocessing. Validation remains the existing deterministic extract_claims check; lexical coverage is not semantic fidelity. Neither invalid drafts nor provider failures are interpreted as non-factual content. Revisions execute after failed base attempts as well as valid ones. M3 verification, citation repair, fallback, targeted review, multi-chunk behavior and end-to-end /verify accuracy are outside this pilot.

Candidate prompt construction preceded access to the new case bodies. A separate case author constructed the materials without candidate prompts or old benchmark examples; another agent reviews the expected semantics before inference. These roles are AI checks and do not constitute independent human gold. Cases and all inference sources/prompts/settings are frozen before the first provider call. Any subsequent study informed by these results must mark this batch exposed; this batch will not be retuned and rerun as unseen confirmation.

## Fixed design and budget

Natural extraction: 16 new answers in four fictional domain families, eight factual answers with two declared factual targets each and eight non-factual answers; eight Chinese/eight English, with language crossed within domains. Six answers are 300–900 characters; all fit the unchanged 1200-character single chunk. Two repetitions, four arms: base, fresh independent extraction with the same base prompt, generic revision, and bidirectional revision. Base goes first; follow-up order rotates using a fixed seed. 16 × 2 × 4 = 128 calls. Repetitions share source answers and are not 32 independent samples per arm.

Controlled extraction: 12 prewritten drafts on answers reused from this new batch: four omission faults, four spurious fact faults, four clean controls. All pass the unchanged structural validator. Generic and bidirectional each run once, with identical payload and balanced order: 24 calls. Neutral draft wording does not announce the injected fault. These artificial failures measure correction competence, not natural fault prevalence. They do not provide additional independent answers and are never pooled into natural performance. Joint omission-plus-spurious faults in one draft are not tested.

Total fixed ceiling: 152 calls. Model deepseek-flash, thinking disabled, output budget 8192, JSON mode, max_claims 64, upstream_retries 0, repair_attempts 0, four workers. No failed-sample retries or replacement cases. Gemini High reviews study design and subsequently results through Antigravity headless CLI; its advisory usage is separate from experiment cost. The source runner is frozen and re-executed from its snapshot. An interrupted run is retained as interrupted, never silently resampled.

## Semantic scoring, fixed denominators and uncertainty

All outputs are preserved. Review each valid extraction against the original answer and predeclared target semantics; spelling overlap alone is insufficient. Score arbitrary synonymous assertions by meaning. A target is fully retained only if all necessary subject, relation, modality, polarity, condition, numerical scope and attribution elements survive. A changed assertion can simultaneously lose a target and introduce a false assertion. In mixed answers, non-factual material wrongly admitted as a fact must be counted too. Do not treat an entirely empty factual output as high precision. Additional genuinely asserted facts discovered by review must be documented as a fixture limitation, not silently added to improve a favored arm.

The semantic audit should hide arm names where practical, record target-to-claim mappings and explicit reasons for errors, and cross-review disputed cases. These are AI-assisted judgments, not the user's author adjudication. Any unresolved interpretation is marked uncertain and reported as a strict/conservative-to-permissive interval. No prompt/gold changes after outputs are seen; post-run interpretations are disclosed.

Pre-inference boundary review: sel-04 consists of commands to suppose/assume for an imaginary exercise. Primary selection scoring treats it as non-factual under the task definition. If an output explicitly retains the imaginary/exercise scope, additionally report a permissive scoped-assumption sensitivity result; do not call it an unqualified invented real-world fact. An unqualified extraction of the imagined premises is an error in either reading. This boundary is fixed before any model output. The clean seed for sel-05 has its `Its technician log` claim text made self-contained before freeze; its exact source span and original answer remain unchanged.

For each natural arm report:

- Structural validity out of all 32 attempts, with failure reasons. This is not production completion rate.
- Target retention out of the fixed 32 opportunities (16 targets × two repeats). Invalid outputs leave their targets **technically unserved**, not semantically proved absent. Separately show semantic omissions among valid outputs and technical unknowns. All-cause unserved = fixed opportunities minus fully served targets.
- Pure non-factual correct-and-valid answers out of all 16 opportunities (eight answers × two repeats). Also show wrong-upgrade count/valid NF outputs and technical failures separately; a failure never earns zero-false-positive credit.
- False additions in mixed and other factual answers, including qualifier/attribution changes and instructions promoted to facts.
- Complete semantic case success out of all 32 attempts: structurally valid, all expected targets retained, no invented/changed assertion and no fact promoted from non-factual material.
- Paired transitions per case/repetition for generic vs bidirectional, the primary comparison. Common-valid paired analyses are supplementary, never the only denominator. Base and fresh are descriptive controls; fresh is not a same-chain-cost revision.

Controlled outputs: report all 4 omission seeds, all 4 spurious seeds and all 4 clean seeds per arm, separately. Omission success requires restoring the missing target while retaining the originally correct fact and adding no false fact. Spurious success requires a valid factless extraction; clean success requires preserving the fully correct semantics. Technical errors count as unsuccessful correction/preservation and remain explicitly identifiable.

## Decision gate fixed before inference

Call the pilot a **simultaneous natural improvement worth expanding** only if bidirectional vs generic satisfies every requirement:

1. Fewer all-cause unserved factual targets AND fewer pure-NF wrong-upgrade cases, with correct-and-valid NF count also increasing. Each direction's favorable transitions must involve at least two distinct natural answer IDs. Repeated results must not show a systematic opposite effect.
2. Structural validity and complete semantic case success do not decrease. No new serious scope, modality, attribution, polarity or conditional reversal; no new loss of a fact preserved by base and generic. Mixed-answer spurious assertions do not increase.
3. Controlled omission and spurious success each reach at least 3/4 and are no worse than generic; clean preservation is 4/4.
4. Estimated all-cache-miss base-plus-revision cost ratio versus generic is at most 1.25. Report latency as measured; twice as many calls does not imply exactly twice the tokens or latency.

If only one error axis improves, report that axis only. If generic has no valid omission opportunity or no advice-upgrade opportunity, simultaneous benefit is unidentifiable on natural outputs, even if the controlled tests succeed. If the conclusion depends on uncertain semantic interpretation, mark it unresolved. A gate pass licenses a larger, independently sourced frozen study only; it never promotes a production change. Counts and paired examples are descriptive, not statistical proof; four constructed domains and two repeats are insufficient for a broad generalization claim.

## Runtime and accounting

Report actual provider prompt/completion/reasoning/cache-hit tokens, fingerprints, attempts, errors, wall time and per-call latency. Reference USD estimates use the project's existing fixed prices per million: input 0.30, cached input 0.006, output 1.20. These are reference estimates, not an invoice or claim about current pricing. Report cached and all-cache-miss estimates. Revision incremental cost and base-plus-revision chain cost are separate; the base is physically executed once and reused by both paired arms, so chain-cost comparisons must not be summed into physical spending. Gemini advisory costs/usage are disclosed separately. Keep raw journals, freeze/source hashes and analysis artifacts.

## Gemini design review disposition

Accepted: move semantic reminders into the shared revision prompt so the unique intervention is direction/order; retain fixed all-attempt denominators; report opportunity ceilings; distinguish correction competence from natural incidence.

Not adopted: copying historical model-output templates into controlled drafts could contaminate the construction and is unnecessary; this pilot uses explicitly disclosed artificial neutral drafts. A suggested one-axis non-inferiority criterion cannot answer the user's simultaneous-improvement question, so the stricter gate above is used. Exact cost/latency doubling is not assumed; actual measurements decide.
