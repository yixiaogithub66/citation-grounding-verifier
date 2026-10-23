"""Offline behavior scoring, provenance, and fixed-claim isolation without APIs."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationRequest, VerificationResult
from grounding.verifiers_v4 import OptimizedV4Verifier
from scripts import benchmark_v4_behavior as behavior


def prediction(case, verdict=None):
    verdict = verdict or case["expected_label"]
    return {"claims": [{"claim_text": case["fixed_claim_text"], "verdict": verdict,
                        "reasoning": "Synthetic diagnostic output.",
                        "citations": [] if verdict == "UNSUPPORTED" else [{"index": 0, "quote": case["input"]["context_passages"][0]}]}]}


def record(pair, side, verdict, backend="optimized-v4.0", mode="end_to_end"):
    case = pair[side]
    report = prediction(case, verdict)
    return {"pair_id": pair["id"], "side": side, "family": pair["family"], "domain": pair["domain"],
            "backend": backend, "mode": mode, "latency_seconds": .1, "telemetry": {"calls": []},
            "score": behavior.score_case(case, report)}


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self.pairs = behavior.load_pairs(behavior.DEFAULT_DATASET)

    def test_drafts_have_distinct_pairs_and_cross_domain_predeclared_relations(self):
        self.assertEqual(len(self.pairs), 24)
        self.assertEqual({p["domain"] for p in self.pairs}, {"systems", "science", "ordinary", "business"})
        families = {p["family"] for p in self.pairs}
        self.assertTrue({"entity_renaming", "paraphrase", "source_reordering", "necessary_premise_deletion",
                         "multi_passage_premises", "numeric_sign", "numeric_decimal", "negation",
                         "condition_change", "source_over_world_knowledge", "embedded_fact_in_advice"} <= families)
        for pair in self.pairs:
            self.assertIn("not author-approved", pair["provenance"])

    def test_stable_wrong_is_consistent_but_not_correct(self):
        pair = self.pairs[0]
        rows = [record(pair, side, "UNSUPPORTED") for side in ("base", "variant")]
        summary = behavior.summarize([pair], rows)["groups"]["optimized-v4.0/end_to_end"]
        self.assertEqual(summary["relation_consistency_all_pairs"]["value"], 1)
        self.assertEqual(summary["both_expected_correct_all_pairs"]["value"], 0)
        self.assertEqual(summary["stable_wrong_pair_count"], 1)

    def test_transition_requires_the_declared_direction_not_arbitrary_difference(self):
        pair = next(p for p in self.pairs if p["family"] == "necessary_premise_deletion")
        rows = [record(pair, "base", "UNSUPPORTED"), record(pair, "variant", "SUPPORTED")]
        summary = behavior.summarize([pair], rows)["groups"]["optimized-v4.0/end_to_end"]
        self.assertEqual(summary["relation_consistency_all_pairs"]["value"], 0)

    def test_empty_factual_answer_is_not_vacuously_supported(self):
        score = behavior.score_case(self.pairs[0]["base"], {"claims": []})
        self.assertEqual(score["observed_label"], "NON_FACTUAL")
        self.assertFalse(score["expected_correct"])
        self.assertEqual(score["aligned_target_count"], 0)

    def test_partial_label_unknown_retains_positive_detection_and_coverage(self):
        case = self.pairs[0]["base"]
        report = prediction(case, "UNSUPPORTED")
        report.update(status="partial", errors=[{"id": "c2", "code": "upstream_timeout", "message": "Timed out."}])
        score = behavior.score_case(case, report)
        self.assertEqual(score["execution_status"], "partial")
        self.assertIsNone(score["observed_label"])
        self.assertTrue(score["positive_detected_in_completed_claims"])
        self.assertEqual(score["known_extracted_factual_count"], 2)
        self.assertEqual(score["known_completed_factual_count"], 1)
        self.assertFalse(score["expected_correct"])

    def test_invalid_evidence_and_all_failure_stay_unknown(self):
        case = self.pairs[0]["base"]
        report = prediction(case)
        report["claims"][0]["citations"][0]["quote"] = "Invented quote."
        score = behavior.score_case(case, report)
        self.assertEqual(score["execution_status"], "error")
        self.assertIsNone(score["observed_label"])
        score = behavior.score_case(case, None, {"code": "failure"}, telemetry={"completion": {"total_extracted": 3, "non_factual_fallbacks": 1}})
        self.assertEqual(score["known_extracted_factual_count"], 2)
        self.assertEqual(score["known_completed_factual_count"], 0)

    def test_missing_pair_side_counts_in_denominator(self):
        pair = self.pairs[0]
        summary = behavior.summarize([pair], [record(pair, "base", "SUPPORTED")])["groups"]["optimized-v4.0/end_to_end"]
        self.assertEqual(summary["both_expected_correct_all_pairs"], {"numerator": 0, "denominator": 1, "value": 0})
        self.assertEqual(summary["pair_resolution"]["value"], 0)

    def test_fixture_contract_rejects_changed_provenance_or_relation(self):
        for mutate in (lambda p: p.update(provenance="human gold"), lambda p: p.update(relation="expected_transition")):
            pair = deepcopy(self.pairs[0])
            mutate(pair)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.jsonl"
                path.write_text(json.dumps(pair) + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    behavior.load_pairs(path)

    def test_reordering_preserves_attributed_identity_and_updates_required_index(self):
        pair = next(p for p in self.pairs if p["family"] == "source_reordering")
        self.assertEqual(pair["base"]["input"]["context_passages"][0], pair["variant"]["input"]["context_passages"][1])
        self.assertIn("Passage 0", pair["base"]["input"]["generated_answer"])
        self.assertIn("Passage 1", pair["variant"]["input"]["generated_answer"])
        self.assertEqual(pair["variant"]["required_passage_indices"], [1])

    def test_fixed_claim_skips_m1_without_injecting_expected_or_family_metadata(self):
        case = self.pairs[0]["base"]
        seen = []
        class Client:
            def complete(self, messages, stage, telemetry):
                seen.append((stage, deepcopy(messages)))
                payload = json.loads(messages[1]["content"])
                self_claim = payload["claims"][0]
                row = {"id": self_claim["id"], "claim_text": self_claim["claim_text"], "verdict": "SUPPORTED",
                       "reasoning": "The source states the target.", "derivation": "Directly stated.", "conflict": None,
                       "citations": [{"index": 0, "quote": case["input"]["context_passages"][0]}]}
                telemetry["calls"].append({"stage": stage, "response_text": json.dumps({"claims": [row]}),
                                           "usage": {"prompt_tokens": 2, "completion_tokens": 2}})
                return {"claims": [row]}
        verifier = OptimizedV4Verifier(Settings(api_key="fake-only"), Client(), replace(V4Config(), max_workers=1))
        behavior.fixed_claim_control(verifier, case["fixed_claim_text"])
        result = verifier.verify(VerificationRequest.from_dict(case["input"]))
        self.assertEqual([stage for stage, _ in seen], ["verify"])
        self.assertEqual(result.telemetry["extraction"]["mode"], "offline_fixed_claim_control")
        user_payload = json.loads(seen[0][1][1]["content"])
        for forbidden in ("expected_label", "family", "domain", "relation", "pair_id"):
            self.assertNotIn(forbidden, user_payload)
            self.assertNotIn(forbidden, user_payload["claims"][0])

    def test_review_audit_distinguishes_corrections_errors_and_failures(self):
        row = record(self.pairs[0], "base", "SUPPORTED", mode="fixed_claim")
        row["telemetry"] = {"unsupported_reviews": [
            {"claim_id": "c1", "before_verdict": "UNSUPPORTED", "after_verdict": "SUPPORTED"},
            {"claim_id": "c1", "before_verdict": "UNSUPPORTED", "after_verdict": "UNSUPPORTED"},
            {"claim_id": "c1", "before_verdict": "UNSUPPORTED", "after_verdict": "CONTRADICTED"},
            {"claim_id": "c1", "before_verdict": "UNSUPPORTED", "after_verdict": None, "error": {"code": "failure"}},
        ], "contradiction_reviews": [
            {"claim_id": "c1", "before_verdict": "SUPPORTED", "after_verdict": "CONTRADICTED"},
        ]}
        summary = behavior.review_audit([row])
        self.assertEqual(summary["outcome_counts"], {"right_to_wrong": 1, "wrong_to_right": 1, "unchanged": 1,
                                                     "wrong_to_different_wrong": 1, "failure": 1})
        self.assertEqual(summary["net_corrections"], 0)
        self.assertEqual(behavior.review_audit([{**row, "mode": "end_to_end"}])["review_event_count"], 0)

    def test_dataset_race_fails_before_any_output_or_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "pairs.jsonl"
            dataset.write_bytes(behavior.DEFAULT_DATASET.read_bytes())
            output = Path(directory) / "run"
            def changed(path):
                path.write_text("changed while loading", encoding="utf-8")
                return self.pairs
            with patch.object(behavior, "load_pairs", side_effect=changed):
                with self.assertRaisesRegex(ValueError, "Dataset changed"):
                    behavior.run(dataset, output, Settings(api_key="fake"), V4Config())
            self.assertFalse(output.exists())

    def test_source_change_invalidates_scored_comparison(self):
        hashes = {"scripts/benchmark_v4_behavior.py": behavior._sha(Path(behavior.__file__))}
        verifier = SimpleNamespace(verify=lambda request: VerificationResult({"claims": []}))
        with tempfile.TemporaryDirectory() as directory, patch.object(behavior, "code_hashes", side_effect=[hashes, hashes, {}]):
            output = Path(directory) / "run"
            with self.assertRaisesRegex(ValueError, "frozen comparison is invalid"):
                behavior.run(behavior.DEFAULT_DATASET, output, Settings(api_key="fake"), V4Config(),
                             limit_pairs=1, modes=("end_to_end",), backends=("optimized-v4.0",), workers=1,
                             verifier_factory=lambda *args, **kwargs: verifier)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["run_status"], "invalid_source_changed")
            self.assertNotIn("groups", report)
            self.assertTrue((output / "responses.jsonl").exists())

    def test_run_archives_inputs_raw_telemetry_and_config_without_secret(self):
        secret = "fake-test-key-never-persist"
        seen = []
        class FakeVerifier:
            def verify(self, request):
                seen.append(request.to_dict())
                telemetry = {"calls": [{"stage": "verify", "model": "fake", "system_fingerprint": "fake-fingerprint",
                                        "response_text": "raw fake result", "usage": {"prompt_tokens": 2, "completion_tokens": 1}}]}
                if hasattr(self, "_decompose"):
                    text = self._decompose(request.generated_answer, telemetry)[0]["claim_text"]
                else:
                    text = request.generated_answer
                report = {"claims": [{"claim_text": text, "verdict": "SUPPORTED", "reasoning": "Fixture source.",
                                      "citations": [{"index": 0, "quote": request.context_passages[0]}]}]}
                return VerificationResult(report, telemetry)
        def factory(backend, settings, *, v4_config):
            self.assertIn(backend, behavior.BACKENDS)
            return FakeVerifier()
        # Other agents can edit independent runtime modules; this evaluator test
        # freezes only its own stable source, so concurrency cannot create a race.
        hashes = {"scripts/benchmark_v4_behavior.py": behavior._sha(Path(behavior.__file__))}
        with tempfile.TemporaryDirectory() as directory, patch.object(behavior, "code_hashes", return_value=hashes):
            output = Path(directory) / "run"
            report = behavior.run(behavior.DEFAULT_DATASET, output, Settings(api_key=secret), V4Config(),
                                  limit_pairs=1, workers=2, verifier_factory=factory,
                                  prices={"input_per_million": 1, "output_per_million": 2})
            self.assertEqual(len(seen), 8)
            self.assertTrue(all(set(request) == {"context_passages", "generated_answer"} for request in seen))
            self.assertEqual(len(report["groups"]), 4)
            self.assertTrue(report["source_files_unchanged_after_run"])
            self.assertEqual(behavior._sha(output / "pairs.jsonl"), behavior._sha(behavior.DEFAULT_DATASET))
            self.assertTrue((output / "source/scripts/benchmark_v4_behavior.py").exists())
            raw = (output / "responses.jsonl").read_text(encoding="utf-8")
            self.assertIn("fake-fingerprint", raw)
            self.assertNotIn(secret, raw + (output / "config.json").read_text(encoding="utf-8"))
            for summary in report["groups"].values():
                self.assertIsNotNone(summary["cost"]["estimated_amount"])
            with self.assertRaises(FileExistsError):
                behavior.run(behavior.DEFAULT_DATASET, output, Settings(api_key=secret), V4Config(), limit_pairs=1, verifier_factory=factory)


if __name__ == "__main__":
    unittest.main()
