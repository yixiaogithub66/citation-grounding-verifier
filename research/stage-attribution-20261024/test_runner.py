"""Network-free isolation, paired-review, durability, and resume checks."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("stage_attribution_runner_test", Path(__file__).with_name("runner.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

ANSWER = "The indicator is amber."
CONTEXTS = [ANSWER]
CLAIM = {"id": "c1", "claim_text": ANSWER}
ROW = {**CLAIM, "verdict": "SUPPORTED", "reasoning": "The supplied passage states this.",
       "citations": [{"index": 0, "quote": ANSWER}],
       "derivation": "The quoted passage entails this claim.", "conflict": None}
U_ROW = {**ROW, "verdict": "UNSUPPORTED", "citations": [], "derivation": "No support was found."}


def settings():
    return runner.Settings(api_key="LOCAL_TEST_SECRET", thinking="disabled", max_output_tokens=8192,
                           upstream_retries=0, repair_attempts=0)


def fixture_cases():
    return [{"id": f"schedule-case-{i}", "generated_answer": ANSWER,
             "context_passages": CONTEXTS,
             "claims": [{"id": f"c{j + 1}", "claim_text": ANSWER} for j in range(3)] if i < 15 else []}
            for i in range(20)]


class FakeClient:
    calls = []
    response = None
    hook = None

    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages, stage, telemetry):
        if type(self).hook:
            type(self).hook(messages, stage, telemetry)
        type(self).calls.append({"messages": deepcopy(messages), "stage": stage,
                                 "settings": self.settings.public_dict()})
        payload = json.loads(messages[1]["content"])
        if type(self).response is not None:
            value = deepcopy(type(self).response)
        elif stage.startswith("m1"):
            value = {"claims": [{"claim_text": payload["generated_answer"], "source_span": payload["generated_answer"]}],
                     "non_factual_spans": []}
        else:
            value = {"claims": [{**deepcopy(ROW), **claim} for claim in payload["claims"]]}
            if stage == "m3_simple":
                for row in value["claims"]:
                    row.pop("derivation")
                    row.pop("conflict")
        telemetry["calls"].append({"stage": stage, "attempt": 1, "model": "deepseek-flash", "system_fingerprint": "fake",
                                  "response_text": json.dumps(value), "usage": {"prompt_tokens": 20, "completion_tokens": 10}})
        return value


class RunnerTests(unittest.TestCase):
    def setUp(self):
        FakeClient.calls, FakeClient.response, FakeClient.hook = [], None, None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = {"id": "one-case", "generated_answer": ANSWER, "context_passages": CONTEXTS, "claims": [CLAIM]}

    def ledger(self, tasks, reviews=(), name="run"):
        return runner.Ledger(self.root / name, {"test": "fixed"},
                             {"initial": list(tasks), "reviews": list(reviews)}, secret=settings().api_key)

    def task(self, stage="m3", arm="current"):
        return {**runner.identity(stage, self.case["id"], arm, 0),
                "messages": runner.protocol().make_m1_messages(arm, ANSWER) if stage == "m1" else
                runner.protocol().make_m3_messages(arm, CONTEXTS, [CLAIM])}

    def test_request_only_cases_accept_exact_matrix(self):
        path = self.root / "cases.json"
        runner.write_new(path, fixture_cases())
        cases = runner.inference_cases(path)
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(len(c["claims"]) for c in cases), 45)

    def test_case_and_claim_metadata_rejected(self):
        for location, key in (("case", "gold"), ("case", "domain"), ("case", "expected_facts"),
                              ("claim", "verdict"), ("claim", "source_span")):
            with self.subTest(location=location, key=key):
                cases = fixture_cases()
                target = cases[0] if location == "case" else cases[0]["claims"][0]
                target[key] = "FORBIDDEN_GOLD"
                path = self.root / (location + key + ".json")
                runner.write_new(path, cases)
                with self.assertRaises(ValueError):
                    runner.inference_cases(path)

    def test_wrong_case_matrix_and_oversize_rejected(self):
        variants = [fixture_cases()[:-1], fixture_cases(), fixture_cases()]
        variants[1][0]["generated_answer"] = "x" * 1201
        variants[2][0]["claims"] = []
        for i, value in enumerate(variants):
            path = self.root / f"bad-{i}.json"
            runner.write_new(path, value)
            with self.assertRaises(ValueError):
                runner.inference_cases(path)

    def test_duplicate_ids_rejected(self):
        value = fixture_cases()
        value[1]["id"] = value[0]["id"]
        path = self.root / "duplicates.json"
        runner.write_new(path, value)
        with self.assertRaises(ValueError):
            runner.inference_cases(path)

    def test_schedule_is_seeded_complete_and_independent_of_input_order(self):
        first = runner.plans(fixture_cases(), "test-seed")
        second = runner.plans(list(reversed(fixture_cases())), "test-seed")
        self.assertEqual(first[0], second[0])
        self.assertEqual(len(first[0]), 140)
        self.assertEqual(len(first[1]), 90)
        self.assertEqual(len({r["key"] for r in first[0] + first[1]}), 230)
        self.assertNotEqual(first[0], runner.plans(fixture_cases(), "different-seed")[0])
        for item in first[0]:
            text = json.dumps(item["messages"])
            self.assertNotIn("schedule-case-", text)
            self.assertNotIn("gold", json.loads(item["messages"][-1]["content"]))
        with self.assertRaises(ValueError):
            runner.plans(fixture_cases(), "test-seed", 3)

    def test_atomic_write_never_overwrites(self):
        path = self.root / "record.json"
        runner.write_new(path, {"before": 1})
        with self.assertRaises(FileExistsError):
            runner.write_new(path, {"after": 2})
        self.assertEqual(runner.read_json(path), {"before": 1})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_freeze_detects_source_changes_and_settings_changes(self):
        source = self.root / "source.py"
        source.write_text("x = 1\n", encoding="utf-8")
        path = self.root / "FROZEN.json"
        runner.write_new(path, {"files": {"source.py": runner.sha(source)}, "settings": settings().public_dict(),
                                "seed": "test", "repetitions": 2})
        runner.check_freeze(path, settings=settings(), seed="test", repetitions=2, root=self.root)
        with self.assertRaises(ValueError):
            runner.check_freeze(path, settings=replace(settings(), max_output_tokens=1024), root=self.root)
        source.write_text("x = 2\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.check_freeze(path, root=self.root)

    def test_freeze_rejects_unbound_cases_and_path_escape(self):
        source = self.root / "source.py"
        source.write_text("x=1", encoding="utf-8")
        cases = self.root / "cases.json"
        runner.write_new(cases, [])
        path = self.root / "FROZEN.json"
        runner.write_new(path, {"files": {"source.py": runner.sha(source)}})
        with self.assertRaises(ValueError):
            runner.check_freeze(path, cases_path=cases, root=self.root)
        outside = self.root / "escape.json"
        runner.write_new(outside, {"files": {"../elsewhere.py": "0" * 64}})
        with self.assertRaises(ValueError):
            runner.check_freeze(outside, root=self.root)

    def test_initial_single_call_reserved_before_provider_and_saved_after(self):
        task = self.task()
        ledger = self.ledger([task])
        def check(messages, stage, telemetry):
            self.assertTrue(ledger.path("stage-reservations", task["key"]).exists())
            self.assertEqual(len(list((ledger.output / "call-reservations").glob("*.json"))), 1)
        FakeClient.hook = check
        result = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(len(FakeClient.calls), 1)
        self.assertEqual(ledger.stage_result(task)["raw_output"], {"claims": [ROW]})
        saved = next((ledger.output / "call-results").glob("*.json"))
        self.assertEqual(runner.read_json(saved)["calls"][0]["system_fingerprint"], "fake")

    def test_m1_invalid_keeps_raw_without_retry(self):
        task = self.task("m1", "current")
        ledger = self.ledger([task])
        FakeClient.response = {"claims": [], "non_factual_spans": []}
        result = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["raw_output"], FakeClient.response)
        self.assertEqual(len(FakeClient.calls), 1)

    def test_transport_error_is_saved_without_retry(self):
        task = self.task()
        ledger = self.ledger([task])
        def fail(messages, stage, telemetry):
            telemetry["calls"].append({"stage": stage, "attempt": 1, "usage": None})
            raise runner.VerificationError("upstream_timeout", "Synthetic timeout")
        FakeClient.hook = fail
        result = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "upstream_timeout")
        self.assertEqual(result["physical_calls"], 1)
        self.assertEqual(len(list((ledger.output / "call-results").glob("*.json"))), 1)

    def test_unknown_initial_is_never_resampled_even_on_resume(self):
        task = self.task()
        ledger = self.ledger([task])
        ledger.reserve("stage-reservations", task["key"], {"task": task, "reserved_at": runner.now()})
        resumed = runner.Ledger(ledger.output, {"test": "fixed"}, {"initial": [task], "reviews": []}, resume=True)
        self.assertIsNone(runner.initial_stage(task, self.case, settings(), resumed, FakeClient))
        self.assertEqual(FakeClient.calls, [])
        self.assertEqual(resumed.progress()["unknown_stage_keys"], [task["key"]])

    def test_finished_initial_is_reused_without_provider_call(self):
        task = self.task()
        ledger = self.ledger([task])
        first = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        second = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(first, second)
        self.assertEqual(len(FakeClient.calls), 1)

    def paired_tasks(self):
        initial = self.task()
        review = {**runner.identity("review", self.case["id"], "current", 0, "c1"), "initial_key": initial["key"]}
        return initial, review

    def test_review_reads_exact_saved_initial_and_records_no_trigger(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["before"], ROW)
        self.assertEqual(result["after"], ROW)
        self.assertFalse(result["triggered"])
        self.assertEqual(result["physical_calls"], 0)
        self.assertEqual(len(FakeClient.calls), 1)
        self.assertEqual(result["initial_result_sha256"], runner.sha(ledger.path("stage-results", initial["key"])))

    def test_u_review_calls_real_trigger_with_review_settings(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        FakeClient.response = {"claims": [U_ROW]}
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        FakeClient.response = {"claims": [ROW]}
        def check(messages, stage, telemetry):
            self.assertTrue(ledger.path("stage-results", initial["key"]).exists())
            self.assertEqual(json.loads(messages[1]["content"])["diagnostics"]["previous_result"], U_ROW)
        FakeClient.hook = check
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["before"]["verdict"], "UNSUPPORTED")
        self.assertEqual(result["after"]["verdict"], "SUPPORTED")
        self.assertEqual(FakeClient.calls[-1]["settings"]["thinking"], "enabled")
        self.assertEqual(FakeClient.calls[-1]["settings"]["max_output_tokens"], 16384)
        self.assertEqual(FakeClient.calls[-1]["settings"]["upstream_retries"], 0)
        self.assertEqual(result["telemetry"]["review_state"]["u_review_used"], True)

    def test_initial_invalid_row_has_ineligible_review_no_call(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        FakeClient.response = {"claims": [{**ROW, "citations": [{"index": 0, "quote": "missing quote"}]}]}
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "ineligible")
        self.assertEqual(result["physical_calls"], 0)
        self.assertEqual(len(FakeClient.calls), 1)

    def test_real_c_then_u_review_keeps_single_initial(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        FakeClient.response = {"claims": [{**ROW, "verdict": "CONTRADICTED", "conflict": None}]}
        first = runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        self.assertEqual(first["status"], "valid")
        def route(messages, stage, telemetry):
            FakeClient.response = {"claims": [U_ROW if stage == "contradiction_review" else ROW]}
        FakeClient.hook = route
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["physical_calls"], 2)
        self.assertEqual(result["after"]["verdict"], "SUPPORTED")
        self.assertTrue(result["telemetry"]["review_state"]["c_review_used"])
        self.assertTrue(result["telemetry"]["review_state"]["u_review_used"])
        self.assertEqual([c["stage"] for c in FakeClient.calls], ["m3_current", "contradiction_review", "unsupported_review"])

    def test_each_format_retry_has_its_own_durable_call_record(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        FakeClient.response = {"claims": [U_ROW]}
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        def route(messages, stage, telemetry):
            FakeClient.response = {} if stage == "unsupported_review" else {"claims": [ROW]}
        FakeClient.hook = route
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["physical_calls"], 2)
        self.assertEqual(result["status"], "valid")
        calls = [runner.read_json(path) for path in (ledger.output / "call-reservations").glob("*.json")]
        self.assertEqual(sorted(c["ordinal"] for c in calls if c["stage_key"] == review["key"]), [0, 1])
        self.assertEqual(len(list((ledger.output / "call-results").glob("*.json"))), 3)

    def test_review_failure_keeps_saved_initial_and_does_not_synthesize_final(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        FakeClient.response = {"claims": [U_ROW]}
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        FakeClient.response = {}
        result = runner.review_stage(review, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["before"], U_ROW)
        self.assertIsNone(result["after"])
        self.assertEqual(result["physical_calls"], 2)
        self.assertEqual(ledger.stage_result(initial)["raw_output"], {"claims": [U_ROW]})

    def test_unknown_review_does_not_repeat_initial_or_review(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        ledger.reserve("stage-reservations", review["key"], {"task": review, "reserved_at": runner.now()})
        self.assertIsNone(runner.review_stage(review, self.case, settings(), ledger, FakeClient))
        runner.initial_stage(initial, self.case, settings(), ledger, FakeClient)
        self.assertEqual(len(FakeClient.calls), 1)

    def test_missing_initial_never_causes_a_new_initial(self):
        initial, review = self.paired_tasks()
        ledger = self.ledger([initial], [review])
        self.assertIsNone(runner.review_stage(review, self.case, settings(), ledger, FakeClient))
        self.assertEqual(FakeClient.calls, [])
        self.assertEqual(ledger.disposition(review), "unreserved")

    def test_recording_client_rejects_hidden_transport_retry(self):
        task = self.task()
        ledger = self.ledger([task])
        factory = runner.RecordingFactory(ledger, task, 1, FakeClient)
        with self.assertRaises(ValueError):
            factory(replace(settings(), upstream_retries=1))

    def test_reservation_failure_prevents_provider(self):
        task = self.task()
        ledger = self.ledger([task])
        with patch.object(runner, "write_new", side_effect=OSError("synthetic disk full")):
            with self.assertRaises(runner.DurabilityError):
                runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(FakeClient.calls, [])
        self.assertTrue(ledger.stop.is_set())

    def test_derived_progress_lock_does_not_lose_result(self):
        task = self.task()
        ledger = self.ledger([task])
        with patch.object(runner, "write_view", side_effect=PermissionError("synthetic progress lock")):
            result = runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(len(ledger.warnings), 1)
        self.assertFalse(ledger.stop.is_set())
        self.assertTrue(ledger.path("stage-results", task["key"]).exists())

    def test_all_persisted_data_redacts_credentials(self):
        task = self.task()
        ledger = self.ledger([task])
        FakeClient.response = {"claims": [{**ROW, "reasoning": settings().api_key}]}
        runner.initial_stage(task, self.case, settings(), ledger, FakeClient)
        for path in ledger.output.rglob("*.json"):
            self.assertNotIn(settings().api_key, path.read_text(encoding="utf-8"))

    def test_whole_matrix_and_resume_make_exactly_140_provider_calls(self):
        cases_path, freeze_path = self.root / "cases.json", self.root / "FROZEN.json"
        runner.write_new(cases_path, fixture_cases())
        runner.write_new(freeze_path, {"synthetic": "manifest"})
        with patch.object(runner, "check_freeze", return_value={}), patch.object(runner, "check_imports"):
            result = runner.run(cases_path, self.root / "full", settings(), freeze_path=freeze_path,
                                seed="test-seed", client_factory=FakeClient)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["progress"]["stage_results"], 230)
            self.assertEqual(result["progress"]["provider_results"], 140)
            resumed = runner.run(cases_path, self.root / "full", settings(), freeze_path=freeze_path,
                                 seed="test-seed", client_factory=FakeClient, resume=True)
        self.assertEqual(resumed["status"], "complete")
        self.assertEqual(len(FakeClient.calls), 140)


if __name__ == "__main__":
    unittest.main()


