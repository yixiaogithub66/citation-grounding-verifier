"""Behavioral regression tests for v3 merging and contradiction review."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from grounding.config import Settings
from grounding.contracts import VerificationError, VerificationRequest
from grounding.verifiers_v3 import OptimizedV3Verifier, _sentences, merge_candidates


class FakeClient:
    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.inputs: list[dict] = []

    def complete(self, messages: list, stage: str, telemetry: dict) -> dict:
        self.inputs.append({"messages": list(messages), "stage": stage})
        output = self.outputs.pop(0)
        telemetry["calls"].append({
            "stage": stage, "attempt": 1, "response_text": None, "latency_seconds": 0.01,
            "http_status": 200, "usage": {"prompt_tokens": 10, "completion_tokens": 10}, "finish_reason": "stop",
        })
        if isinstance(output, Exception):
            raise output
        telemetry["calls"][-1]["response_text"] = json.dumps(output)
        return output


def extraction(*texts: str, exclusions: tuple[str, ...] = ()) -> dict:
    return {
        "claims": [{"claim_text": text, "source_span": text} for text in texts],
        "non_factual_spans": [{"text": text, "reason": "Connective."} for text in exclusions],
    }


def merge_decision(*groups: list[str], candidate_id: str = "m1") -> dict:
    return {"candidate_id": candidate_id, "groups": [
        {"claim_ids": group, "reason": "Same assertion." if len(group) > 1 else "Keep a distinct assertion."}
        for group in groups
    ]}


def row(text: str, verdict: str, *, index: int = 0, quote: str = "The speed is 2 m/s.", claim_id: str = "c1", conflict=None) -> dict:
    return {
        "id": claim_id, "claim_text": text, "verdict": verdict, "reasoning": "Compared against the stated premise.",
        "citations": [] if verdict == "UNSUPPORTED" else [{"index": index, "quote": quote}],
        "conflict": conflict,
    }


def conflict(span: str, quote: str = "The speed is 2 m/s.", *, index: int = 0, kind: str = "direct") -> dict:
    return {"claim_span": span, "evidence": [{"index": index, "quote": quote}], "kind": kind,
            "explanation": "The stated value is incompatible with the claim under the same conditions."}


def review_row(text: str, verdict: str, **kwargs) -> dict:
    result = row(text, verdict, **kwargs)
    result["review_evidence"] = [{"index": kwargs.get("index", 0), "quote": kwargs.get("quote", "The speed is 2 m/s.")}]
    return result


class V3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(base_url="http://example.test", model="fake", api_key="fake-test-only")

    def run_verifier(self, answer: str, outputs: list, contexts: list[str] | None = None):
        client = FakeClient(outputs)
        result = OptimizedV3Verifier(self.settings, client).verify(
            VerificationRequest(contexts if contexts is not None else [], answer),
        )
        return result, client

    def test_json_mode_provider_contract_for_every_stage_including_merge_and_verify(self) -> None:
        answer = "The rate is 2, in other words rate = 2."
        source = "rate = 2"
        outputs = [
            extraction("The rate is 2", "rate = 2.", exclusions=("in other words",)),
            {"decisions": [merge_decision(["c1", "c2"])]},
            {"claims": [row(answer, "CONTRADICTED", quote=source)]},
            {"claims": [review_row(answer, "SUPPORTED", quote=source)]},
        ]

        class Response(io.BytesIO):
            status = 200

        def transport(request, *, timeout):
            body = json.loads(request.data)
            self.assertEqual(body["response_format"], {"type": "json_object"})
            self.assertTrue(any("json" in message["content"].lower() for message in body["messages"]))
            content = json.dumps(outputs.pop(0))
            return Response(json.dumps({
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            }).encode("utf-8"))

        with patch("grounding.client.urlopen", side_effect=transport):
            result = OptimizedV3Verifier(self.settings).verify(VerificationRequest([source], answer))
        self.assertEqual([call["stage"] for call in result.telemetry["calls"]], [
            "decompose", "merge", "verify", "contradiction_review",
        ])
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        self.assertEqual(outputs, [])

    def test_blank_and_semantic_no_facts(self) -> None:
        result, client = self.run_verifier("  ", [])
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual(client.inputs, [])
        result, client = self.run_verifier("Thank you!", [extraction(exclusions=("Thank you!",))])
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose"])

    def test_no_candidates_adds_no_merge_or_review_call(self) -> None:
        text = "The speed is 2 m/s."
        result, client = self.run_verifier(text, [extraction(text), {"claims": [row(text, "SUPPORTED")]}], [text])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify"])
        self.assertEqual(result.telemetry["backend"], "optimized-v3")
        self.assertEqual(result.telemetry["prompts"]["version"], "grounding-v3")
        self.assertEqual(result.telemetry["merge_audits"], [])
        self.assertEqual(set(result.report["claims"][0]), {"claim_text", "verdict", "reasoning", "citations"})

    def test_exact_duplicate_reaches_semantic_merge_and_preserves_sentence(self) -> None:
        text = "The speed is 2 m/s."
        result, client = self.run_verifier(text, [
            extraction(text, text), {"decisions": [merge_decision(["c1", "c2"])]},
        ])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "merge"])
        self.assertEqual([item["claim_text"] for item in result.report["claims"]], [text])
        self.assertTrue(result.telemetry["merge_audits"][0]["merged"])
        self.assertEqual(result.telemetry["merge_audits"][0]["input_count"], 2)
        self.assertEqual(result.telemetry["merge_audits"][0]["output_count"], 1)

    def test_repeated_source_occurrences_have_ordered_distinct_offsets(self) -> None:
        first, middle = "A is warm.", "B is cool."
        answer = first + " " + middle + " " + first
        verifier = OptimizedV3Verifier(self.settings, FakeClient([]))
        claims = verifier._extract(extraction(first, middle, first), answer)
        self.assertEqual([item["source_start"] for item in claims], [0, answer.index(middle), answer.rindex(first)])
        self.assertEqual(merge_candidates(claims, answer), [])

    def test_repeated_adjacent_sentence_deduplicates_wording_but_covers_both_occurrences(self) -> None:
        text = "A is warm."
        answer = text + " " + text
        result, _ = self.run_verifier(answer, [extraction(text, text), {"decisions": [merge_decision(["c1", "c2"])]}])
        self.assertEqual(result.report["claims"][0]["claim_text"], text)
        self.assertEqual(result.telemetry["extraction"]["claims_after_merge"][0]["source_span"], answer)

    def test_restatement_merge_has_answer_only_input_and_copies_original_sentence(self) -> None:
        answer = "The rate is 2, in other words rate = 2."
        source = "The rate is 2."
        result, client = self.run_verifier(answer, [
            extraction("The rate is 2", "rate = 2.", exclusions=("in other words",)),
            {"decisions": [merge_decision(["c1", "c2"])]},
            {"claims": [row(answer, "SUPPORTED", quote=source)]},
        ], [source])
        payload = json.loads(client.inputs[1]["messages"][1]["content"])
        self.assertEqual(set(payload), {"generated_answer", "claims", "candidates"})
        self.assertNotIn("context_passages", payload)
        self.assertEqual(result.report["claims"][0]["claim_text"], answer)

    def test_marker_does_not_merge_prose_and_formula_with_different_values(self) -> None:
        left, right = "The rate is 2", "rate = 3."
        answer, source = left + ", i.e. " + right, "rate = 2"
        result, client = self.run_verifier(answer, [
            extraction(left, right, exclusions=("i.e.",)),
            {"decisions": [merge_decision(["c1"], ["c2"])]},
            {"claims": [row(left, "SUPPORTED", quote=source), row(
                right, "CONTRADICTED", quote=source, claim_id="c2", conflict=conflict("3", source),
            )]},
        ], [source])
        self.assertEqual([item["verdict"] for item in result.report["claims"]], ["SUPPORTED", "CONTRADICTED"])
        self.assertTrue(all(not item["merged"] for item in result.telemetry["merge_audits"]))
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "merge", "verify"])

    def test_abbreviation_and_decimal_periods_do_not_end_sentences(self) -> None:
        for abbreviation in ("i.e.", "e.g."):
            first = "The rate is 2.5, " + abbreviation + " rate = 2.5."
            answer = first + " The mass is 7."
            spans = _sentences(answer)
            self.assertEqual([answer[start:end].strip() for start, end in spans], [first, "The mass is 7."])

    def test_equal_token_sets_are_candidates_not_automatic_equivalence(self) -> None:
        left, right = "z = x-y", "z = y-x"
        answer = left + ", and " + right
        result, client = self.run_verifier(answer, [
            extraction(left, right, exclusions=("and",)),
            {"decisions": [merge_decision(["c1"], ["c2"])]},
        ])
        self.assertEqual(len(result.report["claims"]), 2)
        payload = json.loads(client.inputs[1]["messages"][1]["content"])
        self.assertIn("critical_token_set_equal", payload["candidates"][0]["triggers"])

    def test_two_equivalent_fragments_do_not_swallow_third_independent_predicate(self) -> None:
        left, formula, independent = "The rate is 2", "rate = 2", "the mass is 7."
        answer = left + ", in other words " + formula + ", and " + independent
        result, _ = self.run_verifier(answer, [
            extraction(left, formula, independent, exclusions=("in other words", "and")),
            {"decisions": [merge_decision(["c1", "c2"], ["c3"])]},
        ])
        texts = [item["claim_text"] for item in result.report["claims"]]
        self.assertEqual(texts, [left + ", in other words " + formula, independent])
        self.assertNotIn(independent, texts[0])

    def test_shared_whole_sentence_spans_cannot_swallow_an_unmerged_predicate(self) -> None:
        answer = "The rate is 2, in other words rate = 2, and the mass is 7."
        parsed = extraction("The rate is 2", "rate = 2", "the mass is 7.")
        for claim in parsed["claims"]:
            claim["source_span"] = answer
        result, _ = self.run_verifier(answer, [parsed, {"decisions": [merge_decision(["c1", "c2"], ["c3"])]}])
        self.assertEqual(len(result.report["claims"]), 3)
        self.assertEqual(result.telemetry["merge_audits"][0]["decision"], "keep_safety_guard")

    def test_multiple_candidates_use_one_batched_merge_call(self) -> None:
        sentence_a, sentence_b = "A is hot.", "B is cold."
        answer = sentence_a + " " + sentence_b
        result, client = self.run_verifier(answer, [
            extraction(sentence_a, sentence_a, sentence_b, sentence_b),
            {"decisions": [merge_decision(["c1", "c2"]), merge_decision(["c3", "c4"], candidate_id="m2")]},
        ])
        self.assertEqual(len(result.report["claims"]), 2)
        self.assertEqual([item["stage"] for item in client.inputs].count("merge"), 1)

    def test_invalid_merge_partition_exhausts_repair_without_losing_claims(self) -> None:
        text = "A is hot."
        bad = {"decisions": [merge_decision(["c1"])]}
        client = FakeClient([extraction(text, text), bad, bad])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV3Verifier(self.settings, client).verify(VerificationRequest([], text))
        self.assertEqual(raised.exception.code, "invalid_model_output")
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "merge", "merge_repair_1"])
        self.assertEqual(raised.exception.telemetry["merge_audits"], [])

    def test_extraction_coverage_order_and_claim_limit_remain_enforced(self) -> None:
        verifier = OptimizedV3Verifier(self.settings, FakeClient([]))
        with self.assertRaisesRegex(VerificationError, "unaccounted"):
            verifier._extract(extraction("A is hot."), "A is hot. B is cold.")
        with self.assertRaisesRegex(VerificationError, "answer order"):
            verifier._extract(extraction("B is cold.", "A is hot."), "A is hot. B is cold.")
        limited = OptimizedV3Verifier(Settings(max_claims=1), FakeClient([]))
        with self.assertRaisesRegex(VerificationError, "limits"):
            limited._extract(extraction("A is hot.", "A is hot."), "A is hot.")

    def test_coverage_does_not_treat_ascii_negative_sign_as_discardable_punctuation(self) -> None:
        verifier = OptimizedV3Verifier(self.settings, FakeClient([]))
        with self.assertRaisesRegex(VerificationError, "unaccounted"):
            verifier._extract(extraction("x =", "2"), "x = -2")

    def test_valid_conflict_anchor_needs_no_extra_review(self) -> None:
        text, source = "The speed is 3 m/s.", "The speed is 2 m/s."
        result, client = self.run_verifier(text, [
            extraction(text), {"claims": [row(text, "CONTRADICTED", conflict=conflict("3 m/s"))]},
        ], [source])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify"])
        self.assertEqual(result.telemetry["contradiction_reviews"], [])
        self.assertTrue(result.telemetry["contradiction_checks"][0]["passed"])
        self.assertNotIn("conflict", result.report["claims"][0])

    def test_review_can_correct_initial_contradicted_to_supported(self) -> None:
        text = "The speed is 2 m/s."
        result, client = self.run_verifier(text, [
            extraction(text), {"claims": [row(text, "CONTRADICTED")]},
            {"claims": [review_row(text, "SUPPORTED")]},
        ], [text])
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        review = result.telemetry["contradiction_reviews"][0]
        self.assertEqual((review["before_verdict"], review["after_verdict"]), ("CONTRADICTED", "SUPPORTED"))
        self.assertEqual(review["evidence"], [{"index": 0, "quote": text}])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify", "contradiction_review"])

    def test_review_unsupported_has_internal_premise_but_empty_public_citations(self) -> None:
        text = "The material is copper."
        bad_conflict = conflict("not present in the claim")
        result, _ = self.run_verifier(text, [
            extraction(text), {"claims": [row(text, "CONTRADICTED", conflict=bad_conflict)]},
            {"claims": [review_row(text, "UNSUPPORTED")]},
        ], ["The speed is 2 m/s."])
        self.assertEqual(result.report["claims"][0]["verdict"], "UNSUPPORTED")
        self.assertEqual(result.report["claims"][0]["citations"], [])
        self.assertNotIn("review_evidence", result.report["claims"][0])
        self.assertTrue(result.telemetry["contradiction_reviews"][0]["evidence"])

    def test_calculated_contradiction_can_use_multiple_passage_premises(self) -> None:
        text, sources = "x + y = 6.", ["x = 2", "y = 3"]
        result_row = row(text, "CONTRADICTED", quote=sources[0], conflict={
            "claim_span": "x + y = 6", "kind": "calculation", "explanation": "2 + 3 = 5, incompatible with 6.",
            "evidence": [{"index": 0, "quote": sources[0]}, {"index": 1, "quote": sources[1]}],
        })
        result_row["citations"].append({"index": 1, "quote": sources[1]})
        result, client = self.run_verifier(text, [extraction(text), {"claims": [result_row]}], sources)
        self.assertEqual(result.report["claims"][0]["verdict"], "CONTRADICTED")
        self.assertEqual(len(client.inputs), 2)

    def test_multiple_initial_conflict_failures_share_one_review_batch(self) -> None:
        texts, sources = ["A is hot.", "B is cold."], ["A is warm.", "B is cold."]
        result, client = self.run_verifier(" ".join(texts), [
            extraction(*texts), {"claims": [row(texts[0], "CONTRADICTED", quote=sources[0]), row(
                texts[1], "CONTRADICTED", quote=sources[1], index=1, claim_id="c2",
            )]},
            {"claims": [review_row(texts[0], "UNSUPPORTED", quote=sources[0]), review_row(
                texts[1], "SUPPORTED", quote=sources[1], index=1, claim_id="c2",
            )]},
        ], sources)
        self.assertEqual([item["stage"] for item in client.inputs].count("contradiction_review"), 1)
        self.assertEqual([item["after_verdict"] for item in result.telemetry["contradiction_reviews"]], ["UNSUPPORTED", "SUPPORTED"])

    def test_review_can_confirm_contradiction_with_valid_anchors(self) -> None:
        text = "The speed is 3 m/s."
        reviewed = review_row(text, "CONTRADICTED", conflict=conflict("3 m/s"))
        result, _ = self.run_verifier(text, [extraction(text), {"claims": [row(text, "CONTRADICTED")]}, {"claims": [reviewed]}], ["The speed is 2 m/s."])
        self.assertEqual(result.telemetry["contradiction_reviews"][0]["after_verdict"], "CONTRADICTED")

    def test_review_network_failure_propagates_and_never_becomes_unsupported(self) -> None:
        text = "The speed is 3 m/s."
        client = FakeClient([extraction(text), {"claims": [row(text, "CONTRADICTED")]}, VerificationError("upstream_timeout", "Timed out.", 504)])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV3Verifier(self.settings, client).verify(VerificationRequest(["The speed is 2 m/s."], text))
        self.assertEqual(raised.exception.status, 504)
        self.assertEqual(raised.exception.telemetry["contradiction_reviews"][0]["after_verdict"], None)
        self.assertEqual(raised.exception.telemetry["repairs"], [])
        self.assertEqual(len(client.inputs), 3)

    def test_invalid_review_json_repairs_are_bounded_without_semantic_fallback(self) -> None:
        text = "The speed is 3 m/s."
        client = FakeClient([
            extraction(text), {"claims": [row(text, "CONTRADICTED")]},
            VerificationError("invalid_model_output", "Invalid JSON."), VerificationError("invalid_model_output", "Invalid JSON."),
        ])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV3Verifier(self.settings, client).verify(VerificationRequest(["The speed is 2 m/s."], text))
        self.assertEqual(raised.exception.code, "invalid_model_output")
        self.assertEqual([item["stage"] for item in client.inputs][-2:], ["contradiction_review", "contradiction_review_repair_1"])
        self.assertIsNone(raised.exception.telemetry["contradiction_reviews"][0]["after_verdict"])

    def test_review_with_fabricated_quote_or_missing_conflict_exhausts_repair(self) -> None:
        text = "The speed is 3 m/s."
        for bad in (review_row(text, "UNSUPPORTED", quote="fabricated"), review_row(text, "CONTRADICTED")):
            with self.subTest(verdict=bad["verdict"]):
                client = FakeClient([extraction(text), {"claims": [row(text, "CONTRADICTED")]}, {"claims": [bad]}, {"claims": [bad]}])
                with self.assertRaises(VerificationError):
                    OptimizedV3Verifier(self.settings, client).verify(VerificationRequest(["The speed is 2 m/s."], text))
                self.assertEqual(len(client.inputs), 4)

    def test_invalid_primary_quote_is_format_failure_not_semantic_review(self) -> None:
        text = "The speed is 3 m/s."
        bad = {"claims": [row(text, "CONTRADICTED", quote="fabricated")]}
        client = FakeClient([extraction(text), bad, bad])
        with self.assertRaises(VerificationError) as raised:
            OptimizedV3Verifier(self.settings, client).verify(VerificationRequest(["The speed is 2 m/s."], text))
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify", "verify_repair_1"])
        self.assertEqual(raised.exception.telemetry["contradiction_reviews"], [])

    def test_internal_conflict_evidence_must_be_returned_in_public_citations(self) -> None:
        text = "The speed is 3 m/s."
        source = "The speed is 2 m/s. The mass is 5 kg."
        claim = row(text, "CONTRADICTED", quote="The mass is 5 kg.", conflict=conflict("3 m/s"))
        verifier = OptimizedV3Verifier(self.settings, FakeClient([]))
        claims = verifier._extract(extraction(text), text)
        _, checks = verifier._verify_output({"claims": [claim]}, claims, [source])
        self.assertFalse(checks[0]["passed"])
        self.assertIn("covered", checks[0]["reason"])


if __name__ == "__main__":
    unittest.main()
