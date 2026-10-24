# Fresh 180 operational audit

Status: passed (final)

Frozen source files: 65; reservations: 540; durable results: 540 / 540.

| Backend | Records | Errors | Partial | Provider attempts | Usage unknown | C / U logical reviews |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 180 | 0 | 0 | 0 | 0 | 0 / 0 |
| minimal | 180 | 3 | 0 | 180 | 0 | 0 / 0 |
| optimized-v4.0 | 180 | 0 | 5 | 1434 | 2 | 2 / 310 |

Violations: 0

- No gold was deserialized; no accuracy, hallucination label, or selection decision was computed.
- Provider-attempt totals include every saved telemetry.calls entry, including retries, repairs, reviews, failed requests, and partial reports.
- Missing provider usage remains unknown. Token totals are sums of known reported usage, not provider invoices.
- Minimal request budgets are verified through frozen source/config; unlike v4 traces they are not echoed as per-call thinking/token fields.
- This audit checks durable artifacts and recorded traces. It cannot independently observe requests outside the instrumented process.
