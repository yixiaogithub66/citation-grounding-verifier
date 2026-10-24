"""Meaningful isolation, journal and immutable-freeze checks; no real model calls."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError, VerificationResult
from scripts import benchmark_v4_nf as runner


class NFOccurrenceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(api_key="secret-not-in-journal", thinking="enabled")
        self.config = V4Config()
        self.request = {"context_passages": ["The beam is 7 m long."], "generated_answer": "The beam is 7 m long."}
        self.case = {"dataset": "synthetic", "id": "offline-identity", "input": self.request,
                     "meta": {"source_id": "offline-source", "generator": "offline-generator"},
                     "backend_order": ["post_fix", "pre_fix"],
                     "expected": {"label": "DO_NOT_SEND"}}

    def records(self):
        return [json.loads(line) for line in (self.root / "responses.jsonl").read_text().splitlines()]

    def test_same_two_field_request_settings_and_config_failure_preserved(self):
        received = []
        owner = self
        def factory(variant, settings, config):
            self.assertIs(settings, self.settings)
            self.assertIs(config, self.config)
            class Verifier:
                def verify(self, request):
                    received.append(request.to_dict())
                    if variant == "pre_fix":
                        raise VerificationError("upstream_timeout", owner.settings.api_key, 504,
                                                {"calls": [{"stage": "decompose", "error": "timeout"}]})
                    return VerificationResult({"claims": []})
            return Verifier()
        progress = runner.run_records([self.case], self.root, self.settings, self.config, factory)
        self.assertEqual(received, [self.request, self.request])
        self.assertEqual(progress["completed_records"], 2)
        self.assertEqual(progress["error_records"], 1)
        self.assertNotIn(self.settings.api_key, (self.root / "responses.jsonl").read_text())
        failed = next(r for r in self.records() if r["variant"] == "pre_fix")
        self.assertIsNone(failed["prediction"])
        self.assertFalse(failed["schema_valid"])
        self.assertEqual(failed["telemetry"]["calls"][0]["error"], "timeout")

    def test_variant_order_is_deterministic_and_sequential(self):
        observed = []
        def factory(variant, *args):
            observed.append(variant)
            return Mock(verify=lambda request: VerificationResult({"claims": []}))
        runner.run_records([self.case], self.root, self.settings, self.config, factory)
        expected = self.case["backend_order"]
        self.assertEqual(observed, expected)
        self.assertEqual([r["backend_order_index"] for r in self.records()], [0, 1])
        self.assertTrue(all(r["backend_order"] == expected for r in self.records()))

    def test_schedule_has_exact_balance_in_every_registered_stratum(self):
        cases = [{"dataset": "dev", "id": str(i), "meta": {"source_id": "source"}} for i in range(6)]
        cases += [{"dataset": "behavior", "id": str(i), "meta": {"pair_id": "pair"}} for i in range(2)]
        cases += [{"dataset": "physics", "id": str(i), "meta": {}} for i in range(46)]
        scheduled = runner.balanced_schedule(cases, 20261023)
        for dataset, expected in (("dev", 3), ("behavior", 1), ("physics", 23)):
            self.assertEqual(sum(c["dataset"] == dataset and c["backend_order"][0] == "pre_fix" for c in scheduled), expected)
        self.assertEqual(scheduled, runner.balanced_schedule(cases, 20261023))
        reversed_result = runner.balanced_schedule(cases[::-1], 20261023)
        key = lambda c: (c["dataset"], c["id"])
        self.assertEqual(sorted(scheduled, key=key), sorted(reversed_result, key=key))
        with self.assertRaises(ValueError):
            runner.balanced_schedule(cases[:-1], 20261023)

    def test_invalid_public_report_keeps_telemetry_but_never_counts_complete(self):
        factory = Mock(return_value=Mock(verify=lambda request: VerificationResult(
            {"claims": [{"verdict": "SUPPORTED"}]}, {"calls": [{"stage": "verify"}]})))
        progress = runner.run_records([self.case], self.root, self.settings, self.config, factory)
        self.assertEqual(progress["error_records"], 2)
        self.assertTrue(all(r["validation_errors"] and r["prediction"] is None for r in self.records()))
        self.assertTrue(all(r["telemetry"]["calls"] for r in self.records()))

    def test_no_overwrite_or_second_inference(self):
        factory = Mock(return_value=Mock(verify=lambda request: VerificationResult({"claims": []})))
        runner.run_records([self.case], self.root, self.settings, self.config, factory)
        before = (self.root / "responses.jsonl").read_bytes()
        calls = factory.call_count
        with self.assertRaises(FileExistsError):
            runner.run_records([self.case], self.root, self.settings, self.config, factory)
        self.assertEqual(factory.call_count, calls)
        self.assertEqual((self.root / "responses.jsonl").read_bytes(), before)

    def fixture_freeze(self):
        (self.root / "artifact.py").write_text("value=1\n")
        value = {"schema_version": runner.SCHEMA, "backends": list(runner.VARIANTS),
                 "files_sha256": {"artifact.py": runner._sha(self.root / "artifact.py")}}
        (self.root / "config.json").write_text(json.dumps(value))
        (self.root / "config.sha256").write_text(runner._sha(self.root / "config.json"))

    def test_manifest_and_artifact_tampering_rejected(self):
        self.fixture_freeze()
        self.assertEqual(runner.verify_freeze(self.root)["schema_version"], runner.SCHEMA)
        (self.root / "artifact.py").write_text("value=2\n")
        with self.assertRaisesRegex(ValueError, "artifact mismatch"):
            runner.verify_freeze(self.root)
        self.fixture_freeze()
        (self.root / "config.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            runner.verify_freeze(self.root)

    def test_real_inference_refuses_unfrozen_checkout(self):
        self.fixture_freeze()
        with patch.object(runner, "frozen_factory") as factory:
            with self.assertRaisesRegex(ValueError, "frozen runner"):
                runner.run_frozen(self.root, self.settings)
            factory.assert_not_called()

    def test_old_and_current_module_globals_are_isolated(self):
        fixtures = Path(__file__).resolve().parent / "fixtures"
        proof = json.loads((fixtures / "v4_nf_pre_fix.provenance.json").read_text(encoding="utf-8"))
        old_source = (fixtures / "v4_nf_pre_fix.py").read_bytes()
        expected_sha256 = "ea9354a600807f671097a6961c9a854103e41d1751950314279c792c0dcc45aa"
        self.assertEqual(proof["source_commit"], "1106c2b536b19b311c57e006b7554a5d6d64c2af")
        self.assertTrue(proof["source_commit"].startswith(runner.PRE_COMMIT))
        self.assertEqual(proof["source_path"], "grounding/verifiers_v4.py")
        self.assertEqual(proof["sha256"], expected_sha256)
        self.assertEqual(hashlib.sha256(old_source).hexdigest(), expected_sha256)
        self.assertEqual(len(old_source), proof["size_bytes"])
        old_path = self.root / "pre_fix/grounding/verifiers_v4.py"
        old_path.parent.mkdir(parents=True)
        old_path.write_bytes(old_source)
        # This regression must also run from an exported tree or shallow clone.
        # Loading the exact historical fixture cannot depend on Git availability.
        with patch.object(runner.subprocess, "check_output", side_effect=AssertionError("Git is not available to this test")):
            build = runner.frozen_factory(self.root)
            old = build("pre_fix", self.settings, self.config)
            new = build("post_fix", self.settings, self.config)
        before = old._decompose.__func__.__globals__["extract_claims"]
        after = new._decompose.__func__.__globals__["extract_claims"]
        self.assertIsNot(before, after)
        payload = {"claims": [], "non_factual_spans": [{"text": "Thanks.", "reason": "politeness"}]}
        self.assertEqual(len(before(payload, "Thanks. Thanks.", max_claims=64)[1]), 2)
        with self.assertRaises(VerificationError):
            after(payload, "Thanks. Thanks.", max_claims=64)


if __name__ == "__main__":
    unittest.main()
