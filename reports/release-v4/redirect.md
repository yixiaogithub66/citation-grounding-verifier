# Redirect fixture stability check

2026-10-24, Windows / Python 3.12.5. This check uses only loopback HTTP servers,
a synthetic credential and the existing `ChatClient`; it makes no model call and
does not read `.env`.

The original test could return `upstream_connection_error` before observing the
302 response, even when run without the rest of the suite. An initial batch of
30 repetitions reproduced one failure. The redirect fixture was returning and
closing an HTTP/1.0 connection without consuming its POST request body.

The following bounded fixture comparisons kept the security assertions and
client settings unchanged. Each variant started new servers for each test:

| Fixture variant | Repetitions | Failures | Errors |
| --- | ---: | ---: | ---: |
| Original | 80 | 2 | 0 |
| Add `Content-Length: 0` only | 80 | 8 | 0 |
| Drain the request body only | 80 | 0 | 0 |
| Drain body and declare response length | 80 | 0 | 0 |

This isolates the missing request-body consumption as the useful correction;
response framing alone did not eliminate the connection failure. The counts
describe these runs, not estimates of universal failure probabilities. No packet
capture was used to prove a particular TCP reset sequence.

The fixture change consumes the complete POST before returning 302
and declares the empty response length. The destination fixture also consumes
any request body and declares its two-byte response. The production client,
timeout, retry count and assertions are unchanged:

- The error must remain `upstream_http_error` with status 302.
- Exactly one provider attempt is recorded.
- Only the configured origin may receive the synthetic Authorization header;
  the redirect destination must receive no request.

Verification after the edit:

- Exact redirect test repeated 100 times: **100 passed, 0 failures/errors**.
- `python -m unittest discover -s tests -p test_verifiers.py -q`: **24 passed**.
- Frozen-v2 provenance check: **verified**, including the unchanged client.

Full release-suite and clean-checkout results are recorded separately by the
release coordinator after all entry-point edits are integrated.
