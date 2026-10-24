"""Synthetic network-free tests of experiment integrity, not model semantics."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("bidirectional_pilot", Path(__file__).with_name("pilot.py"))
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

ANSWER = "The gauge is amber."
VALID = {"claims": [{"claim_text": ANSWER, "source_span": ANSWER}], "non_factual_spans": []}


def fixture_cases():
    return {"cases": [{"id": f"case-{i}", "generated_answer": ANSWER,
                       "expected_facts": ["SECRET_GOLD"], "family": "SECRET_FAMILY",
                       "language": "SECRET_LANGUAGE"} for i in range(16)],
            "controlled_seeds": [{"seed_id": f"seed-{i}", "case_id": f"case-{i}",
                                  "draft": deepcopy(VALID), "kind": "SECRET_KIND",
                                  "expected_missing_fact_ids": ["SECRET_GOLD"]} for i in range(12)]}


class FakeClient:
    def __init__(self, value=None, error=False):
        self.value, self.error, self.seen = value, error, []

    def complete(self, messages, stage, telemetry):
        self.seen.append(deepcopy(messages))
        telemetry["calls"].append({"stage": stage, "model": "deepseek-flash", "system_fingerprint": "fake",
                                   "response_text": "SYNTHETIC_BAD_JSON" if self.error else json.dumps(self.value),
                                   "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 20}})
        if self.error:
            raise pilot.VerificationError("invalid_model_output", "Synthetic malformed JSON")
        return deepcopy(self.value)


class PilotTests(unittest.TestCase):
    def test_whitelists_strip_gold_identity_and_seed_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(fixture_cases()), encoding="utf-8")
            cases, seeds = pilot.inference_cases(path)
        natural = pilot.extraction_payload(cases[0])
        controlled = pilot.revision_payload(seeds[0], seeds[0]["draft"])
        self.assertEqual(set(natural), {"generated_answer", "max_claims", "boundary_context"})
        self.assertEqual(set(controlled), set(natural) | {"draft"})
        self.assertEqual(set(controlled["draft"]), {"raw_output", "raw_text", "validation_status", "validator_error"})
        self.assertEqual(controlled["draft"]["validation_status"], "valid")
        for payload in (natural, controlled):
            text = json.dumps(payload)
            self.assertNotIn("SECRET", text)
            self.assertNotIn("case-", text)
            self.assertNotIn("seed-", text)
        self.assertEqual(pilot.prompts()["base"], pilot.prompts()["fresh"])
        self.assertTrue(pilot.prompts()["generic"].startswith(pilot.DECOMPOSE_PROMPT + pilot.REVISION_COMMON))
        self.assertTrue(pilot.prompts()["bidirectional"].startswith(pilot.DECOMPOSE_PROMPT + pilot.REVISION_COMMON))

    def test_schedule_exact_deterministic_and_balanced(self):
        cases = [{"id": str(i)} for i in range(16)]
        seeds = [{"id": str(i)} for i in range(12)]
        schedule = pilot.jobs(cases, seeds)
        self.assertEqual(schedule, pilot.jobs(list(reversed(cases)), list(reversed(seeds))))
        self.assertEqual(len(schedule), 44)
        self.assertEqual(len(pilot.expected_identities(cases, seeds)), 152)
        natural = [task for task in schedule if task["probe"] == "natural"]
        self.assertEqual(len(natural), 32)
        for position in range(3):
            counts = Counter(task["order"][position] for task in natural)
            self.assertEqual(set(counts), {"fresh", "generic", "bidirectional"})
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        controlled = [task for task in schedule if task["probe"] == "controlled"]
        self.assertEqual(Counter(task["order"][0] for task in controlled), {"generic": 6, "bidirectional": 6})

    def test_draft_status_is_deterministic_not_semantic_and_keeps_invalid_raw(self):
        # A structurally valid but semantically wrong extraction stays "valid".
        wrong = {"claims": [], "non_factual_spans": [{"text": ANSWER, "reason": "Not factual"}]}
        state = pilot.draft_state(wrong, ANSWER)
        self.assertEqual(state["validation_status"], "valid")
        self.assertEqual(state["raw_output"], wrong)
        invalid = {"claims": [], "non_factual_spans": []}
        state = pilot.draft_state(invalid, ANSWER)
        self.assertEqual(state["validation_status"], "invalid")
        self.assertEqual(state["raw_output"], invalid)
        self.assertIsNotNone(state["validator_error"])
        absent = pilot.draft_state(None, ANSWER, "{broken", {"code": "invalid_model_output"})
        self.assertEqual(absent["validation_status"], "unavailable")
        self.assertEqual(absent["raw_text"], "{broken")
        self.assertIsNone(absent["raw_output"])

    def test_single_call_failure_retains_raw_text_and_telemetry_without_retry(self):
        client = FakeClient(error=True)
        settings = pilot.Settings(api_key="SYNTHETIC_SECRET", thinking="disabled", upstream_retries=0)
        case = {"generated_answer": ANSWER}
        result = pilot.single_call(client, settings, "natural", "case", "base", 0,
                                   pilot.extraction_payload(case), pilot.DECOMPOSE_PROMPT,
                                   lambda raw, tel: pilot.validate_extraction(raw, case))
        self.assertEqual(len(client.seen), 1)
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["validated_output"])
        self.assertEqual(len(result["telemetry"]["calls"]), 1)
        self.assertEqual(result["telemetry"]["calls"][0]["max_output_tokens"], 8192)
        state = pilot.draft_from_record(result, case)
        self.assertEqual(state["raw_text"], "SYNTHETIC_BAD_JSON")
        self.assertNotIn("UNSUPPORTED", json.dumps(result))
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_invalid_or_oversize_inputs_do_not_get_truncated_or_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            source = fixture_cases()
            source["cases"][0]["generated_answer"] = "x" * 1201
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "one-chunk bound"):
                pilot.inference_cases(path)
            source = fixture_cases()
            source["controlled_seeds"][0]["draft"] = {"claims": [], "non_factual_spans": []}
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identical structural validation"):
                pilot.inference_cases(path)

    def test_freeze_fake_full_run_failure_followups_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            project, output = Path(directory) / "project", Path(directory) / "run"
            folder = project / pilot.REL
            folder.mkdir(parents=True)
            for sub in ("grounding", "scripts"):
                (project / sub).mkdir()
                (project / sub / "test.py").write_text("# fixture\n", encoding="utf-8")
            for name in ("pilot.py", "test_pilot.py", "PLAN.md"):
                (folder / name).write_text("fixture\n", encoding="utf-8")
            (folder / pilot.CASE_FILE).write_text(json.dumps(fixture_cases()), encoding="utf-8")
            settings = pilot.Settings(api_key="FAKE_LOCAL_KEY", thinking="disabled", max_output_tokens=8192,
                                      repair_attempts=0, upstream_retries=0)
            manifest = pilot.freeze(output, settings, project_root=project)
            self.assertEqual(manifest["max_model_calls"], 152)
            self.assertEqual(pilot.check_freeze(output), manifest)
            self.assertNotIn("FAKE_LOCAL_KEY", (output / "freeze.json").read_text())
            with self.assertRaises(FileExistsError):
                pilot.freeze(output, settings, project_root=project)

            class StageClient(FakeClient):
                def __init__(self, settings):
                    super().__init__(value=VALID)

                def complete(self, messages, stage, telemetry):
                    self.error = stage == "natural_base"
                    return super().complete(messages, stage, telemetry)

            # The fake runs in this interpreter. Only its location guard is
            # mocked; the separate test below exercises both real guard failures.
            with patch.object(pilot, "ROOT", output / "source"), patch.object(pilot, "HERE", output / "source" / pilot.REL), patch.object(pilot, "ChatClient", StageClient), patch.object(pilot, "check_imported_dependencies") as guard:
                progress = pilot.run(output, settings)
                self.assertEqual(progress["record_count"], 152)
                self.assertEqual(progress["model_calls_started"], 152)
                self.assertEqual(progress["error"], 32)
                self.assertEqual(progress["valid"], 120)
                records = [json.loads(line) for line in (output / "responses.jsonl").read_text().splitlines()]
                for row in records:
                    if row["probe"] == "natural" and row["arm"] in ("generic", "bidirectional"):
                        self.assertEqual(row["payload"]["draft"]["validation_status"], "unavailable")
                        self.assertEqual(row["payload"]["draft"]["raw_text"], "SYNTHETIC_BAD_JSON")
                        self.assertEqual(row["status"], "valid")
                        self.assertEqual(len(row["validated_output"]["claims"]), 1)
                analysis = pilot.analyze(output)
                self.assertEqual(analysis["runtime"]["usage"]["calls"], 152)
                self.assertEqual(analysis["same_input_revision_pairs"], 44)
                self.assertIsNone(analysis["semantic_scores"])
                self.assertGreater(guard.call_count, 0)
                with self.assertRaises(FileExistsError):
                    pilot.run(output, settings)
                with self.assertRaises(FileExistsError):
                    pilot.analyze(output)
            (output / "source" / "grounding/test.py").write_text("# changed\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                pilot.check_freeze(output)

    def test_dependency_guard_rejects_outside_snapshot_and_unbound_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            outside = Path(directory) / "client.py"
            outside.write_text("# outside\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escaped the frozen source"):
                pilot.check_imported_dependencies(source, {}, [("grounding.client", SimpleNamespace(__file__=str(outside)))])
            inside = source / "grounding/client.py"
            inside.parent.mkdir()
            inside.write_text("# inside\n", encoding="utf-8")
            modules = [("grounding.client", SimpleNamespace(__file__=str(inside)))]
            with self.assertRaisesRegex(ValueError, "not bound to this freeze"):
                pilot.check_imported_dependencies(source, {}, modules)
            pilot.check_imported_dependencies(source, {"grounding/client.py": pilot.sha(inside)}, modules)


if __name__ == "__main__":
    unittest.main()
