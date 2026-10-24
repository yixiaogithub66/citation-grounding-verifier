"""Synthetic, network-free checks; never loads RAGTruth raw examples or labels."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("fresh180_summarize", Path(__file__).with_name("summarize.py"))
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def claim(verdict="SUPPORTED"):
    return {"claim_text": "Alpha exists.", "verdict": verdict, "reasoning": "Synthetic fixture.",
            "citations": [] if verdict == "UNSUPPORTED" else [{"index": 0, "quote": "Alpha exists."}]}


def fixture():
    manifest, gold, inputs, records = [], [], [], []
    prices = {"input_per_million": .30, "cached_input_per_million": .006, "output_per_million": 1.20, "currency": "USD"}
    for i in range(6):
        identifier, source = str(i), "synthetic-source-" + str(i // 2)
        manifest.append({"id": identifier, "source_id": source, "task_type": ("QA", "Summary", "Data2txt")[i // 2], "generator": "model-" + str(i % 2), "answer_chars": 13})
        gold.append({"id": identifier, "source_id": source, "labels": [{}] if i in (0, 2, 4, 5) else []})
        inputs.append({"id": identifier, "input": {"context_passages": ["Alpha exists."], "generated_answer": "Alpha exists."}})
        for position, backend in enumerate(summary.BACKENDS):
            prediction = {"claims": [claim("UNSUPPORTED" if i in (0, 3) else "SUPPORTED")]}
            if i in (2, 3):
                prediction.update(status="partial", errors=[{"id": "unfinished", "code": "fixture", "message": "unfinished fixture"}])
            if i == 4:
                prediction = {"claims": []}
            error = {"code": "fixture", "message": "synthetic failure"} if i == 5 else None
            if error:
                prediction = None
            calls = [] if backend == "baseline" else [{"stage": "fixture", "model": "synthetic-model", "system_fingerprint": "synthetic-fingerprint", "usage": {
                "prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 40,
                "prompt_cache_miss_tokens": 60, "completion_tokens_details": {"reasoning_tokens": 5}}}]
            records.append({"id": identifier, "source_id": source, "backend": backend,
                            "prediction": prediction, "error": error, "schema_valid": not bool(error),
                            "validation_errors": [], "telemetry": {"calls": calls}, "answer_chars": 13,
                            "latency_seconds": float(i + 1), "backend_order_index": position})
    return records, manifest, gold, inputs, {"backends": list(summary.BACKENDS), "price_reference": prices}


def analyzed(data=None):
    return summary.analyze(*(data or fixture()), samples=40, seed=20261024)


class SummaryTests(unittest.TestCase):
    def test_partial_empty_and_error_denominators(self):
        report = analyzed()
        item = report["backends"]["optimized-v4.0"]
        self.assertEqual(item["confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1, "unknown_positive": 2, "unknown_negative": 0})
        self.assertEqual(item["status_counts"], {"complete": 3, "partial": 2, "error": 1})
        self.assertEqual(item["correct_decisions_per_all_cases"]["value"], 2 / 6)
        self.assertEqual(item["resolved_only"]["accuracy"]["value"], .5)
        self.assertEqual(item["decision_coverage"]["value"], 4 / 6)
        self.assertEqual(item["empty_claims_count"], 1)
        self.assertEqual(item["nonempty_answer_empty_claims_count"], 1)
        self.assertEqual(item["unknown_claim_total_case_count"], 1)
        self.assertEqual(item["claim_completion_known_cases"]["value"], 4 / 6)
        # The historical comparator still rejects both partial envelopes.
        self.assertEqual(report["legacy_whole_case_failure"]["backends"]["optimized-v4.0"]["success_count"], 3)

    def test_actual_context_overrides_schema_valid_metadata(self):
        data = fixture()
        row = next(row for row in data[0] if row["id"] == "1" and row["backend"] == "minimal")
        row["prediction"]["claims"][0]["citations"][0]["quote"] = "Invented quotation."
        report = analyzed(data)
        scored = next(row for row in report["case_results"] if row["id"] == "1" and row["backend"] == "minimal")
        self.assertEqual(scored["status"], "error")
        self.assertIsNone(scored["y_pred"])
        self.assertEqual(report["backends"]["minimal"]["confusion"]["unknown_negative"], 1)

    def test_missing_usage_and_whole_record_are_unknown_not_free(self):
        data = fixture()
        selected = [row for row in data[0] if row["backend"] == "minimal"]
        selected[0]["telemetry"] = {"usage_unknown": True}
        selected[0]["latency_seconds"] = None
        selected[1]["telemetry"]["calls"][0].pop("usage")
        runtime = summary.measured_runtime(selected, data[-1]["price_reference"])
        self.assertEqual(runtime["usage"]["records_missing_telemetry"], 1)
        self.assertFalse(runtime["usage"]["call_count_complete"])
        self.assertEqual(runtime["usage"]["calls_missing_usage"], 1)
        self.assertIsNone(runtime["reference_cost"]["estimated_total"])
        self.assertIsNone(runtime["reference_cost"]["cache_standardized_all_miss_total"])
        self.assertGreater(runtime["reference_cost"]["known_usage_subtotal"], 0)
        self.assertEqual(runtime["latency_unknown_count"], 1)
        self.assertEqual(runtime["mean_latency_seconds"], 4.0)

    def test_third_position_cost_and_reasoning_not_double_counted(self):
        report = analyzed()
        runtime = report["runtime_by_backend"]["optimized-v4.0"]
        self.assertEqual(runtime["by_execution_position"]["2"]["record_count"], 6)
        self.assertEqual(runtime["usage"]["total_tokens"], 720)
        self.assertEqual(runtime["usage"]["reasoning_tokens"], 30)
        self.assertAlmostEqual(runtime["reference_cost"]["known_usage_subtotal"], 6 * (60 * .30 + 40 * .006 + 20 * 1.20) / 1e6)
        self.assertAlmostEqual(runtime["reference_cost"]["cache_standardized_all_miss_total"], 6 * (100 * .30 + 20 * 1.20) / 1e6)
        self.assertEqual(report["runtime_by_backend"]["baseline"]["usage"]["calls"], 0)

    def test_bootstrap_is_paired_by_source_and_reproducible(self):
        report = analyzed()
        bootstrap = report["three_backend_source_bootstrap"]
        self.assertEqual(bootstrap["source_count"], 3)
        self.assertEqual(bootstrap, summary.paired_bootstrap(report["case_results"], samples=40, seed=20261024))
        self.assertEqual(len(bootstrap["paired"]), 3)
        for pair in bootstrap["paired"].values():
            for result in pair.values():
                self.assertEqual(result["point_estimate"], 0.0)
                self.assertEqual(result["low"], 0.0)
                self.assertEqual(result["high"], 0.0)

    def test_zero_denominator_remains_null_and_no_quotes_not_100_percent(self):
        data = fixture()
        for gold in data[2]:
            gold["labels"] = []
        for row in data[0]:
            row.update(prediction={"claims": []}, error=None, schema_valid=True)
        report = analyzed(data)
        item = report["backends"]["minimal"]
        self.assertIsNone(item["resolved_only"]["f1"]["value"])
        self.assertIsNone(item["public_citation_contract"]["rate"])
        interval = report["three_backend_source_bootstrap"]["backends"]["minimal"]["resolved_f1"]
        self.assertEqual(interval["undefined_replicates"], 40)
        self.assertIsNone(interval["low"])

    def test_pair_transition_separates_recovery_from_existing_decisions(self):
        data = fixture()
        row = next(row for row in data[0] if row["id"] == "5" and row["backend"] == "optimized-v4.0")
        row.update(prediction={"claims": [claim("UNSUPPORTED")]}, error=None, schema_valid=True)
        report = analyzed(data)
        pair = report["paired_transitions"]["optimized-v4.0_minus_minimal"]
        self.assertEqual(pair["reference_to_candidate"]["unknown_to_correct"], 1)
        self.assertEqual(pair["common_resolved"]["count"], 4)
        self.assertEqual(pair["common_resolved"]["candidate_correct_only"], 0)
        self.assertEqual(pair["common_resolved"]["reference_correct_only"], 0)

    def test_full_slot_integrity_and_non_llm_baseline(self):
        data = fixture()
        data[0].pop()
        with self.assertRaisesRegex(ValueError, "exactly one record"):
            analyzed(data)
        data = fixture()
        data[0].append(copy.deepcopy(data[0][0]))
        with self.assertRaisesRegex(ValueError, "exactly one record"):
            analyzed(data)
        data = fixture()
        data[0][0]["telemetry"]["calls"] = [{"usage": {"prompt_tokens": 1, "completion_tokens": 1}}]
        with self.assertRaisesRegex(ValueError, "baseline unexpectedly"):
            analyzed(data)

    def test_finalization_hashes_preserve_unknown_and_detect_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "predictions.jsonl").write_text('{}\n', encoding="utf-8")
            (root / "reservation.json").write_text('{}\n', encoding="utf-8")
            (root / "progress.json").write_text(json.dumps({"status": "completed_with_unknown", "finalized_records": 1, "frozen_artifacts_unchanged": True}), encoding="utf-8")
            integrity = {"record_count": 1, "predictions_sha256": summary.sha(root / "predictions.jsonl"),
                         "durable_result_count": 0, "unknown_count": 1,
                         "files_sha256": {"reservation.json": summary.sha(root / "reservation.json")}}
            (root / "result-integrity.json").write_text(json.dumps(integrity), encoding="utf-8")
            self.assertEqual(summary.check_finalization(root, expected_records=1)["unknown_count"], 1)
            (root / "reservation.json").write_text('{"changed": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "reservation changed"):
                summary.check_finalization(root, expected_records=1)


if __name__ == "__main__":
    unittest.main()
