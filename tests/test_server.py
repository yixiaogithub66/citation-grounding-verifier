"""HTTP contract tests against a real local listener without external requests."""

import http.client
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from grounding.contracts import VerificationError, VerificationResult
from grounding.server import MAX_BODY_BYTES, VerificationServer


class StubVerifier:
    def __init__(self, report=None, error=None):
        self.report = report if report is not None else {"claims": []}
        self.error = error
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return VerificationResult(self.report)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.verifier = StubVerifier()
        self.server = VerificationServer(("127.0.0.1", 0), self.verifier, backend="test")
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, payload=None, *, path="/verify", raw=None, content_type="application/json", method="POST"):
        body = raw if raw is not None else json.dumps(
            payload if payload is not None else {"context_passages": [], "generated_answer": ""},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(self.url + path, data=body if method == "POST" else None,
                          method=method, headers={"Content-Type": content_type})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_success_response_has_only_claims(self):
        status, data = self.request()
        self.assertEqual((status, data), (200, {"claims": []}))
        self.assertEqual(self.verifier.requests[0].context_passages, [])

    def test_request_shapes_and_unknown_fields(self):
        for value in ([], {}, {"context_passages": "x", "generated_answer": ""},
                      {"context_passages": [], "generated_answer": False},
                      {"context_passages": [3], "generated_answer": ""},
                      {"context_passages": [], "generated_answer": "", "claims": []}):
            with self.subTest(value=value):
                self.assertEqual(self.request(value)[0], 400)
        self.assertFalse(self.verifier.requests)

    def test_invalid_json_duplicate_keys_and_surrogates(self):
        for raw in (b"{", b'{"a":1,"a":2}', b'{"context_passages":[],"generated_answer":"\\ud800"}', b"\xff"):
            with self.subTest(raw=raw):
                self.assertEqual(self.request(raw=raw)[0], 400)

    def test_routes_and_content_type(self):
        self.assertEqual(self.request(path="/health", method="GET"), (200, {"status": "ok", "backend": "test"}))
        self.assertEqual(self.request(method="GET")[0], 405)
        self.assertEqual(self.request(path="/unknown")[0], 404)
        self.assertEqual(self.request(content_type="text/plain")[0], 415)

    def test_oversized_request_rejected_before_reading(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.putrequest("POST", "/verify")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 413)
        response.read()
        connection.close()
        self.assertFalse(self.verifier.requests)

    def test_invalid_model_citation_cannot_escape_service(self):
        self.verifier.report = {"claims": [{
            "claim_text": "a", "verdict": "SUPPORTED", "reasoning": "evidence",
            "citations": [{"index": True, "quote": "made up"}],
        }]}
        status, body = self.request({"context_passages": ["a"], "generated_answer": "a"})
        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["code"], "invalid_model_output")

    def test_upstream_failure_not_returned_as_unsupported(self):
        self.verifier.error = VerificationError("upstream_timeout", "Model timed out.", 504)
        status, body = self.request()
        self.assertEqual(status, 504)
        self.assertNotIn("claims", body)

    def test_unexpected_failure_hides_details(self):
        self.verifier.error = RuntimeError("secret must not appear")
        status, body = self.request()
        self.assertEqual(status, 500)
        self.assertNotIn("secret", json.dumps(body))

    def test_busy_server_returns_json_error(self):
        for _ in range(4):
            self.server.slots.acquire()
        try:
            self.assertEqual(self.request()[0], 503)
        finally:
            for _ in range(4):
                self.server.slots.release()


if __name__ == "__main__":
    unittest.main()
