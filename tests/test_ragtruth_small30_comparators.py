"""Synthetic checks for the comparison wrapper; no live calls or benchmark gold."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from grounding import config, contracts
from scripts import ragtruth_small30 as helper
from scripts import ragtruth_small30_comparators as compare


def api():
    return SimpleNamespace(helper=helper, contracts=contracts, config=config)


def fixture(identifier="synthetic"):
    case = {"id": identifier, "input": {"context_passages": ["A value is 3."], "generated_answer": "A value is 3."}}
    meta = {"id": identifier, "source_id": "source-" + identifier, "task_type": "QA", "generator": "fixture",
            "input_sha256": helper._canonical_sha(case["input"]), "answer_chars": 13}
    return case, meta


class ComparatorTests(unittest.TestCase):
    def test_only_two_request_fields_reach_verifier(self):
        case, meta = fixture()
        seen = []
        def factory(backend, settings):
            def verify(request):
                seen.append(request.to_dict())
                return contracts.VerificationResult({"claims": []}, {"calls": []})
            return SimpleNamespace(verify=verify)
        result = compare.infer_one(case, meta, "baseline", config.Settings(), api(), factory)
        self.assertEqual(seen, [case["input"]])
        self.assertEqual(set(seen[0]), {"context_passages", "generated_answer"})
        self.assertEqual(result["source_id"], meta["source_id"])
        self.assertTrue(result["schema_valid"])

    def test_failed_model_call_retains_usage_telemetry(self):
        case, meta = fixture()
        trace = {"calls": [{"stage": "minimal", "usage": {"prompt_tokens": 20, "completion_tokens": 4}}]}
        def factory(backend, settings):
            def verify(request):
                raise contracts.VerificationError("invalid_model_output", "Bad JSON", telemetry=trace)
            return SimpleNamespace(verify=verify)
        result = compare.infer_one(case, meta, "minimal", config.Settings(), api(), factory)
        self.assertIsNone(result["prediction"])
        self.assertEqual(result["telemetry"], trace)
        self.assertEqual(result["error"]["code"], "invalid_model_output")

    def test_public_contract_failure_keeps_call_accounting(self):
        case, meta = fixture()
        trace = {"calls": [{"stage": "minimal", "usage": {"prompt_tokens": 9, "completion_tokens": 8}}]}
        bad = {"claims": [{"claim_text": "A value is 3.", "verdict": "SUPPORTED", "reasoning": "Source.",
                           "citations": [{"index": 0, "quote": "A value is 35."}]}]}
        factory = lambda backend, settings: SimpleNamespace(verify=lambda request: contracts.VerificationResult(bad, trace))
        result = compare.infer_one(case, meta, "minimal", config.Settings(), api(), factory)
        self.assertIsNone(result["prediction"])
        self.assertEqual(result["telemetry"], trace)
        self.assertFalse(result["schema_valid"])

    def test_duplicate_missing_and_foreign_backend_are_rejected(self):
        inputs = [fixture("a")[0], fixture("b")[0]]
        valid = [{"id": c["id"], "backend": b} for c in inputs for b in compare.NEW_BACKENDS]
        compare.require_pairs(valid, inputs, compare.NEW_BACKENDS)
        for broken in (valid[:-1], [*valid[:-1], valid[0]], [*valid[:-1], {"id": "b", "backend": "optimized-v4.0"}]):
            with self.subTest(records=broken), self.assertRaises(ValueError):
                compare.require_pairs(broken, inputs, compare.NEW_BACKENDS)

    def test_environment_only_supplies_secret(self):
        values = helper.public_settings(config.Settings(thinking="enabled", max_output_tokens=16384))
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("LLM_API_KEY=synthetic-secret\nLLM_MODEL=wrong-model\nLLM_THINKING=disabled\nLLM_MAX_OUTPUT_TOKENS=7\n", encoding="utf-8")
            with patch.dict("os.environ", {}, clear=True):
                settings = compare.frozen_settings(api(), values, env)
        self.assertEqual(settings.api_key, "synthetic-secret")
        self.assertEqual(helper.public_settings(settings), values)

    def test_scoring_reuses_original_journal_without_mutating_it(self):
        inputs, manifest = zip(*(fixture(str(i)) for i in range(30)))
        def record(case, meta, backend):
            return {**meta, "backend": backend, "prediction": {"claims": []}, "error": None,
                    "schema_valid": True, "validation_errors": [], "telemetry": {"calls": []},
                    "latency_seconds": .01, "citations": {"citation_count": 0, "valid_citation_count": 0}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / "old", root / "new"
            (source / "data").mkdir(parents=True)
            output.mkdir()
            def journal(path, rows):
                path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
            journal(source / "data/inputs.jsonl", inputs)
            journal(source / "data/manifest.jsonl", manifest)
            journal(source / "data/native_gold.jsonl", [{"id": m["id"], "source_id": m["source_id"], "labels": []} for m in manifest])
            helper._write_json(source / "data/preparation.json", {})
            journal(source / "predictions.jsonl", [record(c, m, "optimized-v4.0") for c, m in zip(inputs, manifest)])
            journal(output / "predictions.jsonl", [record(c, m, b) for c, m in zip(inputs, manifest) for b in compare.NEW_BACKENDS])
            helper._write_json(output / "freeze.json", {})
            helper._write_json(output / "progress.json", {"status": "completed", "completed_records": 60, "frozen_artifacts_unchanged": True})
            bound = {"source_run": str(source), "price_reference": helper.PRICES, "qualification": "Synthetic only"}
            old_bytes = (source / "predictions.jsonl").read_bytes()
            with patch.object(compare, "check", return_value=bound):
                result = compare.score(output, api())
            self.assertEqual(result["scored_records"], 90)
            self.assertEqual((source / "predictions.jsonl").read_bytes(), old_bytes)
            report = json.loads((output / "scored/report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(report["backends"]), set(compare.ALL_BACKENDS))
            self.assertEqual(len(report["case_results"]), 90)
            self.assertEqual(report["input_hashes"]["original_predictions.jsonl"], compare.sha(source / "predictions.jsonl"))


if __name__ == "__main__":
    unittest.main()
