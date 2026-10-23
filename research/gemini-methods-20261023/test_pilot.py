"""Synthetic, network-free tests of probe boundaries, not expected model answers."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("generic_pilot", Path(__file__).with_name("pilot.py"))
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class FakeClient:
    def __init__(self, value=None, error=False):
        self.value, self.error, self.seen = value, error, []

    def complete(self, messages, stage, telemetry):
        self.seen.append(deepcopy(messages))
        telemetry["calls"].append({"stage": stage, "model": "deepseek-flash", "system_fingerprint": "fake",
                                   "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 20}})
        if self.error:
            raise pilot.VerificationError("upstream_timeout", "Synthetic timeout")
        return deepcopy(self.value)


class PilotTests(unittest.TestCase):
    def test_request_whitelists_strip_gold_and_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            cases = [{"id": f"case{i}", "claim_text": "The gauge is amber.",
                      "context_passages": ["The gauge is amber."], "expected_verdict": "SECRET_LABEL",
                      "rationale": "SECRET_GOLD", "family": "SECRET_FAMILY"} for i in range(12)]
            path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
            stripped = pilot.inference_cases(path, "p1")
            payload = pilot.judgment_payload(stripped[0])
            self.assertEqual(set(payload), {"context_passages", "claims"})
            self.assertEqual(payload["claims"], [{"id": "c1", "claim_text": "The gauge is amber."}])
            self.assertNotIn("SECRET", json.dumps(payload))
            self.assertNotIn("case0", json.dumps(payload))
        audit = pilot.audit_payload("A is amber. Please wait.",
                                    [{"text": "Please wait.", "reason": "SECRET_REASON"}],
                                    [{"source_span": "A is amber.", "claim_text": "SECRET_CLAIM"}])
        self.assertEqual(audit["already_extracted_spans"], ["A is amber."])
        self.assertNotIn("SECRET", json.dumps(audit))
        self.assertNotIn("context_passages", audit)

    def test_schedule_balanced_deterministic_and_repeat_unchanged(self):
        p1 = [{"id": str(i)} for i in range(12)]
        p2 = [{"id": str(i)} for i in range(12)]
        schedule = pilot.jobs(p1, p2)
        self.assertEqual(schedule, pilot.jobs(list(reversed(p1)), list(reversed(p2))))
        self.assertEqual(len(schedule), 36)
        p1jobs = [j for j in schedule if j["probe"] == "p1"]
        self.assertEqual(sum(j["order"][0] == "base" for j in p1jobs), 12)
        for case in p1:
            pair = [j for j in p1jobs if j["case"]["id"] == case["id"]]
            self.assertEqual(pair[0]["order"], tuple(reversed(pair[1]["order"])))
        self.assertEqual(pilot.prompts()["p2_base"], pilot.prompts()["p2_repeat"])

    def test_judgment_safe_format_repair_not_content_repair(self):
        case = {"claim_text": "The reading is 3.5.", "context_passages": ['The reading is 3.5; mode "amber".']}
        row = {"id": "c1", "claim_text": case["claim_text"], "verdict": "SUPPORTED", "reasoning": "Direct.",
               "derivation": "The source states the reading.", "citations": [{"index": 0, "quote": 'mode “amber”'}], "conflict": None}
        telemetry = pilot._local_telemetry()
        output = pilot.validate_judgment({"claims": [row]}, case, telemetry)
        self.assertEqual(output["citations"][0]["quote"], 'mode "amber"')
        self.assertEqual(output["verdict"], "SUPPORTED")
        self.assertTrue(telemetry["citation_repairs"])
        row["citations"] = [{"index": 0, "quote": "The reading is 35"}]
        with self.assertRaises(pilot.VerificationError):
            pilot.validate_judgment({"claims": [row]}, case, pilot._local_telemetry())
        row["citations"] = [{"index": 0, "quote": "The reading is 3.5"}]
        row["verdict"] = "CONTRADICTED"
        with self.assertRaises(pilot.VerificationError):
            pilot.validate_judgment({"claims": [row]}, case, pilot._local_telemetry())

    def test_nf_recoveries_require_the_identified_source_span(self):
        payload = pilot.audit_payload("Try it. It cools the chamber.",
                                      [{"text": "Try it."}, {"text": "It cools the chamber."}], [])
        row = {"exclusion_id": "e2", "source_span": "It cools the chamber.", "claim_text": "It cools the chamber."}
        self.assertEqual(pilot.validate_audit({"recoveries": [row]}, payload), {"recoveries": [row]})
        row["exclusion_id"] = "e1"
        with self.assertRaises(pilot.VerificationError):
            pilot.validate_audit({"recoveries": [row]}, payload)
        self.assertEqual(pilot.validate_audit({"recoveries": []}, payload), {"recoveries": []})

    def test_single_failure_is_explicit_and_preserves_one_call(self):
        client = FakeClient(error=True)
        settings = pilot.Settings(api_key="SYNTHETIC_SECRET", thinking="disabled", upstream_retries=0)
        result = pilot.single_call(client, settings, "p1", "case", "base", 0, {"x": "input"}, "JSON task",
                                   lambda raw, tel: raw)
        self.assertEqual(len(client.seen), 1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "upstream_timeout")
        self.assertIsNone(result["validated_output"])
        self.assertEqual(len(result["telemetry"]["calls"]), 1)
        self.assertNotIn("UNSUPPORTED", json.dumps(result))
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_freeze_copies_binds_and_rejects_change_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            project, output = Path(directory) / "project", Path(directory) / "run"
            folder = project / pilot.REL
            folder.mkdir(parents=True)
            for sub in ("grounding", "scripts"):
                (project / sub).mkdir()
                (project / sub / "test.py").write_text("# synthetic source\n", encoding="utf-8")
            for name in ("pilot.py", "test_pilot.py", "PLAN.md"):
                (folder / name).write_text("synthetic freeze fixture\n", encoding="utf-8")
            first = [{"id": str(i), "claim_text": "A is amber.", "context_passages": ["A is amber."],
                      "expected_verdict": "SUPPORTED"} for i in range(12)]
            second = [{"id": str(i), "generated_answer": "A is amber."} for i in range(12)]
            for name, cases in zip(pilot.CASE_FILES, (first, second)):
                (folder / name).write_text(json.dumps({"cases": cases}), encoding="utf-8")
            settings = pilot.Settings(api_key="FAKE_LOCAL_KEY")
            manifest = pilot.freeze(output, settings, project_root=project)
            self.assertEqual(manifest["max_model_calls"], 84)
            self.assertEqual(pilot.check_freeze(output), manifest)
            with self.assertRaises(FileExistsError):
                pilot.freeze(output, pilot.Settings(), project_root=project)
            class StageClient(FakeClient):
                def __init__(self, settings):
                    super().__init__()

                def complete(self, messages, stage, telemetry):
                    if stage.startswith("p1"):
                        self.value = {"claims": [{"id": "c1", "claim_text": "A is amber.", "verdict": "SUPPORTED",
                                                  "reasoning": "Direct.", "derivation": "Direct.", "conflict": None,
                                                  "citations": [{"index": 0, "quote": "A is amber."}]}]}
                    else:
                        self.value = {"claims": [{"claim_text": "A is amber.", "source_span": "A is amber."}],
                                      "non_factual_spans": []}
                    return super().complete(messages, stage, telemetry)

            # This in-process fake does not reload dependencies from a new
            # interpreter. Mock only that filesystem/module-location check here;
            # the separate guard test exercises rejection without any bypass.
            with patch.object(pilot, "ROOT", output / "source"), patch.object(pilot, "HERE", output / "source" / pilot.REL), patch.object(pilot, "ChatClient", StageClient), patch.object(pilot, "check_imported_dependencies") as dependency_guard:
                progress = pilot.run(output, settings)
                self.assertEqual(progress["record_count"], 84)
                self.assertEqual(progress["model_calls_started"], 72)
                self.assertEqual(progress["skipped"], 12)
                analysis = pilot.analyze(output)
                self.assertEqual(analysis["p1"]["base"]["valid_and_label_hits"], 24)
                self.assertEqual(analysis["runtime"]["usage"]["calls"], 72)
                self.assertIsNone(analysis["p2"]["base"]["semantic_score"])
                self.assertGreater(dependency_guard.call_count, 0)
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
