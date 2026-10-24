"""Synthetic-only adapter tests; no upstream test record is inspected here."""

from __future__ import annotations

import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ragtruth_data import (
    DEFAULT_SEED, TASKS, file_sha256, input_sha256, load_jsonl, main, prepare_dataset,
)


def native_label(answer: str, text: str = "invented") -> dict:
    start = answer.index(text)
    return {"start": start, "end": start + len(text), "text": text,
            "label_type": "Evident Baseless Info", "due_to_null": False,
            "implicit_true": False, "meta": "NATIVE_GOLD_ONLY"}


class RagtruthDataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()

    def fixture(self, count: int = 3, split: str = "test"):
        sources, responses = [], []
        for task in TASKS:
            for index in range(count):
                sid = f"{task}-{index}"
                raw = {
                    "QA": {"question": "QUESTION_MUST_NOT_ENTER_EVIDENCE",
                           "passages": "passage 1:Exact first.\n\npassage 2:第二个\n"},
                    "Summary": "  Exact source\nwith whitespace.\r\n",
                    "Data2txt": {"name": "样本", "missing": None, "open": True,
                                 "attributes": {"disabled": False}, "reviews": [None, 3]},
                }[task]
                sources.append({"source_id": sid, "task_type": task,
                                "source_info": raw, "prompt": "PROMPT_MUST_NOT_ENTER_EVIDENCE",
                                "source": "synthetic"})
                for generator in ("alpha", "beta", "bad"):
                    answer = f"🙂 Answer {sid} {generator}; invented.\n"
                    responses.append({
                        "id": f"{sid}-{generator}", "source_id": sid, "split": split,
                        "model": generator, "quality": "good" if generator != "bad" else "truncated",
                        "response": answer, "labels": [native_label(answer)] if generator == "alpha" else [],
                        "temperature": 0.7,
                    })
        return sources, responses

    def write_raw(self, sources, responses):
        for name, rows in (("source_info.jsonl", sources), ("response.jsonl", responses)):
            with (self.raw / name).open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        provenance = {"kind": "synthetic", "commit": "test-only", "files": {
            name: {"sha256": file_sha256(self.raw / name)}
            for name in ("source_info.jsonl", "response.jsonl")
        }}
        (self.raw / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")

    def prepare(self, sources, responses, name="output", **kwargs):
        self.write_raw(sources, responses)
        directory = self.root / name
        manifest = prepare_dataset(self.raw, directory, **kwargs)
        return directory, manifest

    def test_deterministic_grouped_sampling_and_hash_bindings(self):
        sources, responses = self.fixture()
        directory, preparation = self.prepare(sources, responses, sources_per_task=2)
        inputs = load_jsonl(directory / "inputs.jsonl")
        metadata = load_jsonl(directory / "manifest.jsonl")
        gold = load_jsonl(directory / "native_gold.jsonl")
        self.assertEqual(len(inputs), 12)
        self.assertEqual([row["id"] for row in inputs], [row["id"] for row in metadata])
        self.assertEqual([row["id"] for row in inputs], [row["id"] for row in gold])
        lookup = {row["id"]: row for row in responses}
        for request, record, labels in zip(inputs, metadata, gold):
            expected = lookup[request["id"]]
            self.assertEqual(request["input"]["generated_answer"], expected["response"])
            self.assertEqual(record["input_sha256"], input_sha256(request["input"]))
            self.assertEqual(record["quality"], "good")
            self.assertEqual(labels["labels"], expected["labels"])
            self.assertEqual(labels["has_hallucination"], bool(expected["labels"]))
            self.assertNotIn("labels", request)
            self.assertNotIn("labels", record)
            self.assertNotIn("NATIVE_GOLD_ONLY", json.dumps(request))
            self.assertNotIn("QUESTION_MUST_NOT_ENTER_EVIDENCE", json.dumps(request))
            self.assertNotIn("PROMPT_MUST_NOT_ENTER_EVIDENCE", json.dumps(request))
        for task in TASKS:
            expected_sources = sorted(
                [row["source_id"] for row in sources if row["task_type"] == task],
                key=lambda sid: hashlib.sha256(f"{DEFAULT_SEED}|{task}|{sid}".encode()).hexdigest(),
            )[:2]
            self.assertEqual(preparation["selected_source_ids"][task], expected_sources)
            for sid in expected_sources:
                self.assertEqual(sum(row["source_id"] == sid for row in metadata), 2)
        for name, digest in preparation["artifacts_sha256"].items():
            self.assertEqual(file_sha256(directory / name), digest)
        other, second = self.prepare(list(reversed(sources)), list(reversed(responses)), "reordered",
                                     sources_per_task=2)
        self.assertEqual(preparation["selected_source_ids"], second["selected_source_ids"])
        for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl"):
            self.assertEqual((directory / name).read_bytes(), (other / name).read_bytes())

    def test_exact_qa_offsets_unicode_and_summary_preservation(self):
        sources, responses = self.fixture(1)
        original = "passage 1:🙂\r\n\r\npassage 2:尾部  \n"
        sources[0]["source_info"]["passages"] = original
        directory, _ = self.prepare(sources, responses, sources_per_task=0)
        inputs, records = load_jsonl(directory / "inputs.jsonl"), load_jsonl(directory / "manifest.jsonl")
        for row, record in zip(inputs, records):
            contexts = row["input"]["context_passages"]
            mapping = record["adapter"]
            if record["task_type"] == "QA":
                self.assertEqual(len(contexts), 2)
                self.assertEqual("".join(contexts), original)
                for context, offsets in zip(contexts, mapping["passage_offsets"]):
                    self.assertEqual(context, original[offsets["start"]:offsets["end"]])
                self.assertFalse(mapping["question_included"])
                self.assertIn("question", mapping["contract_difference"])
            elif record["task_type"] == "Summary":
                self.assertEqual(contexts, [sources[1]["source_info"]])

    def test_ambiguous_qa_boundaries_stay_one_exact_block(self):
        ambiguous = [" prefix\npassage 1:a\n\npassage 2:b", "passage 1:a\n\npassage 3:b",
                     "passage 1:a\npassage 2:b", "passage 1:a\n\npassage 1:b",
                     "plain evidence", "passage 1:a\n\npassage 2:b\n\npassage x:c"]
        for index, original in enumerate(ambiguous):
            with self.subTest(original=original):
                sources, responses = self.fixture(1)
                sources[0]["source_info"]["passages"] = original
                directory, _ = self.prepare(sources, responses, f"ambiguous-{index}", sources_per_task=0)
                row = load_jsonl(directory / "inputs.jsonl")[0]
                self.assertEqual(row["input"]["context_passages"], [original])

    def test_data2txt_preserves_null_boolean_and_deterministic_serialization(self):
        sources, responses = self.fixture(1)
        directory, _ = self.prepare(sources, responses, sources_per_task=0)
        row = load_jsonl(directory / "inputs.jsonl")[-1]
        actual = row["input"]["context_passages"][0]
        raw = sources[2]["source_info"]
        self.assertEqual(actual, json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        self.assertEqual(json.loads(actual), raw)
        self.assertIn('"missing": null', actual)
        self.assertIn('"open": true', actual)
        self.assertIn('"disabled": false', actual)

    def test_cross_split_leakage_rejected_even_non_good_response(self):
        sources, responses = self.fixture(1)
        responses[2]["split"] = "train"
        self.write_raw(sources, responses)
        with self.assertRaisesRegex(ValueError, "crosses official"):
            prepare_dataset(self.raw, self.root / "invalid", sources_per_task=0)
        self.assertFalse((self.root / "invalid").exists())

    def test_duplicates_and_missing_joins_rejected(self):
        for error in ("duplicate_source", "duplicate_response", "missing_join"):
            with self.subTest(error=error):
                sources, responses = self.fixture(1)
                if error == "duplicate_source":
                    sources.append(deepcopy(sources[0]))
                elif error == "duplicate_response":
                    responses.append(deepcopy(responses[0]))
                else:
                    responses[0]["source_id"] = "missing"
                self.write_raw(sources, responses)
                with self.assertRaises(ValueError):
                    prepare_dataset(self.raw, self.root / error, sources_per_task=0)

    def test_invalid_selected_spans_fail_without_repair_or_output(self):
        changes = [{"start": -1}, {"start": True}, {"end": 10000}, {"end": 0},
                   {"text": "wrong"}, {"label_type": "Unknown Type"}]
        for index, changeset in enumerate(changes):
            with self.subTest(changes=changeset):
                sources, responses = self.fixture(1)
                responses[0]["labels"][0].update(changeset)
                self.write_raw(sources, responses)
                directory = self.root / f"invalid-{index}"
                with self.assertRaisesRegex(ValueError, "Invalid selected label"):
                    prepare_dataset(self.raw, directory, sources_per_task=0)
                self.assertFalse(directory.exists())

    def test_gold_does_not_control_selection_or_inputs(self):
        sources, responses = self.fixture(4)
        first, preparation = self.prepare(sources, responses, "first", sources_per_task=1)
        changed = deepcopy(responses)
        selected = {sid for ids in preparation["selected_source_ids"].values() for sid in ids}
        for row in changed:
            row["labels"] = [] if row["source_id"] in selected else [{"start": -100, "text": "INVALID_UNSELECTED"}]
        second, second_preparation = self.prepare(sources, changed, "changed", sources_per_task=1)
        self.assertEqual(preparation["selected_source_ids"], second_preparation["selected_source_ids"])
        self.assertEqual((first / "inputs.jsonl").read_bytes(), (second / "inputs.jsonl").read_bytes())
        self.assertEqual((first / "manifest.jsonl").read_bytes(), (second / "manifest.jsonl").read_bytes())
        self.assertNotEqual((first / "native_gold.jsonl").read_bytes(), (second / "native_gold.jsonl").read_bytes())

    def test_size_exclusion_preserves_entire_source_groups(self):
        sources, responses = self.fixture(2)
        responses[0]["response"] = "x" * 20001
        responses[0]["labels"] = [{"invalid": "labels on excluded source are never inspected"}]
        responses[5]["response"] = "x" * 20001  # Bad quality does not affect its source eligibility.
        directory, preparation = self.prepare(sources, responses, sources_per_task=0)
        self.assertEqual(preparation["counts"]["excluded_sources"], 1)
        self.assertEqual(preparation["exclusions"][0]["source_id"], "QA-0")
        self.assertEqual(preparation["exclusions"][0]["excluded_good_response_count"], 2)
        self.assertEqual(preparation["selected_source_ids"]["QA"], ["QA-1"])
        self.assertEqual(len(load_jsonl(directory / "inputs.jsonl")), 10)

    def test_http_size_preflight_has_distinct_reason(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        with patch("scripts.ragtruth_data.MAX_BODY_BYTES", 5):
            preparation = prepare_dataset(self.raw, self.root / "small-http", sources_per_task=0)
        self.assertEqual(preparation["counts"]["selected_responses"], 0)
        for excluded in preparation["exclusions"]:
            self.assertEqual(excluded["failed_responses"][0]["reason"], "http_body_too_large")

    def test_insufficient_strata_abort(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        with self.assertRaisesRegex(ValueError, "Insufficient eligible"):
            prepare_dataset(self.raw, self.root / "insufficient", sources_per_task=2)

    def test_official_split_filter(self):
        sources, responses = self.fixture(1, split="train")
        directory, preparation = self.prepare(sources, responses, sources_per_task=1, split="train")
        self.assertEqual(preparation["split"], "train")
        self.assertTrue(all(row["upstream_split"] == "train" for row in load_jsonl(directory / "manifest.jsonl")))

    def test_existing_output_never_overwritten_including_empty_directory(self):
        sources, responses = self.fixture(1)
        directory, _ = self.prepare(sources, responses, sources_per_task=0)
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with self.assertRaises(FileExistsError):
            prepare_dataset(self.raw, directory, sources_per_task=0)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(FileExistsError):
            prepare_dataset(self.raw, empty, sources_per_task=0)
        self.assertEqual(list(empty.iterdir()), [])

    def test_publication_failure_cleans_only_reserved_output(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        directory = self.root / "failed"
        with patch("scripts.ragtruth_data.os.link", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                prepare_dataset(self.raw, directory, sources_per_task=0)
        self.assertFalse(directory.exists())
        self.assertEqual(list(self.root.glob(".ragtruth-stage-*")), [])

    def test_jsonl_rejects_duplicate_keys_and_nonfinite_values(self):
        path = self.root / "invalid.jsonl"
        for text in ('{"id":"a","id":"b"}', '{"x":NaN}', '[1,2]'):
            path.write_text(text + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_jsonl(path)

    def test_provenance_digest_mismatch_rejected_before_adaptation(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        with (self.raw / "response.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with patch("scripts.ragtruth_data._adapt_source") as adapt:
            with self.assertRaisesRegex(ValueError, "does not match upstream provenance"):
                prepare_dataset(self.raw, self.root / "tampered", sources_per_task=0)
            adapt.assert_not_called()
        self.assertFalse((self.root / "tampered").exists())

    def test_provenance_requires_both_raw_file_bindings(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        path = self.raw / "provenance.json"
        provenance = json.loads(path.read_text(encoding="utf-8"))
        del provenance["files"]["response.jsonl"]
        path.write_text(json.dumps(provenance), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing or invalid raw-file SHA256"):
            prepare_dataset(self.raw, self.root / "unbound", sources_per_task=0)

    def test_cli_reports_counts_without_contents_or_gold(self):
        sources, responses = self.fixture(1)
        self.write_raw(sources, responses)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["--raw-dir", str(self.raw), "--output-dir", str(self.root / "cli"),
                           "--sources-per-task", "1"])
        self.assertEqual(status, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["model_calls"], 0)
        self.assertEqual(summary["counts"]["selected_responses"], 6)
        for secret in ("invented", "QUESTION_MUST_NOT_ENTER_EVIDENCE", "NATIVE_GOLD_ONLY", "labels"):
            self.assertNotIn(secret, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
