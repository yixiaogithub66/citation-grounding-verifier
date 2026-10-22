# Grounding v3.1: design and confirmation protocol

This iteration follows the author's updated CPHOS28 plan dated 2026-10-22. The historical `grounding-v2` test is preserved. It motivated v3's design, so those old test cases are now diagnostic/regression material for v3, not an unseen evaluation.

## Scope and controls

`minimal` retains its original single-call prompt and implementation. `optimized-v2` retains the original inference files from commit `cfadeca`; their exact byte hashes are checked against `grounding/frozen_v2.json`. `optimized-v3` runs the current `grounding-v3.1` implementation described below. The compatibility name `optimized` selects that same backend. Neither the original 46 cases/58 gold claims nor the scoring rules are changed to improve a score.

The historical strict correct count of 29 for each LLM means 29 text-aligned, correctly labeled gold claims. It does not isolate semantic judgment accuracy. The old result is v2, not v1. All performance improvements in this iteration must be observed, not assumed.

## Extraction and merging

The extraction rule preserves the full original sentence when it expresses one proposition. A formula and its equivalent prose can remain one proposition when the quantity, value, sign, conditions and scope agree. V3.1 also permits a consistent redundant property description in the same sentence as a fuller formula, retaining the complete formula even when the property does not entail all of it. A sentence containing independent propositions with different truth values must still split. Requiring multiple source passages does not itself justify splitting a single conclusion.

Merging takes place before verification and receives only the answer and extracted claims, never source context or gold labels. Deterministic similarity and explicit restatement connectors select candidates; they do not prove equivalence. One batched model call decides which candidates satisfy the author-approved grouping rule, defaulting to separate claims when uncertain. In v3.1 this includes consistent redundant property descriptions in the same sentence as their complete formula: the formula may contain more information, but the prose cannot add a new assertion or conflict with it. This is annotation grouping, not a claim of logical equivalence. Reconstructed text comes from the original answer. A merge must preserve coverage and cannot absorb unrelated clauses merely because they share a sentence. Shared subjects and conditions must survive splitting.

The merge decision records `equivalent`, `same_sentence_redundancy` or `distinct`. The redundancy exception does not apply across sentences, to conflicting prose/formulas, or to a merely weaker inequality. Identical extracted wording cannot bypass preservation of the fuller formula or absorb an unmerged third assertion. Verification and contradiction-review semantics are unchanged from the initial v3; the v3.1 policy change concerns extraction and grouping.

## Contradiction evidence review

Initial verification supplies an internal conflict record for each `CONTRADICTED` verdict: an answer/claim anchor, verbatim evidence, and a brief explanation of the incompatible fact or calculation. The program checks structure, literal anchors, source indices and quote validity. It does not prove semantic entailment or algebraic equivalence.

Contradictions lacking a usable conflict record enter one batched review. This is a fresh three-way judgment: the result may remain `CONTRADICTED`, become `SUPPORTED`, or become `UNSUPPORTED`. Arithmetic or algebra from cited premises is permitted. Internal review evidence remains in telemetry when a claim becomes unsupported; the public `UNSUPPORTED` response still has empty citations.

Invalid JSON, fabricated public citations, upstream failures and exhausted format repairs remain errors. They must not be converted into successful unsupported judgments. Each additional call, including repairs and retries, contributes to usage and latency. Reports retain candidate decisions and contradiction-review directions.

## Data and review sequence

The formal **same-source, same-question-family confirmation set** is now frozen in [dataset/cphos28-confirmation](../dataset/cphos28-confirmation/README.md): 12 cases, 42 gold claims and 22 excerpts from Q2, Q6 and Q7. The four categories each contain three cases: dense answers, scope distractors, mixed-truth compounds and reformulation/calculation. No Q5 case or reviewed pilot is included. The formal labels were constructed with AI assistance and independently reviewed by a second AI role; they have not received the author's per-claim approval.

The actual sequence is recorded in [construction.json](../dataset/cphos28-confirmation/construction.json), including the initial draft and final hashes:

