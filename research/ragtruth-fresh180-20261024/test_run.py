"""Network-free crash, leakage, and frozen-run contract checks."""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fresh180_runner_under_test", HERE / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class VerificationError(Exception):
    def __init__(self, code="invalid_model_output", message="invalid", telemetry=None):
        self.code, self.message, self.telemetry = code, message, telemetry
        super().__init__(message)


class Request:
    @classmethod
    def from_dict(cls, value):
        if set(value) != {"context_passages", "generated_answer"}:
            raise VerificationError()
        return SimpleNamespace(**value)


@dataclass
class Settings:
    api_key: str = "secret-test-placeholder"
    upstream_retries: int = 1
    repair_attempts: int = 1


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def synthetic():
    value = {"context_passages": ["The prism is blue."], "generated_answer": "The prism is blue."}
    return [{"id": "synthetic-a", "input": value}], [{"id": "synthetic-a", "source_id": "synthetic-source", "task_type": "synthetic-task", "generator": "synthetic-generator", "input_sha256": canonical(value)}]


def fake_api(factory=None):
    return SimpleNamespace(contracts=SimpleNamespace(VerificationError=VerificationError, VerificationRequest=Request),
                           factory=factory, validate=lambda report, contexts: None,
                           helper=SimpleNamespace(_citation_counts=lambda report, contexts: {"citation_count": 0, "valid_citation_count": 0},
                                                  _canonical_sha=canonical,
                                                  _jsonl=lambda path: [json.loads(line) for line in Path(path).read_text().splitlines()]))


def record(task, case, meta):
    return {"id": case["id"], **{k: meta[k] for k in ("source_id", "task_type", "generator", "input_sha256")},
            "backend": task["backend"], "pair_key": task["key"], "prediction": {"claims": []}, "error": None,
            "telemetry": {"calls": []}, "schema_valid": True, "backend_order": task["backend_order"],
            "backend_order_index": task["backend_order_index"]}


class DurableRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fresh180-tests-")
        self.root = Path(self.temporary.name)
        self.inputs, self.metadata = synthetic()
        self.plan = run.schedule(self.inputs, self.metadata, 20261024)
        self.config = {"schema_version": run.SCHEMA, "test_only": True}

    def tearDown(self):
        self.temporary.cleanup()

    def ledger(self):
        return run.Ledger(self.root / "output", self.config, self.plan)

    def test_publish_never_overwrites(self):
        path = self.root / "immutable.json"
        run.write_new(path, {"a": 1})
        with self.assertRaises(FileExistsError):
            run.write_new(path, {"a": 2})
        self.assertEqual(run.read_json(path), {"a": 1})

    def test_request_inference_whitelist_rejects_gold(self):
        self.inputs[0]["input"]["gold"] = "SUPPORTED"
        with self.assertRaises(VerificationError):
            Request.from_dict(self.inputs[0]["input"])

    def test_schedule_uses_no_generator_or_gold(self):
        changed = [dict(self.metadata[0], generator="different-generator", labels=[{"gold": "secret"}])]
        self.assertEqual(run.schedule(self.inputs, changed, 20261024), self.plan)
        self.assertEqual({p["backend"] for p in self.plan}, set(run.BACKENDS))

    def test_reservation_failure_never_calls_verifier(self):
        ledger = self.ledger()
        with patch.object(run, "write_new", side_effect=OSError("disk failed")), patch.object(run, "infer_one") as infer:
            with self.assertRaises(run.DurabilityError):
                run.execute(self.inputs, self.metadata, self.plan, Settings(), None, fake_api(), ledger)
            infer.assert_not_called()

    def test_result_failure_stops_new_dispatch_but_retains_reservation(self):
        ledger = self.ledger()
        original = run.write_new
        def fail_result(path, value):
            if Path(path).parent.name == "records":
                raise OSError("result disk failed")
            return original(path, value)
        def infer(case, meta, task, *_):
            return record(task, case, meta)
        with patch.object(run, "write_new", side_effect=fail_result), patch.object(run, "infer_one", side_effect=infer) as called:
            with self.assertRaises(run.DurabilityError):
                run.execute(self.inputs, self.metadata, self.plan, Settings(), None, fake_api(), ledger)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(len(ledger.reserved), 1)
        self.assertEqual(len(ledger.done), 0)

    def test_orphan_is_not_reissued_and_is_explicit_unknown(self):
        original = self.ledger()
        original.reserve(self.plan[0])
        ledger = run.Ledger(self.root / "output", self.config, self.plan, resume=True)
        def infer(case, meta, task, *_):
            return record(task, case, meta)
        with patch.object(run, "infer_one", side_effect=infer) as called:
            run.execute(self.inputs, self.metadata, self.plan, Settings(), None, fake_api(), ledger)
        self.assertEqual(called.call_count, 2)
        result = run.finalize(ledger, self.plan, self.inputs, self.metadata)
        rows = [json.loads(line) for line in (ledger.output / "predictions.jsonl").read_text().splitlines()]
        self.assertEqual(result["status"], "completed_with_unknown")
        unknown = [r for r in rows if r["error"]]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["error"]["code"], "reserved_result_unknown")
        self.assertNotIn("calls", unknown[0]["telemetry"])
        self.assertIsNone(unknown[0]["latency_seconds"])

    def test_progress_failure_does_not_lose_results_or_abort(self):
        ledger = self.ledger()
        def infer(case, meta, task, *_):
            self.assertTrue(ledger.path("reservations", task["key"]).exists())
            return record(task, case, meta)
        with patch.object(run, "write_view", side_effect=PermissionError("reader lock")), patch.object(run, "infer_one", side_effect=infer):
            run.execute(self.inputs, self.metadata, self.plan, Settings(), None, fake_api(), ledger)
        self.assertEqual(len(ledger.done), 3)
        self.assertEqual(len(ledger.warnings), 3)
        self.assertEqual(len(list((ledger.output / "records").glob("*.json"))), 3)

    def test_resuming_completed_pairs_calls_nothing_and_finalization_is_idempotent(self):
        ledger = self.ledger()
        for task in self.plan:
            ledger.reserve(task)
            ledger.result(task, record(task, self.inputs[0], self.metadata[0]))
        run.finalize(ledger, self.plan, self.inputs, self.metadata)
        previous = (ledger.output / "predictions.jsonl").read_bytes()
        resumed = run.Ledger(ledger.output, self.config, self.plan, resume=True)
        with patch.object(run, "infer_one") as called:
            run.execute(self.inputs, self.metadata, self.plan, Settings(), None, fake_api(), resumed)
        called.assert_not_called()
        run.finalize(resumed, self.plan, self.inputs, self.metadata)
        self.assertEqual((ledger.output / "predictions.jsonl").read_bytes(), previous)

    def test_finalize_refuses_never_reserved_pairs(self):
        with self.assertRaisesRegex(ValueError, "never reserved"):
            run.finalize(self.ledger(), self.plan, self.inputs, self.metadata)

    def test_existing_record_identity_tamper_is_rejected(self):
        ledger = self.ledger()
        task = self.plan[0]
        ledger.reserve(task)
        changed = record(task, self.inputs[0], self.metadata[0])
        changed["backend"] = "wrong-backend"
        ledger.result(task, changed)
        with self.assertRaisesRegex(ValueError, "identity"):
            run.Ledger(ledger.output, self.config, self.plan, resume=True)

    def test_changed_final_journal_is_rejected(self):
        ledger = self.ledger()
        for task in self.plan:
            ledger.reserve(task)
            ledger.result(task, record(task, self.inputs[0], self.metadata[0]))
        run.finalize(ledger, self.plan, self.inputs, self.metadata)
        (ledger.output / "predictions.jsonl").write_text("altered")
        with self.assertRaisesRegex(ValueError, "Final artifact differs"):
            run.finalize(ledger, self.plan, self.inputs, self.metadata)

    def test_minimal_single_call_settings_and_failure_telemetry_preserved(self):
        seen = []
        telemetry = {"calls": [{"usage": {"prompt_tokens": 9}, "response_text": "invalid"}]}
        def factory(backend, settings):
            seen.append(settings)
            def fail(request):
                raise VerificationError(telemetry=telemetry)
            return SimpleNamespace(verify=fail)
        task = next(t for t in self.plan if t["backend"] == "minimal")
        row = run.infer_one(self.inputs[0], self.metadata[0], task, Settings(), None, fake_api(factory))
        self.assertEqual(len(seen), 1)
        self.assertEqual((seen[0].upstream_retries, seen[0].repair_attempts), (0, 0))
        self.assertEqual(row["telemetry"], telemetry)
        self.assertEqual(row["error"]["code"], "invalid_model_output")

    def test_v4_partial_and_full_telemetry_preserved(self):
        partial = {"claims": [], "status": "partial", "errors": [{"id": "c1", "reason": "unknown"}]}
        telemetry = {"calls": [{"stage": "decompose", "attempt": 1}, {"stage": "decompose", "attempt": 2}], "chain": ["initial", "review"]}
        config = object()
        def factory(backend, settings, *, v4_config):
            self.assertIs(config, v4_config)
            return SimpleNamespace(verify=lambda request: SimpleNamespace(report=partial, telemetry=telemetry))
        task = next(t for t in self.plan if t["backend"] == "optimized-v4.0")
        row = run.infer_one(self.inputs[0], self.metadata[0], task, Settings(), config, fake_api(factory))
        self.assertEqual(row["prediction"], partial)
        self.assertEqual(row["telemetry"], telemetry)

    def test_baseline_must_have_zero_provider_attempts(self):
        def factory(backend, settings):
            return SimpleNamespace(verify=lambda request: SimpleNamespace(report={"claims": []}, telemetry={"calls": [{"usage": {}}]}))
        task = next(t for t in self.plan if t["backend"] == "baseline")
        row = run.infer_one(self.inputs[0], self.metadata[0], task, Settings(), None, fake_api(factory))
        self.assertEqual(row["error"]["code"], "call_budget_violation")

    def make_freeze(self):
        source = self.root / "source"
        source.mkdir()
        (source / "sentinel.py").write_text("# frozen code\n")
        data = self.root / "data"
        data.mkdir()
        for name in run.DATA_FILES:
            (data / name).write_text("not JSON on purpose: native gold is opaque")
        pre = {"source_root": str(source), "code_files_sha256": {"sentinel.py": run.sha(source / "sentinel.py")},
               "backends": list(run.BACKENDS), "python_version": platform.python_version(), "runner_sha256": run.sha(run.__file__),
               "run_options": {"workers": 4, "seed": 20261024}}
        prepath, boundpath = self.root / "preselection.json", self.root / "binding.json"
        run.write_new(prepath, pre)
        bound = {"preselection_sha256": run.sha(prepath), "data_files_sha256": {name: run.sha(data / name) for name in run.DATA_FILES}}
        run.write_new(boundpath, bound)
        for path in (prepath, boundpath):
            path.with_suffix(".sha256").write_text(run.sha(path))
        return prepath, boundpath, data, source

    def test_gold_is_hashed_without_deserializing(self):
        pre, bound, data, _ = self.make_freeze()
        run.check_freeze(pre, bound, data)

    def test_freeze_sidecar_prevents_settings_manifest_mutation(self):
        pre, bound, data, _ = self.make_freeze()
        value = run.read_json(pre)
        value["backends"] = ["minimal"]
        pre.write_bytes(run.encoded(value))
        with self.assertRaisesRegex(ValueError, "sidecar"):
            run.check_freeze(pre, bound, data)

    def test_source_mutation_is_rejected(self):
        pre, bound, data, source = self.make_freeze()
        (source / "sentinel.py").write_text("# changed after freeze")
        with self.assertRaisesRegex(ValueError, "Frozen source"):
            run.check_freeze(pre, bound, data)

    def test_data_mutation_is_rejected(self):
        pre, bound, data, _ = self.make_freeze()
        (data / "native_gold.jsonl").write_text("changed opaque bytes")
        with self.assertRaisesRegex(ValueError, "dataset binding"):
            run.check_freeze(pre, bound, data)

    def test_inputs_cannot_carry_annotations(self):
        data = self.root / "data"
        data.mkdir()
        inputs = [dict(self.inputs[0], labels=[])]
        (data / "inputs.jsonl").write_text(json.dumps(inputs[0]) + "\n")
        (data / "manifest.jsonl").write_text(json.dumps(self.metadata[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "unique IDs"):
            run.load_requests(data, fake_api(), {}, expected_count=1)

    def test_exposed_source_is_rejected_before_inference(self):
        data = self.root / "data"
        data.mkdir()
        (data / "inputs.jsonl").write_text(json.dumps(self.inputs[0]) + "\n")
        (data / "manifest.jsonl").write_text(json.dumps(self.metadata[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "overlap"):
            run.load_requests(data, fake_api(), {"sampling": {"excluded_source_ids": ["synthetic-source"]}}, expected_count=1)


if __name__ == "__main__":
    unittest.main()
