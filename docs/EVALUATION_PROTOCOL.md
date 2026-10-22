# Evaluation protocol

## What is measured

The task is faithfulness to supplied text, including short algebraic consequences, not external truth or independent exam solving. All methods receive exactly `context_passages` and `generated_answer`. Gold data is loaded only by the scoring layer.

Every method uses its own claim extraction. The LLM methods use the same model, thinking setting, JSON-output setting and output-token budget. The minimal method gets one request with no retries. Optimized pays for its additional decomposition, verification, correction and transient retry calls. V3 also pays for every candidate-merge and contradiction-review call. The baseline uses zero model requests.

## Data separation

Development: Q1, Q3, Q4, 18 cases. Held-out test: Q2, Q5, Q6, Q7, 24 cases. Edge diagnostics: 4 cases. Variants of a question stay in the same split. Data selection corrections discovered on development are versioned; test inputs and labels are unchanged by those corrections.

There are only seven underlying questions; cases within a question are correlated. Aggregate scores are descriptive, not statistically independent measurements or general-domain performance estimates.

For v3, the old test has been used for diagnosis and system design; it is now regression material. Its original frozen v2 results remain intact. The three approved pilot examples are in a separate `review` dataset and never contribute to confirmation scores. The frozen formal `confirmation` dataset contains 12 cases and 42 gold claims using 22 new excerpts from Q2, Q6 and Q7. Each of its four categories has three cases. It is a same-source, same-question-family confirmation set, not a question-level independent test; cases share passages and each question supplies four cases.

The formal labels were constructed with AI assistance and reviewed by an independent AI role. The author's approval covers the pilots and annotation policy, not per-claim review of these 42 labels. The original 58 claims have a separate author adjudication record: four specific decisions plus a reported spot-check of the remainder. Neither process rewrites the historical gold or results.

The [construction record](../dataset/cphos28-confirmation/construction.json) preserves the actual sequence. The initial code freeze preceded the formal draft. Independent synthetic code review then identified a duplicate-wording guard defect, corrected before the code author or integrator read formal case contents or predictions. The final code freeze preceded independent data-review completion, and the reviewed data, code and model settings were bound in `confirmation.freeze.json` before inference. Thus the final guard correction occurred after draft construction had begun, without using it. See [the v3.1 design](V3_DESIGN.md) for the timestamps and separate code, data-review and runner freeze artifacts.

## Metrics

Primary automated results are **strict joint extraction-and-verdict metrics**. Claim text must match after NFC and whitespace normalization, and its verdict must match. Unmatched gold claims count as missing; unmatched predictions count as extra. Wrong labels contribute both the appropriate false positive and false negative. Whole-case accuracy also requires no missing or extra claims. Empty-gold cases pass only with a valid empty output. API/contract failures fail the case.

Formula-aware approximate matching is a secondary diagnostic. It matches one-to-one without consulting verdicts, preserves critical numbers/negation/ordered math tokens, and rejects ambiguous matches. Its acceptance thresholds are fixed in code and recorded in every report. This is not an LLM semantic judge. Equivalent reformulation and valid alternative decomposition can still fail, and every approximate pair is auditable. No rule awards an arbitrary single prediction credit just because the gold has one claim.

Citation metrics are separated:

- Exact-source validity: valid index and literal nonempty substring.
- Passage coverage: predicted indices cover an acceptable annotated evidence set.
- Required-passage coverage: all passages annotated as necessary to a multi-source claim are cited.
- Gold-anchor containment: at least one literal quote from the same passage contains the annotated quote text.
- Gold exact span match: reported only as a strict diagnostic, since longer correct quotations are valid.

The scorer's containment metric operates on individual quoted spans; adjacent pieces are not implicitly reassembled. Thus splitting a gold span into several shorter adequate quotations can still be flagged for review. None of these syntactic metrics proves semantic entailment. All citation recall denominators include unmatched gold evidence-bearing claims.

Passage and gold-anchor recall receive credit only for aligned claims whose verdict is correct; exact-source substring validity is measured separately regardless of semantic correctness.

The annotation convention permits coordinated subjects with a single shared predicate as one joint claim; every subject must be supported for a SUPPORTED verdict. This can be coarser than a decomposition that emits one claim per subject. Such granularity differences require review, rather than being automatically interpreted as semantic mistakes.

The new-case policy in `docs/ANNOTATION_POLICY_V3.md` groups a formula and equivalent prose. The author-approved v3.1 extension also groups a consistent redundant property description with its fuller formula within the same sentence, preserving the complete formula. The property need not entail every part of the formula. Conflicting restatements, independent mixed-truth assertions and cross-sentence redundancy remain separate. It does not rewrite historical labels. No scorer threshold or text-matching rule is changed for v3 or v3.1.

## Runtime and cost

Measure wall time around each complete verification call, including all stages and retries. Report mean and nearest-rank P50/P95 (for an even-sized sample, this P50 is the lower middle observation, not the arithmetic median). Formal confirmation executes sequentially in the fixed order `baseline`, `minimal`, `optimized-v2`, `optimized-v3` for each case; historical three-backend runs retain their recorded order. This is reproducible, but prompt caching and network conditions can advantage later calls; the table is not a randomized latency experiment.

Record each upstream call's final JSON text, usage, returned model/fingerprint, finish reason and error. Do not record keys or provider chain-of-thought text. Sum all reported usage, including failed validation calls and corrections. Missing counts remain unknown. The standardized price convention is in `reports/PRICING.md`; these estimates are not billing records.

## Audit and reproduction

Each run records dataset/source hashes, Python version, generation settings, code/prompt hashes, complete predictions, alignment details, failures, and partial checkpoints. Existing run directories cannot be overwritten. Long-running interruptions preserve completed records.

Confirmation reproduction uses the committed `dataset/cphos28-confirmation/confirmation.freeze.json` directly. Do not rerun the initial freeze helper or overwrite its inputs. The runner checks the complete ordered case list, four backend names, implementation/scorer hashes, pilot-policy approval and model settings before any API call. The exact command and reference-price arguments are documented in [V3_DESIGN.md](V3_DESIGN.md#reproducing-the-frozen-confirmation).

The local `results/confirmation-ledger` records exposure to an exact input batch. A repeat in the same workspace, including recovery after an interruption, requires `--confirmation-replicate` and a fresh output directory. That flag requires a prior local ledger entry. A clean clone's empty ledger cannot prove that no previous run exists elsewhere; its local first-run label is not evidence of globally unseen data. Readers reproducing a published experiment should describe it as reproduction even when it is the first recorded run in their checkout.

Freeze precedes predictions. Do not tune inference, the scorer or gold after seeing confirmation outcomes. Disclose any subsequently discovered annotation issue separately while retaining the original data and result. Compare v2/v3.1 and minimal/v3.1 on this same set; cross-set score differences mix system changes with dataset difficulty. Twelve correlated, constructed cases do not establish significance, general-domain performance or a component-level ablation.

Read `docs/ITERATIONS.md` for observed development errors and the changes they motivated. The final test results must be reported even if the method named optimized does not outperform minimal. A larger prompt or more calls is not evidence of better quality.
