You are the independent Gemini High results critic for this preregistered component pilot. Read only supplied materials; no tool use, no new model tests. Reply in Chinese <=1500 Chinese characters. Audit the interpretation of three component contrasts and explicitly distinguish observed gains from untested claims. Give a cautious next research priority, not a production change or case-specific fix. There must be no benchmark tuning. Initial evidence: 20 newly AI-authored cases, 45 coverage targets, 2 repetitions; 140 initial calls and 27 actual policy reviews, 167 total. Initial M1/M3 all same model/thinking disabled/8192, review production enabled/16384; transport retries disabled for persistence. M1 concise is a research extraction control, not deployed end-to-end minimal. M3 simple is minimal prompt plus fixed-claim adapter. 85 eligible current M3 initials all had correct labels, so review observed no wrong label eligible to fix; do not claim review is useless or proven effective. Its one C review removed a schema-invalid extra kind_note and supplemented citations while keeping C. Other 26 U reviews kept U. Important: in your prior design review you wrongly claimed review state should be shared per case. Production creates state per claim; author limits are per claim. That suggestion was rejected. Do not repeat it.
M1 raw content: each arm retained 88/90 targets with 2 uncertain occurrences, not 2 confirmed omissions. Same R2 item across both repeats/arms has frozen reference port detail only in the suggested action, not the explicit factual reason; retain sensitivity, do not retune or relabel. M1 all claims raw readable; strict joint requires validity + standalone faithful facts + no false inclusions/NF contradictions. Current reduced false-inclusion outputs but joint completion did not increase. 45 targets do not force 45 atomic output rows.
M3 failures: simple one batch altered fixed claim identities/text (three targets); current one invalid JSON batch (three targets) plus two U rows with forbidden citations. Current 87 identifiable labels correct vs simple84/87, but common valid-correct 85 vs84 /90. This is not end-to-end accuracy and not a claim every raw model judgment was observable.
Evidence audit: all 68 distinct S/C citation combos independently AI audited, five insufficient agreed; two local-scope ambiguities preserved null. Semantic sufficient results thus bounds. Gold/reference remains AI-only; no author approval, no formal RAGTruth v2, no new unseen empirical generalization proof.

FROZEN PLAN:
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

