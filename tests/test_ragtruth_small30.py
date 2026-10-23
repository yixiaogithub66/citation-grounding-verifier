import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from grounding.config import Settings
from grounding.config_v4 import V4Config
from scripts import ragtruth_small30 as small


def fixtures():
    sources, responses = [], []
    for task in small.adapter.TASKS:
        for i in range(12):
            sid = f"{task}-{i}"
            content = {"passages": "A source."} if task == "QA" else "A source." if task == "Summary" else {"value": 3}
            sources.append({"source_id": sid, "task_type": task, "source_info": content})
            for j in range(2):
                responses.append({"id": f"{sid}-r{j}", "source_id": sid, "split": "test",
                                  "quality": "good", "model": f"model-{j}", "response": "A source.", "labels": []})
    return sources, responses


def policy():
    return {"seed": small.SEED, "tasks": list(small.adapter.TASKS), "split": "test",
            "quality": "good", "excluded_source_ids": [], "sources_per_task": 10}


class Small30Tests(unittest.TestCase):
    def test_deterministic_one_per_source_and_task_quotas(self):
        sources, responses = fixtures()
        rows, excluded = small.select_records(sources, responses, policy())
        shuffled, _ = small.select_records(sources[::-1], responses[::-1], policy())
        self.assertEqual(rows, shuffled)
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({r["source_id"] for r in rows}), 30)
        self.assertFalse(excluded)
        for task in small.adapter.TASKS:
            self.assertEqual(sum(r["task_type"] == task for r in rows), 10)

    def test_labels_and_generator_do_not_change_selection(self):
        sources, responses = fixtures()
        before, _ = small.select_records(sources, responses, policy())
        for response in responses:
            response["labels"] = {"invalid": "must not be read during selection"}
            response["model"] = "another-generator"
        after, _ = small.select_records(sources, responses, policy())
        self.assertEqual([r["response"]["id"] for r in before], [r["response"]["id"] for r in after])

    def test_known_source_exclusions_apply_to_all_responses(self):
        sources, responses = fixtures()
        before, _ = small.select_records(sources, responses, policy())
        p = policy()
        p["excluded_source_ids"] = [before[0]["source_id"]]
        after, _ = small.select_records(sources, responses, p)
        self.assertEqual(len(after), 30)
        self.assertNotIn(before[0]["source_id"], {r["source_id"] for r in after})

    def test_whole_source_rejected_when_an_unchosen_response_is_oversize(self):
        sources, responses = fixtures()
        before, _ = small.select_records(sources, responses, policy())
        sid, chosen = before[0]["source_id"], before[0]["response"]["id"]
        for response in responses:
            if response["source_id"] == sid and response["id"] != chosen:
                response["response"] = "oversize-fixture"
        real = small.adapter._preflight
        with patch.object(small.adapter, "_preflight", side_effect=lambda request:
                ("verification_request_too_large", {}) if request["generated_answer"] == "oversize-fixture" else real(request)):
            after, excluded = small.select_records(sources, responses, policy())
        self.assertNotIn(sid, {r["source_id"] for r in after})
        self.assertEqual(excluded[0]["reason"], "source_group_input_limit")

    def test_split_contamination_and_insufficient_pool_fail(self):
        sources, responses = fixtures()
        responses[0]["split"] = "train"
        with self.assertRaisesRegex(ValueError, "crosses"):
            small.select_records(sources, responses, policy())
        sources, responses = fixtures()
        p = policy()
        p["excluded_source_ids"] = [s["source_id"] for s in sources if s["task_type"] == "QA"]
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            small.select_records(sources, responses, p)

    def test_inference_factory_sees_no_evaluation_metadata(self):
        seen = []
        def factory(backend, settings, *, v4_config):
            self.assertEqual(backend, small.BACKEND)
            class Fake:
                def verify(self, request):
                    seen.append(request)
                    return SimpleNamespace(report={"claims": []}, telemetry={"calls": []})
            return Fake()
        request = {"context_passages": ["A source."], "generated_answer": "Thanks."}
        case = {"id": "private-id", "input": request}
        meta = {"source_id": "private-source", "task_type": "QA", "generator": "private-model", "input_sha256": small._canonical_sha(request)}
        row = small.infer_one(case, meta, Settings(), V4Config(), factory)
        self.assertIsNone(row["error"])
        self.assertEqual(seen[0].context_passages, request["context_passages"])
        self.assertEqual(seen[0].generated_answer, request["generated_answer"])
        self.assertFalse(hasattr(seen[0], "id"))

    def test_contract_failure_preserves_returned_telemetry(self):
        calls = [{"stage": "verify", "usage": {"prompt_tokens": 3, "completion_tokens": 4}}]
        def factory(*args, **kwargs):
            return SimpleNamespace(verify=lambda request: SimpleNamespace(report={"bad": []}, telemetry={"calls": calls}))
        request = {"context_passages": ["A source."], "generated_answer": "An assertion."}
        row = small.infer_one({"id": "x", "input": request},
            {"source_id": "s", "task_type": "QA", "generator": "g", "input_sha256": small._canonical_sha(request)}, Settings(), V4Config(), factory)
        self.assertIsNone(row["prediction"])
        self.assertIsNotNone(row["error"])
        self.assertEqual(row["telemetry"]["calls"], calls)

    def test_selected_source_reservation_survives_invalid_gold(self):
        sources, responses = fixtures()
        for response in responses:
            response["labels"] = "invalid"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, raw = root / "run", root / "raw"
            output.mkdir()
            raw.mkdir()
            for name, rows in (("source_info.jsonl", sources), ("response.jsonl", responses)):
                (raw / name).write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            (raw / "provenance.json").write_text("{}")
            (output / "preselection.json").write_text("{}")
            frozen = {"project_root": str(root), "raw_dir": str(raw), "sampling": policy(),
                "exposure_ledger_files_sha256": {}, "qualification": "synthetic test",
                "upstream_raw_sha256": {name: small._sha(raw / name) for name in ("source_info.jsonl", "response.jsonl", "provenance.json")}}
            with patch.object(small, "check_freeze", return_value=frozen):
                with self.assertRaisesRegex(ValueError, "labels must"):
                    small.prepare(output)
            ledger = list((root / "results/ragtruth-ledger").glob("*.json"))
            self.assertEqual(len(ledger), 1)
            value = small._object(ledger[0])
            self.assertEqual(len(value["source_ids"]), 30)
            self.assertEqual(value["status"], "preparation_failed_source_still_exposed")
            self.assertEqual(value["mode"], "exploratory-source-disjoint-small30")
            self.assertFalse((output / "data").exists())


if __name__ == "__main__":
    unittest.main()
