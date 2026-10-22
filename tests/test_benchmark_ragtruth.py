"""No-network checks for frozen RAGTruth inference and exposure accounting."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from grounding.config import Settings
from grounding.contracts import VerificationError, VerificationResult
from scripts import benchmark_ragtruth as runner


class RagtruthRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.freeze = self.root / "freeze.json"
        self.ledger = self.root / "ledger"
        self.settings = Settings(api_key="test-secret-value", thinking="enabled")
        self.calls = []
        self.call_lock = threading.Lock()
        self.provenance = {"python_version": "test", "inference_files_sha256": {"inference": "frozen"},
                           "support_files_sha256": {"scripts/benchmark_ragtruth.py": "frozen",
                                                     "scripts/ragtruth_score.py": "scorer-frozen"}}
        self.patch = patch.object(runner, "implementation_provenance", return_value=self.provenance)
        self.patch.start()
        self.write_data()

    def tearDown(self) -> None:
        self.patch.stop()
        self.temporary.cleanup()

    def write_data(self, *, split: str = "test", source: str = "source-1", identifier: str = "response-1") -> None:
        request = {"context_passages": ["The measured length is 12 m."],
                   "generated_answer": "The measured length is 12 m."}
        case = {"id": identifier, "input": request}
        meta = {"id": identifier, "source_id": source, "task_type": "Summary", "generator": "generator-1",
                "input_sha256": runner._canonical_sha(request), "gold_marker": "never-send-this"}
        for name, value in (("inputs.jsonl", case), ("manifest.jsonl", meta)):
            (self.data / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
        (self.data / "preparation.json").write_text(json.dumps({"split": split}), encoding="utf-8")
        # Deliberately invalid JSON. A successful run proves labels were not parsed.
        (self.data / "native_gold.jsonl").write_bytes(b"not JSON; private gold marker\xff")

    def factory(self, backend, settings):
        owner = self

        class FakeVerifier:
            def verify(self, request):
                with owner.call_lock:
                    owner.calls.append((backend, copy.deepcopy(request.to_dict()), id(self)))
                return VerificationResult({"claims": []}, {"calls": [{"stage": "verify", "usage": {"prompt_tokens": 3}}]})

        return FakeVerifier()

    def make_freeze(self, **kwargs):
        return runner.create_freeze(self.data, self.freeze, self.settings, **kwargs)

    def run_formal(self, name="run", **kwargs):
        return runner.run_benchmark(self.data, self.root / name, self.settings,
            freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=self.factory, **kwargs)

    def records(self, name="run"):
        return [json.loads(line) for line in (self.root / name / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_frozen_run_is_two_key_only_and_gold_is_never_parsed(self) -> None:
        self.make_freeze()
        result = self.run_formal()
        self.assertEqual(result["completed_records"], 3)
        self.assertEqual(result["error_records"], 0)
        self.assertFalse(result["gold_loaded"])
        self.assertEqual({call[0] for call in self.calls}, set(runner.PRIMARY_BACKENDS))
        for _, request, _ in self.calls:
            self.assertEqual(set(request), {"context_passages", "generated_answer"})
            self.assertNotIn("never-send-this", json.dumps(request))
        records = self.records()
        expected = runner.backend_order("response-1", runner.DEFAULT_SEED, runner.PRIMARY_BACKENDS)
        self.assertEqual([row["backend"] for row in records], expected)
        self.assertTrue(all(row["schema_valid"] and row["answer_chars"] > 0 for row in records))
        self.assertTrue(all(row["telemetry"]["calls"] for row in records))
        ledger = json.loads(next(self.ledger.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(ledger["status"], "completed")
        self.assertEqual(ledger["source_ids"], ["source-1"])

    def test_freeze_and_output_never_overwrite(self) -> None:
        self.make_freeze()
        before = self.freeze.read_bytes()
        with self.assertRaises(FileExistsError):
            self.make_freeze()
        self.assertEqual(self.freeze.read_bytes(), before)
        self.run_formal()
        before = (self.root / "run" / "predictions.jsonl").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_formal(replicate=True)
        self.assertEqual((self.root / "run" / "predictions.jsonl").read_bytes(), before)

    def test_freeze_rejects_native_gold_mutation_before_calls(self) -> None:
        self.make_freeze()
        with (self.data / "native_gold.jsonl").open("ab") as handle:
            handle.write(b"changed")
        with self.assertRaisesRegex(ValueError, "data_files_sha256"):
            self.run_formal()
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "run").exists())

    def test_settings_code_order_and_workers_are_frozen(self) -> None:
        self.make_freeze()
        for changed in ({"workers": 2}, {"seed": 1}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "run_options"):
                self.run_formal(**changed)
        with patch.object(runner, "implementation_provenance", return_value={"changed": True}):
            with self.assertRaisesRegex(ValueError, "provenance"):
                self.run_formal()
        changed_settings = Settings(api_key="test-secret-value", thinking="enabled", model="other")
        with self.assertRaisesRegex(ValueError, "settings"):
            runner.run_benchmark(self.data, self.root / "run", changed_settings,
                freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=self.factory)
        self.assertEqual(self.calls, [])

    def test_initial_inference_freeze_is_verified(self) -> None:
        self.patch.stop()
        try:
            with patch.object(runner, "SUPPORT_FILES", ()):
                provenance = runner.implementation_provenance()
                self.assertTrue(provenance["frozen_v2"]["verified"])
            initial = runner._object(runner.INITIAL_FREEZE)
            initial["files"]["grounding/config.py"] = "changed"
            changed_path = self.root / "bad-initial-freeze.json"
            changed_path.write_text(json.dumps(initial), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "initial RAGTruth freeze"):
                runner.implementation_provenance(changed_path)
        finally:
            self.patch.start()

    def test_errors_are_durable_and_credentials_redacted_everywhere(self) -> None:
        self.make_freeze()
        secret = self.settings.api_key

        def factory(backend, settings):
            class Fake:
                def verify(self, request):
                    if backend == "baseline":
                        raise VerificationError("upstream_error", "error " + secret, telemetry={
                            "calls": [{"response_text": secret, secret: {"nested": [secret]}}]})
                    if backend == "minimal":
                        raise RuntimeError("Do not persist unknown exception message " + secret)
                    return VerificationResult({"claims": "invalid"}, {"calls": [{"stage": "verify"}]})
            return Fake()

        result = runner.run_benchmark(self.data, self.root / "run", self.settings,
            freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=factory)
        self.assertEqual(result["error_records"], 3)
        records = {row["backend"]: row for row in self.records()}
        self.assertEqual(records["minimal"]["error"], {"code": "unexpected_error", "type": "RuntimeError"})
        self.assertEqual(records["optimized-v3"]["telemetry"]["calls"], [{"stage": "verify"}])
        self.assertTrue(records["optimized-v3"]["validation_errors"])
        self.assertTrue(all(not row["schema_valid"] and row["prediction"] is None for row in records.values()))
        for path in self.root.rglob("*.json*"):
            self.assertNotIn(secret.encode(), path.read_bytes())

    def test_source_overlap_requires_explicit_replicate_even_for_new_response(self) -> None:
        self.make_freeze()
        self.run_formal()
        self.write_data(identifier="new-response-same-source")
        self.freeze = self.root / "freeze-second.json"
        self.make_freeze()
        with self.assertRaisesRegex(ValueError, "--replicate"):
            self.run_formal("blocked")
        self.assertEqual(len(self.calls), 3)
        self.run_formal("replicate", replicate=True)
        config = runner._object(self.root / "replicate" / "config.json")
        self.assertEqual(config["exposure"]["role"], "replicate")
        self.assertTrue(config["exposure"]["prior_overlaps"][0]["source_ids"])

    def test_reservation_precedes_first_verifier_construction(self) -> None:
        self.make_freeze()
        original = self.factory

        def checking_factory(backend, settings):
            paths = list(self.ledger.glob("*.json"))
            self.assertEqual(len(paths), 1)
            self.assertEqual(runner._object(paths[0])["status"], "reserved")
            self.assertTrue((self.root / "run" / "config.json").exists())
            return original(backend, settings)

        runner.run_benchmark(self.data, self.root / "run", self.settings,
            freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=checking_factory)
        self.assertEqual(len(self.calls), 3)

    def test_smoke_only_accepts_train_and_subset(self) -> None:
        with self.assertRaisesRegex(ValueError, "train split"):
            runner.run_benchmark(self.data, self.root / "bad-smoke", self.settings,
                smoke=True, backends=("baseline",), ledger_dir=self.ledger, verifier_factory=self.factory)
        self.write_data(split="train")
        result = runner.run_benchmark(self.data, self.root / "smoke", self.settings,
            smoke=True, backends=("baseline",), ledger_dir=self.ledger, verifier_factory=self.factory)
        self.assertEqual(result["completed_records"], 1)
        self.assertEqual(self.calls[0][0], "baseline")

    def test_interrupt_retains_journal_and_reserves_sources(self) -> None:
        self.make_freeze(workers=1)
        invoked = 0

        def factory(backend, settings):
            class Fake:
                def verify(self, request):
                    nonlocal invoked
                    invoked += 1
                    if invoked == 2:
                        raise KeyboardInterrupt()
                    return VerificationResult({"claims": []})
            return Fake()

        result = runner.run_benchmark(self.data, self.root / "run", self.settings, workers=1,
            freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=factory)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(len(self.records()), 1)
        with self.assertRaisesRegex(ValueError, "--replicate"):
            self.run_formal("cannot-resume", workers=1)

    def stopped_origin(self):
        self.make_freeze(workers=1)
        invoked = 0

        def factory(backend, settings):
            class Fake:
                def verify(self, request):
                    nonlocal invoked
                    invoked += 1
                    if invoked == 2:
                        raise VerificationError("upstream_error", "Retained failure", telemetry={"calls": [{"stage": "verify"}]})
                    if invoked == 3:
                        raise KeyboardInterrupt()
                    return VerificationResult({"claims": []})
            return Fake()

        runner.run_benchmark(self.data, self.root / "origin", self.settings, workers=1,
            freeze_manifest=self.freeze, ledger_dir=self.ledger, verifier_factory=factory)
        self.provenance["support_files_sha256"]["scripts/benchmark_ragtruth.py"] = "recorder-recovery"
        self.freeze = self.root / "freeze-recovery.json"
        self.make_freeze(workers=1)

    def test_resume_reuses_exact_bytes_and_failures_without_repeating_calls(self) -> None:
        self.stopped_origin()
        original = (self.root / "origin" / "predictions.jsonl").read_bytes()
        original_config = (self.root / "origin" / "config.json").read_bytes()
        progress = self.run_formal("recovery", workers=1, replicate=True, resume_from=self.root / "origin")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(progress["completed_records"], 3)
        self.assertEqual(progress["reused_records"], 2)
        self.assertEqual(progress["reused_error_records"], 1)
        self.assertEqual(progress["error_records"], 1)
        self.assertEqual(progress["new_records"], 1)
        self.assertTrue((self.root / "recovery" / "predictions.jsonl").read_bytes().startswith(original))
        self.assertEqual((self.root / "origin" / "predictions.jsonl").read_bytes(), original)
        self.assertEqual((self.root / "origin" / "config.json").read_bytes(), original_config)
        self.assertEqual(len({(row["id"], row["backend"]) for row in self.records("recovery")}), 3)
        proof = runner._object(self.root / "recovery" / "config.json")["resume"]
        self.assertEqual(proof["origin_predictions_sha256"], runner._sha(self.root / "origin" / "predictions.jsonl"))
        self.assertEqual(proof["reused_errors"], 1)

    def test_resume_rejects_completed_origin_and_requires_replicate(self) -> None:
        self.stopped_origin()
        with self.assertRaisesRegex(ValueError, "formal --replicate"):
            self.run_formal("bad", workers=1, resume_from=self.root / "origin")
        progress_path = self.root / "origin" / "progress.json"
        value = runner._object(progress_path)
        value["status"] = "completed"
        runner._write_json(progress_path, value)
        with self.assertRaisesRegex(ValueError, "failed or interrupted"):
            self.run_formal("bad", workers=1, replicate=True, resume_from=self.root / "origin")
        self.assertEqual(self.calls, [])

    def test_resume_rejects_changed_model_data_and_scorer(self) -> None:
        self.stopped_origin()
        original_config_path = self.root / "origin" / "config.json"
        original = runner._object(original_config_path)
        for name in ("settings", "data_files_sha256", "provenance"):
            with self.subTest(name=name):
                changed = copy.deepcopy(original)
                if name == "settings":
                    changed[name]["model"] = "different-model"
                elif name == "data_files_sha256":
                    changed[name]["inputs.jsonl"] = "different-inputs"
                else:
                    changed[name]["support_files_sha256"]["scripts/ragtruth_score.py"] = "different-scorer"
                runner._write_json(original_config_path, changed)
                with self.assertRaises(ValueError):
                    self.run_formal("bad", workers=1, replicate=True, resume_from=self.root / "origin")
                runner._write_json(original_config_path, original)
        self.assertEqual(self.calls, [])

    def test_resume_rejects_duplicate_unknown_mismatch_and_torn_records(self) -> None:
        self.stopped_origin()
        path = self.root / "origin" / "predictions.jsonl"
        original = path.read_bytes()
        records = self.records("origin")
        mutations = [original + original.splitlines(keepends=True)[0], original[:-1]]
        for key, value in (("id", "unknown"), ("backend", "unknown"), ("input_sha256", "changed")):
            changed = copy.deepcopy(records)
            changed[0][key] = value
            mutations.append(("\n".join(json.dumps(row) for row in changed) + "\n").encode())
        for index, content in enumerate(mutations):
            with self.subTest(index=index):
                path.write_bytes(content)
                with self.assertRaises(ValueError):
                    self.run_formal("bad", workers=1, replicate=True, resume_from=self.root / "origin")
        path.write_bytes(original)
        self.assertEqual(self.calls, [])

    def test_resume_allows_identical_data_in_a_new_directory(self) -> None:
        self.stopped_origin()
        relocated = self.root / "relocated-data"
        relocated.mkdir()
        for name in runner.DATA_FILES:
            (relocated / name).write_bytes((self.data / name).read_bytes())
        self.data = relocated
        result = self.run_formal("recovery", workers=1, replicate=True, resume_from=self.root / "origin")
        self.assertEqual(result["new_records"], 1)

    def test_transient_atomic_replace_permission_error_retries(self) -> None:
        path = self.root / "snapshot.json"
        replacement = Path.replace
        attempts = 0

        def flaky_replace(source, target):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise PermissionError("temporary sharing violation")
            return replacement(source, target)

        with patch.object(Path, "replace", new=flaky_replace), patch.object(runner.time, "sleep") as sleep:
            runner._write_json(path, {"complete": True})
        self.assertEqual(attempts, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.1])
        self.assertEqual(runner._object(path), {"complete": True})

    def test_optional_progress_failure_never_discards_durable_records(self) -> None:
        self.make_freeze()
        original_write = runner._write_json
        progress_writes = 0

        def failing_progress(path, value, **kwargs):
            nonlocal progress_writes
            if path.name == "progress.json":
                progress_writes += 1
                if 2 <= progress_writes <= 4:
                    raise PermissionError("sharing violation")
            return original_write(path, value, **kwargs)

        with patch.object(runner, "_write_json", side_effect=failing_progress):
            result = self.run_formal()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["snapshot_write_failures"], 3)
        self.assertEqual(len(self.records()), 3)
        self.assertEqual(runner._object(self.root / "run" / "progress.json")["completed_records"], 3)


if __name__ == "__main__":
    unittest.main()
