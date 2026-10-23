# RAGTruth exploratory 30: exposure audit

Audit date: 2026-10-23, Asia/Shanghai. This document records preselection exposure evidence, not evaluation results. The user authorized a separate 30-record exploratory evaluation; this is not the formal 180-record blind-v2 acceptance run.

[exposure-audit.json](exposure-audit.json) records 9 canonical exposure ledgers, their union of **33 source IDs and 198 response IDs**, and hashes of all evidence. The sources comprise the 30 old blind-v1 test sources and three train-smoke sources (`12075`, `14808`, `15196`). All recorded smoke sources have explicit mappings. A metadata-only check of configuration, preparation and freeze files under `results`, `reports`, `dataset` and `tmp` found no additional source IDs outside this union. This local check cannot establish exposure outside these records.

The cached upstream revision is `c103204b9ce28d6bbad859304bf30de72b8ed8fe`. Opaque SHA-256 checks of `source_info.jsonl`, `response.jsonl` and `provenance.json` match the original preparation. The audit did not read raw source/response text or new native labels, open new web pages or make model calls. The 13 hashed evidence files are the 9 canonical ledgers, old v1 manifest and preparation, and the two existing literature-exposure records.

Two literature exposures remain unmapped: the RT4CHART paper's displayed IDs `879`, `587`, `25`, whose identifier namespace is unknown, and four UUID candidates observed in a RAGTruth++ search snippet. Their exact existing provenance is copied into the JSON. Neither identifier set is assumed to equal original RAGTruth response/source IDs. No new lookup was performed, and no resolution is claimed.

The new selection must exclude all 33 registered sources and freeze inference, configuration and sampling before selection. It may be described as disjoint from known recorded evaluation sources; it **cannot be certified wholly untouched**, and is not a formal blind-v2 confirmation. New sampled source groups must be registered before evaluation and excluded from subsequent unseen selections. Response IDs and exposure metadata are audit bookkeeping only; they must not enter inference prompts, rules or settings.

Use the existing deterministic native adapter and keep native labels separate from verifier inputs. RAGTruth's native annotations support response-level binary hallucination detection, not atomic S/C/U accuracy. This 30-record slice is a different sample from the prior 180 and must not be described as a paired before/after comparison.
