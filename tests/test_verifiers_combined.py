"""H2/H3 fault injection with fixed synthetic claims to isolate verification."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import threading
import unittest

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.evidence_combined import EVIDENCE_PROTOCOL
from grounding.prompts_combined import BLIND_REVIEW_PROMPT, prompt_metadata
from grounding.verifiers_combined import OptimizedV4CombinedVerifier
from grounding.verifiers_v4 import sentence_spans


def row(text, verdict="SUPPORTED", *, claim_id="c1", ids=None, considered=None, conflict=None):
    ids = ([] if verdict == "UNSUPPORTED" else ["p0u1"]) if ids is None else ids
    return {"evidence_protocol": EVIDENCE_PROTOCOL, "id": claim_id, "claim_text": text,
            "verdict": verdict, "reasoning": "A source-grounded judgment.",
            "considered_evidence_ids": list(ids) if considered is None else considered,
            "decision_evidence_ids": ids, "derivation": "The given premises establish the relation.",
            "conflict": conflict}


def conflict(span, ids=None):
    return {"claim_span": span, "evidence_ids": ids or ["p0u1"], "kind": "direct",
            "explanation": "The same entity has incompatible properties under the same conditions."}


class FakeClient:
    def __init__(self, handler):
        self.handler, self.inputs, self.lock = handler, [], threading.Lock()

    def complete(self, messages, stage, telemetry):
        with self.lock:
            self.inputs.append({"messages": deepcopy(messages), "stage": stage, "telemetry_id": id(telemetry)})
        call = {"stage": stage, "attempt": 1, "model": "synthetic", "system_fingerprint": "test-only",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "response_text": None}
        telemetry["calls"].append(call)
        result = self.handler(messages, stage)
        call["response_text"] = json.dumps(result)
        return result


class FixedClaimsVerifier(OptimizedV4CombinedVerifier):
    """Offline M3 isolation only; production M1 is not changed."""

    def _decompose(self, answer, telemetry):
        claims = [{"id": f"c{i}", "claim_text": answer[start:end].strip(),
                   "source_span": answer[start:end], "source_start": start, "source_end": end,
                   "answer_background": [{"text": "Unverified explanatory background only."}]}
                  for i, (start, end) in enumerate(sentence_spans(answer), 1) if answer[start:end].strip()]
        telemetry["extraction"] = {"claims": claims, "chunks": []}
        return claims


class CombinedVerifierTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(base_url="http://example.test", model="fake", api_key="fake-only")
        self.config = replace(V4Config(), max_workers=1, format_retries=0)

    def execute(self, text, handler, *, contexts=None, config=None):
        client = FakeClient(handler)
        verifier = FixedClaimsVerifier(self.settings, client, config or self.config)
        return verifier.verify(VerificationRequest(contexts or [text], text)), client

    def test_all_sources_visible_exact_quotes_no_general_supported_review(self):
        contexts = ["The object is red.", "The object is round."]
        text = "The object is red and round."
        def handler(messages, stage):
            self.assertEqual(stage, "verify")
            payload = json.loads(messages[1]["content"])
            self.assertEqual(payload["evidence_protocol"], EVIDENCE_PROTOCOL)
            self.assertEqual(["".join(u["text"] for u in p["source_units"]) for p in payload["context_passages"]], contexts)
            self.assertIn("answer_background", payload["claims"][0])
            return {"claims": [row(text, ids=["p0u1", "p1u1"])]}
        result, client = self.execute(text, handler, contexts=contexts)
        self.assertEqual(len(client.inputs), 1)
        self.assertEqual(result.report["claims"][0]["citations"], [{"index": i, "quote": c} for i, c in enumerate(contexts)])
        self.assertEqual(result.telemetry["backend"], "optimized-v4-combined")
        self.assertEqual(result.telemetry["prompts"]["verify_sha256"], prompt_metadata()["verify_sha256"])
        event = next(e for e in result.telemetry["protocol_events"] if e["kind"] == "evidence_ir_transition")
        self.assertEqual(event["raw_internal"], event["validated_internal"])
        self.assertEqual(event["public_projection"], result.report["claims"][0])

    def test_unsupported_review_blinds_initial_verdict_reasoning_and_candidates(self):
        text = "A is warm."
        def handler(messages, stage):
            if stage == "verify":
                initial = row(text, "UNSUPPORTED", considered=["p0u1"])
                initial["reasoning"] = "SECRET_INITIAL_REASONING"
                return {"claims": [initial]}
            self.assertEqual(stage, "unsupported_review")
            self.assertEqual(messages[0]["content"], BLIND_REVIEW_PROMPT)
            payload = json.loads(messages[1]["content"])
            self.assertNotIn("diagnostics", payload)
            self.assertNotIn("SECRET_INITIAL_REASONING", json.dumps(messages))
            self.assertNotIn("previous_result", json.dumps(messages))
            return {"claims": [row(text, "CONTRADICTED", conflict=conflict("warm"))]}
        result, client = self.execute(text, handler, contexts=["A is cold."])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual([c["stage"] for c in client.inputs], ["verify", "unsupported_review"])
        self.assertEqual(result.telemetry["summary"]["contradiction_review_triggers"], 0)
        self.assertTrue(result.telemetry["unsupported_reviews"][0]["initial_verdict_blinded"])

    def test_invalid_initial_c_gets_one_blinded_c_then_one_blinded_u_review(self):
        text = "A is warm."
        def handler(messages, stage):
            if stage == "verify":
                return {"claims": [row(text, "CONTRADICTED")]}
            self.assertEqual(messages[0]["content"], BLIND_REVIEW_PROMPT)
            self.assertNotIn("diagnostics", json.loads(messages[1]["content"]))
            if stage == "contradiction_review":
                return {"claims": [row(text, "UNSUPPORTED", considered=["p0u1"])]}
            return {"claims": [row(text, "CONTRADICTED", conflict=conflict("warm"))]}
        result, client = self.execute(text, handler, contexts=["A is cold."])
        self.assertEqual([c["stage"] for c in client.inputs], ["verify", "contradiction_review", "unsupported_review"])
        self.assertEqual(result.telemetry["summary"]["contradiction_review_triggers"], 1)
        self.assertEqual(result.telemetry["summary"]["unsupported_review_triggers"], 1)
        transitions = [event for event in result.telemetry["protocol_events"] if event["kind"] == "evidence_ir_transition"]
        self.assertEqual([event["conflict_gate_pending"] for event in transitions], [True, False, False])

    def test_numeric_signal_from_s_triggers_blinded_c_review_without_code_verdict(self):
        text = "The limit is 20 kg."
        def handler(messages, stage):
            if stage == "verify":
                return {"claims": [row(text)]}
            self.assertEqual(stage, "contradiction_review")
            self.assertNotIn("diagnostics", json.loads(messages[1]["content"]))
            return {"claims": [row(text, "CONTRADICTED", conflict=conflict("20 kg"))]}
        result, _ = self.execute(text, handler, contexts=["The limit is 200 kg."])
        self.assertTrue(result.telemetry["numeric_signals"])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")

    def test_invalid_u_decision_evidence_spends_targeted_retry_never_silently_drops(self):
        text = "A is warm."
        def handler(messages, stage):
            if stage == "verify":
                return {"claims": [row(text, "UNSUPPORTED", ids=["p0u1"])]}
            self.assertEqual(stage, "verify_claim_requery")
            self.assertIn("never silently removed", messages[1]["content"])
            return {"claims": [row(text)]}
        result, client = self.execute(text, handler)
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        self.assertEqual(len(result.telemetry["targeted_reasks"]), 1)
        self.assertEqual(len(client.inputs), 2)
        events = [e for e in result.telemetry["protocol_events"] if e["kind"] == "evidence_ir_transition"]
        self.assertEqual([e["status"] for e in events], ["invalid", "validated"])

    def test_unknown_ids_exhaust_to_partial_preserving_successful_sibling(self):
        text = "A is warm. B is cold."
        def handler(messages, stage):
            claims = json.loads(messages[1]["content"])["claims"]
            return {"claims": [row(c["claim_text"], claim_id=c["id"], ids=["p0u1"] if c["id"] == "c1" else ["bad"]) for c in claims]}
        result, client = self.execute(text, handler)
        self.assertEqual(result.report["status"], "partial")
        self.assertEqual([c["claim_text"] for c in result.report["claims"]], ["A is warm."])
        self.assertEqual(result.report["errors"][0]["id"], "c2")
        self.assertEqual(len(result.telemetry["targeted_reasks"]), 1)
        self.assertEqual(len(client.inputs), 2)

    def test_invalid_u_to_c_conflict_fails_without_another_c_review(self):
        text = "A is warm."
        def handler(messages, stage):
            return {"claims": [row(text, "UNSUPPORTED", considered=["p0u1"]) if stage == "verify" else row(text, "CONTRADICTED")]}
        client = FakeClient(handler)
        with self.assertRaises(VerificationError) as raised:
            FixedClaimsVerifier(self.settings, client, self.config).verify(VerificationRequest([text], text))
        self.assertEqual([c["stage"] for c in client.inputs], ["verify", "unsupported_review"])
        self.assertEqual(raised.exception.telemetry["backend"], "optimized-v4-combined")
        self.assertEqual(raised.exception.telemetry["contradiction_reviews"], [])

    def test_review_format_repair_can_see_own_output_but_not_initial_result(self):
        text = "A is warm."
        def handler(messages, stage):
            if stage == "verify":
                value = row(text, "UNSUPPORTED", considered=["p0u1"])
                value["reasoning"] = "SECRET_FIRST_JUDGMENT"
                return {"claims": [value]}
            self.assertNotIn("SECRET_FIRST_JUDGMENT", json.dumps(messages))
            if stage == "unsupported_review":
                value = row(text, "CONTRADICTED")
                value["reasoning"] = "OWN_REVIEW_OUTPUT"
                return {"claims": [value]}
            self.assertEqual(stage, "unsupported_review_repair_1")
            self.assertIn("OWN_REVIEW_OUTPUT", json.dumps(messages))
            return {"claims": [row(text, "CONTRADICTED", conflict=conflict("warm"))]}
        result, client = self.execute(text, handler, contexts=["A is cold."], config=replace(self.config, format_retries=1))
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual(len(client.inputs), 3)

    def test_shared_instance_concurrent_requests_keep_source_identity_local(self):
        barrier = threading.Barrier(2)
        def handler(messages, stage):
            payload = json.loads(messages[1]["content"])
            barrier.wait(timeout=10)
            return {"claims": [row(payload["claims"][0]["claim_text"])]}
        client = FakeClient(handler)
        verifier = FixedClaimsVerifier(self.settings, client, self.config)
        requests = [VerificationRequest([text], text) for text in ("A is warm.", "B is cold.")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(verifier.verify, requests))
        for request, result in zip(requests, results):
            self.assertEqual(result.report["claims"][0]["citations"], [{"index": 0, "quote": request.generated_answer}])
            self.assertEqual(len(result.telemetry["calls"]), 1)
        self.assertNotEqual(client.inputs[0]["telemetry_id"], client.inputs[1]["telemetry_id"])

    def test_all_upstream_timeouts_keep_status_and_combined_metadata(self):
        def handler(messages, stage):
            raise VerificationError("upstream_timeout", "Synthetic timeout", 504)
        client = FakeClient(handler)
        with self.assertRaises(VerificationError) as raised:
            FixedClaimsVerifier(self.settings, client, self.config).verify(VerificationRequest(["A is warm."], "A is warm."))
        self.assertEqual(raised.exception.status, 504)
        self.assertEqual(raised.exception.telemetry["backend"], "optimized-v4-combined")


if __name__ == "__main__":
    unittest.main()
