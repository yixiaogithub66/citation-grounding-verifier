# Fresh RAGTruth 180 selection and adaptation audit

Status: **PASS**; 35 checks, 0 failures.

Frozen seed: `ragtruth-fresh180-v2-20261024`. All 180 selected IDs and their ordering independently reproduce from source-group hash ranking after exclusions and unchanged input limits.

| Task | Official test groups | Frozen exclusions | Missing six good | Input limit | Eligible | Selected |
|---|---:|---:|---:|---:|---:|---:|
| QA | 150 | 21 | 18 | 0 | 111 | 10 |
| Summary | 150 | 27 | 0 | 0 | 123 | 10 |
| Data2txt | 150 | 20 | 0 | 0 | 130 | 10 |

The 71 frozen excluded source IDs contain 68 official test sources and 3 prior train smoke sources. Of the 68 test exclusions, 67 are exposed sources and 1 is an input-only duplicate source (12183). The legacy preparation field names all 68 `previously_exposed_source`; this audit preserves the frozen file and records the distinction.

Selected data: 30 sources × 6 good responses, 60 responses per task. Response IDs, complete request hashes and source-context hashes are unique at their appropriate units. All intersections with recorded source/response exposure and used request/context hashes are empty.

All source hashes and dataset bindings match. Answers are exact original strings without truncation. QA passages preserve all original characters; Summary retains its complete source block; Data2txt retains every JSON value under deterministic serialization. The existing QA question omission is preserved and explicitly documented.

Selected native label arrays equal upstream arrays and every label offset identifies the original substring. No native positive rates, label counts, or model results were reported.

The frozen runner passes only `VerificationRequest.from_dict(case["input"])` to `instance.verify(request)`. Each input has only `context_passages` and `generated_answer`. IDs, task/source/generator metadata and native gold are not passed to verification. This is static-path and serialized-input inspection, not a claim of packet interception.

No selected item was replaced and no frozen file, production code or model configuration was changed. See [selection-audit.json](selection-audit.json) for check results and evidence hashes.
