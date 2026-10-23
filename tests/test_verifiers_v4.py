"""Synthetic fault injection for v4 isolation, provenance and bounded reviews.

No provider, credential, dataset label or network access is used here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from email.message import Message
from io import BytesIO
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from grounding.config import Settings
from grounding.config_v4 import StageConfig, V4Config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.contracts_v4 import validate_v4_report
from grounding.server import VerificationHandler
from grounding.verifiers_v4 import OptimizedV4Verifier, decomposition_chunks, extract_claims


def extraction(*texts: str, exclusions: tuple[str, ...] = ()) -> dict:
    return {
        "claims": [{"claim_text": text, "source_span": text} for text in texts],
        "non_factual_spans": [{"text": text, "reason": "Non-factual wording."} for text in exclusions],
    }


def conflict(span: str, quote: str, *, index: int = 0) -> dict:
    return {
        "claim_span": span, "evidence": [{"index": index, "quote": quote}],
        "kind": "direct", "explanation": "The quoted premise is incompatible under the same conditions.",
    }


def row(text: str, verdict: str = "SUPPORTED", *, claim_id: str = "c1", quote: str | None = None,
        index: int = 0, conflict_value=None) -> dict:
    return {
        "id": claim_id, "claim_text": text, "verdict": verdict,
        "reasoning": "The cited premise establishes the stated relation." if verdict != "UNSUPPORTED" else "A required premise is absent.",
        "citations": [] if verdict == "UNSUPPORTED" else [{"index": index, "quote": quote if quote is not None else text}],
        "derivation": "The assertion follows directly from the quoted premise." if verdict != "UNSUPPORTED" else "The necessary premise is not supplied.",
        "conflict": conflict_value,
    }


class FakeClient:
    def __init__(self, outputs=None, handler=None):
        self.outputs = list(outputs or [])
        self.handler = handler
        self.inputs = []
        self.lock = threading.Lock()

    def complete(self, messages, stage, telemetry):
        with self.lock:
            self.inputs.append({"messages": deepcopy(messages), "stage": stage, "telemetry_id": id(telemetry)})
            scripted = self.outputs.pop(0) if self.handler is None else None
        telemetry["calls"].append({
            "stage": stage, "attempt": 1, "response_text": None, "latency_seconds": 0.01,
            "http_status": 200, "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "finish_reason": "stop",
        })
        output = self.handler(messages, stage, telemetry) if self.handler is not None else scripted
        if isinstance(output, Exception):
            raise output
        telemetry["calls"][-1]["response_text"] = json.dumps(output, ensure_ascii=False)
        return deepcopy(output)


class V4VerifierTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(base_url="http://example.test", model="fake", api_key="fake-only")
        self.config = replace(V4Config(), max_workers=1)

    def run_case(self, answer, outputs=None, *, contexts=None, config=None, handler=None):
        client = FakeClient(outputs, handler)
        result = OptimizedV4Verifier(self.settings, client, config or self.config).verify(
            VerificationRequest(contexts if contexts is not None else [answer], answer),
        )
        return result, client

    def test_blank_and_model_classified_no_facts_keep_legacy_complete_schema(self):
        result, client = self.run_case(" \n", [])
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual(client.inputs, [])
        result, client = self.run_case("Thank you!", [extraction(exclusions=("Thank you!",))])
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose"])

    def test_exact_duplicate_same_occurrence_deduplicates_without_merge_call(self):
        text = "A is warm."
        result, client = self.run_case(text, [extraction(text, text), {"claims": [row(text)]}])
        self.assertEqual(len(result.report["claims"]), 1)
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify"])
        self.assertEqual(set(result.report), {"claims"})
        self.assertEqual(set(result.report["claims"][0]), {"claim_text", "verdict", "reasoning", "citations"})
        self.assertEqual(result.telemetry["summary"]["citation_repairs"], 0)

    def test_repeated_answer_occurrences_are_individually_accounted_for(self):
        text = "A is warm."
        claims, _ = extract_claims(extraction(text, text), text + " " + text, max_claims=64)
        self.assertEqual([claim["source_start"] for claim in claims], [0, len(text) + 1])
        self.assertEqual(len(claims), 2)

    def test_every_chunk_is_bounded_even_for_an_indivisible_long_sentence(self):
        text = "a" * 270 + "."
        spans = decomposition_chunks(text, 128)
        self.assertEqual("".join(text[start:end] for start, end in spans), text)
        self.assertTrue(all(end - start <= 128 for start, end in spans))

    def test_hard_chunk_boundaries_have_context_and_exact_global_offsets(self):
        answer = "a" * 270 + "."

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage == "decompose":
                self.assertIn("boundary_context", payload)
                return extraction(payload["generated_answer"])
            return {"claims": [row(claim["claim_text"], claim_id=claim["id"], quote=claim["source_span"]) for claim in payload["claims"]]}

        result, _ = self.run_case(answer, handler=handler, config=replace(self.config, decompose_chunk_chars=128))
        chunks = result.telemetry["extraction"]["chunks"]
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(chunk["hard_split"] for chunk in chunks))
        for claim in result.telemetry["extraction"]["claims"]:
            self.assertEqual(answer[claim["source_start"]:claim["source_end"]], claim["source_span"])

    def test_exhausted_extraction_uses_recorded_sentence_skeletons_and_continues(self):
        answer = "A is warm. B is cold."
        bad = extraction("A is warm.")
        result, client = self.run_case(answer, [
            bad, bad, {"claims": [row("A is warm."), row(" B is cold.", claim_id="c2", quote="B is cold.")]},
        ])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "decompose_repair_1", "verify"])
        self.assertEqual(result.telemetry["summary"]["decomposition_fallback_chunks"], 1)
        self.assertTrue(all(claim["extraction_fallback"] for claim in result.telemetry["extraction"]["claims"]))
        self.assertEqual(len(result.report["claims"]), 2)

    def test_invalid_extracted_unicode_uses_fallback_before_transport(self):
        text = "A is warm."
        bad = {"claims": [{"claim_text": "\ud800", "source_span": text}], "non_factual_spans": []}
        result, client = self.run_case(text, [bad, bad, {"claims": [row(text)]}])
        self.assertEqual(result.report["claims"][0]["claim_text"], text)
        self.assertTrue(result.telemetry["extraction"]["claims"][0]["extraction_fallback"])
        for call in client.inputs:
            for message in call["messages"]:
                message["content"].encode("utf-8")

    def test_failed_chunk_does_not_reextract_successful_chunk(self):
        first, second = "A" * 90 + ".", "B" * 90 + "."
        answer = first + " " + second
        counts = {"first": 0, "second": 0}

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage.startswith("decompose"):
                text = payload["generated_answer"]
                key = "first" if text.startswith("A") else "second"
                counts[key] += 1
                return extraction(text) if key == "first" else {"bad": "shape"}
            return {"claims": [row(claim["claim_text"], claim_id=claim["id"], quote=claim["source_span"]) for claim in payload["claims"]]}

        result, _ = self.run_case(answer, handler=handler, config=replace(self.config, decompose_chunk_chars=128))
        self.assertEqual(counts, {"first": 1, "second": 2})
        self.assertEqual([chunk["fallback"] for chunk in result.telemetry["extraction"]["chunks"]], [False, True])

    def test_failed_hard_cut_recovers_original_sentence_and_keeps_other_sentence(self):
        long_sentence, other = "A" * 270 + ".", "B is cold."
        answer = long_sentence + " " + other

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage.startswith("decompose"):
                text = payload["generated_answer"]
                if len(text) == 128 and "." in payload["boundary_context"]["after"]:
                    return {"bad": "failed middle of a sentence"}
                if other in text:
                    return extraction(text.split(" ")[0], other)
                return extraction(text)
            return {"claims": [row(claim["claim_text"], claim_id=claim["id"], quote=claim["source_span"]) for claim in payload["claims"]]}

        result, _ = self.run_case(answer, handler=handler, config=replace(self.config, decompose_chunk_chars=128))
        claims = result.telemetry["extraction"]["claims"]
        self.assertEqual([claim["claim_text"] for claim in claims], [long_sentence, other])
        self.assertTrue(claims[0]["hard_split_recovery"])
        self.assertNotIn("extraction_fallback", claims[1])
        recoveries = result.telemetry["extraction"]["hard_split_recoveries"]
        self.assertEqual(len(recoveries), 1)
        self.assertEqual(recoveries[0]["source_span"], long_sentence)
        self.assertGreaterEqual(len(recoveries[0]["superseded_claims"]), 3)

    def test_failed_hard_cut_advice_is_classified_only_as_one_complete_original_sentence(self):
        answer = "Please " + "restart " * 40 + "the app."

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage.startswith("decompose"):
                return {"bad": "shape"}
            self.assertEqual(len(payload["claims"]), 1)
            claim = payload["claims"][0]
            self.assertEqual(claim["claim_text"], answer)
            return {"claims": [{"id": claim["id"], "claim_text": answer, "non_factual": True, "reason": "Pure request."}]}

        result, _ = self.run_case(answer, handler=handler, contexts=[], config=replace(self.config, decompose_chunk_chars=128))
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual(len(result.telemetry["fallback_exclusions"]), 1)

    def test_non_factual_fallback_skeleton_is_excluded_without_a_fake_unsupported(self):
        text = "Please restart the app."
        result, _ = self.run_case(text, [
            {"bad": 1}, {"bad": 1},
            {"claims": [{"id": "c1", "claim_text": text, "non_factual": True, "reason": "A request, with no asserted premise."}]},
        ], contexts=[])
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual(len(result.telemetry["fallback_exclusions"]), 1)
        self.assertEqual(result.telemetry["summary"]["unsupported_review_triggers"], 0)

    def test_normal_claim_cannot_be_hidden_as_non_factual(self):
        text = "A is warm."
        bad = {"claims": [{"id": "c1", "claim_text": text, "non_factual": True, "reason": "Hide it."}]}
        client = FakeClient([extraction(text), bad, bad, bad])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, self.config).verify(VerificationRequest([text], text))
        self.assertEqual(raised.exception.code, "verification_failed")
        self.assertEqual(raised.exception.telemetry["fallback_exclusions"], [])

    def test_empty_context_for_extracted_facts_uses_no_verify_or_review_call(self):
        text = "A is warm."
        result, client = self.run_case(text, [extraction(text)], contexts=[" "])
        self.assertEqual(result.report["claims"][0]["verdict"], "UNSUPPORTED")
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose"])

    def test_empty_context_fallback_factuality_call_does_not_trigger_u_review(self):
        text = "A is warm."
        result, client = self.run_case(text, [{}, {}, {"claims": [row(text, "UNSUPPORTED")]}], contexts=[])
        self.assertEqual(result.report["claims"][0]["verdict"], "UNSUPPORTED")
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "decompose_repair_1", "verify"])

    def test_wrong_index_unique_exact_quote_repairs_without_semantic_call(self):
        text = "A is warm."
        result, client = self.run_case(text, [extraction(text), {"claims": [row(text, index=9)]}], contexts=[text])
        self.assertEqual(result.report["claims"][0]["citations"], [{"index": 0, "quote": text}])
        self.assertEqual(len(client.inputs), 2)
        self.assertEqual(result.telemetry["summary"]["citation_repairs"], 1)

    def test_fuzzy_content_change_requires_one_claim_rejudgment_and_preserves_sibling(self):
        first, second = "The item is blue.", "The limit is 20 kg."
        source = "The item is blue. The limit is 200 kg."
        bad = row(second, claim_id="c2", quote=second)
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"claims": [row(first), bad]},
            {"claims": [row(second, "CONTRADICTED", claim_id="c2", quote="The limit is 200 kg.", conflict_value=conflict("20 kg", "The limit is 200 kg."))]},
            {"claims": [row(second, "CONTRADICTED", claim_id="c2", quote="The limit is 200 kg.", conflict_value=conflict("20 kg", "The limit is 200 kg."))]},
        ], contexts=[source])
        self.assertEqual([claim["verdict"] for claim in result.report["claims"]], ["SUPPORTED", "CONTRADICTED"])
        self.assertEqual(result.telemetry["summary"]["targeted_reasks"], 1)
        targeted_payload = json.loads(client.inputs[2]["messages"][1]["content"])
        self.assertEqual([claim["id"] for claim in targeted_payload["claims"]], ["c2"])
        self.assertEqual(result.telemetry["summary"]["citation_repairs"], 0)
        chain = next(chain for chain in result.telemetry["verdict_chains"] if chain["claim_id"] == "c2")
        self.assertEqual(chain["steps"][0], {"stage": "verify_unvalidated", "verdict": "SUPPORTED", "validated": False})
        self.assertEqual(chain["steps"][1]["stage"], "targeted_requery")
        self.assertEqual(chain["steps"][1]["verdict"], "CONTRADICTED")
        self.assertEqual(chain["final_verdict"], "CONTRADICTED")

    def test_malformed_single_row_becomes_partial_without_reasking_valid_sibling(self):
        first, second = "A is warm.", "B is cold."
        invalid = {"id": "c2", "claim_text": second, "verdict": "SUPPORTED"}
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"claims": [row(first), invalid]}, {"claims": [invalid]}, {"claims": [invalid]},
        ])
        self.assertEqual(result.report["status"], "partial")
        self.assertEqual([claim["claim_text"] for claim in result.report["claims"]], [first])
        self.assertEqual(result.report["errors"][0]["id"], "c2")
        self.assertEqual(result.telemetry["summary"]["targeted_reasks"], 1)
        validate_v4_report(result.report, [first + " " + second])
        self.assertTrue(all("c1" not in json.loads(call["messages"][1]["content"])["claims"][0]["id"] for call in client.inputs[2:]))

    def test_invalid_unicode_in_requery_diagnostics_cannot_break_transport(self):
        first, second = "A is warm.", "B is cold."
        bad = row(second, claim_id="c2")
        bad["reasoning"] = "\ud800"
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"claims": [row(first), bad]},
            {"claims": [row(second, claim_id="c2")]},
        ])
        self.assertEqual(len(result.report["claims"]), 2)
        self.assertEqual(len(result.telemetry["targeted_reasks"]), 1)
        self.assertEqual(json.loads(client.inputs[-1]["messages"][1]["content"])["diagnostics"]["previous_result"]["reasoning"], "\ud800")
        for call in client.inputs:
            for message in call["messages"]:
                message["content"].encode("utf-8")

    def test_unhashable_unknown_id_does_not_crash_or_reask_good_rows(self):
        first, second = "A is warm.", "B is cold."
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"claims": [{"id": []}, row(first), row(second, claim_id="c2")]},
        ])
        self.assertEqual(len(result.report["claims"]), 2)
        self.assertEqual(len(client.inputs), 2)
        self.assertEqual(result.telemetry["summary"]["targeted_reasks"], 0)
        self.assertTrue(result.telemetry["protocol_events"])

    def test_reverse_order_is_deterministically_restored_by_immutable_ids(self):
        first, second = "A is warm.", "B is cold."
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"claims": [row(second, claim_id="c2"), row(first)]},
        ])
        self.assertEqual([claim["claim_text"] for claim in result.report["claims"]], [first, second])
        self.assertEqual(len(client.inputs), 2)

    def test_review_keeps_valid_requested_row_despite_extra_malformed_rows(self):
        text = "A is warm."
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "UNSUPPORTED")]},
            {"claims": [{"id": []}, row(text), {"id": "unknown"}]},
        ])
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        self.assertEqual(len(client.inputs), 3)
        self.assertEqual(result.telemetry["summary"]["format_repairs"], 0)
        self.assertEqual(result.telemetry["summary"]["targeted_reasks"], 0)
        self.assertEqual(result.telemetry["protocol_events"][-1]["positions"], [0, 2])

    def test_batch_envelope_failure_retries_only_that_batch_then_returns_partial(self):
        first, second = "A is warm.", "B is cold."
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), {"bad": 1}, {"bad": 2}, {"claims": [row(second, claim_id="c2")]},
        ], config=replace(self.config, max_batch_claims=1))
        self.assertEqual(result.report["status"], "partial")
        self.assertEqual(result.report["claims"][0]["claim_text"], second)
        self.assertEqual(result.report["errors"][0]["id"], "c1")
        self.assertEqual([call["stage"] for call in client.inputs], ["decompose", "verify", "verify_batch_retry_1", "verify"])
        self.assertEqual(result.telemetry["summary"]["batch_retries"], 1)

    def test_batch_transport_failure_is_not_format_retry_or_unsupported(self):
        first, second = "A is warm.", "B is cold."
        result, client = self.run_case(first + " " + second, [
            extraction(first, second), VerificationError("upstream_timeout", "Timeout.", 504),
            {"claims": [row(second, claim_id="c2")]},
        ], config=replace(self.config, max_batch_claims=1))
        self.assertEqual(result.report["errors"][0]["code"], "upstream_timeout")
        self.assertEqual(len(client.inputs), 3)
        self.assertEqual(result.telemetry["summary"]["batch_retries"], 0)

    def test_all_claims_failed_raise_and_retain_each_error(self):
        text = "A is warm."
        client = FakeClient([extraction(text), {}, {}])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, self.config).verify(VerificationRequest([text], text))
        self.assertEqual(raised.exception.code, "verification_failed")
        self.assertEqual(len(raised.exception.telemetry["errors"]), 1)
        self.assertEqual(raised.exception.telemetry["completion"]["coverage"], 0)

    def test_all_upstream_failures_preserve_original_code_and_http_status(self):
        first, second = "A is warm.", "B is cold."
        for code, status in (("upstream_timeout", 504), ("upstream_http_error", 503),
                             ("upstream_http_error", 502), ("upstream_connection_error", 502)):
            with self.subTest(code=code, status=status):
                client = FakeClient([extraction(first, second),
                                     VerificationError(code, "Original upstream error.", status),
                                     VerificationError(code, "Original upstream error.", status)])
                verifier = OptimizedV4Verifier(self.settings, client, replace(self.config, max_batch_claims=1))
                with self.assertRaises(VerificationError) as raised:
                    verifier.verify(VerificationRequest([first + " " + second], first + " " + second))
                self.assertEqual((raised.exception.code, raised.exception.status), (code, status))
                self.assertEqual(raised.exception.message, "Original upstream error.")
                self.assertEqual(raised.exception.telemetry["completion"]["coverage"], 0)
                self.assertEqual(len(raised.exception.telemetry["error_statuses"]), 2)
                self.assertTrue(all("status" not in error for error in raised.exception.telemetry["errors"]))

    def test_all_review_timeouts_preserve_timeout_status(self):
        first, second = "A is warm.", "B is cold."
        client = FakeClient([extraction(first, second),
                             {"claims": [row(first, "UNSUPPORTED"), row(second, "UNSUPPORTED", claim_id="c2")]},
                             VerificationError("upstream_timeout", "Review timed out.", 504),
                             VerificationError("upstream_timeout", "Review timed out.", 504)])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, self.config).verify(
                VerificationRequest([first + " " + second], first + " " + second))
        self.assertEqual((raised.exception.code, raised.exception.status), ("upstream_timeout", 504))
        self.assertEqual([error["stage"] for error in raised.exception.telemetry["errors"]], ["review", "review"])

    def test_mixed_upstream_http_statuses_keep_generic_failure(self):
        first, second = "A is warm.", "B is cold."
        client = FakeClient([extraction(first, second),
                             VerificationError("upstream_http_error", "Rate limit.", 503),
                             VerificationError("upstream_http_error", "Bad gateway.", 502)])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, replace(self.config, max_batch_claims=1)).verify(
                VerificationRequest([first + " " + second], first + " " + second))
        self.assertEqual((raised.exception.code, raised.exception.status), ("verification_failed", 502))

    def test_http_returns_original_failure_status_or_200_for_partial(self):
        first, second = "A is warm.", "B is cold."
        for code, expected_status, partial in (("upstream_timeout", 504, False),
                                               ("upstream_http_error", 503, False),
                                               ("upstream_timeout", 200, True)):
            with self.subTest(code=code, expected_status=expected_status, partial=partial):
                failure_status = 504 if code == "upstream_timeout" else 503
                client = FakeClient([extraction(first, second),
                                     VerificationError(code, "Upstream failed.", failure_status),
                                     {"claims": [row(second, claim_id="c2")]} if partial else
                                     VerificationError(code, "Upstream failed.", failure_status)])
                verifier = OptimizedV4Verifier(self.settings, client, replace(self.config, max_batch_claims=1))
                payload = json.dumps({"context_passages": [first + " " + second],
                                      "generated_answer": first + " " + second}).encode("utf-8")
                handler = VerificationHandler.__new__(VerificationHandler)
                handler.path = "/verify"
                handler.headers = Message()
                handler.headers["Content-Type"] = "application/json"
                handler.headers["Content-Length"] = str(len(payload))
                handler.rfile = BytesIO(payload)
                handler.server = SimpleNamespace(verifier=verifier, slots=threading.BoundedSemaphore(1))
                handler.send_json = Mock()
                handler.do_POST()
                handler.send_json.assert_called_once()
                status, response = handler.send_json.call_args.args
                self.assertEqual(status, expected_status)
                if partial:
                    self.assertEqual(response["status"], "partial")
                    self.assertEqual(response["claims"][0]["claim_text"], second)
                    self.assertNotIn("status", response["errors"][0])
                else:
                    self.assertEqual(response["error"]["code"], code)

    def test_u_review_can_find_support_and_records_one_step_and_full_sources(self):
        text = "A is warm."
        contexts = ["Unrelated premise.", text]
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [row(text, index=1)]},
        ], contexts=contexts)
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        event = result.telemetry["unsupported_reviews"][0]
        self.assertEqual(event["after_verdict"], "SUPPORTED")
        self.assertTrue(event["derivation"])
        self.assertEqual(json.loads(client.inputs[-1]["messages"][1]["content"])["context_passages"], [{"index": i, "text": passage} for i, passage in enumerate(contexts)])

    def test_c_to_u_to_c_uses_each_logical_review_once_without_cycle(self):
        text, source = "A is cold.", "A is warm."
        final = row(text, "CONTRADICTED", quote=source, conflict_value=conflict("cold", source))
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "CONTRADICTED", quote=source)]},
            {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [final]},
        ], contexts=[source])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual([call["stage"] for call in client.inputs], ["decompose", "verify", "contradiction_review", "unsupported_review"])
        self.assertEqual([step["verdict"] for step in result.telemetry["verdict_chains"][0]["steps"]], ["CONTRADICTED", "UNSUPPORTED", "CONTRADICTED"])

    def test_invalid_u_to_c_conflict_gets_only_one_format_repair_no_c_review(self):
        text, source = "A is cold.", "A is warm."
        bad = row(text, "CONTRADICTED", quote=source)
        good = row(text, "CONTRADICTED", quote=source, conflict_value=conflict("cold", source))
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [bad]}, {"claims": [good]},
        ], contexts=[source])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual([call["stage"] for call in client.inputs][-2:], ["unsupported_review", "unsupported_review_repair_1"])
        self.assertEqual(result.telemetry["contradiction_reviews"], [])
        self.assertEqual(result.telemetry["summary"]["unsupported_review_triggers"], 1)

    def test_exhausted_u_to_c_conflict_becomes_error_not_u(self):
        text, source = "A is cold.", "A is warm."
        bad = {"claims": [row(text, "CONTRADICTED", quote=source)]}
        client = FakeClient([extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, bad, bad])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, self.config).verify(VerificationRequest([source], text))
        telemetry = raised.exception.telemetry
        self.assertEqual(telemetry["contradiction_reviews"], [])
        self.assertEqual(len(telemetry["unsupported_reviews"]), 1)
        self.assertEqual(len(telemetry["errors"]), 1)

    def test_final_review_citations_also_receive_safe_wrong_index_repair(self):
        text = "A is warm."
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [row(text, index=88)]},
        ])
        self.assertEqual(result.report["claims"][0]["citations"][0]["index"], 0)
        self.assertEqual(result.telemetry["summary"]["citation_repairs"], 1)
        self.assertEqual(len(client.inputs), 3)

    def test_final_u_review_can_spend_one_remaining_targeted_quote_rejudgment(self):
        text, source = "A is cold.", "A is warm."
        result, client = self.run_case(text, [
            extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [row(text, quote="A is very warm.")]},
            {"claims": [row(text, "CONTRADICTED", quote=source, conflict_value=conflict("cold", source))]},
        ], contexts=[source])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual(len(client.inputs), 4)
        self.assertEqual(len(result.telemetry["unsupported_reviews"]), 1)
        self.assertEqual(result.telemetry["contradiction_reviews"], [])
        self.assertEqual(len(result.telemetry["targeted_reasks"]), 1)
        event = result.telemetry["targeted_reasks"][0]
        self.assertEqual(event["kind"], "targeted")
        self.assertEqual(event["previous_result"]["citations"][0]["quote"], "A is very warm.")
        self.assertEqual(event["after_verdict"], "CONTRADICTED")
        chain = result.telemetry["verdict_chains"][0]
        self.assertEqual([(step["stage"], step["verdict"]) for step in chain["steps"]], [
            ("verify", "UNSUPPORTED"), ("unsupported_review_unvalidated", "SUPPORTED"),
            ("unsupported_review_targeted", "CONTRADICTED"), ("unsupported_review", "CONTRADICTED"),
        ])
        self.assertEqual(chain["final_verdict"], "CONTRADICTED")

    def test_final_u_review_cannot_start_second_targeted_semantic_requery(self):
        text, source = "A is cold.", "A is warm."
        client = FakeClient([
            extraction(text), {"claims": [row(text, quote="A is very warm.")]},
            {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [row(text, quote="A is very warm.")]},
        ])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, self.config).verify(VerificationRequest([source], text))
        self.assertEqual(raised.exception.telemetry["errors"][0]["code"], "citation_requery_required")
        self.assertEqual(len(client.inputs), 4)
        self.assertEqual(len(raised.exception.telemetry["targeted_reasks"]), 1)

    def test_numeric_signal_on_supported_triggers_model_review_not_code_verdict(self):
        text, source = "The speed is 3 m/s.", "The speed is 2 m/s."
        reviewed = row(text, "CONTRADICTED", quote=source, conflict_value=conflict("3 m/s", source))
        result, client = self.run_case(text, [extraction(text), {"claims": [row(text, quote=source)]}, {"claims": [reviewed]}], contexts=[source])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual(len(result.telemetry["numeric_signals"]), 1)
        self.assertEqual(result.telemetry["contradiction_reviews"][0]["before_verdict"], "SUPPORTED")
        self.assertEqual(client.inputs[-1]["stage"], "contradiction_review")

    def test_numeric_signal_on_valid_contradiction_triggers_only_one_model_review(self):
        text, source = "The speed is 3 m/s.", "The speed is 2 m/s."
        contradicted = row(text, "CONTRADICTED", quote=source, conflict_value=conflict("3 m/s", source))
        result, client = self.run_case(text, [
            extraction(text), {"claims": [contradicted]}, {"claims": [contradicted]},
        ], contexts=[source])
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual(len(result.telemetry["numeric_signals"]), 1)
        self.assertTrue(result.telemetry["contradiction_checks"][0]["passed"])
        self.assertEqual(len(result.telemetry["contradiction_reviews"]), 1)
        self.assertEqual([call["stage"] for call in client.inputs], ["decompose", "verify", "contradiction_review"])

    def test_batch_budget_and_size_never_remove_common_evidence(self):
        texts = [f"Item {letter} is warm." for letter in "ABC"]
        contexts = [" ".join(texts), "A separate supporting paragraph."]

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage == "decompose":
                return extraction(*texts)
            self.assertEqual([passage["text"] for passage in payload["context_passages"]], contexts)
            return {"claims": [row(claim["claim_text"], claim_id=claim["id"]) for claim in payload["claims"]]}

        result, _ = self.run_case(" ".join(texts), handler=handler, contexts=contexts,
                                  config=replace(self.config, verify_batch_token_budget=128))
        self.assertEqual(len(result.telemetry["batches"]), 3)
        self.assertTrue(all(batch["oversize_single_claim"] for batch in result.telemetry["batches"]))
        self.assertGreater(result.telemetry["common_input_estimated_tokens"], 0)

    def test_parallel_batches_own_telemetry_and_aggregate_in_answer_order(self):
        texts = ["A is warm.", "B is cold."]
        barrier = threading.Barrier(2, timeout=3)

        def handler(messages, stage, telemetry):
            payload = json.loads(messages[1]["content"])
            if stage == "decompose":
                return extraction(*texts)
            barrier.wait()
            claim = payload["claims"][0]
            return {"claims": [row(claim["claim_text"], claim_id=claim["id"])]}

        result, client = self.run_case(" ".join(texts), handler=handler, config=replace(self.config, max_batch_claims=1, max_workers=2))
        calls = [call for call in client.inputs if call["stage"] == "verify"]
        self.assertEqual(len({call["telemetry_id"] for call in calls}), 2)
        self.assertEqual([claim["claim_text"] for claim in result.report["claims"]], texts)
        self.assertEqual([batch["batch_id"] for batch in result.telemetry["batches"]], ["b1", "b2"])
        self.assertEqual(sum(call["usage"]["completion_tokens"] for call in result.telemetry["calls"]), 15)

    def test_overall_claim_capacity_raises_without_silent_truncation(self):
        answer = "A is warm. B is cold."
        client = FakeClient([extraction("A is warm.", "B is cold."), extraction("A is warm.", "B is cold.")])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV4Verifier(self.settings, client, replace(self.config, max_claims=1)).verify(VerificationRequest([answer], answer))
        self.assertEqual(raised.exception.code, "claim_limit_exceeded")
        self.assertEqual(len(raised.exception.telemetry["extraction"]["claims"]), 2)
        self.assertEqual(len(client.inputs), 2)

    def test_stage_configuration_is_recorded_for_all_calls(self):
        text = "A is warm."
        config = replace(self.config, decompose=StageConfig("enabled", 4096),
                         verify=StageConfig("disabled", 8192), review=StageConfig("enabled", 16384))
        result, _ = self.run_case(text, [extraction(text), {"claims": [row(text, "UNSUPPORTED")]}, {"claims": [row(text)]}], config=config)
        self.assertEqual([call["phase"] for call in result.telemetry["calls"]], ["decompose", "verify", "review"])
        self.assertEqual([call["thinking"] for call in result.telemetry["calls"]], ["enabled", "disabled", "enabled"])
        self.assertEqual([call["max_output_tokens"] for call in result.telemetry["calls"]], [4096, 8192, 16384])
        self.assertEqual(result.telemetry["config"], config.public_dict())


if __name__ == "__main__":
    unittest.main()