1. The author approved the three excluded pilots and annotation policy, including the same-sentence redundancy extension. Historical label adjudication was recorded separately without overwriting released data or results.
2. The v3.1 implementation and unchanged scorer were initially frozen at 02:53:51 UTC on 2026-10-22, after synthetic tests and development/regression work. A separate data author then constructed the formal draft at 02:59:25 UTC.
3. Independent synthetic code review exposed a duplicate-wording path that could discard a fuller formula or absorb a third assertion. The deterministic guard fix was finalized at 03:02:20 UTC in [the final code freeze](../reports/v3.1-code-freeze-final.json). Neither the code author nor the integrator had read formal case contents or model predictions when making this correction. This was a documented amendment after data construction had started, not an unchanged initial freeze.
4. Independent AI data review completed at 03:12:54 UTC, before formal model inference. It corrected one scope label, removed one unnecessary nonzero assumption and clarified six quantifier scopes; the initial draft and review decisions remain available. [The data-review freeze](../dataset/cphos28-confirmation/freeze.json) binds the reviewed data.
5. At 03:18:10 UTC, [confirmation.freeze.json](../dataset/cphos28-confirmation/confirmation.freeze.json) bound the finalized inputs, sources, code, policy approval, model settings and ordered four-backend list before inference. It is distinct from the data-review freeze.
6. Run the frozen comparison sequentially in the order `baseline`, `minimal`, `optimized-v2`, `optimized-v3` for each case. Preserve all outcomes, including failures and regressions. Do not tune inference or relabel the set after inspecting predictions. Any discovered annotation error is disclosed separately with the original result intact.

The first three pilot examples use `split=review` and never contribute confirmation credit. The initial implementation freeze preceded data construction; the final independent guard correction preceded data finalization and all confirmation inference. The chronology above preserves that distinction.

The author-facing materials are `reviews/cphos28/REVIEW.md` (58 historical claims) and `dataset/cphos28-review/REVIEW.md` (three new pilots). On 2026-10-22 the author approved the pilots, resolved all four flagged historical items and reported spot-checking the remainder without issues. The author also explicitly approved the same-sentence redundancy extension. `reviews/cphos28/pilot-author-review.json` records the actual pilot-policy confirmation and binds the reviewed files and `docs/ANNOTATION_POLICY_V3.md`; it does not certify human review of the formal confirmation labels.

## Reproducing the frozen confirmation

Use the committed data and `confirmation.freeze.json`; do not recreate or overwrite the freeze. With the same model settings configured and an API key in the local `.env`, a checkout with no existing local execution ledger can run:

```powershell
python scripts/benchmark.py --dataset dataset/cphos28-confirmation/cases.jsonl --confirmation-manifest dataset/cphos28-confirmation/confirmation.freeze.json --split confirmation --backends baseline minimal optimized-v2 optimized-v3 --thinking enabled --input-price-per-million 0.30 --cached-input-price-per-million 0.006 --output-price-per-million 1.20 --currency USD --output-dir results/confirmation-reproduction
```

The prices are the standardized reference tariff recorded for comparison, not a claim about current billing. In a workspace where this input batch already has a ledger entry, add `--confirmation-replicate` and use another new output directory. This also applies after an interrupted or failed run. The flag requires an existing local ledger entry; a clean clone normally lacks one. Such a clone's local `confirmation-first-run` label means only first recorded in that checkout, and does not establish a globally first or previously unseen evaluation.

The benchmark checks the author-reviewed pilot data, source and policy hashes, excludes pilot inputs even if renamed, and checks the formal code/data/settings bindings before any model call. The ledger in `results/confirmation-ledger` prevents an accidental second local first-run in another output folder. It cannot observe other checkouts or direct external API calls.

For provenance only, the manifest was originally created once with the command below. This is not a reproduction step: the helper refuses to overwrite the committed freeze and never manufactures author approval.

```powershell
python scripts/freeze_confirmation.py --dataset dataset/cphos28-confirmation/cases.jsonl --author-review reviews/cphos28/pilot-author-review.json --thinking enabled
```

## Interpretation and release

V2 versus v3 on the same confirmation cases is the primary comparison for this iteration. V3 versus minimal on that same set is also a valid comparison. Comparing a new confirmation score directly with an old test score confounds dataset difficulty. One run on 12 related cases is descriptive evidence, not a significance result or a component-level ablation; sampling variation and additional call budgets remain relevant.

Submission notes must retain the historical negative result, add actual v3 findings when available, and state the author review's real scope. A clean clone must pass the documented commands without PDF files or an API key for offline checks. Email submission is a separate author action; an implementation plan is not evidence that an email has been sent.
