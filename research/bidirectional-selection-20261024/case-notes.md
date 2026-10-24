# New selection-fidelity materials, 2026-10-24

These are **AI-drafted fictional diagnostic materials, without author final review**. They are not RAGTruth records, a new blind benchmark, or a substitute for independent human gold.

The case-author subagent read only AGENTS.md, docs/V4_DECISIONS.md, and the current extract_claims structural validator. It did not read the candidate prompt, any prior concrete case bodies, benchmark text, or candidate/baseline outputs, and made no model calls. The materials were authored from the task distinction between asserted propositions and instructions/questions/suppositions.

The single cases.json contains `cases` and `controlled_seeds`. In natural trials only `generated_answer` is inference input. In controlled trials resolve `case_id` to that answer and send only the answer and `draft`; family, language, kind, ids, expected facts, forbidden assertions and provenance are scorer-only. Do not serialize the whole case object to a model.

## Composition

Four fictional domain families each contain four conditions:

| Family | Ordinary factual | Advice with factual premises | Pure advice | Other non-assertive control |
|---|---|---|---|---|
| nursery | sel-01 (zh) | sel-02 (en) | sel-03 (zh) | sel-04 (en; explicitly imaginary exercise) |
| sound_archive | sel-05 (en) | sel-06 (zh) | sel-07 (en) | sel-08 (zh; questions) |
| ferry_service | sel-09 (zh) | sel-10 (en) | sel-11 (zh) | sel-12 (en; performative refusal and question) |
| textile_lab | sel-13 (en) | sel-14 (zh) | sel-15 (en) | sel-16 (zh; tentative design and questions) |

There are eight factual answers with exactly two expected assertions each, plus eight pure non-factual answers. Each family has two Chinese and two English answers; domain is not confounded completely with language. Six answers have 300–900 characters (four English and two Chinese); every answer is shorter than the current 1200-character chunk limit. These materials probe selection in a single chunk, not cross-chunk coreference.

Expected facts specify exact source substrings and semantic elements that must remain present: subject, relation, polarity, condition, modality, numerical scope and source attribution where applicable. A necessary condition must not become sufficient; a stated limit must not become a measured outcome. The fictional supposition in sel-04 is an instruction for an imagined exercise, not a report about actual seedlings. The refusal in sel-12 is performative and provides no assertion about a vessel's properties or a real schedule. These are intentional non-assertive controls.

`forbidden_assertions` gives illustrative semantic errors for scoring, not an exhaustive phrase blacklist. Semantic equivalents of an expected fact are valid. Source-span overlap, exact word matching or lexical coverage alone cannot establish fidelity. Invented assertions not listed there must still be counted; factless output must not earn perfect precision by hiding recall failures.

## Controlled drafts

The twelve controlled drafts are **deliberate injected faults**, not observed failures or an estimate of natural error frequency:

- Four omission seeds use the mixed-advice cases. Each retains one correct factual premise and places the other premise in an excluded non-factual segment. The missing target alternates between first and second assertions.
- Four spurious seeds use pure-advice cases. Each promotes one recommendation into an asserted existing arrangement/action. It preserves the underlying topic and avoids adding a new causal benefit, so the repair must distinguish advice from assertion rather than merely spot an unrelated hallucinated causal claim.
- Four clean seeds cover two factual answers and two pure non-factual controls. They measure unwanted edits or newly invented/missed facts.

No seed tests a joint omission and spurious fault in the same draft; repair behavior for simultaneous faults remains unmeasured. Controlled and natural outcomes must be reported separately. Natural and controlled rows reuse some answers, so they are not independent additional cases and must not be pooled into a 28-case generalization estimate.

## Checks performed before delivery

- Exactly 16 unique natural cases, 16 unique expected fact ids, 12 unique controlled seed ids.
- Eight Chinese / eight English; four cases and two languages in each family.
- Exactly eight factual and eight pure non-factual answers.
- Every expected source_quote occurs exactly once in its answer.
- Every controlled draft passes the current `grounding.verifiers_v4.extract_claims(..., max_claims=64)` exact-span, source-order and complete lexical-coverage checks.
- All controlled seed metadata stays outside `draft`; all draft rows use the current schema.
- All lengths are below 1200 characters; no sample truncation or benchmark-driven selection was used.

These checks establish data shape and provenance, not semantic gold correctness. Main-agent review remains appropriate; no author approval is implied. The current fixture does not measure downstream evidence retrieval, verification accuracy, multi-chunk repair, real-world fault prevalence, or statistical generalization. Freeze the candidate independently before exposing the body of this file or the case file to the implementation path; any future edits after results are seen must mark this set exposed.

## Machine-checked summary

```json
{
  "cases": 16,
  "languages": {
    "zh": 8,
    "en": 8
  },
  "families": {
    "nursery": 4,
    "sound_archive": 4,
    "ferry_service": 4,
    "textile_lab": 4
  },
  "fact_cases": 8,
  "expected_facts": 16,
  "pure_nf_cases": 8,
  "long_cases_300_to_900_chars": [
    "sel-02",
    "sel-03",
    "sel-07",
    "sel-10",
    "sel-15",
    "sel-16"
  ],
  "length_range": [
    48,
    567
  ],
  "controlled_seeds": {
    "omission": 4,
    "spurious": 4,
    "clean": 4
  }
}
```

cases.json SHA-256: `0188d3084786c4dc654fc311bd8a522aa2fe5e43e2a2bf85a8cad973a60244cc`.

## Pre-inference cross-review correction

Before any real model run, cross-review found that the second claim in `inject-clean-02` retained the pronoun “Its” and was not independently self-contained. Only that draft claim_text was changed to explicitly name the Bracken sound archive technician log. The answer, source_span, expected facts, and every other sample remained unchanged. All 12 controlled drafts were validated again with the current extract_claims validator. This is a contract-level coreference correction made before observing model outputs.
