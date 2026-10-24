"""Safety and bounded-work regressions for deterministic v4 evidence handling."""

from __future__ import annotations

from difflib import SequenceMatcher
import unittest
from unittest.mock import patch

from grounding.evidence_v4 import MAX_FUZZY_WINDOWS, numeric_conflict_signals, repair_citations


class CitationRepairTests(unittest.TestCase):
    def repair(self, quote, contexts, *, index=0, **kwargs):
        return repair_citations([{"index": index, "quote": quote}], contexts, **kwargs)

    def assert_exact_outputs(self, result, contexts):
        for citation in result["citations"]:
            self.assertIn(citation["quote"], contexts[citation["index"]])
        for event in result["events"]:
            if "after" in event:
                citation = event["after"]
                self.assertEqual(contexts[citation["index"]][event["start"]:event["end"]], citation["quote"])
        for candidate in result["candidates"]:
            self.assertEqual(contexts[candidate["index"]][candidate["start"]:candidate["end"]], candidate["quote"])

    def test_exact_citation_retains_contract_and_unicode_offsets(self):
        contexts = ["😀中文前缀 The speed is 2 m/s."]
        result = self.repair("The speed is 2 m/s.", contexts)
        self.assertFalse(result["needs_requery"])
        self.assertEqual(result["events"][0]["start"], 6)
        self.assertEqual(set(result["citations"][0]), {"index", "quote"})
        self.assert_exact_outputs(result, contexts)

    def test_valid_index_exact_quote_needs_no_repair_despite_other_occurrences(self):
        result = self.repair("fact", ["fact fact", "fact"])
        self.assertFalse(result["needs_requery"])
        self.assertEqual(result["events"][0]["kind"], "exact")

    def test_valid_optional_unicode_offsets_select_repeated_occurrence(self):
        citation = {"index": 0, "quote": "fact", "start_char": 7, "end_char": 11}
        contexts = ["😀 fact fact"]
        result = repair_citations([citation], contexts)
        self.assertFalse(result["needs_requery"])
        self.assertEqual(result["citations"], [citation])
        self.assertEqual(result["events"][0]["start"], 7)
        self.assert_exact_outputs(result, contexts)

    def test_incorrect_optional_offsets_are_repaired_without_semantic_requery(self):
        for offsets in ((0, 2), (True, 5), ("2", "6"), (2, 100)):
            with self.subTest(offsets=offsets):
                citation = {"index": 0, "quote": "fact", "start_char": offsets[0], "end_char": offsets[1]}
                result = repair_citations([citation], ["😀 fact"])
                self.assertFalse(result["needs_requery"])
                self.assertEqual(result["citations"][0], {"index": 0, "quote": "fact", "start_char": 2, "end_char": 6})
                self.assertEqual(result["events"][0]["method"], "offsets")

    def test_ambiguous_invalid_offsets_are_removed_with_unchanged_valid_quote(self):
        citation = {"index": 0, "quote": "fact", "start_char": 0, "end_char": 1}
        result = repair_citations([citation], ["😀 fact fact"])
        self.assertFalse(result["needs_requery"])
        self.assertEqual(result["citations"], [{"index": 0, "quote": "fact"}])
        self.assertEqual(result["events"][0]["method"], "offsets_removed_ambiguous")

    def test_format_and_wrong_index_repairs_update_optional_offsets(self):
        cases = [({"index": 0, "quote": "A fact.", "start_char": 0, "end_char": 7}, ["😀 A  fact."]),
                 ({"index": 0, "quote": "fact", "start_char": 0, "end_char": 4}, ["other", "😀 fact"])]
        for citation, contexts in cases:
            with self.subTest(citation=citation):
                result = repair_citations([citation], contexts)
                self.assertFalse(result["needs_requery"])
                fixed = result["citations"][0]
                self.assertEqual(contexts[fixed["index"]][fixed["start_char"]:fixed["end_char"]], fixed["quote"])
                self.assert_exact_outputs(result, contexts)

    def test_whitespace_repair_preserves_original_substring(self):
        contexts = ["😀 A\t\n  stable\u00a0value is 3 m/s."]
        result = self.repair("A stable value is 3 m/s.", contexts)
        self.assertFalse(result["needs_requery"])
        self.assertEqual(result["citations"][0]["quote"], "A\t\n  stable\u00a0value is 3 m/s.")
        self.assertEqual(result["events"][0]["method"], "safe_format")
        self.assert_exact_outputs(result, contexts)

    def test_paired_quote_and_safe_fullwidth_punctuation_repair(self):
        contexts = ["The label is “ready”， and it works！"]
        result = self.repair('The label is "ready", and it works!', contexts)
        self.assertFalse(result["needs_requery"])
        self.assert_exact_outputs(result, contexts)

    def test_unique_wrong_index_exact_repair_including_out_of_bounds(self):
        for index in (0, -1, 10):
            with self.subTest(index=index):
                contexts = ["Another fact.", "😀 Actual quoted fact."]
                result = self.repair("Actual quoted fact.", contexts, index=index)
                self.assertFalse(result["needs_requery"])
                self.assertEqual(result["citations"][0]["index"], 1)
                self.assertEqual(result["events"][0]["method"], "wrong_index_exact")
                self.assert_exact_outputs(result, contexts)

    def test_wrong_index_and_format_changes_combined_require_rejudgment(self):
        result = self.repair("A stable value.", ["unrelated", "A   stable value."])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["candidates"][0]["index"], 1)

    def test_normalized_duplicates_in_one_or_multiple_passages_are_ambiguous(self):
        for contexts in (["A   fact. A   fact."], ["A   fact.", "A fact."]):
            with self.subTest(contexts=contexts):
                result = self.repair("A\tfact.", contexts)
                self.assertTrue(result["needs_requery"])
                self.assertEqual(result["citations"], [])
                self.assertEqual(result["errors"][0]["code"], "ambiguous_quote")
                self.assert_exact_outputs(result, contexts)

    def test_wrong_index_reverse_lookup_never_selects_between_duplicates(self):
        result = self.repair("A fact.", ["unrelated", "A fact.", "A fact."])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(result["citations"], [])

    def test_exact_reverse_lookup_also_checks_normalized_global_ambiguity(self):
        result = self.repair("A fact.", ["unrelated", "A fact.", "A  fact."])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(result["errors"][0]["code"], "ambiguous_quote")

    def test_no_digit_letter_or_operator_folding(self):
        pairs = [
            ("The value is 2.", "The value is ²."),
            ("The value is 2.", "The value is ２."),
            ("The value is IV.", "The value is Ⅳ."),
            ("The name is ffi.", "The name is ﬃ."),
            ("The name is A.", "The name is Ａ."),
            ("x - y", "x − y"), ("x * y", "x × y"),
            ("x/y", "x∕y"), ("x^2", "x²"),
            ("a < b", "a > b"), ("x = 2", "x ≠ 2"),
            ("X is ready.", "x is ready."),
            ("The value is 1.5.", "The value is 15."),
            ("The value is 1000.", "The value is 1 000."),
        ]
        for quote, context in pairs:
            with self.subTest(quote=quote, context=context):
                result = self.repair(quote, [context], fuzzy_threshold=0.4)
                self.assertTrue(result["needs_requery"])
                self.assertEqual(result["citations"], [])
                self.assertFalse(any(event["kind"] == "repair" for event in result["events"]))

    def test_negation_numeric_and_entity_changes_are_only_candidates(self):
        pairs = [
            ("The control system does support remote access in the main operating mode.",
             "The control system does not support remote access in the main operating mode."),
            ("The control system allows 3 active clients in the main operating mode.",
             "The control system allows 5 active clients in the main operating mode."),
            ("The control system sends requests to Atlas in the main operating mode.",
             "The control system sends requests to Brisk in the main operating mode."),
        ]
        for quote, paragraph in pairs:
            with self.subTest(quote=quote):
                result = self.repair(quote, [paragraph], fuzzy_threshold=0.8)
                self.assertTrue(result["needs_requery"])
                self.assertEqual(result["citations"], [])
                self.assertTrue(result["candidates"])
                self.assertTrue(all(row["method"] == "fuzzy_candidate" for row in result["candidates"]))
                self.assert_exact_outputs(result, [paragraph])

    def test_missing_punctuation_is_not_deleted_by_normalization(self):
        result = self.repair("Do not stop.", ["Do, not stop."])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(result["citations"], [])

    def test_no_matching_context_does_not_fabricate_citations(self):
        result = self.repair("Entirely invented evidence.", ["Nothing related."])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["candidates"], [])

    def test_empty_citations_is_valid_but_empty_context_with_citation_requires_requery(self):
        self.assertFalse(repair_citations([], [])["needs_requery"])
        self.assertTrue(self.repair("missing", [])["needs_requery"])

    def test_malformed_citation_shapes_are_local_errors(self):
        malformed = [None, "text", 3, {}, {"quote": "x"}, {"index": True, "quote": "x"},
                     {"index": "0", "quote": "x"}, {"index": 0, "quote": []},
                     {"index": 0, "quote": " "}, {"index": 0, "quote": "x", "extra": True}]
        for bad in malformed:
            with self.subTest(bad=bad):
                result = repair_citations([bad, {"index": 0, "quote": "valid"}], ["valid"])
                self.assertTrue(result["needs_requery"])
                self.assertEqual(result["citations"], [{"index": 0, "quote": "valid"}])
                self.assertEqual(len(result["errors"]), 1)
        for bad in (None, {}, "text", [{"index": 0, "quote": "x"}] * 33):
            self.assertTrue(repair_citations(bad, ["x"])["needs_requery"])

    def test_invalid_settings_are_reported_without_raw_exception(self):
        for config in ({"fuzzy_threshold": float("nan")}, {"fuzzy_threshold": True},
                       {"window_tokens": 0}, {"window_tokens": 10000}, {"window_tokens": "80"}):
            with self.subTest(config=config):
                result = self.repair("x", ["x"], **config)
                self.assertEqual(result["errors"][0]["code"], "invalid_repair_config")

    def test_long_paragraph_search_has_bounded_comparisons_and_finds_late_rare_anchor(self):
        paragraph = "boilerplate " * 14000 + "UniqueAnchor system allows 5 active clients in the main operating mode."
        quote = "UniqueAnchor system allows 3 active clients in the main operating mode."
        with patch("grounding.evidence_v4.SequenceMatcher", wraps=SequenceMatcher) as matcher:
            result = self.repair(quote, [paragraph], fuzzy_threshold=0.8)
        self.assertLessEqual(matcher.call_count, MAX_FUZZY_WINDOWS)
        self.assertTrue(result["needs_requery"])
        self.assertTrue(result["candidates"])
        self.assertGreater(result["candidates"][0]["start"], 100000)
        self.assert_exact_outputs(result, [paragraph])

    def test_oversized_quote_skips_fuzzy_work_but_still_requires_requery(self):
        with patch("grounding.evidence_v4.SequenceMatcher", wraps=SequenceMatcher) as matcher:
            result = self.repair("many " * 1000 + "claims", ["many " * 1000 + "facts"])
        self.assertTrue(result["needs_requery"])
        self.assertEqual(matcher.call_count, 0)

    def test_repair_does_not_mutate_model_output(self):
        citations = [{"index": 1, "quote": "A fact."}]
        repair_citations(citations, ["A fact.", "unrelated"])
        self.assertEqual(citations, [{"index": 1, "quote": "A fact."}])


