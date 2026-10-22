# RAGTruth native blind evaluation

This benchmark measures the existing service on externally generated, human-annotated answers. It does not turn RAGTruth hallucination spans into invented atomic-claim or source-evidence gold. Historical CPHOS results and inference code remain unchanged.

## Registered first-run scope

The user selected a stratified first evaluation rather than the full test set: ten source IDs from each of `QA`, `Summary`, and `Data2txt`, retaining every eligible response for each selected source (approximately 180 answers). The three primary backends are `baseline`, `minimal`, and `optimized-v3` (the current v3.1 prompt). No historical backend is substituted after seeing outcomes.

The upstream repository is https://github.com/ParticleMedia/RAGTruth at revision `c103204b9ce28d6bbad859304bf30de72b8ed8fe`. Both original JSONL files are pinned by SHA-256 and Git blob identity in the download provenance. The current implementation was separately frozen in `reports/ragtruth-inference-freeze.json` before raw data was downloaded. Adapter and scorer development uses synthetic fixtures and official training data; test records are processed mechanically without displaying their text or labels during implementation.

Sampling uses official `split=test`, `quality=good`, and source-level grouping. Good quality does not mean hallucination-free. Source IDs are ranked within task by the SHA-256 of `ragtruth-blind-v1-20261022|task_type|source_id`; the first ten eligible sources per task are selected. Selection does not use hallucination labels, model predictions, or scores. All quality-good responses associated with a source stay together. Sources with input-limit violations are excluded as a group before selection and recorded; no input or answer is silently truncated. Source IDs crossing official splits are rejected. Invalid selected annotation offsets stop preparation rather than being silently repaired or removed.

## Input conversion

Only `context_passages` and `generated_answer` reach a verifier. The latter is the unchanged upstream `response` string.

- QA uses the existing `source_info.passages`. Unambiguous numbered passage boundaries may become separate passages, preserving all characters and recording source offsets; otherwise the entire block remains one passage. The upstream question is retained in the original upstream snapshot, not added as factual evidence. This is a known difference from the official detector, which also receives the question; short or question-dependent answers require care when interpreting the result.
- Summary uses the unchanged source string as one passage.
- Data2txt uses a deterministic JSON serialization with sorted keys, indentation, Unicode text, and JSON boolean/null values. Citations refer to this frozen rendered evidence. Values are not expanded into generated prose or inferred facts. This serialization differs from the Python dictionary string representation in the upstream baseline and is recorded explicitly.

Metadata, generator identity, quality, native labels, annotation comments, and gold spans are never embedded in evidence. The original span offsets are Python Unicode character intervals `[start,end)` in the unchanged answer, not offsets in source passages. Every selected span must satisfy `response[start:end] == text`.

The adapter checks the service's character/claim-independent input contract and the HTTP JSON body size in advance. Provider token-limit or output-limit failures still count as execution failures; character limits cannot guarantee a model's token budget. The runner uses the same backend factory as the HTTP service and validates the same public response contract.

## Native outcome and missing capabilities

The response-level gold is `len(labels) > 0`, matching the released baseline evaluation code. All original labels are retained, including `implicit_true` and `due_to_null`. The prediction is positive if a structurally valid response contains at least one `CONTRADICTED` or `UNSUPPORTED` claim. A valid empty claim list is negative under this native projection, but nonempty answers with empty predictions are reported separately: response-level detection does not verify extraction coverage.

Report confusion counts and precision/recall/F1 on valid outputs, with their valid-output denominator. API, timeout, parsing, schema, and citation-contract failures remain in the full evaluation population. End-to-end accuracy counts each failed case as incorrect. A separately named pessimistic F1 bound assigns positive failures to false negatives and negative failures to false positives; it is not the official score. Report both views and the failure rate, never silently treat failures as clean answers.

Report task and answer-generator breakdowns. Bootstrap uncertainty resamples entire source groups from the pooled source population, not individual correlated answers; this is not a task-stratified bootstrap and does not isolate model/API variation; the paired optimized-minus-minimal comparison uses the same resampled source groups. The first run has only ten sources per task, so its intervals and descriptive results cannot establish universal superiority.

The three-class counts are output distributions, not three-class accuracy. Exact-source citation validity is a structural diagnostic, not evidence sufficiency. Native span localization, semantic claim coverage, atomic-claim S/C/U accuracy, and semantic citation accuracy are **not evaluated** in this first run. Public service claims can be paraphrased, and not all backends expose answer offsets; assigning whole claim spans or using gold positions to locate predictions would distort a native span comparison. The historical exact-text claim F1 is not used for this benchmark.

Full Gist evaluation requires a separately selected and independently annotated subset: all atomic claims, answer locations, three-way verdicts, sufficient source quotes, and adjudication. Unmarked answer text is not automatically SUPPORTED gold. In particular, RAGTruth's Subtle Conflict category can include semantic shifts that need fresh C/U adjudication under the Gist's direct-refutation requirement. A hallucinated answer span is never a source citation.

## Freeze, execution, and scoring

