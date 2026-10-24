"""Network-free tests of frozen input isolation and durable experiment accounting."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("coverage_pilot_test", Path(__file__).with_name("pilot.py"))
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

ANSWER = "The gauge is amber."
VALID = {"claims": [{"claim_text": ANSWER, "source_span": ANSWER}], "non_factual_spans": []}


def fixture_cases():
    return {"cases": [{"id": f"case-{i}", "generated_answer": ANSWER,
                       "expected_facts": ["SECRET_GOLD"], "family": "SECRET_FAMILY",
                       "language": "SECRET_LANGUAGE"} for i in range(pilot.CASES)]}


class FakeProtocol:
    ARMS = pilot.ARMS

    @staticmethod
    def prompts():
        return {arm: "Synthetic prompt " + arm for arm in pilot.ARMS}

    @staticmethod
    def payload(arm, answer):
        if not isinstance(answer, str):
            raise AssertionError("Protocol must receive only answer text")
        return {"generated_answer": answer, "max_claims": 64}

    @staticmethod
    def validate(arm, raw, answer, max_claims=64):
        if raw != VALID:
            raise pilot.VerificationError("invalid_model_output", "Synthetic invalid shape")
        return deepcopy(VALID)


class FakeClient:
    def __init__(self, settings=None, error=False):
        self.error, self.seen = error, []

    def complete(self, messages, stage, telemetry):
        self.seen.append(deepcopy(messages))
        telemetry["calls"].append({"stage": stage, "model": "deepseek-flash", "system_fingerprint": "fake",
                                   "response_text": "SYNTHETIC_BAD_JSON" if self.error else json.dumps(VALID),
                                   "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 20}})
        if self.error:
            raise pilot.VerificationError("invalid_model_output", "Synthetic malformed JSON")
        return deepcopy(VALID)


def settings():
    return pilot.Settings(api_key="SYNTHETIC_LOCAL_KEY", thinking="disabled", max_output_tokens=8192,
                          repair_attempts=0, upstream_retries=0)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.protocol_patch = patch.object(pilot, "_protocol", FakeProtocol())
        self.protocol_patch.start()

    def tearDown(self):
        self.protocol_patch.stop()

    def test_whitelist_and_request_hash_strip_gold_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(fixture_cases()), encoding="utf-8")
            cases = pilot.inference_cases(path)
        self.assertEqual(set(cases[0]), {"id", "generated_answer"})
        planned = pilot.planned_requests(cases)
        self.assertEqual(len(planned), 120)
        for request in planned:
            text = json.dumps(request["payload"])
            self.assertNotIn("SECRET", text)
            self.assertNotIn("case-", text)
            self.assertEqual(request["identity_key"], pilot.identity_key(request))
            self.assertEqual(request["payload_sha256"], pilot.digest(pilot.encoded(request["payload"])))

    def test_schedule_exact_deterministic_and_balanced(self):
        cases = [{"id": str(i), "generated_answer": ANSWER} for i in range(pilot.CASES)]
        schedule = pilot.jobs(cases)
        self.assertEqual(schedule, pilot.jobs(list(reversed(cases))))
        self.assertEqual(len(schedule), 40)
        for position in range(len(pilot.ARMS)):
            counts = Counter(task["order"][position] for task in schedule)
            self.assertEqual(set(counts), set(pilot.ARMS))
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertEqual(len({r["identity_key"] for r in pilot.planned_requests(cases)}), 120)

    def test_single_failure_keeps_raw_trace_and_does_not_retry_or_relabel(self):
        client = FakeClient(error=True)
        planned = pilot.planned_requests([{ "id": str(i), "generated_answer": ANSWER} for i in range(pilot.CASES)])[0]
        result = pilot.single_call(client, settings(), planned, ANSWER)
        self.assertEqual(len(client.seen), 1)
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["validated_output"])
        self.assertIsNone(result["raw_output"])
        self.assertEqual(result["telemetry"]["calls"][0]["response_text"], "SYNTHETIC_BAD_JSON")
        self.assertNotIn("UNSUPPORTED", json.dumps(result))
        self.assertNotIn("SYNTHETIC_LOCAL_KEY", json.dumps(result))

    def test_input_bound_and_duplicate_ids_fail_without_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            source = fixture_cases()
            source["cases"][0]["generated_answer"] = "x" * 1201
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "one-chunk bound"):
                pilot.inference_cases(path)
            source = fixture_cases()
            source["cases"][1]["id"] = source["cases"][0]["id"]
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                pilot.inference_cases(path)

    def test_io_retry_is_bounded_and_exclusive_files_never_overwrite(self):
        attempts = []

        def transient():
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError("Synthetic transient lock")
            return "ok"

        with patch.object(pilot.time, "sleep") as sleep:
            self.assertEqual(pilot.bounded_io(transient), "ok")
            self.assertEqual(sleep.call_count, 2)
            with self.assertRaises(PermissionError):
                pilot.bounded_io(lambda: (_ for _ in ()).throw(PermissionError("Persistent lock")))
            self.assertEqual(sleep.call_count, 6)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            pilot.write_new(path, {"value": 1})
            with self.assertRaises(FileExistsError):
                pilot.write_new(path, {"value": 2})
            self.assertEqual(pilot.read_object(path), {"value": 1})

    def test_reservation_is_durable_before_call_and_unknown_cannot_be_reissued(self):
        planned = pilot.planned_requests([{ "id": str(i), "generated_answer": ANSWER} for i in range(pilot.CASES)])[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            pilot.write_new(output / "freeze.json", {"fixture": True})
            ledger = pilot.RunLedger(output, [planned])
            ledger.reserve(planned)
            path = output / "reservations" / (planned["identity_key"] + ".json")
            self.assertEqual(pilot.read_object(path)["request"], planned)
            with self.assertRaisesRegex(ValueError, "already reserved"):
                ledger.reserve(planned)
            complete = ledger.finalize(False)
            self.assertEqual(complete["unknown_reservations"], [planned["identity_key"]])
            self.assertEqual(complete["model_calls_started"], 1)
            self.assertEqual(complete["record_count"], 0)
            with self.assertRaises(FileExistsError):
                pilot.RunLedger(output, [planned])

    def test_response_checkpoint_failure_stops_dispatch_without_model_resampling(self):
        planned = pilot.planned_requests([{ "id": str(i), "generated_answer": ANSWER} for i in range(pilot.CASES)])[:2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            pilot.write_new(output / "freeze.json", {"fixture": True})
            ledger = pilot.RunLedger(output, planned)
            ledger.reserve(planned[0])
            response = pilot.single_call(FakeClient(), settings(), planned[0], ANSWER)
            with patch.object(pilot, "write_new", side_effect=PermissionError("Checkpoint unavailable")):
                with self.assertRaises(PermissionError):
                    ledger.record(response)
            self.assertTrue(ledger.stop.is_set())
            with self.assertRaisesRegex(RuntimeError, "Dispatch stopped"):
                ledger.reserve(planned[1])
            status = ledger.finalize(False)
            self.assertEqual(status["unknown_reservations"], [planned[0]["identity_key"]])
            self.assertEqual(status["record_count"], 0)

    def test_event_journal_failure_recovers_from_response_checkpoints_without_recall(self):
        planned = pilot.planned_requests([{ "id": str(i), "generated_answer": ANSWER} for i in range(pilot.CASES)])[:2]
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot, "MAX_CALLS", 2):
            output = Path(directory)
            pilot.write_new(output / "freeze.json", {"fixture": True})
            ledger = pilot.RunLedger(output, planned)
            original_stream = ledger.events
            ledger.events = SimpleNamespace(write=lambda raw: (_ for _ in ()).throw(PermissionError("Uncertain append")),
                                            close=original_stream.close)
            client = FakeClient()
            for request in planned:
                ledger.reserve(request)
                ledger.record(pilot.single_call(client, settings(), request, ANSWER))
            complete = ledger.finalize(True)
            self.assertFalse(complete["event_journal_healthy"])
            self.assertEqual(len(client.seen), 2)
            self.assertEqual(complete["record_count"], 2)
            self.assertEqual(complete["unknown_reservations"], [])
            self.assertEqual(len((output / "responses.jsonl").read_text().splitlines()), 2)
            self.assertEqual(len(complete["response_files_sha256"]), 2)
            self.assertEqual(complete["io_warnings"][0]["stage"], "response_event_journal")

    def test_frozen_full_run_survives_locked_progress_and_preserves_120_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            project, output = Path(directory) / "project", Path(directory) / "run"
            folder = project / pilot.REL
            folder.mkdir(parents=True)
            for sub in ("grounding", "scripts"):
                (project / sub).mkdir()
                (project / sub / "fixture.py").write_text("# fixture\n", encoding="utf-8")
            for name in ("pilot.py", "test_pilot.py", "protocol.py", "test_protocol.py", "PLAN.md"):
                (folder / name).write_text("fixture\n", encoding="utf-8")
            (folder / pilot.CASE_FILE).write_text(json.dumps(fixture_cases()), encoding="utf-8")
            manifest = pilot.freeze(output, settings(), project_root=project)
            self.assertEqual(manifest["max_model_calls"], 120)
            self.assertNotIn("SYNTHETIC_LOCAL_KEY", (output / "freeze.json").read_text())
            self.assertEqual(pilot.check_freeze(output), manifest)
            with self.assertRaises(FileExistsError):
                pilot.freeze(output, settings(), project_root=project)

            class StageClient(FakeClient):
                def complete(self, messages, stage, telemetry):
                    self.error = stage == "coverage_legacy"
                    return super().complete(messages, stage, telemetry)

            with patch.object(pilot, "ROOT", output / "source"), patch.object(pilot, "HERE", output / "source" / pilot.REL), patch.object(pilot, "ChatClient", StageClient), patch.object(pilot, "check_imported_dependencies") as guard:
                with patch.object(pilot, "write_progress", side_effect=PermissionError("Synthetic locked progress view")):
                    complete = pilot.run(output, settings())
                self.assertEqual(complete["record_count"], 120)
                self.assertEqual(complete["model_calls_started"], 120)
                self.assertEqual(complete["error"], 40)
                self.assertEqual(complete["valid"], 80)
                self.assertEqual(complete["unknown_reservations"], [])
                self.assertGreater(len(complete["io_warnings"]), 0)
                self.assertFalse((output / "progress.json").exists())
                self.assertEqual(len(list((output / "reservations").glob("*.json"))), 120)
                self.assertEqual(len(list((output / "responses").glob("*.json"))), 120)
                analysis = pilot.analyze(output)
                self.assertEqual(analysis["runtime"]["usage"]["calls"], 120)
                self.assertIsNone(analysis["semantic_scores"])
                self.assertGreater(guard.call_count, 0)
                with self.assertRaises(FileExistsError):
                    pilot.run(output, settings())
                with self.assertRaises(FileExistsError):
                    pilot.analyze(output)
            (output / "source" / "grounding/fixture.py").write_text("# changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen file changed"):
                pilot.check_freeze(output)

    def test_dependency_guard_and_request_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            outside = Path(directory) / "client.py"
            outside.write_text("# outside\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escaped the frozen source"):
                pilot.check_imported_dependencies(source, {}, [("grounding.client", SimpleNamespace(__file__=str(outside)))])
            inside = source / pilot.REL / "protocol.py"
            inside.parent.mkdir(parents=True)
            inside.write_text("# inside\n", encoding="utf-8")
            modules = [("coverage_pilot_protocol", SimpleNamespace(__file__=str(inside)))]
            with self.assertRaisesRegex(ValueError, "not bound to this freeze"):
                pilot.check_imported_dependencies(source, {}, modules)
            pilot.check_imported_dependencies(source, {str(pilot.REL.as_posix()) + "/protocol.py": pilot.sha(inside)}, modules)


if __name__ == "__main__":
    unittest.main()
