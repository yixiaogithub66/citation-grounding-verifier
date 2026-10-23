"""Source-pointer invariants use invented fixtures, never benchmark branches."""

from copy import deepcopy
import unittest

from grounding.contracts import VerificationError
from grounding.evidence_combined import (
    EVIDENCE_PROTOCOL, materialize_ids, project_evidence_row, source_payload, source_units,
)


def pointer_row(text="A is warm.", verdict="SUPPORTED", ids=None, considered=None, conflict=None):
    ids = ([] if verdict == "UNSUPPORTED" else ["p0u1"]) if ids is None else ids
    return {"evidence_protocol": EVIDENCE_PROTOCOL, "id": "c1", "claim_text": text,
            "verdict": verdict, "reasoning": "Source-grounded judgment.",
            "considered_evidence_ids": list(ids) if considered is None else considered,
            "decision_evidence_ids": ids, "derivation": "The complete selected premises determine the assertion.",
            "conflict": conflict}


class SourceEvidenceTests(unittest.TestCase):
    def test_catalog_preserves_every_character_and_source_identity(self):
        contexts = ["😀 A is warm.\nA is warm. ", "", "−5 and 3.5 differ from 5 and 35."]
        first = source_units(contexts)
        self.assertEqual(first, source_units(contexts))
        self.assertEqual(len({unit["id"] for unit in first}), len(first))
        for passage in source_payload(contexts):
            self.assertEqual("".join(unit["text"] for unit in passage["source_units"]), contexts[passage["index"]])
            for unit in passage["source_units"]:
                self.assertEqual(unit["text"], contexts[unit["index"]][unit["start_char"]:unit["end_char"]])

    def test_multisource_decision_materializes_exact_quotes(self):
        contexts = ["The box holds 2 coins.", "Each coin weighs 3 grams."]
        raw = pointer_row("The coins weigh 6 grams.", ids=["p0u1", "p1u1"])
        row, validated = project_evidence_row(raw, contexts)
        self.assertEqual(row["citations"], [{"index": i, "quote": text} for i, text in enumerate(contexts)])
        self.assertEqual(validated, raw)
        self.assertNotIn("considered_evidence_ids", row)

    def test_unsupported_considered_evidence_is_not_decision_evidence(self):
        raw = pointer_row(verdict="UNSUPPORTED", considered=["p0u1"])
        row, validated = project_evidence_row(raw, ["A is blue."])
        self.assertEqual(row["citations"], [])
        self.assertEqual(validated["considered_evidence_ids"], ["p0u1"])
        self.assertEqual(raw, validated)

    def test_blank_source_location_may_be_considered_but_never_decision_evidence(self):
        contexts = ["\n", "A is warm."]
        raw = pointer_row(verdict="UNSUPPORTED", considered=["p0u1", "p1u1"])
        projected, validated = project_evidence_row(raw, contexts)
        self.assertEqual(projected["citations"], [])
        self.assertEqual(validated["considered_evidence_ids"], ["p0u1", "p1u1"])
        with self.assertRaisesRegex(VerificationError, "empty"):
            project_evidence_row(pointer_row(ids=["p0u1"]), contexts)

    def test_unsupported_with_decision_evidence_is_rejected_never_dropped(self):
        raw = pointer_row(verdict="UNSUPPORTED", ids=["p0u1"])
        before = deepcopy(raw)
        with self.assertRaisesRegex(VerificationError, "never silently removed"):
            project_evidence_row(raw, ["A is warm."])
        self.assertEqual(raw, before)

    def test_unknown_considered_or_decision_or_conflict_id_errors(self):
        values = [pointer_row(considered=["unknown"]), pointer_row(ids=["unknown"]),
                  pointer_row(verdict="CONTRADICTED", conflict={"evidence_ids": ["unknown"]})]
        for raw in values:
            with self.subTest(raw=raw), self.assertRaisesRegex(VerificationError, "unknown source"):
                project_evidence_row(raw, ["A is warm."])

    def test_duplicate_nonstring_and_nonconsidered_ids_rejected(self):
        for raw in (pointer_row(ids=["p0u1", "p0u1"]), pointer_row(ids=[[]]),
                    pointer_row(ids=["p0u1"], considered=[])):
            with self.subTest(raw=raw), self.assertRaises(VerificationError):
                project_evidence_row(raw, ["A is warm."])

    def test_legacy_citations_cannot_be_used_as_new_protocol(self):
        raw = pointer_row()
        raw["citations"] = [{"index": 0, "quote": "A is warm."}]
        with self.assertRaisesRegex(VerificationError, "legacy citations"):
            project_evidence_row(raw, ["A is warm."])

    def test_conflict_must_use_decision_ids_and_cannot_inject_free_quotes(self):
        raw = pointer_row(verdict="CONTRADICTED", conflict={
            "claim_span": "warm", "evidence_ids": ["p1u1"], "kind": "direct", "explanation": "Opposite."})
        with self.assertRaisesRegex(VerificationError, "subset"):
            project_evidence_row(raw, ["A is cold.", "Other text."])
        raw["conflict"] = {"claim_span": "warm", "evidence": [{"index": 0, "quote": "A is cold."}],
                           "kind": "direct", "explanation": "Opposite."}
        projected, _ = project_evidence_row(raw, ["A is cold."])
        self.assertIn("invalid_pointer_conflict", projected["conflict"])
        self.assertNotIn("evidence", projected["conflict"])

    def test_source_binding_checks_offsets_text_and_empty_unit(self):
        contexts = ["😀 A is warm."]
        original = {unit["id"]: unit for unit in source_units(contexts)}
        for key, bad in (("index", True), ("start_char", -1), ("end_char", 100), ("text", "A is cold.")):
            units = deepcopy(original)
            units["p0u1"][key] = bad
            with self.subTest(key=key), self.assertRaises(VerificationError):
                materialize_ids(["p0u1"], units, contexts)
        with self.assertRaisesRegex(VerificationError, "empty"):
            project_evidence_row(pointer_row(), [" \n"])


if __name__ == "__main__":
    unittest.main()
