# optimized-v4.0

V4 implements the author decisions in [V4_DECISIONS.md](V4_DECISIONS.md). The service now defaults to `optimized-v4.0`; `optimized` and `optimized-v4` select it too. Explicit `optimized-v2` and `optimized-v3` remain available for historical work. The default stage configuration is resolved from the repository, independently of the launch directory; an explicit `--v4-config` overrides it. No result in this document certifies author adjudication or unseen-test acceptance.

## Pipeline and boundaries

- M0 retains the two-field HTTP input and string-array passages. Structured RAGTruth sources use the existing deterministic JSON adapter, preserving null and booleans; the adapter version and hash are recorded. The verifier records a deterministic request hash.
- M1 divides the answer into bounded character chunks, preferably at sentence boundaries, and asks only for extraction. Exact source-span order and substantive-character coverage are checked. Each failed chunk has one format retry, then original sentence skeletons are explicitly marked as fallback. A failed hard boundary is recovered from complete original sentences, with overlapping extraction decisions recorded as superseded. No runtime semantic merge stage exists.
- M2 accepts exact quotes and conservatively repairs unique formatting/index mistakes. Only a small, documented punctuation/quotation/whitespace normalization is allowed: letters, digits and mathematical operators are not folded. Fuzzy token windows only produce bounded candidates for a new judgment. They never silently replace evidence. Every repaired quote is checked again against original source text.
- M3 estimates variable claim input and output size and batches independently. All passages are included in every batch; common context tokens are reported separately. The estimate is not a tokenizer or a proof that provider reasoning cannot exhaust a budget. A bad batch receives one retry; a valid batch with one bad row sends only that claim for a targeted requery. Successful rows survive failures elsewhere.
- M4 uses at most one logical C review and one logical U review per claim, in that order. Invalid C conflict anchors or a narrowly aligned numeric signal trigger C review. A resulting U receives the one final full-context U review. U can become C only with valid conflict evidence in that review. Format retries and the one shared targeted quote requery are counted separately, without reopening the review chain.
- M5 returns ordinary complete reports or an additive partial report. All claims, errors and fallback exclusions are accounted for. Exact citations, indices and public verdict constraints are rechecked. No completed factual claim plus unresolved errors produces an execution error, never a successful empty report or fabricated U.

Numeric checking emits signals only for strictly aligned text anchors and identical literal unit strings. It does not convert units, solve arithmetic, verify algebra or assign verdicts. Exact citations and conflict structures do not establish semantic truth by themselves.

Fallback sentence skeletons preserve text but may be compound. The verifier can exclude a skeleton as purely non-factual only through an explicit model classification recorded in telemetry. This is a measured degradation, not a claim that deterministic sentence splitting proves atomicity or complete factual extraction.

## Configuration and HTTP

```powershell
python -m grounding.server --backend optimized-v4.0 --v4-config configs/optimized-v4.0.json
```

Model endpoint/key/timeout remain in the existing `.env`; keys are not written into reports. V4 generation and retry settings are independent of the frozen v2/v3 settings. `decompose`, `verify`, and `review` each specify `thinking` and `max_output_tokens`. All effective settings appear in runtime telemetry and freeze manifests.

Complete response retains the Gist shape, including the genuinely no-factual-claims case:

```json
{"claims": []}
```

Partial response uses HTTP 200 and retains the original fields on each completed claim:

```json
{
  "claims": [
    {"claim_text":"A exists.","verdict":"SUPPORTED","reasoning":"Stated in the source.","citations":[{"index":0,"quote":"A exists."}]}
  ],
  "status":"partial",
  "errors":[{"id":"c2","claim_text":"B exists.","stage":"verify","code":"upstream_timeout","message":"Verification timed out."}]
}
```

Consumers that require complete verification must inspect `status`/`errors`; reading `claims` alone only retrieves completed work. The original input limits and 64-claim capacity remain. Overflow is explicit and never silently truncates assertions. `status:complete` is not added to complete responses, preserving the original success schema.

## Current evaluation and archived history

The current runner defaults to baseline, minimal and v4, and preserves partial reports:

```powershell
python scripts/benchmark_v4_claims.py --dataset dataset/cphos28/cases.jsonl --split test --output-dir results/current-comparison
```

Read aligned claim accuracy together with alignment coverage. The historical `benchmark.py` rejects v4 before calling a model because its claims-only scoring contract does not support partial reports. All output directories must be new.

For RAGTruth, a completed C/U detects an answer-level problem; partial all-S remains unknown, neither TN nor FN. Full-case correct yield, complete/partial/error counts, decision coverage and conditional F1 must be reported together. Native annotations do not provide complete atomic-claim gold or author-adjudicated true FP.

The completed fresh180 run and unchanged evidence ZIP are [here](../reports/ragtruth-fresh180-20261024/README.md). It used previously unexposed sources after preselection freezing. Those sources are now exposed and cannot serve as untouched confirmation after subsequent development. Older protocols, review drafts and source snapshots remain in the [immutable development archive](https://github.com/yixiaogithub66/citation-grounding-verifier/tree/bd51922f30f5d1e105e8ebc5578d16fad9585342); historical freezes can require their original checkout or archived source tree.

Author review of the old reported claims was submitted but has not been imported as a final adjudicated dataset. Native labels and scores remain unchanged. This release does not assert completion of the separate FP/FN acceptance gate.

## Known boundaries retained in this release

Repeated source spans with different claim text can still cause unnecessary coverage failures. An occurrence-aware extraction protocol must preserve legitimate multiple claims sharing the same source span. Sentence fallback is an explicit degradation, not factual-selection certification.

Whitespace normalization is not proven safe for indentation-sensitive code or exact string literals. A stricter quote-repair policy needs separate implementation and semantic/cost validation; this entry-point release does not claim that issue is fixed.

Internal conflict-content drift currently takes a targeted requery before a possible C gate. Its routing needs clarification while keeping semantic rejudgment distinct from formatting repair and preserving the total review budget.

Outer HTTP concurrency and internal v4 workers are distinct; their product can increase upstream concurrency. This is a local demonstration service, not a load-tested multi-tenant deployment. See the [results discussion](RESULTS.md) for measured accuracy, high FP and cost limits. No dataset-specific prompt, threshold, keyword branch or runtime merge was added.
