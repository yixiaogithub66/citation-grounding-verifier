# Coverage diagnostic materials — independent AI draft

Prepared on 2026-10-24. These are newly written fictional answers and a provisional semantic inventory, not author-approved gold labels or truth judgments. The drafter read only the task requirements, `AGENTS.md`, and `docs/V4_DECISIONS.md`; no candidate implementation or prompt, old benchmark case body, or prior experimental output was inspected. No external model/API invocation was used for preparation.

Five domains are used: planetarium projection logs, ceramics kilns, puzzle exhibitions, campus parcel lockers, and geological specimen catalogues. There are four cases per domain: two factual/mixed cases, one pure-advice/question case, and one multi-fact case with repetition, reference resolution, or a conditional rule. Each domain has two Chinese and two English cases. All named places, identifiers, measurements, and records are fictional.

The fact inventories follow ordinary assertion content. Advice is non-factual, while its asserted premises are included. A catalogue or log assertion retains its recorded scope. Rules with explicit applicability conditions are factual descriptions of a rule, not claims that an operation was performed. Pure hypothetical scenarios and performative refusals are excluded. The examples do not require retrieval or factual truth verification.

## Case map

| Cases | Domain | Ordinary factual/mixed | Advice with factual premise | Pure NF | Repetition/reference/condition |
| --- | --- | --- | --- | --- | --- |
| cp001–cp004 | Planetarium projection | cp001: zh, 3 facts | cp002: en, 2 facts | cp003: zh | cp004: en, 3 facts |
| cp005–cp008 | Ceramics kiln | cp005: en, 4 facts | cp006: zh, 3 facts | cp007: en | cp008: zh, 2 facts |
| cp009–cp012 | Puzzle exhibition | cp009: zh, 2 facts | cp010: en, 4 facts | cp011: zh | cp012: en, 3 facts |
| cp013–cp016 | Campus parcel lockers | cp013: en, 3 facts | cp014: zh, 2 facts | cp015: en | cp016: zh, 4 facts |
| cp017–cp020 | Geological catalogue | cp017: zh, 4 facts | cp018: en, 3 facts | cp019: zh | cp020: en, 2 facts |

## Occurrence and reference semantics

The source quotes are exact substrings of the corresponding answer. They are not implicit fuzzy matches and must not be rewritten into near-matching spans. Quotes intentionally keep local subjects or discourse references where practical. A quote that begins with a pronoun requires the named antecedent recorded in `required_semantic_elements`; string containment alone cannot certify semantic fidelity.

- cp004/f1: “horizontal offset is -1.25 mm” occurs twice within one sentence. Both occurrences refer to Projector L4 and express the same offset. The full sentence is the single retained quote; it covers both occurrences under the documented within-sentence redundancy rule. cp004/f3 resolves “It” to the calibration entry, not the projector.
- cp008/f1: the card's rule applies only to pieces tagged “薄片”; it does not assert a completed heating event. cp008/f2 covers both same-sentence expressions of the red piece's single tag. “它” refers to that red piece. Applying the rule and predicting a completed event are different operations; no performed event is included in the inventory.
- cp012/f1: the numeral expressed as “four wooden tokens” and “wooden-token count is four” is a same-sentence equivalent restatement. cp012/f2 resolves “Its” to cabinet R and preserves the code's leading zero. cp012/f3 describes catalogue order, not room layout.
- cp016/f1: the exact substring “A 柜的空闲格口为 9 个” has two ordered occurrences within the same sentence, beginning with the first and following “也就是说” for the second. They add no distinct predicate or referent; the full sentence is retained as one source quote. cp016/f3 is a log-status assertion, whereas cp016/f4 is its separately asserted timestamp. Both use A 柜; neither transfers to B 柜.
- cp020/f1: assignment is a rule with a tag condition, not an observation of storage. cp020/f2 contains two same-sentence occurrences of V-2's tagging fact. “that tag” and “layered” share the same referent.
- The remaining facts each have one intended source-quote occurrence. No cross-sentence assertions were silently collapsed. Generic advice can repeat themes without adding facts, but such advice is not counted as coverage of an asserted fact.

## Coverage interpretation and limits

Expected counts vary from two to four factual units; the set does not encode a fixed two-fact shortcut. Inventory entries are coverage targets, not a demand that an extractor use identical wording. If an output combines independent facts, coverage of their elements and atomicity must be assessed separately. A fact should not be credited merely because an unrelated output happens to contain the same number, identifier, or quoted substring.

All expected facts, forbidden assertions, and domain/case labels are evaluation-side material. They must never be inserted into inference prompts or used to choose runtime branches, parameters, or semantic exceptions. The cases remain a small AI-drafted diagnostic collection with varied wording; passing it does not establish generalization. Once results or contents are used to choose or revise a method, the collection must be marked exposed development material.

Mechanical validation is limited to JSON shape, exact quote containment, unique IDs, length, and declared distribution. It does not establish semantic correctness or author acceptance. Any later author adjudication must remain a separate version without overwriting this provenance.

## Completed mechanical checks

- JSON parses; the declared case and fact fields match the requested schema; no `controlled_seeds` field is present.
- 20 unique cases, 5 domains × 4 cases, 10 Chinese and 10 English answers. Each domain has two answers in each language and one pure-NF case.
- 15 factual/mixed answers, 5 pure-NF answers, and 44 expected fact entries. Every factual answer has 2–4 expected facts; every pure-NF answer has none.
- All 44 `source_quote` values occur exactly once as full substrings in their own answers. Redundant subspans inside those full quotes have the occurrence semantics stated above.
- Answer lengths are 92–798 characters, including spaces and newlines. All are within 80–1100 and below the 1200-character block ceiling. Eleven answers are within 350–1000 characters, including nine factual/mixed answers.

| Case | Characters | Case | Characters |
| --- | ---: | --- | ---: |
| cp001 | 368 | cp011 | 113 |
| cp002 | 703 | cp012 | 256 |
| cp003 | 107 | cp013 | 745 |
| cp004 | 220 | cp014 | 388 |
| cp005 | 798 | cp015 | 366 |
| cp006 | 383 | cp016 | 92 |
| cp007 | 380 | cp017 | 179 |
| cp008 | 96 | cp018 | 672 |
| cp009 | 391 | cp019 | 112 |
| cp010 | 712 | cp020 | 272 |

Character counts use PowerShell/.NET string length; all present characters are in the Basic Multilingual Plane, so these equal Unicode code-point counts. This count is not a tokenizer estimate.

## Pre-inference ambiguity review

Before any real model run, an AI critic flagged cp005's original “Its/its” after “Batch Kestrel used kiln 3” as potentially referring either to the batch or the kiln. Those two subjects were made explicit as “Batch Kestrel's” and “the batch's”, with corresponding exact source quotes and semantic elements updated. No fact meaning, count, or other answer was changed. This is AI pre-review, not author adjudication.

Within-sentence faithful repetitions in cp004/cp008/cp012/cp016/cp020 may be represented once, but a faithful repeated extraction is not by itself a factual false positive. Record redundant extraction diagnostically; do not penalize it as non-factual content or a changed meaning solely because it repeats a target. The inventories state distinct semantic targets rather than mandating the extractor's output count.
