"""Network-free recovery identity, reservation and filesystem-lock tests."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


recovery = module("recovery_test_subject", "recovery.py")
pilot = module("recovery_frozen_pilot_fixture", "pilot.py")
ANSWER = "The gauge is amber."
VALID = {"claims": [{"claim_text": ANSWER, "source_span": ANSWER}], "non_factual_spans": []}


class FakeClient:
    seen = []

    def __init__(self, settings=None):
        pass

    def complete(self, messages, stage, telemetry):
        self.seen.append((stage, deepcopy(messages)))
        telemetry["calls"].append({"stage": stage, "attempt": 1,
                                   "model": "deepseek-flash", "response_text": json.dumps(VALID),
                                   "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 20}})
        return deepcopy(VALID)


def fixture(directory):
    root, original, output = Path(directory) / "project", Path(directory) / "original", Path(directory) / "recovered"
    folder = root / recovery.REL
    folder.mkdir(parents=True)
    for name in ("pilot.py", "test_pilot.py", "PLAN.md", "recovery.py", "test_recovery.py", "RECOVERY_PLAN.md"):
        (folder / name).write_text("fixture\n", encoding="utf-8")
    for name in ("grounding", "scripts"):
        (root / name).mkdir()
        (root / name / "fixture.py").write_text("# fixture\n", encoding="utf-8")
    data = {"cases": [{"id": str(i), "generated_answer": ANSWER} for i in range(16)],
            "controlled_seeds": [{"seed_id": "s" + str(i), "case_id": str(i), "draft": VALID} for i in range(12)]}
    (folder / "cases.json").write_text(json.dumps(data), encoding="utf-8")
    settings = pilot.Settings(api_key="FAKE", thinking="disabled", max_output_tokens=8192, upstream_retries=0, repair_attempts=0)
    pilot.freeze(original, settings, project_root=root)
    cases, seeds = pilot.inference_cases(folder / "cases.json")
    records = []
    for task in pilot.jobs(cases, seeds):
        case, probe, rep = task["case"], task["probe"], task["repetition"]
        if probe == "natural":
            base = pilot.single_call(FakeClient(), settings, probe, case["id"], "base", rep,
                                     pilot.extraction_payload(case), pilot.prompts()["base"],
                                     lambda raw, tel: pilot.validate_extraction(raw, case), 0)
            records.append(base)
            state = pilot.draft_from_record(base, case)
        else:
            state = case["draft"]
        for position, arm in enumerate(task["order"], start=1 if probe == "natural" else 0):
            payload = pilot.extraction_payload(case) if arm == "fresh" else pilot.revision_payload(case, state)
            record = pilot.single_call(FakeClient(), settings, probe, case["id"], arm, rep, payload,
                                       pilot.prompts()[arm], lambda raw, tel: pilot.validate_extraction(raw, case), position)
            records.append(record)
    records = records[:50]
    # A journaled failure is retained, not retried or reclassified.
    records[0]["status"] = "error"
    records[0]["validated_output"] = None
    records[0]["error"] = {"code": "invalid_model_output", "message": "Synthetic failure"}
    with (original / "responses.jsonl").open("wb") as stream:
        for record in records:
            recovery.append_sync(stream, record)
    recovery.write_new(original / "progress.json", {"status": "aborted", "record_count": 50, "model_calls_started": 51})
    return root, original, output, settings


class RecoveryTests(unittest.TestCase):
    def test_progress_replace_only_retries_io_and_keeps_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            original_replace = recovery.os.replace
            calls = []
            def transient(a, b):
                calls.append((a, b))
                if len(calls) < 3:
                    raise PermissionError("Synthetic reader lock")
                original_replace(a, b)
            with patch.object(recovery.os, "replace", side_effect=transient):
                self.assertTrue(recovery.write_progress(directory, {"count": 7}, retries=3, delay=0))
            self.assertEqual(len(calls), 3)
            self.assertEqual(recovery.read(Path(directory) / "progress.json"), {"count": 7})
            def locked_progress(a, b):
                if Path(b).name == "progress.json":
                    raise PermissionError("Synthetic long reader lock")
                original_replace(a, b)
            with patch.object(recovery.os, "replace", side_effect=locked_progress):
                self.assertFalse(recovery.write_progress(directory, {"count": 8}, retries=2, delay=0))
            checkpoints = list(Path(directory).glob("progress-checkpoint.*.json"))
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(recovery.read(checkpoints[0]), {"count": 8})

    def test_partial_and_duplicate_journal_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "responses.jsonl"
            path.write_bytes(b'{"partial":')
            with self.assertRaisesRegex(ValueError, "partial trailing"):
                recovery.read_journal(path)
            row = {"probe": "natural", "case_id": "x", "arm": "base", "repetition": 0}
            path.write_text((json.dumps(row) + "\n") * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                recovery.read_journal(path)

    def test_fifty_records_preserved_exactly_and_only_102_reserved_calls_added(self):
        with tempfile.TemporaryDirectory() as directory:
            root, original, output, settings = fixture(directory)
            original_bytes = (original / "responses.jsonl").read_bytes()
            original_progress = (original / "progress.json").read_bytes()
            with patch.object(recovery, "load_pilot", return_value=pilot):
                manifest = recovery.prepare(original, output, project_root=root)
                self.assertEqual(manifest["maximum_new_calls"], 102)
                self.assertEqual(manifest["original_unjournaled_started_counter"], 1)
                self.assertEqual((output / "responses.jsonl").read_bytes(), original_bytes)
                with self.assertRaises(FileExistsError):
                    recovery.prepare(original, output, project_root=root)
                FakeClient.seen = []
                with patch.object(recovery, "__file__", str(output / "recovery-source/recovery.py")), patch.object(pilot, "pilot_settings", return_value=settings), patch.object(pilot, "ChatClient", FakeClient):
                    progress = recovery.run(output, Path("not-used.env"))
                    self.assertEqual(progress["record_count"], 152)
                    self.assertEqual(progress["new_reservations"], 102)
                    self.assertIsNone(progress["physical_provider_attempts_exact"])
                    self.assertEqual(len(FakeClient.seen), 102)
                    with self.assertRaises(ValueError):
                        recovery.run(output, Path("not-used.env"))
                raw, rows = recovery.read_journal(output / "responses.jsonl")
                self.assertTrue(raw.startswith(original_bytes))
                self.assertEqual(rows[0]["status"], "error")
                self.assertEqual((original / "responses.jsonl").read_bytes(), original_bytes)
                self.assertEqual((original / "progress.json").read_bytes(), original_progress)
                reservations = [json.loads(line) for line in (output / "reservations.jsonl").read_text().splitlines()]
                self.assertEqual(len(reservations), 102)
                self.assertEqual({tuple(r["identity"]) for r in reservations}, {recovery.identity(r) for r in rows[50:]})
                self.assertEqual([r["new_attempt_sequence"] for r in reservations], list(range(1, 103)))
                by_id = {recovery.identity(row): row for row in rows}
                for reservation in reservations:
                    row = by_id[tuple(reservation["identity"])]
                    self.assertEqual(reservation["payload_sha256"], row["payload_sha256"])
                    self.assertEqual(reservation["prompt_sha256"], row["prompt_sha256"])
                    self.assertLessEqual(reservation["reserved_at"], row["started_at"])
                for row in rows:
                    if row["arm"] == "generic":
                        pair = by_id[(row["probe"], row["case_id"], "bidirectional", row["repetition"])]
                        self.assertEqual(row["payload"], pair["payload"])
                recovery.check_recovery(output, pilot)

    def test_original_change_and_more_than_102_missing_calls_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root, original, output, settings = fixture(directory)
            with patch.object(recovery, "load_pilot", return_value=pilot):
                recovery.prepare(original, output, project_root=root)
                (original / "progress.json").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Original run was modified"):
                    recovery.check_recovery(output, pilot)
        with tempfile.TemporaryDirectory() as directory:
            root, original, output, settings = fixture(directory)
            raw, rows = recovery.read_journal(original / "responses.jsonl")
            (original / "responses.jsonl").write_bytes(b"\n".join(raw.splitlines()[:49]) + b"\n")
            with patch.object(recovery, "load_pilot", return_value=pilot), self.assertRaisesRegex(ValueError, "ceiling"):
                recovery.prepare(original, output, project_root=root)


if __name__ == "__main__":
    unittest.main()