Before formal inference, bind the prepared inputs, original labels, selection manifest, adapter, native scorer, runner, inference files, generation settings, concurrency, and seed in a no-overwrite freeze manifest. Labels are hashed as opaque bytes at freeze time and are not parsed by the inference runner. Predictions are saved first; a separate scoring command then joins them to native gold.

`minimal` and `optimized-v3` use `deepseek-flash`, thinking enabled, and the saved common generation settings. The lexical `baseline` runs locally with no model requests or API tokens. There are four concurrent cases; backend order within each case is reproducibly shuffled. Each call has its own verifier instance. Additional stages and repairs remain part of each backend and are included in tokens, latency, and cost. This is a comparison of the current complete systems, not a cost-matched architecture ablation.

The same reference tariff as the existing project reports may be used: USD 0.30/million uncached input tokens, USD 0.006/million cached input tokens, and USD 1.20/million output tokens. These are standardized estimates, not a claim about current provider prices or actual billing. Missing usage remains unknown.

Write prediction records durably as each backend finishes and preserve failures and partial runs. Source/response exposure is registered before model calls. Repeats and interrupted-run recovery require an explicit replicate flag and a new output directory. A local ledger cannot observe other workspaces or establish that a public corpus was absent from a foundation model's pretraining. Describe this as a project-held-out evaluation, not proof of universal model-level blindness.

After the first test results are visible, retain the original code, labels, and output artifacts. Any later system changes and repeated evaluations are separately named regressions/replications. Do not select a favorable retry or relabel an error to improve the original result.

## Recorded infrastructure amendment

The original recorder stopped with a local `PermissionError` after 84 durable records, including two model-output failures. Before any native test gold was scored or displayed, the recorder alone was amended to tolerate transient progress-file replacement failures and resume missing pairs. All 84 original journal records, including failures, are copied byte-for-byte; only missing pairs receive new calls. The original inference code, native scorer, inputs, labels, settings, order policy, and concurrency remain identical.

The original freeze and partial outputs are preserved. `dataset/ragtruth-blind-v1/recovery` contains byte-identical copies of the four prepared files and a new recorder freeze. `reports/ragtruth-blind-v1-recovery` is the recovered complete-run destination. The original recorder source is archived and matches its pre-amendment hash. See [the amendment record](../reports/ragtruth-recorder-recovery/README.md), its before/after hashes, and patch. Recovery is local re-exposure for bookkeeping, not a newly independent sample or favorable rerun.

## Commands

Fetch the pinned upstream files without displaying any records:

```powershell
python scripts/fetch_ragtruth.py --output-dir tmp/ragtruth-upstream
```

The committed `dataset/ragtruth-blind-v1` already contains the frozen first selection. For a new preparation in a different, nonexistent directory, use:

```powershell
python scripts/ragtruth_data.py --raw-dir tmp/ragtruth-upstream --output-dir results/ragtruth-prepared-copy --split test --sources-per-task 10
```

`--sources-per-task 0` selects all eligible sources. It does not create a new unseen test set; overlapping sources and responses are tracked by the local exposure ledger.

The original first-run freeze is created once, after tests and train smoke checks:

```powershell
python scripts/benchmark_ragtruth.py freeze --data-dir dataset/ragtruth-blind-v1 --thinking enabled --workers 4 --price-input 0.30 --price-cached-input 0.006 --price-output 1.20
```

Do not recreate or overwrite an existing freeze. To reproduce inference with the committed recovery manifest and matching recorded settings, use a fresh output directory:

```powershell
python scripts/benchmark_ragtruth.py run --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/ragtruth-reproduction --thinking enabled --workers 4
```

If any selected source has already been run in the current workspace, add `--replicate`. A clean clone lacks the local ledger, but repeating a published experiment is still a reproduction. The freeze verifies the code, prepared data, Python version, and generation settings; mismatches stop before model calls. Save a separately named freeze for an explicitly different runtime rather than changing the original.

Score the completed saved predictions without additional API calls:

```powershell
python scripts/ragtruth_score.py --run-dir results/ragtruth-reproduction --data-dir dataset/ragtruth-blind-v1/recovery --bootstrap-samples 2000 --seed 20261022
```

For an offline re-score of the published run, set `--run-dir reports/ragtruth-blind-v1-recovery --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/ragtruth-rescore`. Existing reports are preserved. Generation is the only step that needs an API key; decoding, preparation, testing, and re-scoring do not.

## References

- RAGTruth data schema and dataset: https://github.com/ParticleMedia/RAGTruth/tree/c103204b9ce28d6bbad859304bf30de72b8ed8fe
- Native preparation and quality filtering: https://github.com/ParticleMedia/RAGTruth/blob/c103204b9ce28d6bbad859304bf30de72b8ed8fe/baseline/prepare_dataset.py
- Released response-level scoring: https://github.com/ParticleMedia/RAGTruth/blob/c103204b9ce28d6bbad859304bf30de72b8ed8fe/baseline/predict_and_evaluate.py
- Niu et al., ACL 2024, RAGTruth: A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models: https://aclanthology.org/2024.acl-long.585/

Credit the RAGTruth authors and retain upstream licensing/provenance. The original source corpora and their text are not authored by this project.
