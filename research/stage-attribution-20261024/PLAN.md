# Component attribution pilot — preregistration

2026-10-24 Asia/Shanghai. User request: separately test M1 factual fidelity, M3
accuracy with fixed claims, and the net correction of bounded review, with Gemini
High assistance and fresh cases. No benchmark-specific tuning. Production files
and historical results remain unchanged. This is a diagnostic study, not a
production promotion or formal RAGTruth v2 acceptance.

## New material and inference isolation

20 new fictional, self-contained answers from five domains, ten Chinese and ten
English. Each domain has three factual/mixed answers and one pure non-factual
answer. Each factual answer has three annotated targets: 45 fixed claims in total,
15 S / 15 C / 15 U across the set. Distribution within answers is not prescribed.
These are 45 content-coverage targets, not a required count of M1 output rows;
faithful atomic splitting can map several rows to one compound coverage target.
The fixed M3 target still requires its entire assertion to hold.
Five pure NF answers test false inclusion. Both repetitions use the same inputs;
40 outputs per M1 arm are not 40 independent cases. Answers are 200–1100
characters, so M1 is a single-chunk study and cannot establish long-answer scaling.

An independent AI role drafts the cases without reading old benchmark inputs or
candidate prompts; another role audits before any inference. Gold-like targets
are explicitly AI draft references, never author gold. New prompts are fixed
before the coordinating agent reads these cases. Fix ambiguous labels/materials
before the inference freeze only, keep a change log, and do not condition revisions
on model results. Semantic ambiguities after inference are reported with sensitivity
bounds, never silently relabeled for a preferred arm.

cases.json contains only id, generated_answer, context_passages, and claims
(id + claim_text). annotations.json contains labels, evidence, source spans,
NF boundaries and rationale. Runner reads cases.json only. The case id never
enters the model payload. M1 sees only the answer. M3 sees exactly the same fixed
claims and numbered passages for both arms, never the reference verdict/evidence.

## Frozen component contrasts

1. M1 concise vs current: research-only concise extraction instruction vs unchanged
   production DECOMPOSE_PROMPT, with identical answer payload, exact source-span
   schema and lexical-coverage validator. One attempt, no repair/fallback. The
   concise extractor is NOT the deployed minimal end-to-end backend. It is a
   task-matched extraction control. 20 cases × 2 arms × 2 repeats = 80 calls.
2. M3 simple vs current: minimal's existing semantic instructions plus a fixed-claim
   adapter vs unchanged v4 VERIFY_PROMPT. Same three claims, context, model,
   thinking disabled, 8192 output cap, no transport/format retry. Simple emits
   public fields + id; current additionally emits derivation/conflict. That output
   protocol difference is part of the contrast, not a claim of equal token cost.
   15 cases × 2 arms × 2 repeats = 60 calls, 90 target opportunities per arm.
3. Review: persist every current-M3 initial response first. Each initial valid row
   is passed exactly once to the existing v4 _finish_claim logic. No new initial
   draw. Preserve C/U triggers, order, logical limits and production prompts;
   review thinking enabled / 16384, format and targeted bounds unchanged. Disable
   only transport retries for the whole experiment to persist every HTTP attempt.
   Non-triggered valid rows are recorded unchanged. Invalid initial rows remain
   incomplete; they are not replaced or assigned U. No forced C/U examples or
   added cases if natural triggers are few. This estimates this review policy's
   incremental result, not whether its prompt beats equal-budget resampling.

All initial calls use the same configured provider/model and disabled thinking /
8192 token cap. Shared caps are not equal realized reasoning or total compute.
Production review deliberately has its own existing budget; disclose separately.
Run two repetitions with fixed randomized job order, at most four concurrent
jobs. No optional stopping on scores. No additional attempts beyond registered
review bounds. Failed/unknown calls remain in the planned denominators.

## Scoring fixed before calls

M1: blind, source-grounded semantic audit of ALL 80 outputs, including parseable
structurally invalid raw outputs. Per target score content retained, independently
understandable, subject/attribution/condition/negation/quantity preserved, and exact
source-span sufficiency. Per output score false assertions/advice promoted,
omissions, factual targets excluded as NF, and extra duplicate claims separately.
Strict joint success requires valid protocol, all targets preserved as standalone
faithful atomic assertions, no false additions and no fact in NF. Primary counts
use all planned outputs; semantic-only raw diagnostics cannot turn invalid output
into complete. NF-only correct means valid empty claims with adequate NF coverage.
Report both-repeats success per original answer, gains and harms by case/domain.
Content retention may allow a compound claim; strict atomicity is separate.

