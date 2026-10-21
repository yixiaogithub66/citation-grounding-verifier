# Grounding v3: design and confirmation protocol

This iteration follows the author's updated CPHOS28 plan dated 2026-10-22. The historical `grounding-v2` test is preserved. It motivated v3's design, so those old test cases are now diagnostic/regression material for v3, not an unseen evaluation.

## Scope and controls

`minimal` retains its original single-call prompt and implementation. `optimized-v2` retains the original inference files from commit `cfadeca`; their exact byte hashes are checked against `grounding/frozen_v2.json`. `optimized-v3` adds the stages below. The compatibility name `optimized` selects v3. Neither the original 46 cases/58 gold claims nor the scoring rules are changed to improve a score.

The historical strict correct count of 29 for each LLM means 29 text-aligned, correctly labeled gold claims. It does not isolate semantic judgment accuracy. The old result is v2, not v1. All performance improvements in this iteration must be observed, not assumed.

## Extraction and merging

The extraction rule preserves the full original sentence when it expresses one proposition. A formula and its equivalent prose are one proposition only if the quantity, value, sign, conditions and scope agree. A sentence containing independent propositions with different truth values must still split. Requiring multiple source passages does not itself justify splitting a single conclusion.

Merging takes place before verification and receives only the answer and extracted claims, never source context or gold labels. Deterministic similarity and explicit restatement connectors select candidates; they do not prove equivalence. One batched model call decides which candidates are equivalent, defaulting to separate claims when uncertain. Reconstructed text comes from the original answer. A merge must preserve coverage and cannot absorb unrelated clauses merely because they share a sentence. Shared subjects and conditions must survive splitting.

## Contradiction evidence review

Initial verification supplies an internal conflict record for each `CONTRADICTED` verdict: an answer/claim anchor, verbatim evidence, and a brief explanation of the incompatible fact or calculation. The program checks structure, literal anchors, source indices and quote validity. It does not prove semantic entailment or algebraic equivalence.

Contradictions lacking a usable conflict record enter one batched review. This is a fresh three-way judgment: the result may remain `CONTRADICTED`, become `SUPPORTED`, or become `UNSUPPORTED`. Arithmetic or algebra from cited premises is permitted. Internal review evidence remains in telemetry when a claim becomes unsupported; the public `UNSUPPORTED` response still has empty citations.

Invalid JSON, fabricated public citations, upstream failures and exhausted format repairs remain errors. They must not be converted into successful unsupported judgments. Each additional call, including repairs and retries, contributes to usage and latency. Reports retain candidate decisions and contradiction-review directions.

## Data and review sequence

1. Implement v3 and exercise synthetic behavioral tests plus the existing development/regression material. Freeze the inference implementation and the unchanged scoring rules before evaluating any formal confirmation case.
2. AI-review all 58 historical gold claims, preserving their original labels. Produce a per-claim review table with disputed cases and suggested decisions. The author decides disputed items and spot-checks the rest; until that happens, no document claims completed human review.
3. Prepare three new pilot examples, one each for dense answers, scope distractors and mixed-truth compound sentences. The author reviews them and the annotation rules. These pilot examples use `split=review` in a separate dataset and are excluded from the formal confirmation set, even if they do not lead to code changes.
4. After the pilot review, construct 12 additional cases (three per planned category) from newly transcribed passages. Record page/formula locations and normalization. Use the name **same-source, same-question-family confirmation set**. Do not claim question-level independence from CPHOS28.
5. Validate and freeze the formal data, sources, code hashes, model settings and four-backend list before inference. Store the actual author confirmation of the pilot annotation policy; do not fabricate an approval record. Formal confirmation labels remain AI-assisted unless further human review is actually performed.
6. Run baseline, minimal, frozen v2 and v3 once on the same confirmation set. Preserve all outcomes, including failures and regressions. Do not tune v3 or relabel the set after inspecting confirmation predictions. Discovered annotation errors are disclosed separately with the original result intact.

The first three pilot examples are not an extra source of final evaluation credit. If their review leads to code or policy changes, freeze those changes before constructing the formal confirmation set. Historical labels can be adjudicated separately without overwriting the released v1.2 benchmark or its recorded results.

The prepared author-facing materials are `reviews/cphos28/REVIEW.md` (58 historical claims) and `dataset/cphos28-review/REVIEW.md` (three new pilots). Their empty author-decision fields are pending, not approval. `docs/ANNOTATION_POLICY_V3.md` is the policy artifact to bind to the eventual pilot-review attestation.

After a real author confirmation has been recorded in an attestation JSON and the formal cases have been constructed, the freeze helper validates and binds those existing artifacts without making model calls:

```powershell
python scripts/freeze_confirmation.py --dataset dataset/cphos28-confirmation/cases.jsonl --author-review reviews/cphos28/pilot-author-review.json --thinking enabled
python scripts/benchmark.py --dataset dataset/cphos28-confirmation/cases.jsonl --split confirmation --backends baseline minimal optimized-v2 optimized-v3 --thinking enabled --output-dir results/confirmation-first
```

These commands describe the next stage; the formal dataset and approval file do not exist until their actual prerequisites are complete. The helper never manufactures approval and refuses to overwrite an existing freeze. The benchmark checks the author-reviewed pilot data, source and policy hashes, excludes pilot inputs even if renamed, and checks the formal code/data/settings bindings before any model call. A local execution ledger prevents an accidental second first-run in another output folder. Explicit `--confirmation-replicate` runs are labeled as repeats; this ledger does not prove global uniqueness across other checkouts or external API clients.

## Interpretation and release

V2 versus v3 on the same confirmation cases is the primary comparison for this iteration. V3 versus minimal on that same set is also a valid comparison. Comparing a new confirmation score directly with an old test score confounds dataset difficulty. One run on 12 related cases is descriptive evidence, not a significance result or a component-level ablation; sampling variation and additional call budgets remain relevant.

Submission notes must retain the historical negative result, add actual v3 findings when available, and state the author review's real scope. A clean clone must pass the documented commands without PDF files or an API key for offline checks. Email submission is a separate author action; an implementation plan is not evidence that an email has been sent.
