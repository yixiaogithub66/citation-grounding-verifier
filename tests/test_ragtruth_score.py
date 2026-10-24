"""Synthetic regression tests for native RAGTruth response detection."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ragtruth_score import main, render_report, score_records


def claim(verdict: str = "UNSUPPORTED", text: str = "An unrelated decomposition.") -> dict:
    return {"claim_text": text, "verdict": verdict, "reasoning": "Synthetic explanation.",
            "citations": [] if verdict == "UNSUPPORTED" else [{"index": 0, "quote": "Source quotation."}]}


def fixture(positive: list[bool], sources: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    manifest, gold = [], []
    for index, label in enumerate(positive):
        source = sources[index] if sources else f"source-{index}"
        manifest.append({"id": str(index), "source_id": source, "task_type": "QA" if index % 2 else "Summary",
                         "generator": "generator-A" if index % 2 else "generator-B", "answer_chars": 30})
        gold.append({"id": str(index), "source_id": source,
                     "labels": [{"start": 2, "end": 4, "text": "x", "implicit_true": True, "due_to_null": True}] if label else [],
                     "has_hallucination": label})
    return manifest, gold


def record(index: int, claims: list[dict] | None, backend: str = "minimal", **overrides: object) -> dict:
    result = {"id": str(index), "backend": backend,
              "prediction": {"claims": claims} if claims is not None else None,
              "error": None, "latency_seconds": 1.0, "schema_valid": claims is not None,
              "validation_errors": [], "telemetry": {"calls": []}, "answer_chars": 30}
    result.update(overrides)
    return result


class NativeDetectionTests(unittest.TestCase):
    def score(self, records: list[dict], manifest: list[dict], gold: list[dict], **kwargs: object) -> dict:
        return score_records(records, manifest, gold, bootstrap_samples=kwargs.pop("bootstrap_samples", 0), **kwargs)

    def test_native_labels_include_all_annotation_types_without_claim_alignment(self) -> None:
        manifest, gold = fixture([True, False])
        # Redundant metadata is not allowed to override the native labels rule.
        gold[0]["has_hallucination"] = False
        records = [record(0, [claim("SUPPORTED"), claim("UNSUPPORTED")]), record(1, [claim("SUPPORTED")])]
        report = self.score(records, manifest, gold)
        summary = report["backends"]["minimal"]
        self.assertEqual(summary["confusion"], {"tp": 1, "fp": 0, "tn": 1, "fn": 0,
                                               "positive_failures": 0, "negative_failures": 0})
        self.assertEqual(summary["detection_f1"]["value"], 1.0)
        self.assertEqual(report["gold_has_hallucination_disagreements"], 1)
        self.assertEqual(summary["verdict_counts"], {"SUPPORTED": 2, "CONTRADICTED": 0, "UNSUPPORTED": 1})
        self.assertNotIn("claim_accuracy", summary)
        self.assertNotIn("strict", summary)

    def test_single_marked_error_does_not_create_supported_gold_for_unmarked_text(self) -> None:
        manifest, gold = fixture([True])
        report = self.score([record(0, [claim("SUPPORTED", "Unmarked answer text")])], manifest, gold)
        self.assertEqual(report["overall"]["confusion"]["fn"], 1)
        self.assertEqual(report["overall"]["detection_f1"]["value"], 0)
        self.assertTrue(report["case_results"][0]["y_true"])
        self.assertFalse(report["case_results"][0]["y_pred"])

    def test_mixed_contradicted_and_unsupported_predicts_one_response_positive(self) -> None:
        manifest, gold = fixture([True, True])
        predictions = [record(0, [claim("CONTRADICTED"), claim("UNSUPPORTED")]), record(1, [claim("CONTRADICTED")])]
        result = self.score(predictions, manifest, gold)["overall"]
        self.assertEqual(result["confusion"]["tp"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["verdict_counts"]["CONTRADICTED"], 2)
        self.assertEqual(result["verdict_counts"]["UNSUPPORTED"], 1)

    def test_request_and_schema_failures_remain_in_denominators(self) -> None:
        manifest, gold = fixture([True, False, True, False])
        records = [record(0, [claim()]), record(1, []),
                   record(2, None, error={"code": "timeout"}),
                   record(3, [], prediction={"claims": "not-an-array"})]
        report = self.score(records, manifest, gold)
        summary = report["backends"]["minimal"]
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["error_count"], 2)
        self.assertEqual(summary["coverage"], {"numerator": 2, "denominator": 4, "value": 0.5})
        self.assertEqual(summary["answered_only"]["f1"]["value"], 1)
        self.assertEqual(summary["detection_f1"], {"numerator": 2, "denominator": 4, "value": 0.5})
        self.assertEqual(summary["end_to_end_accuracy"]["value"], 0.5)
        self.assertEqual(summary["confusion"]["positive_failures"], 1)
        self.assertEqual(summary["confusion"]["negative_failures"], 1)
        self.assertEqual(summary["conservative_confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1})
        self.assertEqual(summary["by_task"]["QA"]["error_count"], 1)
        self.assertEqual(summary["by_generator"]["generator-B"]["error_count"], 1)
        self.assertIsNone(report["case_results"][2]["y_pred"])

    def test_missing_record_and_wholly_missing_backend_are_failures(self) -> None:
        manifest, gold = fixture([True, False])
        report = self.score([record(0, [claim()])], manifest, gold, backends=["minimal", "optimized-v3"])
        self.assertEqual(report["expected_record_count"], 4)
        self.assertEqual(report["overall"]["total_count"], 4)
        self.assertEqual(report["overall"]["error_count"], 3)
        missing = report["backends"]["optimized-v3"]
        self.assertEqual(missing["failure_counts"], {"missing_record": 2})
        self.assertEqual(missing["confusion"]["positive_failures"], 1)
        self.assertEqual(missing["confusion"]["negative_failures"], 1)
        self.assertEqual(missing["end_to_end_accuracy"]["value"], 0)
        self.assertFalse(missing["cost"]["complete"])
        self.assertIsNone(missing["cost"]["estimated_amount"])

    def test_empty_record_file_requires_explicit_backends_and_scores_all_failures(self) -> None:
        manifest, gold = fixture([False, True])
        with self.assertRaisesRegex(ValueError, "explicit backends"):
            self.score([], manifest, gold)
        summary = self.score([], manifest, gold, backends=["minimal"])["overall"]
        self.assertEqual(summary["total_count"], 2)
        self.assertEqual(summary["error_count"], 2)
        self.assertEqual(summary["detection_f1"]["value"], 0)
        self.assertIsNone(summary["answered_only"]["f1"]["value"])

    def test_empty_claims_are_negative_and_answer_coverage_is_flagged(self) -> None:
        manifest, gold = fixture([False, True, False, False])
        records = [record(0, [], answer_chars=0), record(1, []), record(2, [])]
        del records[2]["answer_chars"]  # Fall back to manifest length.
        records.append(record(3, []))
        del records[3]["answer_chars"]
        del manifest[3]["answer_chars"]
        summary = self.score(records, manifest, gold)["overall"]
        self.assertEqual(summary["confusion"]["tn"], 3)
        self.assertEqual(summary["confusion"]["fn"], 1)
        self.assertEqual(summary["empty_claims_count"], 4)
        self.assertEqual(summary["nonempty_answer_empty_claims"], 2)
        self.assertEqual(summary["empty_answer_empty_claims"], 1)
        self.assertEqual(summary["empty_claims_answer_length_unknown"], 1)
        self.assertEqual(summary["success_count"], 4)

    def test_malformed_claim_outputs_and_false_context_validation_are_failures(self) -> None:
        malformed = [None, [], {}, {"claims": {}}, {"claims": [None]}, {"claims": [{"verdict": "UNSUPPORTED"}]},
                     {"claims": [claim("UNKNOWN")]}, {"claims": [dict(claim(), citations=[{"index": 0, "quote": "x"}])]},
                     {"claims": [dict(claim("SUPPORTED"), citations=[])]},
                     {"claims": [dict(claim("SUPPORTED"), citations=[{"index": True, "quote": "x"}])]},
                     {"claims": [dict(claim("SUPPORTED"), citations=[{"index": 0, "quote": "x", "start_char": 0}])]}]
        manifest, gold = fixture([False])
        for payload in malformed:
            with self.subTest(payload=payload):
                result = self.score([record(0, [], prediction=payload)], manifest, gold)["overall"]
                self.assertEqual(result["error_count"], 1)
                self.assertEqual(result["confusion"]["negative_failures"], 1)
                self.assertEqual(result["confusion"]["tn"], 0)
        result = self.score([record(0, [], schema_valid=False,
                                    validation_errors=[{"location": "quote", "message": "not exact"}])], manifest, gold)
        self.assertEqual(result["overall"]["failure_counts"], {"invalid_schema": 1})

    def test_even_empty_error_dictionary_is_an_error(self) -> None:
        manifest, gold = fixture([False])
        result = self.score([record(0, [], error={})], manifest, gold)
        self.assertEqual(result["overall"]["error_count"], 1)
        self.assertEqual(result["overall"]["success_count"], 0)

    def test_runner_rejected_output_is_a_schema_error_even_if_prediction_discarded(self) -> None:
        manifest, gold = fixture([False])
        result = self.score([record(0, None, error={"code": "invalid_model_output"},
                                    validation_errors=[{"location": "response", "message": "invalid"}])], manifest, gold)
        self.assertEqual(result["overall"]["failure_counts"], {"invalid_schema": 1})
        self.assertEqual(result["overall"]["schema_outcomes"]["invalid"], 1)
        self.assertEqual(result["overall"]["error_count"], 1)

    def test_citation_diagnostics_and_usage_are_not_semantic_accuracy(self) -> None:
        manifest, gold = fixture([True, False])
        records = [record(0, [claim("CONTRADICTED")], citations={"citation_count": 1, "valid_citation_count": 1},
                          telemetry={"calls": [{"usage": {"prompt_tokens": 100, "completion_tokens": 20}}]}),
                   record(1, None, error={"code": "timeout"},
                          telemetry={"calls": [{"usage": {"prompt_tokens": 50, "completion_tokens": 10}}]})]
        result = self.score(records, manifest, gold, prices={"input_per_million": 1, "output_per_million": 2})["overall"]
        self.assertEqual(result["citations"]["valid_exact_citation_count"], 1)
        self.assertEqual(result["citations"]["records_without_diagnostics"], 1)
        self.assertEqual(result["usage"]["calls"], 2)
        self.assertEqual(result["usage"]["prompt_tokens"], 150)
        self.assertAlmostEqual(result["cost"]["estimated_amount"], 0.00021)
        self.assertEqual(result["latency"]["measured_count"], 2)

    def test_missing_usage_is_unknown_not_free(self) -> None:
        manifest, gold = fixture([False])
        records = [record(0, [])]
        del records[0]["telemetry"]
        result = self.score(records, manifest, gold)["overall"]
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertIsNone(result["cost"]["estimated_amount"])
        self.assertEqual(result["usage"]["records_missing_telemetry"], 1)

    def test_source_clusters_are_resampled_whole_and_reproducibly(self) -> None:
        # One cluster has both a correct and incorrect response; row bootstrap
        # could produce 0 or 1 accuracy, but cluster bootstrap must remain 0.5.
        manifest, gold = fixture([True, False], ["same-source", "same-source"])
        records = [record(0, [claim()]), record(1, [claim()])]
        first = self.score(records, manifest, gold, bootstrap_samples=125, seed=7)
        second = self.score(list(reversed(records)), list(reversed(manifest)), list(reversed(gold)),
                            bootstrap_samples=125, seed=7)
        interval = first["backends"]["minimal"]["bootstrap"]
        self.assertEqual(interval["cluster_count"], 1)
        self.assertEqual(interval["end_to_end_accuracy"]["low"], 0.5)
        self.assertEqual(interval["end_to_end_accuracy"]["high"], 0.5)
        self.assertEqual(interval["detection_f1"]["low"], 2 / 3)
        self.assertEqual(interval, second["backends"]["minimal"]["bootstrap"])

    def test_paired_bootstrap_uses_all_cases_and_identical_source_draws(self) -> None:
        manifest, gold = fixture([True, False, True, False], ["A", "A", "B", "B"])
        records = [record(index, [claim()] if positive else [], backend)
                   for backend in ("minimal", "optimized-v3") for index, positive in enumerate([True, False, True, False])]
        report = self.score(records, manifest, gold, bootstrap_samples=99, seed=4)
        paired = report["paired_comparisons"]["optimized-v3_minus_minimal"]
        self.assertEqual(paired["paired_response_count"], 4)
        for metric in ("detection_f1", "end_to_end_accuracy"):
            self.assertEqual(paired[metric]["point_estimate"], 0)
            self.assertEqual(paired[metric]["low"], 0)
            self.assertEqual(paired[metric]["high"], 0)
            self.assertEqual(paired[metric]["defined_replicates"], 99)

    def test_undefined_f1_bootstrap_is_explicit(self) -> None:
        manifest, gold = fixture([False])
        summary = self.score([record(0, [])], manifest, gold, bootstrap_samples=10)["overall"]
        self.assertIsNone(summary["detection_f1"]["value"])
        self.assertEqual(summary["end_to_end_accuracy"]["value"], 1)
        self.assertEqual(summary["bootstrap"]["detection_f1"]["defined_replicates"], 0)
        self.assertEqual(summary["bootstrap"]["detection_f1"]["undefined_replicates"], 10)
        self.assertIsNone(summary["bootstrap"]["detection_f1"]["low"])

    def test_duplicate_unknown_missing_and_mismatched_keys_are_rejected(self) -> None:
        manifest, gold = fixture([True])
        records = [record(0, [claim()])]
        invalid_inputs = [
            (records * 2, manifest, gold, {}), (records, manifest * 2, gold, {}),
            (records, manifest, gold * 2, {}), (records, manifest, [], {}),
            ([record(9, [])], manifest, gold, {}), ([{"id": "0"}], manifest, gold, {}),
            (records, [{"id": "0"}], gold, {}),
            (records, manifest, [dict(gold[0], source_id="different")], {}),
            ([dict(records[0], source_id="different")], manifest, gold, {}),
            (records, manifest, [dict(gold[0], labels={})], {}),
            (records, manifest, gold, {"backends": ["optimized-v3"]}),
            (records, manifest, gold, {"backends": ["minimal", "minimal"]}),
        ]
        for args, cases, labels, kwargs in invalid_inputs:
            with self.subTest(args=args, cases=cases, labels=labels, kwargs=kwargs), self.assertRaises(ValueError):
                self.score(args, cases, labels, **kwargs)

    def test_inputs_are_not_mutated_and_report_is_strict_json_serializable(self) -> None:
        manifest, gold = fixture([True, False])
        records = [record(0, [claim()])]
        before = copy.deepcopy((records, manifest, gold))
        result = self.score(records, manifest, gold, bootstrap_samples=10)
        self.assertEqual((records, manifest, gold), before)
        json.dumps(result, allow_nan=False)

    def test_markdown_explicitly_discloses_metric_scope_and_failures(self) -> None:
        manifest, gold = fixture([True, False])
        rendered = render_report(self.score([record(0, [claim()])], manifest, gold))
        for phrase in ("pessimistic failure lower bound", "not an official", "Answered-only",
                       "negative failures", "not three-class accuracy", "semantic citation quality",
                       "does not assess extraction coverage", "missing records 1", "implicit_true", "due_to_null"):
            self.assertIn(phrase, rendered)

    def test_cli_can_read_gold_from_separate_directory_and_hash_inputs(self) -> None:
        manifest, gold = fixture([True, False])
        records = [record(0, [claim()]), record(1, [])]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "inference"
            run.mkdir()
            for path, rows in ((run / "predictions.jsonl", records), (run / "manifest.jsonl", manifest),
                               (root / "native_gold.jsonl", gold)):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                status = main(["--run-dir", str(run), "--gold", str(root / "native_gold.jsonl"),
                               "--bootstrap-samples", "10", "--backends", "minimal"])
            self.assertEqual(status, 0)
            self.assertFalse((run / "native_gold.jsonl").exists())
            output = json.loads((run / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(output["input_hashes"]), {"predictions", "manifest", "gold"})
            self.assertEqual(output["overall"]["success_count"], 2)
            self.assertTrue((run / "report.md").is_file())
            original_reports = {name: (run / name).read_bytes() for name in ("report.json", "report.md")}
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--run-dir", str(run), "--gold", str(root / "native_gold.jsonl")]), 2)
            self.assertIn("report already exists", stderr.getvalue())
            self.assertEqual(original_reports, {name: (run / name).read_bytes() for name in original_reports})

    def test_cli_inherits_frozen_prices_and_backends_and_rejects_changed_gold_before_parse(self) -> None:
        manifest, gold = fixture([True])
        manifest[0]["input_sha256"] = "synthetic-input-hash"
        records = [record(0, [claim()], input_sha256="synthetic-input-hash",
                          telemetry={"calls": [{"usage": {"prompt_tokens": 100, "completion_tokens": 20}}]})]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, data = root / "run", root / "data"
            run.mkdir()
            data.mkdir()
            for path, rows in ((run / "predictions.jsonl", records), (data / "manifest.jsonl", manifest),
                               (data / "native_gold.jsonl", gold)):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            (data / "inputs.jsonl").write_text('{}\n', encoding="utf-8")
            (data / "preparation.json").write_text('{"split":"test"}', encoding="utf-8")
            files = ("inputs.jsonl", "manifest.jsonl", "preparation.json", "native_gold.jsonl")
            shared = {"data_files_sha256": {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in files},
                      "selection": {"response_ids": ["0"]}, "backends": ["minimal", "optimized-v3"],
                      "price_reference": {"input_per_million": 1, "output_per_million": 2}}
            freeze = data / "freeze.json"
            freeze.write_text(json.dumps({"schema_version": "ragtruth-benchmark-freeze-v1", **shared}), encoding="utf-8")
            config = {"schema_version": "ragtruth-inference-run-v1", "mode": "formal", "data_dir": str(data),
                      "freeze_manifest": str(root / "original-unavailable-location" / "freeze.json"),
                      "freeze_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(), **shared}
            (run / "config.json").write_text(json.dumps(config), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--run-dir", str(run), "--data-dir", str(data), "--bootstrap-samples", "0"]), 0)
            output = json.loads((run / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(output["overall"]["total_count"], 2)
            self.assertEqual(output["backends"]["optimized-v3"]["missing_record_count"], 1)
            self.assertAlmostEqual(output["backends"]["minimal"]["cost"]["estimated_amount"], 0.00014)
            self.assertEqual(output["run_binding_validation"]["status"], "verified")
            self.assertEqual(output["run_binding_validation"]["resolved_freeze_manifest"], str(freeze.resolve()))
            # Invalid content ensures parsing cannot mask the hash mismatch.
            (data / "native_gold.jsonl").write_text("THIS MUST NEVER BE PARSED", encoding="utf-8")
            stderr = io.StringIO()
            with patch("scripts.ragtruth_score._read_jsonl") as reader, contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--run-dir", str(run), "--output-dir", str(root / "rescore"), "--bootstrap-samples", "0"]), 2)
                reader.assert_not_called()
            self.assertIn("Prepared data hash mismatch", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
