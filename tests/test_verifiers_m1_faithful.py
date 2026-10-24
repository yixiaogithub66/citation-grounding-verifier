"""Synthetic intervention-isolation checks, not semantic prompt-accuracy tests."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.factory import build_verifier, normalize_backend
from grounding.prompts_v4 import DECOMPOSE_PROMPT as ORIGINAL_PROMPT, prompt_metadata as original_metadata
from grounding.prompts_m1_faithful import DECOMPOSE_PROMPT, prompt_metadata
from grounding.verifiers_v4 import OptimizedV4Verifier
from grounding.verifiers_m1_faithful import OptimizedV4M1FaithfulVerifier


class RecordingClient:
    def __init__(self, outputs):
        self.outputs = deepcopy(outputs)
        self.inputs = []

    def complete(self, messages, stage, telemetry):
        self.inputs.append({"messages": deepcopy(messages), "stage": stage})
        output = self.outputs.pop(0)
        telemetry["calls"].append({"stage": stage, "attempt": 1, "response_text": json.dumps(output)})
        return output


def extraction(text):
    return {"claims": [{"claim_text": text, "source_span": text}], "non_factual_spans": []}


def judgment(text, label):
    return {"claims": [{
        "id": "c1", "claim_text": text, "verdict": label,
        "citations": [] if label == "UNSUPPORTED" else [{"index": 0, "quote": text}],
        "derivation": "The given premise is sufficient." if label == "SUPPORTED" else "No premise identified.",
        "reasoning": "A scripted synthetic decision.", "conflict": None,
    }]}


class M1FaithfulIsolationTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(api_key="synthetic-only", base_url="http://example.test", model="fake")
        self.config = replace(V4Config(), max_workers=1, format_retries=1, batch_retries=0)
        self.text = "The vessel is sealed."
        self.request = VerificationRequest([self.text], self.text)

    def test_same_extraction_keeps_initial_and_review_requests_identical(self):
        outputs = [extraction(self.text), judgment(self.text, "UNSUPPORTED"), judgment(self.text, "SUPPORTED")]
        clients = [RecordingClient(outputs), RecordingClient(outputs)]
        a = OptimizedV4Verifier(self.settings, clients[0], self.config).verify(self.request)
        b = OptimizedV4M1FaithfulVerifier(self.settings, clients[1], self.config).verify(self.request)
        self.assertEqual(a.report, b.report)
        self.assertEqual(clients[0].inputs[1:], clients[1].inputs[1:])
        self.assertEqual(clients[0].inputs[0]["messages"][1:], clients[1].inputs[0]["messages"][1:])
        self.assertEqual(clients[0].inputs[0]["messages"][0]["content"], ORIGINAL_PROMPT)
        self.assertEqual(clients[1].inputs[0]["messages"][0]["content"], DECOMPOSE_PROMPT)
        self.assertEqual(b.telemetry["summary"], a.telemetry["summary"])
        self.assertEqual(b.telemetry["config"], a.telemetry["config"])
        self.assertEqual([c["phase"] for c in b.telemetry["calls"]], ["decompose", "verify", "review"])
        self.assertNotEqual(prompt_metadata()["decompose_sha256"], original_metadata()["decompose_sha256"])
        for key, value in original_metadata().items():
            if key.endswith("_sha256") and key != "decompose_sha256":
                self.assertEqual(prompt_metadata()[key], value)

    def test_extraction_repair_and_sentence_fallback_stay_bounded(self):
        advice = "Please inspect the latch."
        excluded = {"claims": [{"id": "c1", "claim_text": advice, "non_factual": True,
                                "reason": "An instruction without an asserted factual premise."}]}
        client = RecordingClient([{}, {}, excluded])
        result = OptimizedV4M1FaithfulVerifier(self.settings, client, self.config).verify(
            VerificationRequest(["The latch is metal."], advice))
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual([i["stage"] for i in client.inputs], ["decompose", "decompose_repair_1", "verify"])
        self.assertEqual(client.inputs[1]["messages"][0]["content"], DECOMPOSE_PROMPT)
        self.assertEqual(result.telemetry["summary"]["decomposition_fallback_chunks"], 1)
        self.assertEqual(len(result.telemetry["fallback_exclusions"]), 1)

    def test_exhausted_judgment_remains_error_with_experiment_metadata(self):
        config = replace(self.config, format_retries=0, targeted_retries=0)
        client = RecordingClient([extraction(self.text), {"claims": []}])
        with self.assertRaises(VerificationError) as caught:
            OptimizedV4M1FaithfulVerifier(self.settings, client, config).verify(self.request)
        self.assertEqual(caught.exception.code, "verification_failed")
        telemetry = caught.exception.telemetry
        self.assertEqual(telemetry["backend"], "optimized-v4-m1-faithful")
        self.assertEqual(telemetry["prompts"], prompt_metadata())
        self.assertEqual(telemetry["completion"]["completed"], 0)
        self.assertEqual(telemetry["completion"]["unfinished"], 1)

    def test_explicit_factory_selection_and_empty_input_do_not_change_defaults(self):
        verifier = build_verifier("optimized-v4-m1-faithful", self.settings, v4_config=self.config)
        self.assertIsInstance(verifier, OptimizedV4M1FaithfulVerifier)
        self.assertEqual(normalize_backend("optimized"), "optimized-v4.0")
        self.assertEqual(normalize_backend("optimized-v4"), "optimized-v4.0")
        result = verifier.verify(VerificationRequest([], " "))
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual(result.telemetry["calls"], [])
        self.assertEqual(result.telemetry["prompts"], prompt_metadata())


if __name__ == "__main__":
    unittest.main()
