import unittest

from grounding.baseline import BaselineVerifier, split_claims
from grounding.contracts import VerificationRequest, validate_report


class BaselineTests(unittest.TestCase):
    def verify(self, context, answer):
        result = BaselineVerifier().verify(VerificationRequest(context, answer))
        validate_report(result.report, context)
        self.assertEqual(result.telemetry["calls"], [])
        return result.report["claims"]

    def test_chinese_and_english_sentences_preserve_numbers(self):
        answer = "数值为 1.03e-4。Version 3.7.0 is installed. It is stable."
        self.assertEqual(split_claims(answer), [
            "数值为 1.03e-4。", "Version 3.7.0 is installed.", "It is stable.",
        ])
        self.assertEqual(
            split_claims("The car is red and the bike is blue."),
            ["The car is red", "the bike is blue."],
        )

    def test_exact_match_returns_literal_sentence_and_original_index(self):
        context = ["Unrelated information.", "A value is 1.03e-4. Version 3.7.0 is installed."]
        claims = self.verify(context, "Version 3.7.0 is installed.")
        self.assertEqual(claims[0]["verdict"], "SUPPORTED")
        self.assertEqual(claims[0]["citations"], [{
            "index": 1, "quote": "Version 3.7.0 is installed.",
        }])

    def test_aligned_numeric_change_is_contradicted(self):
        claims = self.verify(["Alice has 3 cats."], "Alice has 4 cats.")
        self.assertEqual(claims[0]["verdict"], "CONTRADICTED")

    def test_unknown_fact_is_not_a_numeric_contradiction(self):
        claims = self.verify(["Alice has 3 cats."], "Alice has 4 dogs.")
        self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")
        self.assertEqual(claims[0]["citations"], [])

    def test_equivalent_number_format_is_not_a_contradiction(self):
        claims = self.verify(["The mass is 1.0 kg."], "The mass is 1 kg.")
        self.assertNotEqual(claims[0]["verdict"], "CONTRADICTED")

    def test_high_similarity_is_not_enough_for_support(self):
        claims = self.verify(["The large car is red."], "The large car is blue.")
        self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")

    def test_english_and_chinese_negation(self):
        cases = [
            (["The engine is running."], "The engine is not running."),
            (["该碰撞为完全非弹性碰撞。"], "该碰撞为完全弹性碰撞。"),
        ]
        for context, answer in cases:
            with self.subTest(answer=answer):
                self.assertEqual(self.verify(context, answer)[0]["verdict"], "CONTRADICTED")

    def test_formula_copula_change_and_sign_mismatch(self):
        context = ["等效量：f = a*b/(a+b-D)。"]
        self.assertEqual(
            self.verify(context, "等效量为 f = a*b/(a+b-D)。")[0]["verdict"], "SUPPORTED"
        )
        self.assertEqual(
            self.verify(context, "等效量为 f = a*b/(a+b+D)。")[0]["verdict"], "CONTRADICTED"
        )

    def test_formula_case_is_significant(self):
        claims = self.verify(["面积为 S = R*R。"], "面积为 S = r*r。")
        self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")

    def test_optional_unary_plus_is_not_a_contradiction(self):
        for lhs, rhs in (("+a", "a"), ("a", "+a"), ("a+(+b)", "a+(b)")):
            with self.subTest(lhs=lhs, rhs=rhs):
                claims = self.verify([f"The result is f = {lhs}."], f"The result is f = {rhs}.")
                self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")

    def test_zero_sign_change_is_not_a_contradiction(self):
        for lhs, rhs in (("a+0", "a-0"), ("a+0.0", "a-0.0"),
                         ("a+(0)", "a-(0)"), ("a+0*b", "a-0*b")):
            with self.subTest(lhs=lhs, rhs=rhs):
                claims = self.verify([f"The result is f = {lhs}."], f"The result is f = {rhs}.")
                self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")

    def test_actual_nonzero_sign_change_is_not_supported(self):
        claims = self.verify(["The result is f = a+0.5."], "The result is f = a-0.5.")
        self.assertEqual(claims[0]["verdict"], "CONTRADICTED")

    def test_equation_does_not_cover_added_unrelated_fact(self):
        claims = self.verify(["能量为 E = m*c^2。"], "金制装置的能量为 E = m*c^2。")
        self.assertEqual(claims[0]["verdict"], "UNSUPPORTED")

    def test_empty_context_retains_factual_claims(self):
        claims = self.verify([], "The mass is 5 kg. The speed is 3 m/s.")
        self.assertEqual(len(claims), 2)
        self.assertTrue(all(c["verdict"] == "UNSUPPORTED" for c in claims))

    def test_empty_and_nonfactual_answers(self):
        for answer in ("", "   ", "谢谢你的帮助！请继续。", "Thank you!", "What is the mass?"):
            with self.subTest(answer=answer):
                self.assertEqual(self.verify(["The mass is 5 kg."], answer), [])

    def test_thanks_prefix_does_not_hide_an_added_fact(self):
        self.assertEqual(len(self.verify([], "Thank you, the mass is 4 kg.")), 1)
        self.assertEqual(len(self.verify([], "谢谢，质量为四千克。")), 1)


if __name__ == "__main__":
    unittest.main()
