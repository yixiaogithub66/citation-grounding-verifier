import unittest
from scripts.benchmark_v4_combined import BACKENDS
from scripts.summarize_v4_combined import paired_comparison


def observation(identifier, backend, truth, prediction, status="complete"):
    return {"id": identifier, "source_id": "shared-source", "backend": backend, "y_true": truth, "y_pred": prediction,
            "status": status, "completed_claims": int(prediction is not None), "failed_claims": int(status != "complete"),
            "claim_total_known": True, "empty_claims": False, "nonempty_answer_empty_claims": False}


class PairedScoringTests(unittest.TestCase):
    def test_unknown_is_not_false_negative_and_pairs_share_source_draws(self):
        a, b = BACKENDS
        rows = [observation("a", a, True, None, "error"), observation("a", b, True, True),
                observation("b", a, False, False), observation("b", b, False, True)]
        result = paired_comparison(rows, samples=20)
        self.assertEqual(result["transition_counts"], {"unknown_to_correct": 1, "correct_to_wrong": 1})
        self.assertEqual(result["source_cluster_count"], 1)
        delta = result["deltas"]["correct_decisions_per_all_cases"]
        self.assertEqual(delta["low"], 0)
        self.assertEqual(delta["high"], 0)
        self.assertEqual(result, paired_comparison(rows, samples=20))

    def test_missing_backend_cannot_enter_paired_denominator(self):
        with self.assertRaisesRegex(ValueError, "both observations"):
            paired_comparison([observation("a", BACKENDS[0], True, True)], samples=0)

    def test_stable_wrong_has_no_improvement(self):
        rows = [observation("a", backend, True, False) for backend in BACKENDS]
        result = paired_comparison(rows, samples=10)
        self.assertEqual(result["transition_counts"], {"wrong_to_wrong": 1})
        self.assertEqual(result["deltas"]["resolved_f1"]["high"], 0)


if __name__ == "__main__":
    unittest.main()
