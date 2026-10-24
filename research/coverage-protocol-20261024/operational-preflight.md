# Operational preflight

2026-10-24, AI engineering review before inference. Scope: `PLAN.md`, `protocol.py`, `test_protocol.py`, `pilot.py`, `test_pilot.py` and the current production M1 prompt/client interfaces. The reviewer did not read the new `cases.json` bodies or gold, old benchmark bodies, or model outputs. This is an engineering check, not author adjudication or an independent human audit. The reviewer authored the runner and its tests; the protocol was authored by the root agent.

**Decision: no blocking integration or duplicate-dispatch issue found.** Actual freeze and provider invocation remain with the root agent. No code or prompt changed during this read-only review.

## Interface and experimental boundaries

- All three arm names match between runner and protocol. The runner calls `payload(arm, answer)` and `validate(arm, raw, answer, max_claims=64)` with answer text only. Both ledger arms use exactly the same payload. Their normalized outputs supply `claims`, `non_factual_spans` and diagnostics; the runner does not require a fabricated contiguous `source_span` or envelope from the ledger arms.
- Ledger claim order is a stable sort by earliest actual reference. It does not rewrite, merge or remove claims. Noncontiguous source references retain their discrete units. Schema validation does not certify semantic completeness, attribution, source support or atomicity; the plan explicitly measures those separately and includes the masking audit.
- Semantic task text is drawn verbatim from the existing M1 prompt. Legacy-versus-ledger still changes representation, provenance topology and the coverage contract; the plan correctly avoids calling this a clean ID-only causal comparison. Ledger-ID versus ledger-text directly removes the redundant full-text echo while retaining occurrence addressing.
- The fixed matrix is 20 answers × 2 repeats × 3 independent single-call arms = 120 requests. Arm order rotates with fixed hashing, and four workers execute the preplanned jobs. No outcome changes an arm's payload, order or budget. There is no fallback, second-pass review, M3, best-of selection or runtime claim merge.

## Model input isolation

`inference_cases` discards all metadata except the case ID used for scheduling/accounting and the original answer. `planned_requests` sends only the answer string to the protocol. The actual message body is the frozen prompt plus the protocol payload, never the request record's outer case ID, arm, repetition, hash or task index. Generated unit IDs are occurrence addresses produced from the request text; they are not dataset or case identities.

The freeze includes the original cases file for reproducibility, which can contain scorer-only targets. This is logical input isolation, not an operating-system sandbox: expected labels may exist in the frozen directory, but there is no inference-path code that transmits or branches on them. Tests use sentinel gold/domain/identity values to check this boundary. No new case bodies were needed for this review.

## Reservations, checkpoints and failure handling

1. Run startup exclusively writes `run-started.json` and creates the checkpoint directories. Any existing started marker, reservations, responses or journal blocks a subsequent run. There is no resume command.
2. A request must exactly equal a frozen planned identity. Before `single_call`, the runner exclusively writes and fsyncs a reservation; the in-memory reserved set additionally blocks duplicate requests. A reservation failure stops further dispatch. No I/O retry surrounds the provider call.
3. Each provider return, including a model/transport/validation error, becomes an exclusive response checkpoint with flush, fsync and readback. A response-checkpoint failure stops new dispatch. Already active calls can finish and persist their own results; the failed identity is not reissued.
4. `progress.json` is a derived display view. Safe I/O operations have at most five attempts with four short delays. A progress lock is recorded as a warning and does not retry or abort a provider call. An event-journal append failure disables further uncertain appends; the final canonical journal is generated from the independently persisted response records, without new provider calls.
5. A complete seal requires all 120 planned identities and response checkpoints. Analysis verifies the freeze, request matrix, durable reservations/responses, canonical journal and exactly one provider-attempt trace per record. `run-complete.json`, rather than the progress display, is authoritative.

The design prevents deliberate local resampling after logging failures. It cannot promise exactly-once execution inside a remote provider after a network timeout, nor guaranteed persistence during permanent storage failure. Such outcomes remain errors or partial/unknown reservations; they cannot be counted as semantic NF, success or zero cost. A filesystem failure during reservation creation can also leave an on-disk reservation outside an in-memory counter, so aborted-run diagnosis must inspect the durable directories, not only progress counters. The plan's partial/unknown disclosure and no-resend rule cover this limitation.

## Verification basis

The runner's ten network-free tests passed during implementation, including a complete 120-call fake run with every progress write locked, uncertain event-append recovery, failed response persistence stopping dispatch, no reissue of an unknown reservation, identity/gold isolation, frozen dependencies and balanced scheduling. The root reported all 19 runner/protocol tests passing for the integrated preflight version. These are engineering invariant checks, not measured model performance. No paid/provider call was made by this reviewer.

Reviewed SHA-256 values:

| File | SHA-256 |
|---|---|
| pilot.py | `e4241079aeda89a2cc38a32a726943602a1e4692a15015263d54e66db5dcd94f` |
| test_pilot.py | `04c98339d3ac8fae94037fc8df9a7b79c20f2eda7bb1ce70c7984aeaa15f69ce` |
| protocol.py | `f0a9c056b9f8d6cfa2856c0831138c3369965061f21a8c10e93d6c12e066a26f` |
| test_protocol.py | `64df20b2674d9e663fd0a95c13616b44a7887b247471b0dbe8a84901682501d7` |
| PLAN.md | `7de6798f6c65674e04fd4dd89ee3a199a000f8c7cdbce16e4e24a82d913fb330` |
