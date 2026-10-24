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
