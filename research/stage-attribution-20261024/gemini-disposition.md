# Gemini High design consultation: accepted and rejected advice

The CLI review succeeded with model gemini-4-argon-high / effort high. See
[raw response](gemini-design/response.md) and [validation](gemini-design/validation.json).
It saw the plan and protocol, not cases, gold references or model predictions.

Accepted: retain all 90 M3 opportunities including whole-batch failures; distinguish
common public validity from arm-specific internal schema; make the initial-M2
exclusion explicit; do not attribute prompt+schema differences solely to wording;
review changes include extra compute and are not equal-budget comparisons;
independent case count remains 20, with only 15 factual answers.

Rejected: its alleged blocker about per-claim state reset is factually incorrect.
Production grounding/verifiers_v4.py creates state inside the for-each-claim loop
in _batch, and the author explicitly capped C/U review per claim, not per case.
Sharing one dictionary across unrelated claims would suppress legitimate reviews
or raise the duplicate-review assertion. No such change was made.

Clarified rather than changed: public_valid may be true while the richer current
schema fails. These measure different contracts, so keeping them distinct is
intentional. Only validated rows enter review; all requested claims still enter
the fixed scoring denominator. The initial common exact-quote gate deliberately
excludes M2 repair from the controlled initial decision comparison.

Independent source review also caught a malformed-id TypeError in the experimental
validator before inference. A string-type guard was added; no semantic rules or
case-specific behavior changed.
