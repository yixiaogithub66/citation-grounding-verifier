# RAGTruth first project-held-out sample

This fixed sample contains 180 unchanged generated answers from 30 source groups: ten QA, ten Summary, and ten Data2txt sources, with all six quality-good responses retained for each selected source. The upstream test split contains 450 sources and 2,700 responses, of which 2,675 carry `quality=good`. There were no input-size source exclusions in this preparation.

Selection is label-independent: rank source IDs by the SHA-256 of `ragtruth-blind-v1-20261022|task_type|source_id`, then select the first ten per task. Native span labels are validated only after selection. This sample is not 180 statistically independent sources; source-cluster intervals use the 30 source groups.

Files:

- `inputs.jsonl`: response ID and the exact two-field service request; no native labels.
- `manifest.jsonl`: source, task, generator, input hash, and deterministic mapping provenance.
- `native_gold.jsonl`: original hallucination annotations, including flags/comments, kept separate from inference.
- `preparation.json`: selection policy, eligibility counts, source IDs, pinned upstream hashes, and artifact hashes.
- `freeze.json`: inference, evaluation, settings, and data bindings created before the formal run.
- `UPSTREAM_LICENSE`: the upstream repository's license, with authorship retained.

This is a native response-level hallucination benchmark. It has no complete atomic-claim gold and no source-citation gold. In particular, `labels[].text` is a problematic span in the generated answer, not a quote from the source. No SUPPORTED claims or evidence labels have been invented to fit the older CPHOS evaluation schema.

QA evidence comes only from the original retrieved passages; the original question is not promoted to evidence. Summary evidence remains one exact source string. Data2txt evidence uses deterministic JSON serialization, preserving `null` and booleans. Every generated answer remains byte-equivalent after UTF-8 encoding to the original decoded response string, and annotation positions use Python character `[start,end)` intervals.

The [protocol](../../docs/RAGTRUTH_PROTOCOL.md) records the scope, differences from upstream detector inputs, and limits of interpretation. The three implementations were frozen in [the initial manifest](../../reports/ragtruth-inference-freeze.json) before downloading the raw data. This sample and its outputs must not be relabeled or used to retune the originally reported implementation.

Upstream: [ParticleMedia/RAGTruth](https://github.com/ParticleMedia/RAGTruth/tree/c103204b9ce28d6bbad859304bf30de72b8ed8fe), revision `c103204b9ce28d6bbad859304bf30de72b8ed8fe`. Cite Cheng Niu et al., *RAGTruth: A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models*, ACL 2024, [DOI:10.18653/v1/2024.acl-long.585](https://aclanthology.org/2024.acl-long.585/). Source material is retained for evaluation and is not authored by this project.
