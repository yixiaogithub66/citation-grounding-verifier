# v4 submission release checks

2026-10-24. This release collects the existing v4 implementation into a clear public entry point. It does not introduce a new prompt, decomposition/quote policy, benchmark-specific rule, model budget or semantic result.

## Changes

- The server and `optimized` alias select `optimized-v4.0`; `optimized-v3` remains explicit. Default stage configuration is loaded relative to the repository, not the caller's working directory.
- `benchmark_v4_claims.py` defaults to baseline/minimal/v4 and preserves valid partial reports. The historical runner refuses v4 before loading credentials or invoking models and generates comparisons only for selected backends.
- The redirect test fixture consumes incoming POST bodies before responding and uses explicit response lengths. Its credential-isolation and exact 302 assertions remain unchanged; the production client remains frozen.
- The main README is 149 lines. Research drafts, multi-run snapshots and most reviews remain in the immutable `develop` archive at `bd51922`. A small frozen author-review attestation and two test/provenance dependencies are retained where existing manifests/tests require them.
- The latest RAGTruth evidence ZIP is moved intact to the result directory. Original data, labels and scored JSON remain byte-identical. Historical absolute paths remain provenance only; normal startup and testing do not depend on those files existing locally.

## Verified locally

| Check | Result |
| --- | --- |
| Release checkout full suite | 433 passed |
| Two separate full suites in a clean Git-index export | 433 passed each |
| Final export outside any discoverable Git repository | 433 passed |
| Corrected redirect test | 100/100 passed; see [fixture diagnosis](redirect.md) |
| Three dataset validators | 46 / 3 / 12 cases valid |
| Current and historical baseline smoke | 18/18 complete each, zero model calls |
| Real default HTTP startup | `/health`: v4.0; empty answer:200; malformed JSON:400; wrong media type:415 |
| Relocated frozen evidence rescore | Complete JSON byte-identical to the original report |
| Historical v2 file hashes | Verified unchanged |
| v4 inference, prompt, configuration bytes | Unchanged from the published evaluation revision |

The clean export contained no `.env`. HTTP startup used a synthetic credential and only requests that do not invoke a model. The tests use mocks and local servers; no paid inference or new benchmark experiment was run. The first pruning attempt exposed two test-file dependencies; their original bytes were restored before the three successful full-suite runs.

The first remote shallow-checkout CI then exposed a separate test-only `git show` dependency. Earlier local exports were nested beneath the worktree and could still find its Git history. A single byte-preserved, SHA-bound historical test fixture replaces that dependency; the behavioral assertions remain. The final external export was explicitly checked to have no discoverable Git repository and all 433 tests passed. CI now lets all matrix jobs finish so one platform's failure cannot hide the others.

[Machine-readable validation](validation.json) binds the checked source bytes. [Curation summary](curation.json) records the archive revision and retained evidence hash. Remote CI checks the final committed branch independently on Windows/Linux and Python 3.11/3.12.

## Scope left visible

The release preserves the evaluated inference behavior. The known M1 repeated-span ambiguity, semantic-whitespace quote-normalization boundary, high native FP and incomplete usage accounting are disclosed in the main README and design/results pages. Baseline capacity/extreme-numeric handling and the HTTP response-write exception boundary from the separate review remain follow-up engineering items. This submission is a reviewable verifier prototype, not a claim that those issues or the separate author-adjudicated acceptance gate are resolved.

The frozen validation/configuration files still share the existing dataset-validation module under `scripts/`; the required module is retained so a shallow clone remains executable. A dependency-layer refactor is deferred rather than silently changing the archived v2 byte contract.
