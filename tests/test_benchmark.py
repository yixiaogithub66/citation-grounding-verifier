"""Scoring, gold isolation, accounting, and interruption regression checks."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grounding.contracts import VerificationError, VerificationResult
from grounding.scoring import aggregate_backend, align_claims, cost_summary, score_case, usage_summary
from scripts import benchmark


def claim(text: str, verdict: str = "SUPPORTED", quote: str = "The measured length is 12 m.") -> dict:
    return {
        "claim_text": text, "verdict": verdict, "reasoning": "Compare the source.",
        "citations": [] if verdict == "UNSUPPORTED" else [{"index": 0, "quote": quote}],
    }


def case_with_claims(*claims: dict) -> dict:
    gold = []
    for index, item in enumerate(claims):
        gold.append({
            **copy.deepcopy(item), "answer_quote": item["claim_text"], "claim_id": f"case-c{index}",
            "acceptable_evidence_sets": [[0]] if item["citations"] else [],
            "required_passage_indices": [],
        })
    return {
        "id": "sample-1", "split": "dev", "category": "supported",
        "input": {
            "generated_answer": " ".join(item["claim_text"] for item in claims),
            "context_passages": ["In the experiment, The measured length is 12 m. The measured width is 2 m."],
        },
        "expected": {"claims": gold},
        "metadata": {"secret_gold_marker": "must-never-reach-verifier"},
    }


def record(case: dict, prediction: dict | None, error: dict | None = None) -> dict:
    return {
        "id": case["id"], "category": case["category"], "backend": "minimal",
        "prediction": prediction, "error": error, "telemetry": {"calls": []},
        "latency_seconds": 0.1, "score": score_case(case, prediction, error),
    }


class AlignmentTests(unittest.TestCase):
    def test_strict_retains_missing_and_extra_claims(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."), claim("The measured width is 2 m.", quote="The measured width is 2 m."))
        summary = aggregate_backend([record(case, {"claims": [claim("The measured length is 12 m.")]})])
        self.assertEqual(summary["strict"]["claim_recall"]["value"], 0.5)
        self.assertEqual(summary["strict"]["per_label"]["SUPPORTED"]["fn"], 1)
        self.assertEqual(summary["strict"]["confusion_matrix"]["SUPPORTED"]["MISSING"], 1)
        self.assertAlmostEqual(summary["strict"]["macro_f1"]["value"], 2 / 3)

    def test_unrelated_single_claim_is_not_autoaligned(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        result = score_case(case, {"claims": [claim("This planet has two moons.", "UNSUPPORTED")]})
        self.assertEqual(result["approximate"]["matched_claim_count"], 0)
        self.assertEqual(result["approximate"]["confusion_matrix"]["EXTRA"]["UNSUPPORTED"], 1)
        self.assertEqual(result["approximate"]["confusion_matrix"]["SUPPORTED"]["MISSING"], 1)

    def test_close_paraphrase_is_diagnostic_only(self) -> None:
        case = case_with_claims(claim("The measured length of the apparatus is 12 m."))
        result = score_case(case, {"claims": [claim("The measured length of this apparatus is 12 m.")]})
        self.assertEqual(result["strict"]["matched_claim_count"], 0)
        self.assertEqual(result["approximate"]["matched_claim_count"], 1)
        self.assertEqual(result["approximate"]["alignment"]["pairs"][0]["method"], "high_text_similarity")
        self.assertTrue(result["approximate"]["alignment"]["review_required"])

    def test_number_change_does_not_get_similarity_credit(self) -> None:
        case = case_with_claims(claim("The measured length of the apparatus is 12 m."))
        result = score_case(case, {"claims": [claim("The measured length of the apparatus is 13 m.")]})
        self.assertEqual(result["approximate"]["matched_claim_count"], 0)

    def test_formula_sign_change_does_not_get_similarity_credit(self) -> None:
        case = case_with_claims(claim("The focal length is f=a*b/(a+b-D)."))
        result = score_case(case, {"claims": [claim("The focal length is f=a*b/(a+b+D).")]})
        self.assertEqual(result["approximate"]["matched_claim_count"], 0)
        self.assertFalse(result["approximate"]["case_correct"])

    def test_number_next_to_chinese_is_protected(self) -> None:
        case = case_with_claims(claim("在该实验条件下，物体的质量为3千克。"))
        result = score_case(case, {"claims": [claim("在该实验条件下，物体的质量为4千克。")]})
        self.assertEqual(result["approximate"]["matched_claim_count"], 0)

    def test_match_does_not_consult_verdict(self) -> None:
        expected = claim("The measured length is 12 m.")
        actual = claim("The measured length is 12 m.", "CONTRADICTED")
        matched = align_claims([expected], [actual], actual["claim_text"], approximate=True)
        self.assertEqual(len(matched["pairs"]), 1)

    def test_gold_answer_span_can_align_restated_gold(self) -> None:
        case = case_with_claims(claim("The measured length of this apparatus is 12 m."))
        answer = "The measured length of the apparatus is 12 m."
        case["input"]["generated_answer"] = answer
        case["expected"]["claims"][0]["answer_quote"] = answer
        result = score_case(case, {"claims": [claim(answer)]})
        self.assertEqual(result["approximate"]["alignment"]["pairs"][0]["method"], "gold_answer_span")

    def test_ambiguous_paraphrases_do_not_get_greedy_credit(self) -> None:
        gold = [
            claim("The measured length of the apparatus is 12 m."),
            claim("The measured length of this apparatus is 12 m."),
        ]
        prediction = [claim("The measured length of that apparatus is 12 m.")]
        alignment = align_claims(gold, prediction, "", approximate=True)
        self.assertEqual(alignment["pairs"], [])
        self.assertTrue(alignment["review_required"])

    def test_duplicate_prediction_is_extra(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        summary = aggregate_backend([record(case, {"claims": [claim("The measured length is 12 m.")] * 2})])
        self.assertEqual(summary["strict"]["claim_precision"]["value"], 0.5)
        self.assertEqual(summary["strict"]["per_label"]["SUPPORTED"]["fp"], 1)


class EvidenceTests(unittest.TestCase):
    def test_longer_exact_source_quote_covers_gold_quote(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        prediction = {"claims": [claim("The measured length is 12 m.", quote=case["input"]["context_passages"][0])]}
        summary = aggregate_backend([record(case, prediction)])
        self.assertEqual(summary["citations"]["exact_substring_rate"]["value"], 1)
        self.assertEqual(summary["citations"]["strict"]["gold_quote_containment"]["value"], 1)
        self.assertEqual(summary["citations"]["strict"]["gold_quote_exact_match"]["value"], 0)

    def test_alternative_evidence_passage_is_accepted(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        case["input"]["context_passages"].append("The measured length is 12 m.")
        case["expected"]["claims"][0]["acceptable_evidence_sets"] = [[0], [1]]
        actual = claim("The measured length is 12 m.")
        actual["citations"][0]["index"] = 1
        summary = aggregate_backend([record(case, {"claims": [actual]})])
        self.assertEqual(summary["citations"]["strict"]["passage_coverage"]["value"], 1)
        self.assertEqual(summary["citations"]["strict"]["gold_quote_containment"]["value"], 0)

    def test_trivial_valid_quote_requires_evidence_review(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        prediction = {"claims": [claim("The measured length is 12 m.", quote="The")]}
        summary = aggregate_backend([record(case, prediction)])
        self.assertEqual(summary["citations"]["strict"]["passage_coverage"]["value"], 1)
        self.assertEqual(summary["citations"]["strict"]["gold_quote_containment"]["value"], 0)
        self.assertIn("gold_quote_anchor_not_covered_review_needed", summary["failures"][0]["reasons"])

    def test_fabricated_quote_invalidates_response(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        summary = aggregate_backend([record(case, {"claims": [claim("The measured length is 12 m.", quote="fabricated") ]})])
        self.assertEqual(summary["success_rate"]["value"], 0)
        self.assertEqual(summary["citations"]["exact_substring_rate"]["value"], 0)
        self.assertEqual(summary["strict"]["claim_recall"]["value"], 0)

    def test_no_fact_success_and_request_failure_differ(self) -> None:
        case = case_with_claims()
        good = score_case(case, {"claims": []})
        bad = score_case(case, None, {"code": "upstream_error"})
        self.assertTrue(good["strict"]["case_correct"])
        self.assertFalse(bad["strict"]["case_correct"])
        self.assertFalse(bad["schema_valid"])


class AccountingTests(unittest.TestCase):
    def test_all_attempts_and_cache_are_counted(self) -> None:
        data = [
            {"telemetry": {"calls": [
                {"usage": {"prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 40}},
                {"usage": {"prompt_tokens": 200, "completion_tokens": 20, "prompt_cache_hit_tokens": 100}},
            ]}},
        ]
        usage = usage_summary(data)
        self.assertEqual(usage["prompt_tokens"], 300)
        self.assertEqual(usage["completion_tokens"], 30)
        self.assertEqual(usage["prompt_cache_hit_tokens"], 140)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 160)
        cost = cost_summary(usage, {"input_per_million": 1, "output_per_million": 2, "cached_input_per_million": 0.1})
        self.assertAlmostEqual(cost["estimated_amount"], 0.000234)

    def test_missing_usage_is_unknown_and_no_pricing_is_not_free(self) -> None:
        usage = usage_summary([{"telemetry": {"calls": [{"usage": {}}]}}])
        self.assertFalse(usage["usage_complete"])
        self.assertIsNone(cost_summary(usage, None)["estimated_amount"])
        self.assertIsNone(cost_summary(usage, {"input_per_million": 1, "output_per_million": 1})["estimated_amount"])

    def test_malformed_usage_and_nested_details_do_not_abort(self) -> None:
        for malformed in ("invalid", ["invalid"], True, 42):
            with self.subTest(malformed=malformed):
                usage = usage_summary([{"telemetry": {"calls": [{"usage": malformed}]}}])
                self.assertFalse(usage["usage_complete"])
                self.assertFalse(usage["cache_usage_complete"])
                self.assertFalse(usage["reasoning_usage_complete"])
                nested = usage_summary([{"telemetry": {"calls": [{"usage": {
                    "prompt_tokens": 10, "completion_tokens": 3,
                    "prompt_tokens_details": malformed,
                    "completion_tokens_details": malformed,
                }}]}}])
                self.assertTrue(nested["usage_complete"])
                self.assertEqual(nested["prompt_tokens"], 10)
                self.assertEqual(nested["completion_tokens"], 3)
                self.assertFalse(nested["cache_usage_complete"])
                self.assertFalse(nested["reasoning_usage_complete"])
                self.assertEqual(nested["cache_accounted_calls"], 0)
                self.assertEqual(nested["reasoning_accounted_calls"], 0)
                self.assertIsNone(cost_summary(nested, {
                    "input_per_million": 1, "output_per_million": 1, "cached_input_per_million": 0.1,
                })["estimated_amount"])

    def test_valid_cache_count_still_used_with_malformed_nested_details(self) -> None:
        usage = usage_summary([{"telemetry": {"calls": [{"usage": {
            "prompt_tokens": 10, "completion_tokens": 3,
            "prompt_cache_hit_tokens": 4, "prompt_tokens_details": ["invalid"],
            "completion_tokens_details": {"reasoning_tokens": 2},
        }}]}}])
        self.assertTrue(usage["cache_usage_complete"])
        self.assertEqual(usage["prompt_cache_miss_tokens"], 6)
        self.assertTrue(usage["reasoning_usage_complete"])
        self.assertEqual(usage["reasoning_tokens"], 2)

    def test_unstarted_backend_has_unknown_cost(self) -> None:
        result = aggregate_backend([])
        self.assertEqual(result["case_count"], 0)
        self.assertIsNone(result["cost"]["estimated_amount"])
        self.assertFalse(result["cost"]["complete"])


class HarnessTests(unittest.TestCase):
    def setup_run(self, path: Path, cases: list[dict], backends: list[str]) -> tuple[dict, dict]:
        return ({
            "created_at": "2026-10-20T00:00:00Z", "split": "dev",
            "backends": backends, "selected_case_ids": [case["id"] for case in cases],
            "prices": {}, "settings": {"model": "test-model"},
        }, {"dataset_sha256": "test", "implementation_sha256": "test"})

    def test_verifier_gets_only_request_and_gold_isolation(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))
        seen = []

        class Stub:
            def verify(self, request):
                seen.append(request.to_dict())
                request.context_passages.append("backend mutation")
                return VerificationResult({"claims": [claim("The measured length is 12 m.")]})

        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            path = Path(temporary)
            config, provenance = self.setup_run(path, [case], ["baseline", "minimal"])
            report = benchmark.run_cases([case], {"baseline": Stub(), "minimal": Stub()}, path, config, provenance)
            self.assertEqual(report["completed_records"], 2)
        self.assertEqual(seen[0], case["input"])
        self.assertEqual(seen[1], case["input"])
        self.assertEqual(set(seen[0]), {"context_passages", "generated_answer"})

    def test_error_keeps_usage_and_redacts_key(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))

        class Stub:
            def verify(self, request):
                raise VerificationError("upstream_error", "test-secret", telemetry={"calls": [
                    {"usage": {"prompt_tokens": 7, "completion_tokens": 2}, "response_text": "test-secret"}
                ]})

        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            path = Path(temporary)
            config, provenance = self.setup_run(path, [case], ["minimal"])
            report = benchmark.run_cases([case], {"minimal": Stub()}, path, config, provenance, secret="test-secret")
            self.assertEqual(report["backends"]["minimal"]["usage"]["prompt_tokens"], 7)
            self.assertEqual(report["backends"]["minimal"]["strict"]["claim_recall"]["value"], 0)
            self.assertNotIn("test-secret", (path / "responses.jsonl").read_text())
            self.assertNotIn("test-secret", (path / "report.json").read_text())

    def test_interruption_preserves_completed_records(self) -> None:
        case = case_with_claims(claim("The measured length is 12 m."))

        class Stub:
            calls = 0

            def verify(self, request):
                self.calls += 1
                if self.calls == 2:
                    raise KeyboardInterrupt
                return VerificationResult({"claims": [claim("The measured length is 12 m.")]})

        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            path = Path(temporary)
            config, provenance = self.setup_run(path, [case, case], ["minimal"])
            report = benchmark.run_cases([case, case], {"minimal": Stub()}, path, config, provenance)
            self.assertEqual(report["status"], "interrupted")
            self.assertEqual(report["completed_records"], 1)
            self.assertEqual(len((path / "responses.jsonl").read_text().splitlines()), 1)
            self.assertEqual(json.loads((path / "report.json").read_text())["status"], "interrupted")

    def test_missing_api_key_fails_before_building_or_network(self) -> None:
        from grounding.config import Settings

        with patch.object(benchmark, "load_settings", return_value=Settings(api_key="")):
            with patch.object(benchmark, "build_verifier") as build, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(benchmark.main(["--backends", "minimal"]), 2)
                build.assert_not_called()

    def test_invalid_settings_are_clean_configuration_error(self) -> None:
        with patch.object(benchmark, "load_settings", side_effect=VerificationError("configuration_error", "hidden-secret")):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(benchmark.main([]), 2)
                self.assertNotIn("hidden-secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
