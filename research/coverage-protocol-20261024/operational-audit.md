# Coverage-protocol operational audit

Audit date: 2026-10-24. Run: `results/coverage-protocol-20261024`. Preregistered source commit: `dc1cbc0b2c65fe0d43f88f605a9e805f9bd80389`.

**Operational integrity checks passed.** The run completed all 120 reserved single-attempt requests without I/O warnings or unknown reservations. This statement concerns execution/accounting, not semantic fidelity or a successful optimization. Arm-specific operational details are confined to this file so the root reviewer can finish semantic review without receiving arm gains in a message.

This is an AI engineering audit by the runner author, not an independent human audit or author adjudication. I did not alter frozen input, output, code, prompt, model settings or semantic scores, and made no provider calls. Validation was rerun offline against the frozen protocol. New case answers were processed by the whitelist and payload reconstruction code for byte/source checks, without reading the gold to grade outputs.

## Frozen execution and accounting

- 56 frozen source/plan/case files passed SHA-256 verification, and each corresponding current workspace file still matches. The frozen runner reconstructed the 120 planned requests from the frozen cases and protocol and obtained exactly the same matrix.
- `grounding`, `configs` and `prompts` have no tracked differences from production baseline `e78fa35`; the audit-time HEAD is the preregistration commit above. No production runtime modification was made for the pilot.
- Exactly 120 unique identities appear once each in planned requests, exclusive reservations, durable response files, event journal and final canonical journal. Both journals contain identical records when keyed by identity.
- Every reservation preceded its corresponding recorded call start, and every call start preceded completion. All reservation and response hashes match the final completion seal. Each response contains exactly one provider trace with `attempt: 1`.
- `run-complete.json` reports zero unknown reservations, zero I/O warnings and a healthy event journal. No recovery, resume, resampling or automatic model retry occurred.
- Requested settings were deepseek-flash, thinking disabled, max output 8192, JSON mode, max claims 64, upstream retries 0, repair attempts 0, timeout 180 seconds and four workers. No M3, fallback or quote repair occurred.
- The run began at `2026-10-24T02:47:05.626973+00:00` and completed at `2026-10-24T02:49:09.153795+00:00`.
- 117 responses returned HTTP 200, finish_reason=stop, model `deepseek-flash`, fingerprint `e72d3c7f663d3e1383b00b3884cb4501`. Three transport failures have no returned model/fingerprint/usage; requested model does not prove what a remote provider executed for those failures. No observed response was token-truncated.

## Input isolation and protocol provenance

- Reconstructed each transmitted system/user message from its frozen prompt and payload, and compared it to the saved message bytes. The message body contains no outer case ID, arm, repeat, scheduling metadata, expected target, gold or domain/generator metadata.
- Legacy payload keys are exactly generated_answer, max_claims and boundary_context. Ledger payload keys are exactly source_units, max_claims and boundary_context; each source unit has only unit_id and text. Joining the units recovers the complete answer exactly.
- All 40 matched ledger_text/ledger_id input pairs are identical. Source-unit IDs are occurrence addresses generated from the answer, not sample identities. No code path uses a case ID or a target label to select a prompt or interpretation.
- Offline protocol revalidation reproduced every saved success or validation error exactly. All 82 accepted legacy claims point to their exact source substrings and intervals. All 192 accepted ledger claims retain discrete source-unit references; 193 referenced fragments match original intervals exactly. No ledger claim has an invented enclosing source_span/source_end.
- 267 echoed source_text entries across all 37 received ledger_text outputs match their entire input unit exactly, including whitespace and punctuation. The 40 ledger_id outputs omit source_text as required. There is no observed text-echo error in the received outputs; the three unavailable responses cannot be audited for echo quality.
- Exact provenance and explicit ledger accounting do not prove semantic support or complete fact selection. The coarser coverage contract and masking risk still require the separate preregistered semantic review.

## Structural outcomes and error categories

| Arm | Attempted | Structurally valid | Coverage rejection | Transport error | Observed echo/schema rejection |
|---|---:|---:|---:|---:|---:|
| legacy | 40 | 33 | 7 | 0 | 0 |
| ledger_text | 40 | 37 | 0 | 3 | 0 |
| ledger_id | 40 | 40 | 0 | 0 | 0 |

All seven legacy validation failures are meaningful-source-text coverage union failures; they are not JSON parse failures or transport failures. Both ledger protocols accepted every response actually received. The ledger arm validity difference therefore includes transport outcomes and cannot be attributed to avoiding echo errors.

| Arm | Case / repeat | Error category | HTTP / finish / usage |
|---|---|---|---|
| legacy | cp007 / 0 | unaccounted meaningful source text | 200 / stop / present |
| ledger_text | cp003 / 1 | Upstream response could not be read completely. | None / None / unknown |
| ledger_text | cp013 / 0 | Could not connect to upstream API. | None / None / unknown |
| legacy | cp005 / 1 | unaccounted meaningful source text | 200 / stop / present |
| legacy | cp005 / 0 | unaccounted meaningful source text | 200 / stop / present |
| legacy | cp015 / 1 | unaccounted meaningful source text | 200 / stop / present |
| legacy | cp004 / 1 | unaccounted meaningful source text | 200 / stop / present |
| ledger_text | cp002 / 1 | Upstream response could not be read completely. | 200 / None / unknown |
| legacy | cp002 / 1 | unaccounted meaningful source text | 200 / stop / present |
| legacy | cp014 / 1 | unaccounted meaningful source text | 200 / stop / present |

