"""Offline scoring safety: unknowns, missing costs and paired audit integrity."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import analyze_v4_nf as analysis
from scripts.score_v4 import _observe, _summary


def native_row(backend, *, partial=False, positive=False):
    prediction = {"claims": [{"claim_text": "It is blue.", "verdict": "SUPPORTED", "reasoning": "Direct quote.",
                              "citations": [{"index": 0, "quote": "It is blue."}]}]}
    if partial:
        prediction.update(status="partial", errors=[{"id": "c2", "code": "invalid_model_output", "message": "Missing response."}])
    record = {"prediction": prediction, "error": None, "telemetry": {}, "answer_chars": 11}
    meta = {"id": "sample", "source_id": "source", "task_type": "summary", "generator": "fixture"}
    return _observe(meta, {"labels": [{}] if positive else []}, backend, record, ["It is blue."])


class NFAnalysisTests(unittest.TestCase):
    def test_missing_usage_retains_known_subtotal_without_complete_bill(self):
        records = [{"telemetry": {"calls": [
            {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 80}},
            {"usage": None},
            {"usage": {"prompt_tokens": 200, "completion_tokens": 30}},
        ]}}]
        result = analysis.reference_cost(records)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["estimated_total"])
        self.assertEqual(result["priced_calls"], 1)
        self.assertEqual(result["unpriced_calls"], 2)
        self.assertAlmostEqual(result["known_usage_subtotal"], (20 * .30 + 80 * .006 + 20 * 1.20) / 1e6)
        self.assertEqual(result["cache_standardized_priced_calls"], 2)
        self.assertAlmostEqual(result["cache_standardized_all_miss_known_subtotal"], (300 * .30 + 50 * 1.20) / 1e6)

    def test_partial_supported_is_unknown_not_negative(self):
        for positive in (False, True):
            with self.subTest(positive=positive):
                row = native_row("post_fix", partial=True, positive=positive)
                self.assertEqual(row["status"], "partial")
                self.assertIsNone(row["y_pred"])
                summary = _summary([row])
                self.assertEqual(summary["confusion"]["fn"], 0)
                self.assertEqual(summary["confusion"]["tn"], 0)
                self.assertEqual(summary["correct_decisions_per_all_cases"]["value"], 0)

    def test_bootstrap_pairs_sources_and_counts_unknown_in_all_denominator(self):
        rows = [native_row("pre_fix"), native_row("post_fix", partial=True)]
        result = analysis.paired_bootstrap(rows, samples=12)
        self.assertEqual(result["source_cluster_count"], 1)
        self.assertEqual(result["deltas"]["correct_decisions_per_all_cases"]["point_estimate"], -1)
        self.assertEqual(result["deltas"]["resolved_accuracy"]["undefined_replicates"], 12)
        self.assertEqual(result, analysis.paired_bootstrap(rows, samples=12))
        with self.assertRaisesRegex(ValueError, "both observations"):
            analysis.paired_bootstrap(rows[:1])

    def test_journal_cannot_drop_or_duplicate_a_variant(self):
        request = {"dataset": "dev", "id": "sample", "input": {}}
        record = {"dataset": "dev", "id": "sample", "backend": "pre_fix"}
        for records in ([record], [record, record]):
            with self.subTest(records=len(records)), self.assertRaisesRegex(ValueError, "exactly both variants"):
                analysis.analyze_records(records, [request], [], [], [], [], samples=0)

    def test_dual_parser_uses_transport_and_recorded_chunk_not_entire_answer(self):
        # Pure synthetic parser bodies make this test independent of historical
        # benchmark data and Git availability.
        common = """def _invalid(message):\n    raise VerificationError('invalid_model_output', message)\ndef _text(value):\n    return bool(value)\ndef _meaningful(value):\n    return bool(value)\n"""
        old = common + """def extract_claims(payload, answer, *, max_claims):\n    if answer != 'Echo. Echo.': _invalid('wrong chunk')\n    return [], [{'text':'Echo.', 'reason':'greeting', 'source_start':0, 'source_end':5}, {'text':'Echo.', 'reason':'greeting', 'source_start':6, 'source_end':11}]\n"""
        new = common + """def extract_claims(payload, answer, *, max_claims):\n    if answer != 'Echo. Echo.': _invalid('wrong chunk')\n    _invalid('uncovered second occurrence')\n"""
        request = {"dataset": "dev", "id": "synthetic", "input": {"generated_answer": "prefixEcho. Echo.suffix"}}
        row = {"dataset": "dev", "id": "synthetic", "backend": "pre_fix", "telemetry": {
            "calls": [{"stage": "decompose", "chunk_id": "d1", "http_status": 200, "finish_reason": "stop", "response_text": "{}"}],
            "extraction": {"chunks": [{"chunk_id": "d1", "source_start": 6, "source_end": 17, "fallback": False}],
                           "non_factual_spans": [{"text": "Echo.", "reason": "greeting", "source_start": 6, "source_end": 11},
                                                 {"text": "Echo.", "reason": "greeting", "source_start": 12, "source_end": 17}]}}}
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "pre.py", Path(directory) / "post.py"
            a.write_text(old, encoding="utf-8"); b.write_text(new, encoding="utf-8")
            result = analysis.dual_parser_audit([row], [request], a, b)
            self.assertEqual(result["audit_anomalies"], [])
            self.assertEqual(result["changed_calls"][0]["change"], "acceptance_changed")
            self.assertTrue(result["record_flags"][0]["any_transport_usable_parser_difference"])
            failing = deepcopy(row)
            failing["telemetry"]["calls"][0]["finish_reason"] = "length"
            failing["telemetry"]["extraction"]["chunks"][0]["fallback"] = True
            result = analysis.dual_parser_audit([failing], [request], a, b)
            self.assertFalse(result["record_flags"][0]["any_transport_usable_parser_difference"])
            self.assertEqual(result["groups"]["dev/pre_fix"].get("actual_accepted_payloads", 0), 0)

    def test_first_second_runtime_is_separate(self):
        records = [{"latency_seconds": 2, "backend_order_index": 0, "telemetry": {"calls": []}},
                   {"latency_seconds": 8, "backend_order_index": 1, "telemetry": {"calls": []}}]
        runtime = analysis.runtime_summary(records)
        self.assertEqual(runtime["mean_latency_seconds"], 5)
        self.assertEqual(runtime["by_variant_execution_order"]["first"]["mean_latency_seconds"], 2)
        self.assertEqual(runtime["by_variant_execution_order"]["second"]["mean_latency_seconds"], 8)


if __name__ == "__main__":
    unittest.main()
