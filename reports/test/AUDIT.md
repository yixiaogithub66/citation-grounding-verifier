# Held-out prediction audit

This read-only inspection was performed after the frozen held-out run. It did not change gold annotations, model prompts or inference code. Case IDs below omit the common `cphos28-` prefix. Original predictions, reasons, citations and alignment details remain in `responses.jsonl` and `report.json`.

| Case | Observation | Interpretation |
| --- | --- | --- |
| `q5-02`, `q5-06` | Optimized splits the prose explanation and its equivalent formula into two claims; both are correctly marked contradicted. | Redundant decomposition lowers strict and approximate matching scores without showing two incorrect physics verdicts. |
| `q5-03` | Both LLMs split direction and formula. Minimal marks both contradicted; optimized marks direction unsupported because the context does not specify the sign of `eta`, while correctly rejecting the formula's sign. | The gold assumes a positive drag coefficient. This is a context/annotation boundary ambiguity as well as a granularity mismatch. |
| `q2-05` | Minimal computes the correct total with shorter wording, but cites only dimensionless `t_2 = 2.3024461`, omitting the conversion involving `sqrt(R/g)`. Optimized quotes the scaled duration. | The strict text mismatch is not a wrong sum. The minimal citation still lacks part of the evidence needed for the physical duration. |
| `q7-05` | Minimal omits introductory wording while retaining the correct worldline formula, conclusion and both source references. | Strict wording mismatch; approximate alignment succeeds. |
| `q2-06`, `q5-06` | Some predictions use shorter evidence than the gold anchor. | A gold-anchor containment miss is not automatically an invalid or insufficient citation. Read the actual quote. |

Both LLM methods pass all four separate edge cases. The optimized system sometimes preserves fuller wording and evidence, but these examples do not support claiming overall superiority to minimal on the held-out set.