The three transport errors all occurred at execution position 0; two have no HTTP status, and one received HTTP 200 but did not yield a complete readable body. They remain failed attempts with unknown usage. No replacement calls were made.

## Usage, cost and position audit

Costs use the frozen reference USD rates per million tokens: input 0.30, cached input 0.006, output 1.20. These are reference estimates, not provider billing. I independently recomputed both cache-aware and all-cache-miss subtotals from individual provider usage records and matched analysis.json. Missing usage is not zero.

| Arm | Usage known / attempts | Input | Output | Cache hit | Cache miss | Known cache-aware USD | Known all-miss USD | Mean / P95 seconds (all attempts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy | 40 / 40 | 23454 | 10403 | 15741 | 7713 | 0.014891946 | 0.0195198 | 3.286 / 7.859 |
| ledger_text | 37 / 40 | 36189 | 16011 | 22528 | 13661 | 0.023446668 | 0.0300699 | 4.491 / 14.859 |
| ledger_id | 40 / 40 | 38646 | 12087 | 24058 | 14588 | 0.019025148 | 0.0260982 | 3.109 / 8.390 |

The ledger_text and whole-run cost totals are unknown because three calls lack usage; the displayed values are known-call subtotals. Legacy and ledger_id have complete usage. Across all arms the known usage is 98,289 input + 38,501 output = 136,790 tokens, with 62,327 cache-hit input and 35,962 cache-miss input. Known cost is USD 0.057363762 with cache accounting, or USD 0.0756879 with all input priced as cache misses.

| Arm | Position (0-based) | Attempts | Usage known | Input | Output | Hit / miss | Known cached USD | Known all-miss USD | Mean / P95 seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy | 0 | 13 | 13 | 7621 | 3293 | 5248 / 2373 | 0.004694988 | 0.0062379 | 2.779 / 8.453 |
| legacy | 1 | 13 | 13 | 7893 | 3779 | 5245 / 2648 | 0.005360670 | 0.0069027 | 3.175 / 7.859 |
| legacy | 2 | 14 | 14 | 7940 | 3331 | 5248 / 2692 | 0.004836288 | 0.0063792 | 3.860 / 14.719 |
| ledger_text | 0 | 14 | 11 | 10363 | 4201 | 5376 / 4987 | 0.006569556 | 0.0081501 | 6.884 / 25.641 |
| ledger_text | 1 | 13 | 13 | 12665 | 5438 | 8832 / 3833 | 0.007728492 | 0.0103251 | 3.131 / 6.110 |
| ledger_text | 2 | 13 | 13 | 13161 | 6372 | 8320 / 4841 | 0.009148620 | 0.0115947 | 3.273 / 6.734 |
| ledger_id | 0 | 13 | 13 | 13018 | 4618 | 7038 / 5980 | 0.007377828 | 0.0094470 | 2.638 / 4.406 |
| ledger_id | 1 | 14 | 14 | 13106 | 3760 | 8188 / 4918 | 0.006036528 | 0.0084438 | 2.715 / 4.750 |
| ledger_id | 2 | 13 | 13 | 12522 | 3709 | 8832 / 3690 | 0.005610792 | 0.0082074 | 4.002 / 10.546 |

The fixed 40-output all-miss ledger_id cost is 1.337012× legacy (33.70% higher). This exceeds the preregistered 1.30× screening limit, irrespective of semantic scoring. Its complete 40-call cost is below ledger_text's known 37-call subtotal, but ledger_text's full total and the exact percentage reduction against that full total are unknown. This audit does not choose a winner based on cost or completion alone.

For the inherited runtime summary, by_variant_execution_order contains only positions 0 and 1; it must not be mistaken for a complete three-position audit. The explicit per-arm by_execution_position field contains all positions 0, 1 and 2, reproduced above. Similarly, telemetry summary_totals.extracted_claim_count=0 reflects the generic summary helper reading an unused extraction telemetry field, not zero actual claims. Use analysis.arms.*.claim_count or saved validated_output instead.

Thinking disabled is the requested setting. The responses contain no separately accounted reasoning-token field, so the generic usage helper's numeric zero must not be described as measured zero reasoning. Gemini consultation usage is outside this DeepSeek run and must be accounted separately.

## Integrity hashes

| Artifact | SHA-256 |
|---|---|
| freeze.json | `75bbf3a2e4d20ec055a9ad9a098bd8f292f563c0db33e28ba28dc66c21e22fd8` |
| planned-requests.json | `ee1ec17d8125b6a0e11320eb329e4b74975ce63bca56a32f7fe6c99e63a52d31` |
| prompts.json | `5e111749c69ab790f70ce137ae0e0989112f42111d9673749a8e0a7187dcc76f` |
| responses.events.jsonl | `4e1be5b4425c8ed85210661c70bf2dd17025f4daf746af363b814f1f7e2ad8a1` |
| responses.jsonl | `3ecbd01f0816430205289a64ebcbd168ac65b19147a66bcb8a06e29238888c9e` |
| run-complete.json | `e9ce32cf788cefb7beefa976688eb7e1962036d1f94931edca6b12b8006ecd33` |
| analysis.json | `61e59893f4baae726771815fd1e7bb87a9fa204b9d87e503a33ca5df93abfaa9` |

No frozen artifact, response record or semantic score was rewritten by this audit. The only output is this report.
