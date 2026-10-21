"""Freeze CLI refuses pending reviews and never overwrites completed freezes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grounding.config import Settings
from scripts import benchmark, freeze_confirmation


class FreezeCommandTests(unittest.TestCase):
    def prepare(self, root: Path, decision: str) -> list[str]:
        def case(index: int, split: str) -> dict:
            text = f"The {split} object has value {index}."
            return {
                "id": f"{split}-{index}", "split": split, "category": "empty_context",
                "topic": "Synthetic test", "problem_id": split, "context_passage_ids": [],
                "input": {"context_passages": [], "generated_answer": text},
                "expected": {"claims": [{
                    "claim_id": f"{split}-{index}-c1", "claim_text": text, "answer_quote": text,
                    "verdict": "UNSUPPORTED", "reasoning": "No evidence was supplied.",
                    "citations": [], "acceptable_evidence_sets": [], "required_passage_indices": [],
                }]},
            }
        for split, size in (("confirmation", 10), ("review", 3)):
            (root / f"{split}.jsonl").write_text(
                "\n".join(json.dumps(case(index, split)) for index in range(size)) + "\n", encoding="utf-8")
        sources = root / "sources.json"
        sources.write_text('{"documents":[],"passages":[]}', encoding="utf-8")
        policy = root / "policy.md"
        policy.write_text("Synthetic unit-test policy only.\n", encoding="utf-8")
        review = {
            "schema_version": "1.0", "scope": "pilot-annotation-policy", "decision": decision,
            "reviewer": "Simulated test reviewer", "reviewed_at": "2026-01-01T00:00:00Z",
            "authorization_reference": "Synthetic unit test only; not a real approval",
            "case_ids": [f"review-{index}" for index in range(3)],
            "dataset_path": "review.jsonl", "dataset_sha256": benchmark._sha(root / "review.jsonl"),
            "sources_path": "sources.json", "sources_sha256": benchmark._sha(sources),
            "policy_sha256": benchmark._sha(policy),
        }
        (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
        return ["--dataset", str(root / "confirmation.jsonl"), "--sources", str(sources),
                "--author-review", str(root / "review.json"), "--policy", str(policy)]

    def test_pending_review_cannot_produce_a_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.prepare(root, "pending")
            with patch.object(freeze_confirmation, "load_settings", return_value=Settings()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(freeze_confirmation.main(args), 2)
            self.assertFalse((root / "confirmation.freeze.json").exists())
            self.assertEqual(list(root.glob(".confirmation-check-*")), [])

    def test_valid_test_attestation_freezes_without_key_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.prepare(root, "approved")
            secret = "test-only-never-exported-secret"
            with patch.object(freeze_confirmation, "load_settings", return_value=Settings(api_key=secret)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(freeze_confirmation.main(args), 0)
            output = root / "confirmation.freeze.json"
            saved = output.read_bytes()
            self.assertNotIn(secret.encode(), saved)
            manifest = json.loads(saved)
            self.assertNotIn("api_key_configured", manifest["settings"])
            self.assertEqual(len(manifest["case_ids"]), 10)
            self.assertEqual(len(manifest["backends"]), 4)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(freeze_confirmation.main(args), 2)
            self.assertEqual(saved, output.read_bytes())
            self.assertEqual(list(root.glob(".confirmation-check-*")), [])


if __name__ == "__main__":
    unittest.main()
