# Controlled-output AI review

Read only `blind-controlled.json` for results. Did not inspect the private key, original response journal, aggregate analysis, or infer arm identity. The reviewer is the **AI case author and packet-generator author**, not an independent human reviewer or the user's final adjudicator. The parent agent will cross-check this review.

All 24 records were structurally valid. I read each actual validated claim against its answer, expected fact and required qualifiers. All 24 expected-fact mapping slots were retained; all 12 pure-NF outputs had an empty claims array. No spurious claim or lost factual target was found under this pilot's selection-fidelity scope. All 24 records therefore receive semantic_complete=true. This is an arm-blinded controlled-result observation, not evidence of improvement over a baseline, natural-fault prevalence, or full M1 contract success.

The advice-only and question/refusal controls were assessed as non-factual; any row placed in claims would have been a selection error even if its wording remained an instruction. None did so. No output needed the scoped-assumption sensitivity flag. Had a record been technically invalid, its semantic metrics would be null rather than low/zero false-positive scores.

## Standalone naming limitations

Five outputs preserve the proposition and uniquely resolvable source attribution in answer context, but leave a subject pointer unresolved inside a standalone claim. Claim indices below are zero-based. These remain retained=true for selection fidelity, with explicit uncertainty notes; they are additional M1 self-containment diagnostics, not hidden successes on the full contract.

| review_id | claim index | remaining reference |
|---|---:|---|
| r-561528164bb2d521b62c4e67 | 1 | The cabinet's (Larchmere only named elsewhere) |
| r-57681caf1b4913014f887c98 | 1 | The cabinet's (Larchmere only named elsewhere) |
| r-6b4ccd378871cb8af6f44e4e | 1 | 该室 (若岚 only named elsewhere) |
| r-cfa25f5284870814074ad3e0 | 1 | 该室 (若岚 only named elsewhere) |
| r-ec1d863b8712705e7e91b904 | 1 | Its technician log (Bracken only named elsewhere) |

The parent confirmed the frozen pilot's entity-preservation criterion permits unique resolution for the selection score and requires reporting standalone naming separately. No prompt, fixture or label was changed to obtain these judgments. The review JSON contains 24 schema-conforming records, complete expected-fact mappings and in-range claim indices.
