You are Gemini High reviewing a preregistered full-system evaluation, not optimizing prompts. Only inspect the supplied plan and exposure audit; no tools, no model tests, no selection. In Chinese <=900 characters, identify any serious pre-run issue in source isolation, sampling, budgets, partial-aware metrics, native labels and durable execution. Three exact backends baseline/minimal/optimized-v4.0, 180 fresh responses. User explicitly forbids benchmark tuning. Do not treat pending author adjudication as blocking this newly authorized native-label comparison. Avoid requiring unrelated infrastructure or large new studies. State limitations and minimal corrections if necessary.

# Fresh RAGTruth 180: full three-backend comparison

2026-10-24 Asia/Shanghai. The user explicitly requests a complete baseline,
minimal and optimized-v4.0 comparison on180 newly selected, nonrepeated RAGTruth
answers. This supersedes waiting for the earlier author-adjudication acceptance
milestone for the purpose of this native-label comparison. It does not declare
author gold complete or v4 semantic acceptance passed.

## Frozen systems and inputs

No inference code, prompt, semantic rule, budget or model is optimized in this
run. Freeze current grounding/scripts, v4 config, research wrappers/scorer, plan,
raw upstream hashes and exposure evidence before selecting inputs. Execute the
frozen copy. Use the existing baseline, minimal and optimized-v4.0, not the
combined or M1-faithful experiments. One result per answer/backend,540 planned
records. Failed model outputs are not rerun to improve scores.

Pinned upstream commit: c103204b9ce28d6bbad859304bf30de72b8ed8fe. Use official test
split, quality=good. Select30 source groups: QA/Summary/Data2txt10 each, exactly6
good answers per group,180 total. Quality is not a hallucination label. Exclude
all previously used/exposed source IDs, including old180, small30, train-smoke,
other actual trials and resolved public research examples. Also exclude exact
adapted-context aliases of exposed sources and groups containing a previously
used canonical request. For eligible unexposed duplicate-context clusters keep
the lexicographically first source ID; if a six-answer group contains duplicate
canonical requests, exclude that entire group. This input hygiene can affect the
population represented and will be disclosed; it never consults labels or scores.

Selection seed: ragtruth-fresh180-v2-20261024. Rank eligible source IDs by
sha256(seed|task_type|source_id), tie by source_id, as in v1. Take the first10 per
task and all six answers in each source, sorted by response ID. Retain unchanged
input size eligibility: an oversized response excludes the whole source before
ranking; no truncation. Validate selected native label spans only after selection;
invalid labels stop preparation without replacement. No redraw or optional sample
size expansion based on scores. Do not browse chosen answers to tune the systems.

Input adaptation reuses unchanged ragtruth_v4/ragtruth_data: exact QA passage
text (question omitted because it is not a supplied evidence passage), exact
Summary source, deterministic complete JSON serialization for Data2txt preserving
nulls/booleans. generated_answer stays unchanged. Native spans go into a separate
gold artifact. Only context_passages/generated_answer enter verify; no source ID,
task, generator, labels or sampling metadata enter model prompts.

Register the selected sources in the exposure ledger before any model invocation.
Binding records input/manifest/gold/preparation byte hashes, preselection hash and
sampling freeze. Verify180 unique response IDs and canonical requests,30 unique
context groups, zero intersection with all known excluded sources/requests/context
hashes. Metadata-only deduplication is not a new semantic annotation or difficulty
selection. New sources become exposed after this run and cannot be reused as a
future untouched test if they guide development.

## Execution and budgets

Existing provider/model deepseek-flash, global thinking enabled/16384 for minimal;
minimal's existing single-attempt/no-format-repair behavior remains. V4 uses
configs/optimized-v4.0.json: decompose disabled8192, verify disabled8192, review
enabled16384, existing batching, internal parallelism and bounded repairs.
Baseline makes no model calls. This compares existing systems, not equal-compute
component ablations. Record returned model/fingerprint and usage for all attempts.

Four concurrent case workers; each case runs three backends sequentially in the
fixed hash-shuffled order with seed20261024. No per-task/generator configuration.
Write a durable per-pair reservation before verify; atomically save the whole
prediction and telemetry afterward. Existing reservation without result means
UNKNOWN and is never automatically resent. A resumed run may dispatch only pairs
never reserved. Internal production retries are part of the frozen system, not
an external evaluation rerun; all available attempts are charged. A derived
progress-file write failure cannot discard a completed result. Abort dispatch if
durable reservation/result recording fails. Retain failed and unknown records.

## Reporting fixed before observations

