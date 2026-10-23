# optimized-v4.0

V4 implements the author decisions in [V4_DECISIONS.md](V4_DECISIONS.md). It is a separately selectable backend. The `optimized` compatibility alias still selects historical v3; use `optimized-v4.0` explicitly. No result in this document certifies author adjudication or unseen-test acceptance.

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

## Development and regression

Old RAGTruth v1 is now exposed development/regression material. A bounded seven-case quote-recovery check is:

```powershell
python scripts/ragtruth_v4.py run --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/v4-quote-check --backends optimized-v4.0 --ids 2469 445 6276 6279 7022 7033 7036 --replicate --v4-config configs/optimized-v4.0.json
python scripts/score_v4.py --run-dir results/v4-quote-check --data-dir dataset/ragtruth-blind-v1/recovery --output-dir results/v4-quote-check-score
```

Omit `--ids` to run all 180 exposed cases. Output directories must be new. The seven IDs are the historical minimal bad-substring cases; they are not seven v3 failures. A complete report counts toward the 5/7 recovery target whether recovery uses a format repair or a rejudgment. A partial report does not count as complete recovery.

CPHOS and supplemental drafts use the independent claim-gold regression runner:

```powershell
python scripts/benchmark_v4_claims.py --dataset dataset/cphos28/cases.jsonl --output-dir results/v4-cphos-regression --v4-config configs/optimized-v4.0.json
python scripts/benchmark_v4_claims.py --dataset dataset/v4-supplementary-draft/cases.jsonl --output-dir results/v4-supplementary-draft --v4-config configs/optimized-v4.0.json
```

The latter ten cases are AI-authored synthetic source specifications/exercises, pending author review. They are not a human gold set and do not replace the principal external evaluation. They include six systems cases and four physics cases; the supplied premises are self-contained.

Offline behavioral verification:

```powershell
python -m unittest discover -s tests
```

The legacy RAGTruth v1 freeze intentionally rejects the changed v4 checkout. Reproduce that exact historical runtime from commit `5fc6c40` in a separate checkout. Frozen v2 inference files remain unchanged; the new v4 runner can compare old verifiers without altering their original prompts.

## Adjudication and acceptance

The author chose AI drafts followed by the author's own per-claim final review. The review package is [here](../reviews/ragtruth-v4-dev-adjudication-v1/ai-draft/README.md): 96 cases, 341 reported C/U claims, including 82 cases in the native-FP union and 40 backend-disagreement cases. These subsets overlap.

The AI drafting tool receives only source passages and candidate claim text, without the original backend verdict or native label. It logs its prompt, settings, responses and exact-quote validation. This separation does not establish independent human review or independent model errors. All author decisions remain pending until the actual user supplies them. Original native labels are never overwritten.

Reviewing reported claims alone does not prove the absence of unreported hallucinations. An adjudicated full-answer FN claim additionally needs adequate full-answer adjudication coverage. Acceptance must distinguish native, reviewed-claim and author-adjudicated full-answer scopes.

Partial-aware native scoring declares a positive result when any completed valid claim is C/U. A partial report containing only S is unknown, not TN/FN. Reports show resolved-only metrics, decision coverage, complete-case rate, technical failures, known claim completion counts and unknown claim denominators. They preserve historical whole-case-failure scores separately. Zero observed FN with unresolved native-positive cases cannot pass the FN=0 target.

## Unseen v2 procedure

Do not prepare the new slice until implementation/configuration are final and the development review/acceptance prerequisites have been resolved. Preselection freezing hashes code, prompts, stage settings, the original pinned raw files and all recorded source exposure. It is distinct from the later freeze that binds selected inputs and opaque gold bytes.

```powershell
python scripts/ragtruth_v4.py freeze-preselection --freeze-manifest reports/v4-preselection-freeze.json --v4-config configs/optimized-v4.0.json
python scripts/ragtruth_v4.py prepare --raw-dir tmp/ragtruth-upstream --output-dir dataset/ragtruth-blind-v2 --preselection-freeze reports/v4-preselection-freeze.json
python scripts/ragtruth_v4.py freeze-run --data-dir dataset/ragtruth-blind-v2 --preselection-freeze reports/v4-preselection-freeze.json --freeze-manifest dataset/ragtruth-blind-v2/freeze.json
python scripts/ragtruth_v4.py run --mode test --data-dir dataset/ragtruth-blind-v2 --freeze-manifest dataset/ragtruth-blind-v2/freeze.json --output-dir results/ragtruth-blind-v2 --v4-config configs/optimized-v4.0.json
python scripts/score_v4.py --run-dir results/ragtruth-blind-v2 --data-dir dataset/ragtruth-blind-v2 --output-dir reports/ragtruth-blind-v2
```

The new seed contains `v2`; the hash-ranking rule is unchanged. Exclusions apply to complete source groups, including the original 30 and all additionally recorded exposures. Selection keeps ten eligible sources per task and six good responses per source, for 180 responses. The frozen four-way comparison is baseline/minimal/v3/v4 on the same new inputs. V1 and v2 are different slices; their raw scores are not a paired case comparison.

Any changed inference, scorer or configuration invalidates the formal freeze. No retuning or relabelling after viewing test outcomes. New FP adjudication can be disclosed separately while preserving the native result.
