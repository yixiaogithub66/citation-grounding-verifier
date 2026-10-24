"""The development comparison must isolate labels, preserve failures and freeze bytes."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationResult
from grounding.factory import build_verifier, normalize_backend
from scripts.benchmark_ragtruth import _canonical_sha
from scripts.benchmark_v4_combined import run, BACKENDS, SCHEMA, M1_BACKENDS, M1_SCHEMA
from scripts import summarize_v4_combined as summarizer


class CombinedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.root / "grounding").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "grounding/dummy.py").write_text("version=1\n")
        self.request = {"context_passages": ["The beam is 7 m long."], "generated_answer": "The beam is 7 m long."}
        self.meta = {"id": "response", "source_id": "source", "task_type": "Summary", "generator": "not-model-input",
                     "input_sha256": _canonical_sha(self.request), "gold_marker": "not-model-input"}
        for name, value in (("inputs.jsonl", {"id": "response", "input": self.request}), ("manifest.jsonl", self.meta)):
            (self.data / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
        (self.data / "preparation.json").write_text(json.dumps({"seed": "ragtruth-blind-v1-20261022"}), encoding="utf-8")
        # Hash only: parsing this private opaque gold would fail.
        (self.data / "native_gold.jsonl").write_bytes(b"private invalid gold\xff")
        ledger = self.root / "results/ragtruth-ledger"
        ledger.mkdir(parents=True)
        (ledger / "old.json").write_text(json.dumps({"schema_version": "ragtruth-exposure-v1", "run_id": "old",
                                                   "source_ids": ["source"], "response_ids": ["response"], "status": "completed"}))
        self.settings = Settings(api_key="private-test-key", thinking="enabled")

    def test_gold_and_manifest_not_sent_and_failure_remains_failure(self):
        received = []
        owner = self
        def factory(backend, settings, *, v4_config):
            self.assertEqual(v4_config, V4Config())
            class Verifier:
                def verify(self, request):
                    received.append(request.to_dict())
                    if backend == "optimized-v4-combined":
                        raise VerificationError("upstream_timeout", owner.settings.api_key, 504)
                    return VerificationResult({"claims": []}, {"calls": []})
            return Verifier()
        output = self.root / "run"
        progress = run(self.data, output, self.settings, V4Config(), verifier_factory=factory, project_root=self.root)
        self.assertEqual(received, [self.request, self.request])
        self.assertEqual(progress["status"], "completed")
        self.assertEqual(progress["error_records"], 1)
        raw = (output / "predictions.jsonl").read_text()
        self.assertNotIn(self.settings.api_key, raw)
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual({r["backend"] for r in rows}, set(BACKENDS))
        failed = next(r for r in rows if r["error"])
        self.assertIsNone(failed["prediction"])
        self.assertEqual(failed["error"]["status"], 504)
        self.assertFalse(json.loads((output / "config.json").read_text())["gold_loaded"])
        self.assertEqual((output / "source/grounding/dummy.py").read_bytes(), (self.root / "grounding/dummy.py").read_bytes())

    def test_changed_code_invalidates_comparison(self):
        owner = self
        def factory(*args, **kwargs):
            class Verifier:
                def verify(self, request):
                    (owner.root / "grounding/dummy.py").write_text("version=2\n")
                    return VerificationResult({"claims": []}, {"calls": []})
            return Verifier()
        result = run(self.data, self.root / "run", self.settings, V4Config(), verifier_factory=factory, project_root=self.root)
        self.assertEqual(result["status"], "invalidated_changed_inputs")

    def test_m1_pair_freezes_and_summarizes_without_changing_default_pair(self):
        # This synthetic gold is first parsed by the offline scorer, not inference.
        (self.data / "native_gold.jsonl").write_text(json.dumps({
            "id": "response", "source_id": "source", "labels": []}) + "\n", encoding="utf-8")
        received = []
        def factory(backend, settings, *, v4_config):
            received.append((backend, v4_config))
            return Mock(verify=lambda request: VerificationResult({"claims": []}, {"calls": []}))
        output = self.root / "m1-run"
        progress = run(self.data, output, self.settings, V4Config(), verifier_factory=factory,
                       project_root=self.root, backends=M1_BACKENDS, schema=M1_SCHEMA,
                       intervention="Synthetic M1-only comparison")
        self.assertEqual(progress["expected_records"], 2)
        self.assertEqual({b for b, _ in received}, set(M1_BACKENDS))
        frozen = json.loads((output / "config.json").read_text())
        self.assertEqual(frozen["backends"], list(M1_BACKENDS))
        self.assertEqual(frozen["schema_version"], M1_SCHEMA)
        self.assertEqual(frozen["intervention"], "Synthetic M1-only comparison")
        self.assertEqual(frozen["v4_config"], V4Config().public_dict())
        with patch.object(summarizer, "ROOT", self.root):
            report = summarizer.summarize(output, self.data, self.root / "summary", samples=0)
        self.assertEqual(set(report["backends"]), set(M1_BACKENDS))
        self.assertEqual(report["paired_comparison"]["candidate"], M1_BACKENDS[1])
        self.assertEqual(set(report["runtime_diagnostics"]), set(M1_BACKENDS))
        self.assertNotIn("combined_paired_comparison", report)
        self.assertEqual(BACKENDS, ("optimized-v4.0", "optimized-v4-combined"))
        self.assertEqual(SCHEMA, "v4-combined-paired-exposed-dev-v1")

    def test_mismatched_or_unknown_experiment_rejected_before_output_or_calls(self):
        for backends, schema in ((M1_BACKENDS, SCHEMA), (BACKENDS, M1_SCHEMA),
                                 (M1_BACKENDS, "unregistered-schema"), (M1_BACKENDS[::-1], M1_SCHEMA)):
            factory = Mock()
            output = self.root / "invalid-run"
            with self.assertRaisesRegex(ValueError, "schema/backend pair"):
                run(self.data, output, self.settings, V4Config(), verifier_factory=factory,
                    project_root=self.root, backends=backends, schema=schema)
            factory.assert_not_called()
            self.assertFalse(output.exists())

    def test_summarizer_rejects_schema_pair_mismatch_before_scoring(self):
        output = self.root / "invalid-summary-run"
        output.mkdir()
        (output / "config.json").write_text(json.dumps({"schema_version": SCHEMA, "backends": list(M1_BACKENDS)}))
        (output / "progress.json").write_text("{}")
        with patch.object(summarizer, "score_records") as scorer:
            with self.assertRaisesRegex(ValueError, "schema/backend pair"):
                summarizer.summarize(output, self.data, self.root / "summary", samples=0)
            scorer.assert_not_called()

    def test_unseen_seed_rejected_before_calls(self):
        (self.data / "preparation.json").write_text(json.dumps({"seed": "ragtruth-blind-v2"}))
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "exposed v1"):
            run(self.data, self.root / "run", self.settings, V4Config(), verifier_factory=factory, project_root=self.root)
        factory.assert_not_called()

    def test_combined_alias_does_not_replace_historical_defaults(self):
        implementation = Mock()
        with patch.dict("sys.modules", {"grounding.verifiers_combined": Mock(OptimizedV4CombinedVerifier=implementation)}):
            build_verifier("optimized-v4-combined", self.settings, v4_config=V4Config())
        implementation.assert_called_once_with(self.settings, config=V4Config())
        self.assertEqual(normalize_backend("optimized-v4"), "optimized-v4.0")
        self.assertEqual(normalize_backend("optimized"), "optimized-v4.0")


if __name__ == "__main__":
    unittest.main()