class NumericSignalTests(unittest.TestCase):
    def signals(self, claim, evidence, **kwargs):
        return numeric_conflict_signals(claim, [{"index": 0, "quote": evidence}], [evidence], **kwargs)

    def test_same_anchor_same_literal_unit_yields_signal_not_verdict(self):
        signals = self.signals("The speed is 3 m/s.", "The speed is 2 m/s.")
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal["values"], {"claim": "3", "evidence": "2"})
        self.assertEqual(signal["unit"], "m/s")
        self.assertNotIn("verdict", signal)
        self.assertEqual(signal["claim_span"], "The speed is 3 m/s.")

    def test_equal_decimal_values_do_not_create_conflict(self):
        for claim, evidence in (("Speed is 3.0 m/s.", "Speed is 3 m/s."),
                                ("Speed is 3e1 m/s.", "Speed is 30 m/s.")):
            self.assertEqual(self.signals(claim, evidence), [])

    def test_unitless_and_attached_units_keep_exact_anchor(self):
        for claim, evidence, unit in (("Value is 3.", "Value is 2.", ""),
                                      ("Delay = 3ms.", "Delay = 2ms.", "ms"),
                                      ("Rate is 3%.", "Rate is 2%.", "%")):
            with self.subTest(claim=claim):
                signals = self.signals(claim, evidence)
                self.assertEqual(len(signals), 1)
                self.assertEqual(signals[0]["unit"], unit)

    def test_unrecognized_number_notation_is_not_partially_extracted(self):
        pairs = [("Value is 1,000 m.", "Value is 2,000 m."),
                 ("Value is 1 000 m.", "Value is 2 000 m."),
                 ("Value is 1\u00a0000 m.", "Value is 2\u00a0000 m."),
                 ("Value is 1２ m.", "Value is 2２ m."),
                 ("Value is 2² m.", "Value is 3² m."),
                 ("Value is 2^3 m.", "Value is 3^3 m.")]
        for claim, evidence in pairs:
            with self.subTest(claim=claim):
                self.assertEqual(self.signals(claim, evidence), [])

    def test_no_unit_conversion_arithmetic_or_formula_solving(self):
        pairs = [("Speed is 3 m/s.", "Speed is 2 km/s."),
                 ("Delay is 1 s.", "Delay is 1000 ms."),
                 ("Sum is 3.", "Sum is 1 + 1."),
                 ("x = 3.", "x + 1 = 3."),
                 ("Value is 2².", "Value is 4.")]
        for claim, evidence in pairs:
            with self.subTest(claim=claim):
                self.assertEqual(self.signals(claim, evidence), [])

    def test_distinct_anchors_conditions_or_case_are_not_aligned(self):
        pairs = [("Height is 3 m.", "Width is 2 m."),
                 ("The speed is 3 m/s.", "A speed of 2 m/s was recorded."),
                 ("At rest, speed is 3 m/s.", "In motion, speed is 2 m/s."),
                 ("Speed is 3 MB/s.", "Speed is 2 mb/s.")]
        for claim, evidence in pairs:
            self.assertEqual(self.signals(claim, evidence), [])

    def test_ambiguous_repeated_anchor_never_guesses_alignment(self):
        self.assertEqual(self.signals("Speed is 3 m/s.", "Speed is 2 m/s. Speed is 4 m/s."), [])
        self.assertEqual(self.signals("Speed is 3 m/s. Speed is 5 m/s.", "Speed is 2 m/s."), [])

    def test_ambiguous_location_and_invalid_citation_cannot_supply_evidence(self):
        self.assertEqual(numeric_conflict_signals("Speed is 3 m/s.", [{"index": 0, "quote": "Speed is 2 m/s."}],
                                                 ["Speed is 2 m/s. Speed is 2 m/s."]), [])
        for citations in (None, "bad", [None], [{"index": True, "quote": "Speed is 2 m/s."}],
                          [{"index": 0, "quote": "invented 2 m/s"}], []):
            self.assertEqual(numeric_conflict_signals("Speed is 3 m/s.", citations, ["Speed is 2 m/s."]), [])

    def test_duplicate_citations_do_not_make_identical_location_ambiguous(self):
        quote = "Speed is 2 m/s."
        signals = numeric_conflict_signals("Speed is 3 m/s.", [{"index": 0, "quote": quote}] * 2, [quote])
        self.assertEqual(len(signals), 1)

    def test_unicode_offsets_select_exact_claim_and_evidence(self):
        claim, quote = "😀速度是 3 m/s.", "😀速度是 2 m/s."
        paragraph = "前缀 " + quote
        signals = numeric_conflict_signals(claim, [{"index": 0, "quote": quote}], [paragraph])
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(claim[signal["claim_start"]:signal["claim_end"]], signal["claim_span"])
        self.assertEqual(paragraph[signal["evidence_start"]:signal["evidence_end"]], quote)

    def test_fullwidth_digits_and_superscripts_are_never_numeric_normalized(self):
        self.assertEqual(self.signals("Value is ２ m.", "Value is 3 m."), [])
        self.assertEqual(self.signals("Value is ² m.", "Value is 3 m."), [])


if __name__ == "__main__":
    unittest.main()
