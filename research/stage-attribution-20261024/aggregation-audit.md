# Independent aggregation audit

Status: **PASS**; 154 published scalar/transition comparisons, 0 mismatches. analyze.py was not read or imported.

## M1

| Metric | Concise | Current |
| --- | ---: | ---: |
| attempts | 40 | 40 |
| targets | 90 | 90 |
| structurally_valid | 31 | 31 |
| strict_joint_lower | 18 | 16 |
| both_repeats_lower | 7 | 3 |
| false_claim_outputs | 16 | 13 |
| false_claim_outputs_valid | 9 | 8 |
| fact_in_nf_outputs_raw | 0 | 3 |
| fact_in_nf_outputs_valid | 0 | 2 |
| raw_content_retained | 88 | 88 |
| raw_content_retained_unknown | 2 | 2 |
| invalid_output_content_retained | 20 | 20 |
| invalid_output_content_unknown | 1 | 1 |

False-claim output totals use /40 raw outputs per arm; valid-only false-claim counts use /31. Content-retention totals use /90 target opportunities per arm. Structurally invalid outputs still retain raw content; their failure is not automatically semantic omission.

Paired current versus concise strict outcomes over 40 same-case/repeat pairs: {'both_fail': 18, 'harm': 6, 'both_pass': 12, 'gain': 4}.

Structural failure categories: concise {'coverage_unaccounted_characters': 7, 'nf_row_schema': 1, 'nf_substring_occurrence_or_order': 1}; current {'claim_source_substring_or_order': 2, 'nf_substring_occurrence_or_order': 1, 'coverage_unaccounted_characters': 6}.

## Fixed-claim M3

| Metric | Simple | Current |
| --- | ---: | ---: |
| opportunities | 90 | 90 |
| identifiable | 87 | 87 |
| raw_label_correct | 84 | 87 |
| public_valid_correct | 84 | 85 |
| evidence_valid_correct_lower | 80 | 84 |
| evidence_valid_correct_upper | 82 | 85 |
| public_complete_cases | 29 | 27 |
| public_complete_correct_cases | 26 | 27 |
| both_repeats_all_labels_correct | 12 | 14 |
| both_repeats_public_complete_correct | 12 | 12 |

Simple loses three opportunities because one response adds top-level type=json_object to the required claims-only envelope; its claim IDs and texts are intact. Current loses three opportunities because one completion is not strict JSON, plus two public-contract failures because UNSUPPORTED rows contain citations. No observed failure here is an exact-quote substring mismatch.

Across fifteen original cases, count of cases with 0/1/2 repetitions passing all raw labels: simple {'2': 12, '0': 1, '1': 2}, current {'2': 14, '1': 1}. Both repetitions all public-valid and correct: simple 12/15, current 12/15.

## Paired review

Eligible 85/90; triggered 27; C 1, U 26. Semantic label net correction 0; structured usable-correct 84 to 85.

The one C review removes the extra conflict.kind_note field that violated the exact conflict schema and adds a second relevant quote. The verdict is CONTRADICTED both before and after. It is structural recovery, not a corrected semantic classification.

## Cost and unchanged production

| Stage | Calls | Input tokens | Completion tokens | Reasoning already in completion | Observed-cache USD | All-miss USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| m1:concise | 40 | 17118 | 11808 | 0 | 0.017084712 | 0.019305000 |
| m1:current | 40 | 23358 | 11833 | 0 | 0.017443800 | 0.021207000 |
| m3:current | 30 | 30114 | 13451 | 0 | 0.018928488 | 0.025175400 |
| m3:simple | 30 | 14274 | 8116 | 0 | 0.012327960 | 0.014021400 |
| review | 27 | 32295 | 9153 | 5607 | 0.014086500 | 0.020672100 |

All 167 calls satisfy total_tokens=prompt_tokens+completion_tokens; reasoning tokens are a subset and were not added a second time. Production grounding/, configs/, prompts/ match c3c222d, including no untracked additions: True.

Full per-case/repeat pairs, failure opportunities, source hashes and metric comparisons are in aggregation-audit.json.

## Supplementary readable raw-verdict diagnostic

The published raw-label count requires a strict claims-only envelope first. A separate diagnostic ignores only the extra top-level type field in the already parsed simple response, while keeping all three rows public-invalid.

| Arm | Planned | Readable exact-ID/text labels | Correct raw labels | Wrong raw labels | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| simple | 90 | 90 | 87 | 3 | 0 |
| current | 90 | 87 | 87 | 0 | 3 |

The three newly counted simple labels are all correct. Both S/C citation combinations already exist in the evidence review packet, so no new evidence judgment is needed. Main public-valid-correct remains simple 84/90 versus current 85/90; paired review metrics remain unchanged. This diagnostic is additional reporting, not a repaired primary outcome or a new model run.

Published call latency is the RecordingClient complete duration from call-results.latency_seconds. Provider transport trace duration is also reported independently; two phase means differ by about 0.5–0.8 ms because of the wrapper boundary. Cost and token totals do not depend on either latency boundary.

The three current-M1 outputs marking factual content as NF are sa06 repetition 1 and sa14 repetitions 0/1. All three simultaneously retain their targets in claims; these are conflicting factual/NF bookkeeping, not evidence of missed content.
