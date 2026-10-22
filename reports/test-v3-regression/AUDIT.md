# Frozen v3 regression on previously inspected test cases

This is a regression run, not an unseen test or formal confirmation. The old test was already used to design v3. Inference code and scoring were frozen before this run, and no prompts or labels were changed after reading its predictions.

All 24 requests returned valid reports. Strict joint F1 is 58/67 = 0.86567164: 29 correct gold claims, 35 predicted claims, 32 gold claims, 6 extras and 3 missing. Whole-case correctness is 21/24. The same three historical granularity mismatches remain. Average latency was 7.3858 seconds and standardized estimated cost was USD 0.043686744.

| Case | What v3 actually did | Remaining issue |
| --- | --- | --- |
| `q5-02` | Detected a restatement candidate and made a merge call. The model kept the radius-power statement separate from the full torque formula because the formula contains additional coefficient, sign and vector information. Both resulting claims were contradicted. | Strict equivalence is stronger than the historical annotation's grouping of a property with its full formula. The two predictions still fail to align with one gold claim. |
| `q5-06` | Detected the denominator/formula candidate and made a merge call. The model kept them separate because the complete velocity formula asserts more than the denominator alone. | Candidate detection worked, but the semantic decision rejected the desired merge; the historical over-splitting remains. |
| `q5-03` | Split direction from formula, marking direction unsupported because the sign of eta was not explicit and marking the plus-sign formula contradicted. | The known parameter-domain and annotation-granularity ambiguity remains for author adjudication. |

There were two live merge calls, four keep decisions, zero merged groups and zero contradiction-review calls. The new merge stage did not repair the targeted historical mismatches in this run. This must not be presented as a successful optimization merely because the new components ran or the development set remained perfect.

The unresolved policy distinction is whether an original sentence's consistent, redundant description of one property may be grouped with the fuller formula, despite not being logically equivalent to the full formula. The supplied v3 policy currently requires equivalence and independent propositions with different possible verdicts must split. Broadening that rule is an author annotation-policy decision, not a silent prompt tweak for these test cases. Any future policy/implementation change must be versioned and frozen before constructing or evaluating formal confirmation data. Historical gold and results stay intact.

The strict F1 equals the historical v2 test score, but these runs occurred at different times and did not contemporaneously rerun the other backends. This is descriptive regression evidence; the planned same-set four-backend confirmation remains pending author pilot review.
