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