Use score_v4's unchanged native answer-level detection: any completed valid C/U
means detected; full S or a complete empty report means clean; all-S partial or
execution/contract failure means unknown. Primary comparison uses all180 answers
per backend: correct decisions/180, complete/partial/error, decision coverage,
TP/FP/TN/FN and unknown positive/negative. Also show resolved-only precision,
recall/F1/accuracy, always with its denominator. Retain legacy whole-case-failure
F1 as historical comparison, not as a replacement for new partial-aware results.

No new author adjudication is assumed. Native FP is not adjudicated true FP.
RAGTruth spans do not supply full atomic-claim verdict/evidence gold. Report
claim completion only over existing known extracted targets and disclose unknown
totals; it is not factual recall. Report complete empty outputs separately.

Report per-task and per-generator descriptions and native positive prevalence.
For uncertainty retain pooled source-cluster percentile bootstrap (2000 draws,
seed20261024), keeping all6 responses and backends within each drawn source.
Primary pair: v4 minus minimal. Supplement all three backend pairs with the same
method; do not treat180 correlated answers as180 independent source draws. No
selection of favorable metrics or intervals after seeing outputs. V1 and this
new slice are different inputs, so their raw scores are not paired version gains.

Report per-backend actual calls, complete usage/unknown counts, latency mean/P95,
observed cache and standardized all-cache-miss costs. Fixed reference USD per
million: input0.30, cached input0.006, output1.20; not current pricing or billing.
Reasoning is included in completion tokens, never double-counted. Baseline's zero
model bill does not mean zero local compute. Record all3 backend order positions.
Latency/cache comparisons remain system observations, not isolated causal effects.

Independent audits verify source nonoverlap/adaptation, frozen imports, all540
unique results, no hidden reruns, cost accounting and recomputed confusion matrices.
Gemini High may critique the plan/results through headless CLI; its opinions do
not replace source checks, human adjudication or the frozen scoring rules.


# RAGTruth fresh-180 exposure audit

Evaluation bookkeeping only; no inference changes, model calls, or sample selection.

Pinned upstream: `c103204b9ce28d6bbad859304bf30de72b8ed8fe`; both raw-file hashes match the existing provenance.
Existing ledger/manifests: 63 source groups / 228 responses.
Known exposed: **70 source groups** / 236 explicitly observed responses; exclude every answer from each source group.
Additional input-only duplicate exclusions: 1; total excluded source groups: **71**.
Structured artifact exact-response scan: 1500 files; additional source groups beyond registry: [].

| Exposure | Response | Source | Match |
|---|---|---|---|
| 879 | 879 | 15739 | resolved_exact_unique_quote |
| 587 | 587 | 15690 | resolved_exact_unique_quote |
| 25 | 25 | 15596 | resolved_exact_unique_quote |
| 57 | 57 | 15601 | resolved_exact_unique_quote |
| 019a53c9-40e2-7f30-b43e-1abe372da81a | 3915 | 13823 | resolved_original_id_and_exact_full_response |
| 019a53c9-40da-72a1-83d1-1cb5e5f32707 | 4589 | 13935 | resolved_original_id_and_exact_full_response |
| 019a90f6-ccd9-71a1-bdcb-12506f672b7e | 5020 | 13492 | resolved_original_id_and_exact_full_response |
| 019a90f6-cd8d-74e3-80a2-bef412f29c25 | 3884 | 13818 | resolved_original_id_and_exact_full_response |

RT4CHART #57 was visible beside the three logged examples during the same-section mapping; conservatively excluded as a new audit-time exposure. Old exposure logs are preserved unchanged.

All named RAGTruth literature exposures are now mapped. RAGTruth++ mappings use metadata original_id plus exact complete response equality, not assumed UUID arithmetic or new labels.

| Task | Official test sources | Excluded | Remaining | Remaining groups with 6 good responses |
|---|---:|---:|---:|---:|
| Data2txt | 150 | 20 | 130 | 130 |
| QA | 150 | 21 | 129 | 111 |
| Summary | 150 | 27 | 123 | 123 |

Source aliases to exposed contexts: 0; duplicate full requests in six-good-answer groups: 1 source groups; duplicate candidate contexts removed: 0 source groups.

At least ten eligible-by-count source groups remain per task. Input-size eligibility remains the frozen sampler's mechanical responsibility. No unexcluded candidate response text or native labels were emitted; the adjacent paper example #57 is explicitly recorded and excluded.

The conclusion is disjointness from recorded project exposure, not a claim about unrecorded human exposure or foundation-model pretraining. Non-RAGTruth illustrations from other research sources remain outside this RAGTruth mapping.

Machine-readable exclusions, record hashes and per-source provenance: [exposure-audit.json](exposure-audit.json).
