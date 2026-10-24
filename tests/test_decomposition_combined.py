"""Synthetic location, residual and fallback checks; no benchmark text or APIs."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest

from grounding.config import Settings
from grounding.config_v4 import V4Config
from grounding.contracts import VerificationError
from grounding.decomposition_combined import (
    CombinedDecompositionMixin, _allowed_tokens, answer_units, location_chunks,
    parse_decomposition, token_ranges,
)
from grounding.verifiers_v4 import OptimizedV4Verifier, _local_telemetry


def ref(unit_id="a1", start=0, end=1):
    return {"unit_id": unit_id, "start_token": start, "end_token": end}


def extraction(claims=(), non_factual=(), ambiguous=(), unprocessed=()):
    return {"claims": list(claims), "non_factual_spans": list(non_factual),
            "ambiguous_spans": list(ambiguous), "unprocessed_spans": list(unprocessed)}


def claim(text, refs, background=()):
    return {"claim_text": text, "source_refs": refs, "background_refs": list(background)}


def classified(refs, reason="Non-factual wording."):
    return {"source_refs": refs, "reason": reason}


class FakeClient:
    def __init__(self, outputs=None, handler=None):
        self.outputs = list(outputs or [])
        self.handler = handler
        self.inputs = []

    def complete(self, messages, stage, telemetry):
        self.inputs.append({"stage": stage, "messages": deepcopy(messages)})
        value = self.handler(json.loads(messages[1]["content"]), stage) if self.handler else self.outputs.pop(0)
        telemetry["calls"].append({"stage": stage, "attempt": 1, "response_text": json.dumps(value), "usage": {}})
        return deepcopy(value)


class Extractor(CombinedDecompositionMixin, OptimizedV4Verifier):
    pass


class CombinedDecompositionTests(unittest.TestCase):
    def parse(self, answer, payload):
        units = answer_units(answer)
        return parse_decomposition(payload, answer, units, _allowed_tokens(units, 0, len(answer)), max_claims=64)

    def run_extraction(self, answer, outputs=None, handler=None, config=None):
        client = FakeClient(outputs, handler)
        extractor = Extractor(Settings(base_url="http://example.test", model="fake", api_key="fake"), client,
                              config or replace(V4Config(), max_workers=1))
        telemetry = _local_telemetry()
        claims = extractor._decompose(answer, telemetry)
        return claims, telemetry, client

    def test_location_units_keep_exact_offsets_signs_decimal_and_multilingual_text(self):
        answer = "温度是−5.5度。 A costs 3.5, not 35. A costs 3.5, not 35."
        units = answer_units(answer)
        self.assertEqual("".join(unit["text"] for unit in units), answer)
        for unit in units:
            self.assertEqual(answer[unit["source_start"]:unit["source_end"]], unit["text"])
            for token in unit["tokens"]:
                self.assertEqual(answer[token["start"]:token["end"]], token["text"])
        tokens = [token["text"] for unit in units for token in unit["tokens"]]
        self.assertIn("−5.5", tokens)
        self.assertIn("3.5", tokens)
        self.assertIn("35", tokens)
        self.assertEqual(units, answer_units(answer))

    def test_seen_unit_and_background_do_not_cover_unselected_facts(self):
        answer = "A is warm and B is cold."
        result = self.parse(answer, extraction([claim("A is warm.", [ref(end=3)], ["a1"])]))
        self.assertTrue(result["remaining_tokens"])
        self.assertIn(("a1", 6), result["remaining_tokens"])
        self.assertEqual(result["claims"][0]["source_span"], "A is warm")
        self.assertEqual(result["claims"][0]["answer_background"][0]["text"], answer)

    def test_enclosing_span_is_not_used_to_hide_discontiguous_residual(self):
        answer = "A is warm and B is cold."
        result = self.parse(answer, extraction([claim("A and B exist.", [ref(end=1), ref(start=4, end=5)])]))
        self.assertEqual(result["claims"][0]["source_span"], "A is warm and B")
        self.assertIn(("a1", 1), result["remaining_tokens"])
        self.assertIn(("a1", 2), result["remaining_tokens"])

    def test_invalid_locations_and_background_are_rejected(self):
        for refs, background in [([ref("bad")], []), ([ref(start=True)], []),
                                 ([ref(end=99)], []), ([ref()], ["bad"]), ([ref()], ["a1", "a1"])]:
            with self.subTest(refs=refs, background=background), self.assertRaises(VerificationError):
                self.parse("A is warm.", extraction([claim("A is warm.", refs, background)]))

    def test_factual_and_nonfactual_subspans_coexist_without_overlap(self):
        answer = "Try it because it lowers heat."
        result = self.parse(answer, extraction([claim("It lowers heat.", [ref(start=3, end=6)], ["a1"])],
                                              [classified([ref(end=3)])]))
        self.assertFalse(result["remaining_tokens"])
        self.assertEqual(result["claims"][0]["claim_text"], "It lowers heat.")
        with self.assertRaises(VerificationError):
            self.parse(answer, extraction([claim("It lowers heat.", [ref(end=6)])], [classified([ref(end=1)])]))

    def test_residual_pass_uses_only_remaining_locations_and_preserves_background(self):
        answer = "Device limits:\nIt runs cold. It lasts long."
        units = answer_units(answer)
        self.assertEqual(len(units), 3)
        initial = extraction([claim("Under device limits it runs cold.", [ref("a2", end=3)], ["a1"])],
                             [classified([ref("a1", end=3)], "Heading supplies scope, not a standalone fact.")])
        residual = extraction([claim("Under device limits it lasts long.", [ref("a3", end=3)], ["a1"])])
        claims, telemetry, client = self.run_extraction(answer, [initial, residual])
        self.assertEqual([row["stage"] for row in client.inputs], ["decompose", "decompose_residual"])
        self.assertEqual(len(claims), 2)
        self.assertNotIn("extraction_fallback", claims[0])
        payload = json.loads(client.inputs[1]["messages"][1]["content"])
        self.assertEqual({value["unit_id"] for value in payload["target_ranges"]}, {"a3"})
        self.assertEqual(len(payload["answer_context"]), 3)
        self.assertEqual(claims[0]["answer_background"][0]["role"], "unverified_answer_background")
        self.assertFalse(telemetry["extraction"]["residual_ranges_after_fallback"])

    def test_exhausted_residual_replaces_whole_original_sentence_without_merging(self):
        answer = "A is warm and B is cold."
        partial = extraction([claim("A is warm.", [ref(end=3)])])
        claims, telemetry, client = self.run_extraction(answer, [partial, extraction()])
        self.assertEqual([row["stage"] for row in client.inputs], ["decompose", "decompose_residual"])
        self.assertEqual([row["claim_text"] for row in claims], [answer])
        self.assertTrue(claims[0]["extraction_fallback"])
        audit = telemetry["extraction"]["hard_split_recoveries"][0]
        self.assertEqual(audit["superseded_claims"][0]["claim_text"], "A is warm.")
        self.assertTrue(telemetry["extraction"]["residual_ranges_before_fallback"])
        self.assertFalse(telemetry["extraction"]["residual_ranges_after_fallback"])

    def test_expanded_multiunit_recovery_skips_intervening_whitespace_unit(self):
        answer = "A is warm.\n\nB is cold and C is wet."
        self.assertEqual(answer_units(answer)[1]["tokens"], [])
        initial = extraction([claim("A is warm and B is cold.", [ref("a1", end=3), ref("a3", end=3)])])
        claims, telemetry, _ = self.run_extraction(answer, [initial, extraction()])
        self.assertEqual([row["claim_text"] for row in claims], ["A is warm.", "B is cold and C is wet."])
        self.assertTrue(all(row["extraction_fallback"] for row in claims))
        skipped = [row for row in telemetry["extraction"]["hard_split_recoveries"] if row.get("kind") == "formatting_only"]
        self.assertEqual([row["unit_id"] for row in skipped], ["a2"])
        self.assertFalse(telemetry["extraction"]["residual_ranges_after_fallback"])

    def test_ambiguity_and_unprocessed_are_not_turned_into_nonfactual_exclusions(self):
        answer = "It does that. More follows."
        initial = extraction(ambiguous=[classified([ref("a1", end=3)], "Antecedent unclear.")],
                             unprocessed=[classified([ref("a2", end=2)], "Not processed.")])
        claims, telemetry, _ = self.run_extraction(answer, [initial, extraction()])
        self.assertEqual(len(claims), 2)
        self.assertTrue(all(row["extraction_fallback"] for row in claims))
        self.assertEqual(len(telemetry["extraction"]["ambiguous_spans"]), 1)
        self.assertEqual(len(telemetry["extraction"]["unprocessed_spans"]), 1)
        self.assertFalse(telemetry["extraction"]["non_factual_spans"])

    def test_exhausted_bad_format_uses_existing_retry_limit_then_sentence_fallback(self):
        claims, telemetry, client = self.run_extraction("A is warm.", [{"bad": []}, {"bad": []}])
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "decompose_repair_1"])
        self.assertEqual(len(telemetry["repairs"]), 1)
        self.assertTrue(claims[0]["extraction_fallback"])

    def test_only_nonfactual_text_keeps_empty_claims(self):
        answer = "Please wait."
        claims, telemetry, client = self.run_extraction(answer, [extraction(non_factual=[classified([ref(end=2)])])])
        self.assertEqual(claims, [])
        self.assertEqual(len(client.inputs), 1)
        self.assertFalse(telemetry["extraction"]["residual_ranges_after_fallback"])

    def test_chunks_are_bounded_and_never_split_location_token(self):
        answer = "Alpha " * 80 + "ends.\n" + "字" * 250 + "。"
        units = answer_units(answer)
        chunks = location_chunks(answer, units, 128)
        self.assertEqual("".join(answer[start:end] for start, end in chunks), answer)
        self.assertTrue(all(end - start <= 128 for start, end in chunks))
        for unit in units:
            for token in unit["tokens"]:
                owners = [(start, end) for start, end in chunks if start <= token["start"] and token["end"] <= end]
                self.assertEqual(len(owners), 1)

    def test_hard_chunk_failure_retains_original_complete_sentence(self):
        answer = "Long wording " * 26 + "."
        claims, telemetry, client = self.run_extraction(answer, handler=lambda payload, stage: {"bad": []},
                                                      config=replace(V4Config(), decompose_chunk_chars=128, format_retries=0))
        self.assertGreater(len(client.inputs), 1)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_text"], answer)
        self.assertTrue(claims[0]["extraction_fallback"])
        self.assertGreater(len(claims[0]["origin_chunk_ids"]), 1)
        self.assertFalse(telemetry["extraction"]["residual_ranges_after_fallback"])

    def test_repeated_occurrences_have_distinct_ids_and_exact_offsets(self):
        answer = "A is warm. A is warm."
        payload = extraction([claim("A is warm.", [ref("a1", end=3)]), claim("A is warm.", [ref("a2", end=3)])])
        claims, _, _ = self.run_extraction(answer, [payload])
        self.assertEqual(len(claims), 2)
        self.assertNotEqual(claims[0]["source_start"], claims[1]["source_start"])
        self.assertEqual([row["id"] for row in claims], ["c1", "c2"])

    def test_background_does_not_weaken_conditions_or_attribution_in_supplied_target(self):
        answer = "In cold weather:\nSource 2 says unit A runs slowly."
        units = answer_units(answer)
        target = "In cold weather, Source 2 says unit A runs slowly."
        payload = extraction([claim(target, [ref("a2", end=len(units[1]["tokens"]))], ["a1"])],
                             [classified([ref("a1", end=len(units[0]["tokens"]))])])
        claims, _, _ = self.run_extraction(answer, [payload])
        self.assertEqual(claims[0]["claim_text"], target)
        self.assertEqual(claims[0]["answer_background"][0]["text"], "In cold weather:\n")

    def test_location_accounting_explicitly_cannot_detect_semantic_omission(self):
        answer = "A is warm and B is cold."
        payload = extraction([claim("A is warm.", [ref(end=8)])])
        claims, telemetry, _ = self.run_extraction(answer, [payload])
        # This is deliberately semantically incomplete: a pointer validator must
        # not pretend it has proved recall merely because all words were mapped.
        self.assertEqual(claims[0]["claim_text"], "A is warm.")
        self.assertIn("do not prove semantic recall", telemetry["extraction"]["limitation"])

    def test_nonfactual_exact_span_cannot_cover_every_repeated_occurrence(self):
        answer = "Please wait. Please wait."
        units = answer_units(answer)
        parsed = parse_decomposition(extraction(non_factual=[classified([ref("a1", end=2)])]), answer, units,
                                     _allowed_tokens(units, 0, len(answer)), max_claims=64)
        self.assertEqual({unit_id for unit_id, _ in parsed["remaining_tokens"]}, {"a2"})


if __name__ == "__main__":
    unittest.main()
