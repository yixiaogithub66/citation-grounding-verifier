"""Backend CLI selection reaches the unchanged claim scoring runner."""
from pathlib import Path
import unittest
from unittest.mock import patch

from grounding.config import Settings
from scripts import benchmark_v4_claims as claims


class ClaimRunnerCliTests(unittest.TestCase):
    def test_m1_backend_explicit_selection_and_historical_default(self):
        for extra, expected in (([], ("optimized-v4.0",)),
                                (["--backends", "optimized-v4.0", "optimized-v4-m1-faithful"],
                                 ("optimized-v4.0", "optimized-v4-m1-faithful"))):
            args = ["benchmark_v4_claims.py", "--dataset", "synthetic.jsonl", "--output-dir", "synthetic-output", *extra]
            with patch("sys.argv", args), patch.object(claims, "load_settings", return_value=Settings(api_key="fake")), \
                    patch.object(claims, "run") as run:
                claims.main()
            self.assertEqual(run.call_args.kwargs["backends"], expected)
            self.assertEqual(run.call_args.args[0], Path("synthetic.jsonl"))


if __name__ == "__main__":
    unittest.main()
