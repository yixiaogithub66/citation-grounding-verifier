"""The additive v4 HTTP boundary must preserve valid work without hiding errors."""

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationResult
from grounding.contracts_v4 import validate_v4_report
from grounding.factory import frozen_v2_provenance, normalize_backend
from grounding.server import VerificationServer

class V4BoundaryTests(unittest.TestCase):
    def test_partial_is_200_with_same_successful_claims(self):
        report = {"claims": [{"claim_text": "A exists.", "verdict": "SUPPORTED",
                   "reasoning": "Source states it.", "citations": [{"index": 0, "quote": "A exists."}]}],
                  "status": "partial", "errors": [{"id": "c2", "code": "upstream_timeout",
                                                   "message": "Verification timed out.", "claim_text": "B exists."}]}
        class Stub:
            def verify(self, request):
                return VerificationResult(report)
        server = VerificationServer(("127.0.0.1", 0), Stub(), backend="optimized-v4.0")
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            payload = {"context_passages": ["A exists."], "generated_answer": "A exists. B exists."}
            request = Request(f"http://127.0.0.1:{server.server_port}/verify",
                              data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), report)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    def test_partial_cannot_disguise_all_failure_or_bad_quote(self):
        errors = [{"id": "c2", "code": "failure", "message": "Failed."}]
        for claims in ([], [{"claim_text": "A", "verdict": "SUPPORTED", "reasoning": "x",
                             "citations": [{"index": 0, "quote": "invented"}]}]):
            with self.subTest(claims=claims), self.assertRaises(VerificationError):
                validate_v4_report({"claims": claims, "status": "partial", "errors": errors}, ["A"])

    def test_historical_frozen_inference_is_intact(self):
        self.assertTrue(frozen_v2_provenance()["verified"])
        self.assertEqual(normalize_backend("optimized-v4"), "optimized-v4.0")
        self.assertEqual(normalize_backend("optimized"), "optimized-v4.0")

    def test_stage_config_roundtrip_and_strict_unknown_fields(self):
        config = V4Config()
        self.assertEqual(V4Config.from_dict(config.public_dict()), config)
        for bad in ({"format_retries": 2}, {"transport_retries": True}, {"quote_fuzzy_threshold": float("nan")},
                    {"review": {"thinking": "sometimes"}}, {"typo": 3}):
            with self.subTest(bad=bad), self.assertRaises(VerificationError):
                V4Config.from_dict(bad)

if __name__ == "__main__":
    unittest.main()