M3: compare raw identifiable verdict accuracy, common public-contract-valid correct
verdict /90, and complete three-claim cases /30. Missing/changed/duplicate id/text,
invalid JSON, bad quotes count as incomplete, never as a semantic U. Current's
internal conflict validity is reported separately. Review-eligible initial rows
must pass common public validation and current schema; malformed C conflict can
still enter the actual C review. Audit quote semantic sufficiency for all returned
S/C claims (automated exact matching alone is not sufficient). All denominators
and conditional-on-valid diagnostics are shown, not interchangeable rankings.

Review: paired before/after transition matrix using exactly the persisted initial
rows. Count wrong→right, right→wrong, wrong→different wrong, correct→incomplete,
wrong→incomplete and unchanged. Separate semantic label changes from C evidence/
contract repair. Net semantic correction = wrong→right minus right→wrong, with
correct→incomplete additionally subtracted for usable-correct net gain. Also show
all 90 opportunities, number of initially wrong claims eligible/not triggered,
number of C/U reviews, per-kind transitions, actual added calls/tokens/cost. Review
failure does not revert to the initial prediction in the primary final metric.
Low trigger/error counts mean inconclusive, not proof that review works or fails.

Labels are AI references; inference output reviewers see randomized aliases and
not arm names, prompt, token cost or repeat pairing. Schema may reveal the arm,
so describe this as procedural blinding. A second AI reviewer audits disputed
semantic judgments. Retain both readings and sensitivity bounds where needed.
No LLM judge verdict is silently substituted for author approval.

## Decision and reproducibility

No automatic promotion. This study diagnoses a stage, not modifies it. Describe
paired differences and both-repeat consistency; if intervals are used, cluster
by original case, not individual repeated claims. Five artificial domains and
20 answers do not establish broad statistical generalization. Zero observed
errors is a ceiling result, not a newly solved capability. Do not compare these
scores numerically with different earlier M1 criteria or RAGTruth answer labels.

Freeze PLAN, protocol, runner, tests, cases, annotations, production source,
configuration and model settings into FROZEN.json before first inference. Save
durable request reservations before each call, raw response/telemetry and actual
attempts. Resume may execute only never-reserved requests; an outstanding
reservation is UNKNOWN and never automatically resent. Store and verify hashes
before/after. Keep all attempts, errors and intermediate review states.

Report actual usage/fingerprint, completion, latency and fixed reference USD per
million: uncached input .30, cached input .006, output 1.20. Show observed-cache
and all-cache-miss estimates, not provider billing/current prices. Missing usage
is unknown. Review incremental costs separately, Gemini cost separately.

Gemini High reviews this plan before freeze and audits aggregate interpretation
afterward. Its advice is evidence to assess, not authority to retune after exposure.

## Pre-run review disposition and metric clarification

Gemini High design review completed successfully. Adopted reminders: M3 measures
prompt plus output-schema burden; AI references and procedural blinding are limited;
all failed batches still contribute their three targets to /90; review analysis
excludes initial rows that fail the common exact-quote contract, and does not test
initial M2 recovery. public_valid is intentionally distinct from arm-schema validity
and review eligibility. The common-public metric uses public_valid + label_rows,
not the stricter rows mapping. Extra rows/order anomalies are recorded separately.

Rejected Gemini's proposed case-shared review state: production _batch creates a
new state inside its per-claim loop, and the author's C<=1/U<=1 limits are per claim.
Sharing one state across three different claims would violate that contract.
The research adapter correctly creates one state per persisted initial claim.

Usable net benefit is computed directly as after usable-correct minus before
usable-correct. Report public/structured contract recovery separately from label
correction, and evidence-semantic sufficient/correct as an additional audited
metric; unchanged labels can still gain or lose adequate evidence. AI evidence
audit covers every distinct S/C claim+citation combination, with exact duplicates
scored once and mapped back to every planned occurrence.

M1 blind review schema is fixed as per-target content_retained, standalone,
faithful, source_sufficient and atomic (true/false/null), plus output-level
no_false_claims, no_fact_in_nf, all_claims_well_formed and reasons. Null denotes
genuine ambiguity or unavailable output, not success. Strict lower/upper bounds
require all flags true/not-false respectively plus structurally valid output.
Faithful repetition is recorded as redundancy, not invented factual content.
Source sufficiency permits explicit shared antecedents from the answer as the
task allows; it never imports evidence-context-only facts into M1 references.

The protocol was fixed before the coordinating agent read the new case contents.
Independent pre-inference material review corrects only unsupported reference
additions, ambiguity and annotation consistency, with an explicit change log.
Two general validation/reporting additions followed the initial protocol-registration
snapshot before inference: record requested-row order and enforce full evidence
audit coverage. No new inference instruction was derived from case contents.
