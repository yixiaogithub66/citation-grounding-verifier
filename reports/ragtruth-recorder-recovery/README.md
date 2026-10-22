# Recorder recovery amendment

The first RAGTruth run stopped with a `PermissionError` after durably saving 84 unique response/backend records. Its final progress status is `failed`; there are no malformed journal lines or duplicate pairs. Two of those records are model-output contract failures. Their results remain unchanged and must not be retried for a better outcome.

The exception's exact OS operation was not logged by the original recorder. The infrastructure amendment adds bounded retries for transient permission errors when publishing progress snapshots, and an explicit recovery path. It changes neither the inference implementations nor the dataset, prompts, native scoring semantics, or selection.

Recovery uses a new output directory and a separately frozen recorder. The four prepared data files in `dataset/ragtruth-blind-v1/recovery` are byte-identical to the original files. The original freeze and partial run are preserved. The recovered journal starts with every original journal record, including failures; only the 456 missing response/backend pairs are eligible for new calls. Recovery is recorded as local re-exposure, not a new independent blind sample.

No native test gold had been scored or displayed when the recorder amendment was made. Model-output contents were not used to design it. Synthetic tests exercise interrupted-run recovery, exact pair reuse, configuration compatibility, and transient filesystem errors.

`amendment.json` preserves the original progress, journal SHA-256, and before-change recorder hash. Any archived original recorder is authentic only if its SHA-256 matches that recorded hash. The original records remain in `reports/ragtruth-blind-v1`; the completed recovered run is written to `reports/ragtruth-blind-v1-recovery`.
