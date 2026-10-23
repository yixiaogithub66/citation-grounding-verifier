"""Synthetic approvals exercise the gate; no real author decisions are created."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from grounding.contracts import VerificationError
from scripts.benchmark_ragtruth import _sha
from scripts.score_v4_adjudicated import (score_adjudicated, PACKAGE_SCHEMA,
                                        AUTHOR_SCHEMA, APPROVAL_SCHEMA)


class AdjudicatedScoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pending, self.draft = self.root / "pending.json", self.root / "draft.json"
        self.author, self.approval = self.root / "author-reviewed.json", self.root / "approval.json"
        rows = []
        for i, backend in enumerate(("minimal", "optimized-v3", "minimal")):
            rows.append({"review_id": f"r{i}", "backend": backend, "claim_index": i,
                         "reported_claim": {"claim_text": f"Claim {i}.", "verdict": "UNSUPPORTED",
                                            "reasoning": "Reported gap.", "citations": []},
                         "ai_review": {"status": "pending_ai"},
                         "author_review": {"status": "pending_author", "verdict": None}})
        self.package = {"schema_version": PACKAGE_SCHEMA, "counts": {"cases": 1, "reported_claims": 3},
                        "provenance": {"fixture": True}, "cases": [{"id": "case0", "source_id": "source0",
                        "input": {"context_passages": ["Source text."], "generated_answer": "Claim 0. Claim 1. Claim 2."},
                        "native_gold": {"labels": []}, "reported_claims_for_review": rows}]}
        self.write(self.pending, self.package)
        self.proposed = copy.deepcopy(self.package)
        for row in self.proposed["cases"][0]["reported_claims_for_review"]:
            row["ai_review"] = {"status": "ai_draft", "proposed_verdict": "SUPPORTED"}
        self.write(self.draft, self.proposed)

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def approvals(self):
        self.author_value = {"schema_version": AUTHOR_SCHEMA, "reviewer_kind": "human_author",
            "bindings_sha256": {"pending": _sha(self.pending), "draft": _sha(self.draft)},
            "reviews": [{"review_id": f"r{i}", "verdict": verdict, "reasoning": "Synthetic reviewed reason.",
                         "citations": [{"index": 0, "quote": "Source text."}] if verdict == "SUPPORTED" else [],
                         "reviewed_at": "2026-10-23T09:00:00+08:00"}
                        for i, verdict in enumerate(("SUPPORTED", "UNSUPPORTED", "UNCERTAIN"))]}
        self.write(self.author, self.author_value)
        self.approval_value = {"schema_version": APPROVAL_SCHEMA, "reviewer_kind": "human_author",
            "method": "explicit_user_confirmation", "bindings_sha256": {**self.author_value["bindings_sha256"],
                                                                         "author_reviewed": _sha(self.author)},
            "confirmed_at": "2026-10-23T10:00:00+08:00", "approved_review_ids": ["r0", "r1", "r2"],
            "confirmation_text": "Synthetic fixture only; not actual approval.",
            "confirmation_source": {"kind": "user_message", "reference": "fixture://synthetic-message"}}
        self.write(self.approval, self.approval_value)

    def score(self):
        return score_adjudicated(self.pending, self.draft, author_reviewed_path=self.author, approval_path=self.approval)

    def rebind(self):
        self.write(self.author, self.author_value)
        self.approval_value["bindings_sha256"]["author_reviewed"] = _sha(self.author)
        self.write(self.approval, self.approval_value)

    def test_ai_draft_never_becomes_author_gold(self):
        result = score_adjudicated(self.pending, self.draft)
        self.assertEqual(result["acceptance"], "pending")
        self.assertEqual(result["approved_review_count"], 0)
        self.assertIsNone(result["reported_claim_flags"])
        self.assertEqual(result["adjudicated_answer_fn_zero"], "not_evaluable")

    def test_missing_either_independent_artifact_is_pending(self):
        self.approvals()
        for kwargs in ({"author_reviewed_path": self.author}, {"approval_path": self.approval}):
            self.assertEqual(score_adjudicated(self.pending, self.draft, **kwargs)["acceptance"], "pending")

    def test_approved_scope_only_reports_flag_counts_and_preserves_native_gold(self):
        self.approvals()
        before = self.pending.read_bytes(), self.draft.read_bytes()
        result = self.score()
        self.assertEqual(result["status"], "author_approved_reported_claims")
        self.assertEqual(result["reported_claim_flags"]["minimal"]["false_flag"], 1)
        self.assertEqual(result["reported_claim_flags"]["minimal"]["unresolved"], 1)
        self.assertEqual(result["reported_claim_flags"]["optimized-v3"]["true_flag"], 1)
        self.assertEqual(result["reported_claim_flags"]["minimal"]["resolution_coverage"]["value"], .5)
        self.assertEqual(result["adjudicated_answer_fn_zero"], "not_evaluable")
        self.assertEqual(result["acceptance"], "pending")
        self.assertEqual(before, (self.pending.read_bytes(), self.draft.read_bytes()))

    def test_hashes_bind_pending_draft_and_author_files(self):
        self.approvals()
        for key in ("pending", "draft", "author_reviewed"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.approval_value)
                bad["bindings_sha256"][key] = "0" * 64
                self.write(self.approval, bad)
                with self.assertRaisesRegex(ValueError, "all three"):
                    self.score()

    def test_edited_author_file_requires_new_explicit_hash_binding(self):
        self.approvals()
        self.author_value["reviews"][0]["reasoning"] = "Changed review."
        self.write(self.author, self.author_value)
        with self.assertRaisesRegex(ValueError, "all three"):
            self.score()

    def test_missing_extra_and_duplicate_approved_ids_are_rejected(self):
        self.approvals()
        for ids in (["r0", "r1"], ["r0", "r1", "r2", "unexpected"], ["r0", "r1", "r1"]):
            self.approval_value["approved_review_ids"] = ids
            self.write(self.approval, self.approval_value)
            with self.assertRaisesRegex(ValueError, "every required"):
                self.score()

    def test_author_review_ids_must_be_complete_unique_and_known(self):
        self.approvals()
        original = copy.deepcopy(self.author_value["reviews"])
        for reviews in (original[:2], [original[0], original[1], original[1]],
                        original[:2] + [{**original[2], "review_id": "other"}]):
            self.author_value["reviews"] = reviews
            self.rebind()
            with self.assertRaises(ValueError):
                self.score()

    def test_ai_reviewer_auto_approval_or_missing_provenance_are_rejected(self):
        self.approvals()
        for key, value in (("reviewer_kind", "ai"), ("method", "auto_approval"),
                           ("confirmation_source", {"kind": "generated", "reference": "x"}),
                           ("confirmation_source", {"kind": "user_message", "reference": ""}),
                           ("confirmation_text", "")):
            bad = copy.deepcopy(self.approval_value)
            bad[key] = value
            self.write(self.approval, bad)
            with self.assertRaises(ValueError):
                self.score()

    def test_timestamps_require_timezone_and_review_before_approval(self):
        self.approvals()
        for timestamp in ("2026-10-23T09:00:00", "2026-10-24T09:00:00+08:00", "bad"):
            self.author_value["reviews"][0]["reviewed_at"] = timestamp
            self.rebind()
            with self.assertRaises(ValueError):
                self.score()

    def test_author_evidence_must_still_be_exact(self):
        self.approvals()
        self.author_value["reviews"][0]["citations"][0]["quote"] = "Invented source."
        self.rebind()
        with self.assertRaises(VerificationError):
            self.score()

    def test_draft_cannot_change_original_claim_or_native_labels(self):
        for change in ("claim", "gold"):
            bad = copy.deepcopy(self.proposed)
            if change == "claim":
                bad["cases"][0]["reported_claims_for_review"][0]["reported_claim"]["claim_text"] = "Edited."
            else:
                bad["cases"][0]["native_gold"]["labels"] = [{"text": "new"}]
            self.write(self.draft, bad)
            with self.assertRaisesRegex(ValueError, "identities"):
                score_adjudicated(self.pending, self.draft)


if __name__ == "__main__":
    unittest.main()