SUMMARY:
{
  "qualification": "AI-authored diagnostic component study; not author gold or end-to-end benchmark",
  "m1": {
    "concise": {
      "attempts": 40,
      "structurally_valid": 31,
      "raw_readable": 40,
      "targets": 90,
      "strict_joint_lower": 18,
      "strict_joint_upper": 18,
      "false_claim_outputs": 16,
      "pure_nf_attempts": 10,
      "pure_nf_correct_valid": 5,
      "raw_content_retained": 88,
      "raw_content_retained_unknown": 2,
      "completed_content_retained": 68,
      "raw_standalone": 76,
      "raw_standalone_unknown": 0,
      "completed_standalone": 60,
      "raw_faithful": 88,
      "raw_faithful_unknown": 2,
      "completed_faithful": 68,
      "raw_source_sufficient": 90,
      "raw_source_sufficient_unknown": 0,
      "completed_source_sufficient": 69,
      "raw_atomic": 90,
      "raw_atomic_unknown": 0,
      "completed_atomic": 69,
      "both_repeats_lower": 7,
      "both_repeats_upper": 7
    },
    "current": {
      "attempts": 40,
      "structurally_valid": 31,
      "raw_readable": 40,
      "targets": 90,
      "strict_joint_lower": 16,
      "strict_joint_upper": 16,
      "false_claim_outputs": 13,
      "pure_nf_attempts": 10,
      "pure_nf_correct_valid": 7,
      "raw_content_retained": 88,
      "raw_content_retained_unknown": 2,
      "completed_content_retained": 68,
      "raw_standalone": 76,
      "raw_standalone_unknown": 0,
      "completed_standalone": 58,
      "raw_faithful": 88,
      "raw_faithful_unknown": 2,
      "completed_faithful": 68,
      "raw_source_sufficient": 90,
      "raw_source_sufficient_unknown": 0,
      "completed_source_sufficient": 69,
      "raw_atomic": 90,
      "raw_atomic_unknown": 0,
      "completed_atomic": 69,
      "both_repeats_lower": 3,
      "both_repeats_upper": 3
    }
  },
  "m3": {
    "simple": {
      "unexpected_rows": 0,
      "order_invalid_batches": 1,
      "opportunities": 90,
      "identifiable": 87,
      "raw_label_correct": 84,
      "public_valid": 87,
      "public_valid_correct": 84,
      "arm_schema_valid": 87,
      "arm_schema_valid_correct": 84,
      "evidence_valid_correct_lower": 80,
      "evidence_valid_correct_upper": 82,
      "case_attempts": 30,
      "public_complete_cases": 29,
      "public_complete_correct_cases": 26
    },
    "current": {
      "unexpected_rows": 0,
      "order_invalid_batches": 1,
      "opportunities": 90,
      "identifiable": 87,
      "raw_label_correct": 87,
      "public_valid": 85,
      "public_valid_correct": 85,
      "arm_schema_valid": 85,
      "arm_schema_valid_correct": 85,
      "evidence_valid_correct_lower": 84,
      "evidence_valid_correct_upper": 85,
      "case_attempts": 30,
      "public_complete_cases": 27,
      "public_complete_correct_cases": 27
    },
    "paired_common_contract": {
      "correct->correct": 80,
      "correct->not_correct": 4,
      "not_correct->correct": 5,
      "not_correct->not_correct": 1
    }
  },
  "review": {
    "opportunities": 90,
    "eligible": 85,
    "triggered": 27,
    "before_correct": 85,
    "after_correct": 85,
    "before_contract_correct": 84,
    "after_contract_correct": 85,
    "before_evidence_correct_lower": 83,
    "after_evidence_correct_lower": 84,
    "before_evidence_correct_upper": 84,
    "after_evidence_correct_upper": 85,
    "wrong_initial_triggered": 0,
    "wrong_initial_not_triggered": 0,
    "c_reviews": 1,
    "u_reviews": 26,
    "transitions": {
      "correct->correct": 85,
      "incomplete->incomplete": 5
    },
    "net_label_corrections": 0,
    "net_usable_label_gain": 1
  },
  "costs": {
    "m3:current": {
      "calls": 30,
      "prompt_tokens_known": 30114,
      "output_tokens_known": 13451,
      "cache_hit_tokens_known": 21248,
      "usage_missing_calls": 0,
      "cache_missing_calls": 0,
      "all_miss_known_subtotal": 0.025175399999999997,
      "observed_cache_estimate": 0.018928487999999997,
      "cost_complete": true,
      "models": {
        "deepseek-flash": 30
      },
      "fingerprints": {
        "e72d3c7f663d3e1383b00b3884cb4501": 30
      },
      "call_latency_mean_seconds": 2.7635666666630034,
      "call_latency_p95_seconds": 3.2179999999934807
    },
    "review": {
      "calls": 27,
      "prompt_tokens_known": 32295,
      "output_tokens_known": 9153,
      "cache_hit_tokens_known": 22400,
      "usage_missing_calls": 0,
      "cache_missing_calls": 0,
      "all_miss_known_subtotal": 0.0206721,
      "observed_cache_estimate": 0.0140865,
      "cost_complete": true,
      "models": {
        "deepseek-flash": 27
      },
      "fingerprints": {
        "e72d3c7f663d3e1383b00b3884cb4501": 27
      },
      "call_latency_mean_seconds": 2.7210370370626658,
      "call_latency_p95_seconds": 3.952999999979511
    },
    "m3:simple": {
      "calls": 30,
      "prompt_tokens_known": 14274,
      "output_tokens_known": 8116,
      "cache_hit_tokens_known": 5760,
      "usage_missing_calls": 0,
      "cache_missing_calls": 0,
      "all_miss_known_subtotal": 0.014021399999999998,
      "observed_cache_estimate": 0.012327959999999999,
      "cost_complete": true,
      "models": {
        "deepseek-flash": 30
      },
      "fingerprints": {
        "e72d3c7f663d3e1383b00b3884cb4501": 30
      },
      "call_latency_mean_seconds": 1.9406333333191772,
      "call_latency_p95_seconds": 2.422000000020489
    },
    "m1:concise": {
      "calls": 40,
      "prompt_tokens_known": 17118,
      "output_tokens_known": 11808,
      "cache_hit_tokens_known": 7552,
      "usage_missing_calls": 0,
      "cache_missing_calls": 0,
      "all_miss_known_subtotal": 0.019305,
      "observed_cache_estimate": 0.017084712,
      "cost_complete": true,
      "models": {
        "deepseek-flash": 40
      },
      "fingerprints": {
        "e72d3c7f663d3e1383b00b3884cb4501": 40
      },
      "call_latency_mean_seconds": 2.0300749999994876,
      "call_latency_p95_seconds": 2.655999999959022
    },
    "m1:current": {
      "calls": 40,
      "prompt_tokens_known": 23358,
      "output_tokens_known": 11833,
      "cache_hit_tokens_known": 12800,
      "usage_missing_calls": 0,
      "cache_missing_calls": 0,
      "all_miss_known_subtotal": 0.021207,
      "observed_cache_estimate": 0.0174438,
      "cost_complete": true,
      "models": {
        "deepseek-flash": 40
      },
      "fingerprints": {
        "e72d3c7f663d3e1383b00b3884cb4501": 40
      },
      "call_latency_mean_seconds": 2.187074999991455,
      "call_latency_p95_seconds": 3.062999999965541
    }
  },
  "semantic_audit_complete": true
}
OPERATIONAL AUDIT:
# Component pilot operational audit

