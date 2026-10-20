"""Regression checks for malformed model responses and citation offsets."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import evaluate_llm
from validate_dataset import strict_json_loads, validate_prediction


class StubResponse(io.BytesIO):
    status = 200


class TruncatedResponse(StubResponse):
    def read(self, *args: object) -> bytes:
        raise IncompleteRead(b'{"claims":', 20)


class StrictJsonTests(unittest.TestCase):
    def test_rejects_nonfinite_numbers(self) -> None:
        for number in ("1e999", "-1e999", "NaN", "Infinity", "-Infinity"):
            with self.subTest(number=number), self.assertRaises(ValueError):
                strict_json_loads('{"nested":[' + number + "]}")

    def test_accepts_finite_numbers(self) -> None:
        self.assertEqual(strict_json_loads("[1.5,1e100]"), [1.5, 1e100])

    def test_rejects_unpaired_surrogates_in_keys_and_values(self) -> None:
        for raw in (
            r'"\ud800"',
            r'{"nested":["\udfff"]}',
            r'{"\ud800":"value"}',
            r'{"\ud800":0,"\ud800":1}',
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError) as raised:
                strict_json_loads(raw)
            str(raised.exception).encode("utf-8")

    def test_accepts_valid_unicode_surrogate_pairs(self) -> None:
        parsed = strict_json_loads(r'{"\ud83d\ude00":["\ud83d\ude00"]}')
        self.assertEqual(parsed, {"\U0001f600": ["\U0001f600"]})
        json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")

    def test_duplicate_keys_still_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
            strict_json_loads('{"claims":[],"claims":[]}')


class ResponseTests(unittest.TestCase):
    def run_evaluation(self, responses: list[object], *, chat: bool) -> tuple[list[dict], dict]:
        cases = [
            {
                "id": f"case-{index}", "split": "test", "category": "no_facts",
                "topic": "test", "problem_id": f"problem-{index}",
                "input": {"context_passages": [], "generated_answer": ""},
                "expected": {"claims": []},
            }
            for index in range(len(responses))
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "cases.jsonl"
            dataset.write_text("", encoding="utf-8")
            (root / "sources.json").write_text("{}", encoding="utf-8")
            output = root / "results"
            args = ["evaluate_llm.py", "--dataset", str(dataset), "--output-dir", str(output)]
            if chat:
                args += ["--base-url", "http://localhost/v1", "--model", "test"]
            else:
                args += ["--endpoint", "http://localhost/verify"]
            with (
                patch.object(evaluate_llm, "check_dataset", return_value=(cases, {"valid": True})),
                patch.object(evaluate_llm, "urlopen", side_effect=responses),
                patch.object(sys, "argv", args),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(evaluate_llm.main(), 1)
            records = [
                strict_json_loads(line)
                for line in (output / "responses.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            report = strict_json_loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(records), len(responses))
        self.assertTrue(records[-1]["score"]["schema_valid"])
        self.assertEqual(report["overall"]["schema_valid_count"], 1)
        return records, report

    def test_truncated_success_and_error_bodies_do_not_abort_remaining_cases(self) -> None:
        error = HTTPError("http://localhost/verify", 503, "Unavailable", {}, TruncatedResponse())
        records, report = self.run_evaluation(
            [TruncatedResponse(), error, StubResponse(b'{"claims":[]}')], chat=False,
        )
        self.assertEqual([record["http_status"] for record in records], [200, 503, 200])
        self.assertIn("IncompleteRead", records[0]["request_error"])
        self.assertIn("HTTP 503", records[1]["request_error"])
        self.assertIn("IncompleteRead", records[1]["request_error"])
        self.assertEqual(report["overall"]["request_error_count"], 2)
        self.assertTrue(all(record["validation_errors"] for record in records[:2]))

    def test_normal_http_error_preserves_body_and_continues(self) -> None:
        body = b'{"error":"rate limited"}'
        error = HTTPError("http://localhost/verify", 429, "Too Many Requests", {}, io.BytesIO(body))
        records, _ = self.run_evaluation([error, StubResponse(b'{"claims":[]}')], chat=False)
        self.assertEqual(records[0]["request_error"], "HTTP 429")
        self.assertEqual(records[0]["raw_response"], body.decode("utf-8"))
        self.assertEqual(records[1]["prediction"], {"claims": []})

    def test_invalid_json_values_in_endpoint_responses_are_recorded(self) -> None:
        records, _ = self.run_evaluation(
            [
                StubResponse(b'{"claims":[],"extra":1e999}'),
                StubResponse(br'{"claims":[],"extra":"\ud800"}'),
                StubResponse(b'{"claims":[]}'),
            ],
            chat=False,
        )
        for record in records[:2]:
            self.assertIn("Response is not valid JSON", record["request_error"])
            self.assertIsNone(record["prediction"])
            self.assertTrue(record["validation_errors"])

    def test_invalid_json_values_in_chat_completions_are_recorded(self) -> None:
        responses = [
            StubResponse(json.dumps({
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }).encode("utf-8"))
            for content in (
                '{"claims":[],"extra":1e999}',
                r'{"claims":[],"extra":"\ud800"}',
                '{"claims":[]}',
            )
        ]
        records, _ = self.run_evaluation(responses, chat=True)
        for record in records[:2]:
            self.assertIsNone(record["request_error"])
            self.assertIsNone(record["prediction"])
            self.assertTrue(any(error["location"] == "completion" for error in record["validation_errors"]))


class CitationOffsetTests(unittest.TestCase):
    def test_optional_offsets_use_unicode_character_positions(self) -> None:
        passage = "a\U0001f600b"
        citation = {"index": 0, "quote": "\U0001f600", "start_char": 1, "end_char": 2}
        prediction = {"claims": [{
            "claim_text": "An emoji occurs.", "verdict": "SUPPORTED", "reasoning": "Quoted.",
            "citations": [citation],
        }]}
        self.assertEqual(validate_prediction(prediction, [passage]), [])
        citation["end_char"] = 3
        self.assertTrue(validate_prediction(prediction, [passage]))
        del citation["end_char"]
        self.assertTrue(validate_prediction(prediction, [passage]))


if __name__ == "__main__":
    unittest.main()
