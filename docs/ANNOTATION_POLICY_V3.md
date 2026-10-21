# Annotation policy for v3 pilot and confirmation cases

This policy refines proposition boundaries for new cases. It does not retrospectively change the released CPHOS28 v1.2 labels or its historical scores.

## Claims

- Preserve an answer sentence, including its punctuation, as one claim when it expresses one proposition.
- Keep a formula and its direct prose restatement together only when they express the same quantity, value, sign, conditions and scope. A connector such as "in other words" does not establish equivalence by itself.
- Split independent propositions that could receive different judgments. If a sentence's prose and formula disagree, annotate them separately, even when joined by a restatement connector.
- Preserve conditions, qualifiers, signs, units and shared subjects. Only add a shared subject when necessary to make a split claim standalone; do not silently correct its assertion.
- Coordinated subjects sharing one predicate and conditions may remain one joint claim. Supporting that claim requires support for every subject. Different predicates or conditions require separate claims.
- A conclusion requiring several evidence passages remains one claim when it expresses one proposition. A calculation's introductory operation stays attached to its result.
- Greetings, thanks and requests without factual assertions yield no claims. Account for all factual content, including false or unsupported-looking assertions.

## Verdicts and evidence

- `SUPPORTED`: the supplied passages jointly entail the complete claim. Short arithmetic and algebra based on explicit premises are allowed; state the derivation and cite every necessary premise.
- `CONTRADICTED`: supplied evidence establishes an incompatible fact for the same entity, conditions and scope. Explain the conflicting value, sign, negation, condition or derived relationship.
- `UNSUPPORTED`: evidence is absent or insufficient. Do not fill missing parameter domains, nonzero assumptions or customary physical conventions from outside knowledge. An unresolved conflict within the source also warrants an explanation of uncertainty.
- Supported and contradicted claims require exact verbatim quotes and valid passage indices. Unsupported claims have no public citations and no acceptable evidence sets.
- Record `acceptable_evidence_sets` for alternate sufficient evidence and `required_passage_indices` for indispensable multi-passage premises. Citation validity alone is not semantic sufficiency.
- Preserve a verbatim `answer_quote` from the answer for each gold claim. New gold wording follows the claim rules above; do not select it after inspecting model predictions.

## Source and review record

For each new excerpt record its source PDF, page numbers, equation/location and linear-text normalization. Inspect the relevant page visually for signs, indices and conditions. Report ambiguities or suspected source errors; do not silently repair them. Keep original data and model results when a later adjudication changes an interpretation.

AI review and human review are distinct statuses. The author reviews the three pilot examples and this policy before formal confirmation construction. The formal set consists of new cases, excluding the pilots, and remains labeled AI-assisted unless separately reviewed by the author. No approval receipt may be generated before the author actually confirms it.