Status: **PASS**. 29 checks; no semantic scores examined.

The completed run contains 140 initial stages and 90 paired review stages. All 230 stage reservations have matching durable results; all 167 physical-call reservations have matching results. Missing usage: 0.

| Provider phase | Actual calls | Missing usage | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| contradiction_review | 1 | 0 | 1287 | 1107 |
| m1_concise | 40 | 0 | 17118 | 11808 |
| m1_current | 40 | 0 | 23358 | 11833 |
| m3_current | 30 | 0 | 30114 | 13451 |
| m3_simple | 30 | 0 | 14274 | 8116 |
| unsupported_review | 26 | 0 | 31008 | 8046 |

Review triggers: C=1, U=26. Maximum physical review calls for one claim: 1, below the frozen cap of 6. Each claim uses C at most once and U at most once, in the permitted order. Every recorded complete call contains exactly one transport attempt.

All 65 frozen files still match their hashes. Request-only inputs reproduce the frozen request matrix. Review before-values and their source hashes match the persisted current-M3 initial rows. Ineligible rows were not reviewed; non-triggered eligible rows remain unchanged.

No gold/reference metadata or scheduling case identifiers entered model messages. No client-side hidden resampling, unknown reservation, result overwrite, missing trace, or operational warning was observed. No resume/restart occurred. Provider-internal execution cannot be audited from client records.

Checks:

- PASS: `final_summary_complete`
- PASS: `frozen_manifest_sha_consistent`
- PASS: `all_frozen_files_still_match`
- PASS: `cases_file_sha_consistent`
- PASS: `planned_matrix_sha_consistent`
- PASS: `planned_matrix_reconstructed_from_frozen_request_only_inputs`
- PASS: `planned_140_initial_90_reviews`
- PASS: `all_230_stages_reserved_and_completed_once`
- PASS: `all_provider_calls_have_unique_reservation_and_result`
- PASS: `no_unknown_or_missing_stage_or_provider_results`
- PASS: `no_operational_failures_or_warnings`
- PASS: `stage_reservations_equal_plan`
- PASS: `stage_result_identity_matches_plan`
- PASS: `initial_count_by_arm`
- PASS: `call_keys_are_unique_stage_ordinal_hashes`
- PASS: `provider_ordinals_contiguous_without_duplicates`
- PASS: `each_initial_issued_exactly_once`
- PASS: `every_complete_is_exactly_one_transport_attempt`
- PASS: `all_transport_retries_disabled`
- PASS: `initial_and_review_use_frozen_generation_budgets`
- PASS: `stage_counts_match_actual_provider_reservations`
- PASS: `stage_telemetry_has_every_actual_call_exactly_once`
- PASS: `initial_raw_outputs_equal_persisted_call_raw_outputs`
- PASS: `physical_call_ceiling_observed`
- PASS: `review_before_equals_exact_durable_current_initial`
- PASS: `per_claim_C_U_targeted_and_physical_budgets`
- PASS: `review_order_is_C_then_U_without_second_C`
- PASS: `no_gold_metadata_or_scheduling_ids_entered_messages`
- PASS: `single_run_without_resume_or_restart`
