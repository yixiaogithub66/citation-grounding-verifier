# Evaluation protocol

## What is measured

The task is faithfulness to supplied text, including short algebraic consequences, not external truth or independent exam solving. All three methods receive exactly `context_passages` and `generated_answer`. Gold data is loaded only by the scoring layer.

Every method uses its own claim extraction. The two LLM methods use the same model, thinking setting, JSON-output setting and output-token budget. The minimal method gets one request with no retries. Optimized pays for its additional decomposition, verification, correction and transient retry calls. The baseline uses zero model requests.

## Data separation

Development: Q1, Q3, Q4, 18 cases. Held-out test: Q2, Q5, Q6, Q7, 24 cases. Edge diagnostics: 4 cases. Variants of a question stay in the same split. Data selection corrections discovered on development are versioned; test inputs and labels are unchanged by those corrections.

There are only seven underlying questions; cases within a question are correlated. Aggregate scores are descriptive, not statistically independent measurements or general-domain performance estimates.

## Metrics

Primary automated results are **strict joint extraction-and-verdict metrics**. Claim text must match after NFC and whitespace normalization, and its verdict must match. Unmatched gold claims count as missing; unmatched predictions count as extra. Wrong labels contribute both the appropriate false positive and false negative. Whole-case accuracy also requires no missing or extra claims. Empty-gold cases pass only with a valid empty output. API/contract failures fail the case.

Formula-aware approximate matching is a secondary diagnostic. It matches one-to-one without consulting verdicts, preserves critical numbers/negation/ordered math tokens, and rejects ambiguous matches. Its acceptance thresholds are fixed in code and recorded in every report. This is not an LLM semantic judge. Equivalent reformulation and valid alternative decomposition can still fail, and every approximate pair is auditable. No rule awards an arbitrary single prediction credit just because the gold has one claim.

Citation metrics are separated:

- Exact-source validity: valid index and literal nonempty substring.
- Passage coverage: predicted indices cover an acceptable annotated evidence set.
- Required-passage coverage: all passages annotated as necessary to a multi-source claim are cited.
- Gold-anchor containment: a quote or union of quotes from the same passage contains the annotated quote text.
- Gold exact span match: reported only as a strict diagnostic, since longer correct quotations are valid.

The scorer's containment metric operates on individual quoted spans; adjacent pieces are not implicitly reassembled. Thus splitting a gold span into several shorter adequate quotations can still be flagged for review. None of these syntactic metrics proves semantic entailment. All citation recall denominators include unmatched gold evidence-bearing claims.

## Runtime and cost

Measure wall time around each complete verification call, including all stages and retries. Report mean, median and nearest-rank P95. Requests execute sequentially in a fixed baseline/minimal/optimized order per case. This is reproducible, but prompt caching and network conditions can advantage later calls; the table is not a randomized latency experiment.

Record each upstream call's final JSON text, usage, returned model/fingerprint, finish reason and error. Do not record keys or provider chain-of-thought text. Sum all reported usage, including failed validation calls and corrections. Missing counts remain unknown. The standardized price convention is in `reports/PRICING.md`; these estimates are not billing records.

## Audit and reproduction

Each run records dataset/source hashes, Python version, generation settings, code/prompt hashes, complete predictions, alignment details, failures, and partial checkpoints. Existing run directories cannot be overwritten. Long-running interruptions preserve completed records.

Read `docs/ITERATIONS.md` for observed development errors and the changes they motivated. The final test results must be reported even if the method named optimized does not outperform minimal. A larger prompt or more calls is not evidence of better quality.
