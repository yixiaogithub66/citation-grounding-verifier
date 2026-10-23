"""No-network fixtures for preselection freeze, source exclusion and journaling."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from grounding.config import Settings
from grounding.config_v4 import V4Config
from scripts.benchmark_ragtruth import _canonical_sha, _sha, _jsonl
from scripts.ragtruth_v4 import (create_preselection_freeze, prepare_dataset, create_run_freeze,
                               run_benchmark, check_preselection, code_hashes)
from scripts.score_v4 import load_prediction_journal


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


class FrozenV4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw, self.old = self.root / "raw", self.root / "old"
        self.freeze = self.root / "preselection.json"
        self.new = self.root / "new"
        self.settings, self.config = Settings(thinking="enabled"), V4Config()
        write(self.root / "grounding/dummy.json", {"implementation": 1})
        (self.root / "scripts").mkdir()
        (self.root / "scripts/dummy.py").write_text("value=1\n")
        sources, responses, oldmanifest = [], [], []
        for task in ("QA", "Summary", "Data2txt"):
            for index in range(11):
                sid = f"{task}-{index}"
                info = {"passages": "Source."} if task == "QA" else "Source." if task == "Summary" else {"field": "Source."}
                sources.append({"source_id": sid, "task_type": task, "source_info": info})
                for r in range(6):
                    responses.append({"id": f"{sid}-{r}", "source_id": sid, "split": "test", "quality": "good",
                                      "model": "synthetic", "response": "Answer.", "labels": []})
                if index == 0:
                    for historical in range(10):
                        oldsid = sid if historical == 0 else f"historical-{task}-{historical}"
                        oldmanifest.extend({"id": f"old-{oldsid}-{r}", "source_id": oldsid, "task_type": task} for r in range(6))
        lines(self.raw / "source_info.jsonl", sources)
        lines(self.raw / "response.jsonl", responses)
        write(self.raw / "provenance.json", {"fixture": True})
        lines(self.old / "manifest.jsonl", oldmanifest)
        write(self.old / "preparation.json", {"seed": "ragtruth-blind-v1-20261022",
            "selected_source_ids": {task: sorted({m["source_id"] for m in oldmanifest if m["task_type"] == task}) for task in ("QA", "Summary", "Data2txt")},
            "artifacts_sha256": {"manifest.jsonl": _sha(self.old / "manifest.jsonl")},
            "raw_files_sha256": {name: _sha(self.raw / name) for name in ("source_info.jsonl", "response.jsonl", "provenance.json")}})

    def freeze_code(self):
        return create_preselection_freeze(self.old, self.freeze, self.settings, self.config, project_root=self.root)

    def test_preselection_reads_no_test_records_and_hashes_full_v4_config(self):
        with patch("scripts.ragtruth_data.load_jsonl", side_effect=AssertionError("test data read")):
            frozen = self.freeze_code()
        self.assertEqual(frozen["v4_config"], self.config.public_dict())
        self.assertIn("scripts/dummy.py", frozen["code_files_sha256"])
        self.assertEqual(len(frozen["sampling"]["excluded_source_ids"]), 30)
        with self.assertRaises(FileExistsError):
            self.freeze_code()

    def test_source_level_exclusion_keeps_all_six_and_selection_is_deterministic(self):
        self.freeze_code()
        result = prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)
        metas = _jsonl(self.new / "manifest.jsonl")
        self.assertEqual(len(metas), 180)
        self.assertEqual({m["source_id"] for m in metas} & {"QA-0", "Summary-0", "Data2txt-0"}, set())
        second = self.root / "second"
        prepare_dataset(self.raw, second, self.freeze, project_root=self.root)
        self.assertEqual((self.new / "inputs.jsonl").read_bytes(), (second / "inputs.jsonl").read_bytes())
        self.assertEqual(result["counts"]["selected_sources"], 30)
        runfreeze = create_run_freeze(self.new, self.root / "runfreeze.json", self.freeze, project_root=self.root)
        self.assertEqual(runfreeze["v4_config"], self.config.public_dict())

    def test_code_change_fails_before_new_data_loading(self):
        self.freeze_code()
        (self.root / "scripts/dummy.py").write_text("value=2\n")
        with patch("scripts.ragtruth_data.load_jsonl", side_effect=AssertionError("test data read")):
            with self.assertRaisesRegex(ValueError, "code mismatch"):
                prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)
        self.assertFalse(self.new.exists())

    def test_raw_mutation_fails_closed(self):
        self.freeze_code()
        (self.raw / "response.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "raw input hash"):
            prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)

    def test_old_manifest_truncation_cannot_reduce_source_exclusions(self):
        (self.old / "manifest.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "manifest no longer matches"):
            self.freeze_code()

    def test_prepared_gold_mutation_is_not_bound_into_a_new_run_freeze(self):
        self.freeze_code()
        prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)
        with (self.new / "native_gold.jsonl").open("a") as handle:
            handle.write("{}\n")
        with self.assertRaisesRegex(ValueError, "artifacts changed"):
            create_run_freeze(self.new, self.root / "runfreeze.json", self.freeze, project_root=self.root)

    def test_run_rejects_changed_v4_stage_setting_before_inference(self):
        self.freeze_code()
        prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)
        freeze_path = self.root / "runfreeze.json"
        create_run_freeze(self.new, freeze_path, self.freeze, project_root=self.root)
        changed = self.config.public_dict()
        changed["verify"]["thinking"] = "enabled"
        with self.assertRaisesRegex(ValueError, "v4_config"):
            run_benchmark(self.new, self.root / "run", self.settings, changed, mode="test", project_root=self.root,
                          freeze_manifest=freeze_path, verifier_factory=lambda *a, **kw: self.fail("model invoked"))

    def test_ledger_sources_excluded_even_when_not_in_old_manifest(self):
        write(self.root / "results/ragtruth-ledger/smoke.json", {"schema_version": "ragtruth-exposure-v1", "source_ids": ["train-source"]})
        frozen = self.freeze_code()
        self.assertIn("train-source", frozen["sampling"]["excluded_source_ids"])

    def test_custom_empty_ledger_cannot_hide_default_exposure_and_new_exposure_blocks_selection(self):
        default = self.root / "results/ragtruth-ledger"
        write(default / "smoke.json", {"schema_version": "ragtruth-exposure-v1", "source_ids": ["train-source"]})
        frozen = create_preselection_freeze(self.old, self.freeze, self.settings, self.config,
                                           project_root=self.root, ledger_dir=self.root / "empty-ledger")
        self.assertIn("train-source", frozen["sampling"]["excluded_source_ids"])
        write(default / "later.json", {"schema_version": "ragtruth-exposure-v1", "source_ids": ["QA-1"]})
        with patch("scripts.ragtruth_data.load_jsonl", side_effect=AssertionError("new test read")):
            with self.assertRaisesRegex(ValueError, "New source exposure"):
                prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)

    def test_frozen_supplemental_ledger_cannot_change_or_disappear(self):
        extra = self.root / "extra/exposure.json"
        write(extra, {"schema_version": "ragtruth-exposure-v1", "source_ids": ["earlier-source"]})
        create_preselection_freeze(self.old, self.freeze, self.settings, self.config,
                                   project_root=self.root, ledger_dir=extra.parent)
        write(extra, {"schema_version": "ragtruth-exposure-v1", "source_ids": []})
        with self.assertRaisesRegex(ValueError, "changed or disappeared"):
            check_preselection(self.freeze, project_root=self.root)
        extra.unlink()
        with self.assertRaisesRegex(ValueError, "changed or disappeared"):
            check_preselection(self.freeze, project_root=self.root)

    def formal_fixture(self):
        self.freeze_code()
        prepare_dataset(self.raw, self.new, self.freeze, project_root=self.root)
        path = self.root / "runfreeze.json"
        create_run_freeze(self.new, path, self.freeze, project_root=self.root)
        return path

    def test_formal_new_exposure_blocks_calls_even_with_empty_custom_ledger(self):
        freeze = self.formal_fixture()
        write(self.root / "results/ragtruth-ledger/later.json",
              {"schema_version": "ragtruth-exposure-v1", "source_ids": ["QA-1"]})
        with self.assertRaisesRegex(ValueError, "New source exposure"):
            run_benchmark(self.new, self.root / "run", self.settings, self.config, mode="test",
                          freeze_manifest=freeze, project_root=self.root, ledger_dir=self.root / "empty",
                          verifier_factory=lambda *a, **kw: self.fail("model invoked"))

    def test_explicit_replicate_allows_only_this_selection_new_exposure(self):
        freeze = self.formal_fixture()
        selected = {m["source_id"] for m in _jsonl(self.new / "manifest.jsonl")}
        later = self.root / "results/ragtruth-ledger/later.json"
        write(later, {"schema_version": "ragtruth-exposure-v1", "source_ids": sorted(selected)})
        with self.assertRaisesRegex(ValueError, "New source exposure"):
            check_preselection(self.freeze, project_root=self.root)
        check_preselection(self.freeze, project_root=self.root, allow_exposed_sources=selected)
        write(later, {"schema_version": "ragtruth-exposure-v1", "source_ids": sorted(selected | {"foreign-new"})})
        with self.assertRaisesRegex(ValueError, "New source exposure"):
            run_benchmark(self.new, self.root / "run", self.settings, self.config, mode="test", replicate=True,
                          freeze_manifest=freeze, project_root=self.root,
                          verifier_factory=lambda *a, **kw: self.fail("model invoked"))

    def test_formal_supplemental_ledger_must_be_preselection_bound(self):
        freeze = self.formal_fixture()
        with self.assertRaisesRegex(ValueError, "supplemental ledger must be bound"):
            run_benchmark(self.new, self.root / "run", self.settings, self.config, mode="test",
                          freeze_manifest=freeze, project_root=self.root, ledger_dir=self.root / "unbound",
                          verifier_factory=lambda *a, **kw: self.fail("model invoked"))

    def dev_data(self):
        data = self.root / "dev"
        request = {"context_passages": ["Source."], "generated_answer": "Answer. Unfinished."}
        inputs = [{"id": str(i), "input": request} for i in range(2)]
        manifest = [{"id": str(i), "source_id": "s" + str(i), "task_type": "QA", "generator": "g",
                     "input_sha256": _canonical_sha(request)} for i in range(2)]
        lines(data / "inputs.jsonl", inputs)
        lines(data / "manifest.jsonl", manifest)
        lines(data / "native_gold.jsonl", [{"id": str(i), "source_id": "s" + str(i), "labels": []} for i in range(2)])
        write(data / "preparation.json", {"seed": "ragtruth-blind-v1-20261022", "split": "test"})
        return data

    def test_dev_subset_journals_partial_without_loading_gold_and_all_config_is_saved(self):
        data = self.dev_data()
        calls = []
        def factory(backend, settings, **kwargs):
            calls.append((backend, kwargs))
            report = {"claims": [{"claim_text": "Answer.", "verdict": "UNSUPPORTED", "reasoning": "Absent.", "citations": []}],
                      "status": "partial", "errors": [{"id": "c2", "code": "upstream_error", "message": "Failure."}]}
            return SimpleNamespace(verify=lambda request: SimpleNamespace(report=report, telemetry={"calls": []}))
        original = _jsonl
        def guarded(path):
            self.assertNotEqual(path.name, "native_gold.jsonl")
            return original(path)
        with patch("scripts.benchmark_ragtruth._jsonl", side_effect=guarded):
            result = run_benchmark(data, self.root / "run", self.settings, self.config, project_root=self.root,
                backends=("optimized-v4.0",), ids=["1"], limit=1, verifier_factory=factory)
        self.assertEqual(result["completed_records"], 1)
        self.assertEqual(result["partial_records"], 1)
        row = _jsonl(self.root / "run/predictions.jsonl")[0]
        self.assertEqual(row["id"], "1")
        self.assertTrue(row["schema_valid"])
        self.assertEqual(calls[0][1]["v4_config"], self.config)
        config = json.loads((self.root / "run/config.json").read_text())
        self.assertFalse(config["gold_loaded"])
        self.assertEqual(config["v4_config"], self.config.public_dict())
        self.assertIn("not unseen", config["qualification"])
        for name, digest in config["code_files_sha256"].items():
            self.assertEqual(_sha(self.root / "run/source" / name), digest)

    def test_formal_filtering_and_nonv1_dev_are_rejected_before_calls(self):
        data = self.dev_data()
        with self.assertRaisesRegex(ValueError, "forbids"):
            run_benchmark(data, self.root / "run", self.settings, self.config, project_root=self.root, mode="test", limit=1)
        write(data / "preparation.json", {"seed": "ragtruth-blind-v2-20261022", "split": "test"})
        with self.assertRaisesRegex(ValueError, "restricted"):
            run_benchmark(data, self.root / "run", self.settings, self.config, project_root=self.root)

    def test_bad_raw_trace_surrogate_does_not_break_durable_record(self):
        data = self.dev_data()
        def factory(*args, **kwargs):
            return SimpleNamespace(verify=lambda request: SimpleNamespace(
                report={"claims": []}, telemetry={"calls": [{"response_text": "bad\ud800trace"}]}))
        result = run_benchmark(data, self.root / "run", self.settings, self.config, project_root=self.root,
                              backends=("optimized-v4.0",), limit=1, verifier_factory=factory)
        self.assertEqual(result["status"], "completed")
        record = load_prediction_journal(self.root / "run/predictions.jsonl")[0]
        self.assertEqual(record["telemetry"]["calls"][0]["response_text"], "bad\ud800trace")
        self.assertTrue(record["schema_valid"])


if __name__ == "__main__":
    unittest.main()
