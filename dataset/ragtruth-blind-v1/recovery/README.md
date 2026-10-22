# Byte-identical data, amended recorder freeze

The four prepared JSON/JSONL artifacts are byte-identical to their parent directory. This is the same 30-source, 180-response selection, with the same native labels and adapter/scorer code. No new sampling or annotation took place.

`freeze.json` binds the infrastructure-only recovery recorder. The original recorder stopped after 84 durable records; recovery preserves those exact bytes, including two model-output errors, and calls only the missing response/backend pairs. The original data and freeze remain in the parent directory.

Use this directory as `--data-dir` when reproducing or re-scoring `reports/ragtruth-blind-v1-recovery`, so the recorded recovery freeze can be resolved on another machine. See the [data description](../README.md), [protocol](../../../docs/RAGTRUTH_PROTOCOL.md), and [recovery audit](../../../reports/ragtruth-recorder-recovery/README.md).
