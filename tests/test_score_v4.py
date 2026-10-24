"""Synthetic partial semantics and historical metric preservation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.score_v4 import score_records, score_claim_case, validate_v4_prediction, load_prediction_journal
from scripts.build_v4_adjudication import build_package


def claim(verdict="UNSUPPORTED"):
    return {"claim_text": "Statement.", "verdict": verdict, "reasoning": "Synthetic reason.",
            "citations": [] if verdict == "UNSUPPORTED" else [{"index": 0, "quote": "Source."}]}


def partial(verdict="SUPPORTED"):
    return {"claims": [claim(verdict)], "status": "partial",
            "errors": [{"id": "c2", "code": "upstream_error", "message": "Unavailable.", "claim_text": "Unfinished."}]}


def fixture(labels):
    manifest = [{"id": str(i), "source_id": "source" + str(i), "task_type": "QA", "generator": "g", "answer_chars": 12}
                for i in range(len(labels))]
    gold = [{"id": str(i), "source_id": "source" + str(i), "labels": [{"text": "x"}] if label else []}
            for i, label in enumerate(labels)]
    inputs = [{"id": str(i), "input": {"context_passages": ["Source."], "generated_answer": "Statement. Unfinished."}}
              for i in range(len(labels))]
    return manifest, gold, inputs


def record(i, prediction, backend="optimized-v4.0", **extra):
    return {"id": str(i), "backend": backend, "prediction": prediction, "error": None,
            "schema_valid": True, "validation_errors": [], "telemetry": {"calls": []}, "answer_chars": 12, **extra}


class PartialScoreTests(unittest.TestCase):
    def test_journal_raw_unicode_is_retained_but_public_unicode_and_duplicate_keys_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "predictions.jsonl"
            row = record(0, {"claims": []}, telemetry={"calls": [{"response_text": "bad\ud800trace"}]})
            path.write_text(json.dumps(row, ensure_ascii=True), encoding="utf-8")
            self.assertEqual(load_prediction_journal(path)[0]["telemetry"], row["telemetry"])
            row["id"] = "bad\ud800id"
            path.write_text(json.dumps(row, ensure_ascii=True), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_prediction_journal(path)
            path.write_text('{"id":"one","id":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_prediction_journal(path)

    def test_partial_positive_and_unknown_are_not_complete_or_false_negative(self):
        manifest, gold, inputs = fixture([True, False, True, False, True, False])
        records = [record(0, partial("UNSUPPORTED")), record(1, partial("CONTRADICTED")),
                   record(2, partial()), record(3, partial()),
                   record(4, {"claims": []}), record(5, {"claims": [claim("SUPPORTED")]})]
        result = score_records(records, manifest, gold, inputs=inputs, bootstrap_samples=0)
        summary = result["backends"]["optimized-v4.0"]
        self.assertEqual(summary["confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1, "unknown_positive": 1, "unknown_negative": 1})
        self.assertEqual(summary["status_counts"], {"partial": 4, "complete": 2})
        self.assertEqual(summary["claim_completion_known_cases"]["numerator"], 5)
        self.assertEqual(summary["claim_completion_known_cases"]["denominator"], 9)
        self.assertEqual(summary["technical_failure_rate"]["numerator"], 4)
        self.assertEqual(summary["nonempty_answer_empty_claims_count"], 1)
        self.assertEqual(summary["native_fn_zero_target"], "not_met")
        legacy = result["legacy_whole_case_failure"]["backends"]["optimized-v4.0"]
        self.assertEqual(legacy["error_count"], 4)
        self.assertEqual(legacy["confusion"]["positive_failures"], 2)
        self.assertEqual(legacy["confusion"]["negative_failures"], 2)

    def test_same_semantics_for_every_backend_and_allfail_stays_unknown(self):
        manifest, gold, inputs = fixture([True, False])
        names = ["baseline", "minimal", "optimized-v3", "optimized-v4.0"]
        records = [record(0, partial("UNSUPPORTED"), b) for b in names]
        result = score_records(records, manifest, gold, inputs=inputs, backends=names, bootstrap_samples=0)
        for summary in result["backends"].values():
            self.assertEqual(summary["confusion"]["tp"], 1)
            self.assertEqual(summary["confusion"]["unknown_negative"], 1)
            self.assertEqual(summary["unknown_claim_total_case_count"], 1)
            self.assertEqual(summary["complete_case_rate"]["value"], 0)

    def test_invalid_quote_or_duplicate_error_id_is_unknown_not_positive(self):
        manifest, gold, inputs = fixture([True, True])
        badquote = partial("CONTRADICTED")
        badquote["claims"][0]["citations"][0]["quote"] = "Fabricated."
        duplicate = partial("UNSUPPORTED")
        duplicate["errors"] *= 2
        result = score_records([record(0, badquote), record(1, duplicate)], manifest, gold,
                               inputs=inputs, bootstrap_samples=0)
        self.assertEqual(result["overall"]["confusion"]["unknown_positive"], 2)
        self.assertEqual(result["overall"]["confusion"]["fn"], 0)
        self.assertEqual(result["overall"]["status_counts"], {"error": 2})

    def test_partial_needs_source_inputs_and_zero_claim_partial_is_invalid(self):
        self.assertTrue(validate_v4_prediction(partial()))
        invalid = partial()
        invalid["claims"] = []
        self.assertTrue(validate_v4_prediction(invalid, ["Source."]))

    def test_unknown_positive_cannot_satisfy_fn_zero_and_bootstrap_keeps_clusters(self):
        manifest, gold, inputs = fixture([True])
        result = score_records([record(0, partial())], manifest, gold, inputs=inputs, bootstrap_samples=20)
        self.assertEqual(result["overall"]["native_fn_zero_target"], "not_evaluable")
        interval = result["partial_aware_bootstrap"]["backends"]["optimized-v4.0"]["resolved_f1"]
        self.assertEqual(interval["undefined_replicates"], 20)
        self.assertIsNone(interval["point_estimate"])

    def test_allfail_known_claim_total_contributes_to_completion_denominator(self):
        manifest, gold, inputs = fixture([False, True])
        completion = {"total_extracted": 10, "completed": 0, "unfinished": 10,
                      "non_factual_fallbacks": 0, "completed_claim_ids": [],
                      "unfinished_claim_ids": [f"c{i}" for i in range(10)]}
        records = [record(0, {"claims": [claim("SUPPORTED")]}),
                   record(1, None, error={"code": "upstream_error"}, schema_valid=False,
                          telemetry={"calls": [], "completion": completion})]
        result = score_records(records, manifest, gold, inputs=inputs, bootstrap_samples=0)
        self.assertEqual(result["overall"]["claim_completion_known_cases"], {"numerator": 1, "denominator": 11, "value": 1/11})
        self.assertEqual(result["overall"]["unknown_claim_total_case_count"], 0)
        self.assertEqual(result["overall"]["confusion"]["unknown_positive"], 1)

    def test_nonboolean_schema_metadata_is_not_accepted(self):
        manifest, gold, inputs = fixture([True])
        result = score_records([record(0, {"claims": [claim()]}, schema_valid="true")], manifest, gold,
                               inputs=inputs, bootstrap_samples=0)
        self.assertEqual(result["overall"]["confusion"]["unknown_positive"], 1)

    def test_claim_accuracy_excludes_unfinished_but_always_reports_coverage(self):
        case = {"input": {"context_passages": ["Source."], "generated_answer": "Statement. Unfinished."},
                "expected": {"claims": [claim("SUPPORTED"), {**claim("UNSUPPORTED"), "claim_text": "Unfinished."}]}}
        result = score_claim_case(case, partial())
        self.assertEqual(result["completed_aligned_verdict_accuracy"]["value"], 1)
        self.assertEqual(result["gold_alignment_coverage"]["value"], .5)
        self.assertFalse(result["legacy_whole_case_failure"]["schema_valid"])

    def test_adjudication_selects_fp_union_and_disagreement_without_approving(self):
        manifest, gold, inputs = fixture([False, True, False])
        records = [record(0, {"claims": [claim()]}, "minimal"),
                   record(0, {"claims": [claim("SUPPORTED")]}, "optimized-v3"),
                   record(1, {"claims": [claim()]}, "minimal"),
                   record(1, {"claims": [claim("SUPPORTED")]}, "optimized-v3"),
                   record(2, {"claims": [claim("SUPPORTED")]}, "minimal"),
                   record(2, {"claims": [claim("SUPPORTED")]}, "optimized-v3")]
        before = copy.deepcopy(gold)
        package = build_package(records, inputs, manifest, gold)
        self.assertEqual([c["id"] for c in package["cases"]], ["0", "1"])
        self.assertEqual(package["counts"]["union_native_fp_cases"], 1)
        for case in package["cases"]:
            self.assertIsNone(case["case_adjudicated_positive"])
            for item in case["reported_claims_for_review"]:
                self.assertEqual(item["ai_review"]["status"], "pending_ai")
                self.assertEqual(item["author_review"]["status"], "pending_author")
                self.assertIsNone(item["author_review"]["verdict"])
        self.assertEqual(gold, before)


if __name__ == "__main__":
    unittest.main()
