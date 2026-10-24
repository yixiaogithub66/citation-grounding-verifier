"""Backend CLI selection reaches the unchanged claim scoring runner."""
from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from grounding.config import Settings
from grounding.config_v4 import load_v4_config
from grounding.contracts import VerificationResult
from grounding.factory import DEFAULT_V4_CONFIG_PATH
from scripts import benchmark_v4_claims as claims


class ClaimRunnerCliTests(unittest.TestCase):
    def test_current_three_way_default_and_explicit_selection(self):
        for extra, expected in (([], ("baseline", "minimal", "optimized-v4.0")),
                                (["--backends", "optimized-v4.0", "optimized-v4-m1-faithful"],
                                 ("optimized-v4.0", "optimized-v4-m1-faithful")),
                                (["--backends", "optimized", "optimized-v4", "minimal"],
                                 ("optimized-v4.0", "minimal"))):
            args = ["benchmark_v4_claims.py", "--dataset", "synthetic.jsonl", "--output-dir", "synthetic-output", *extra]
            with patch("sys.argv", args), patch.object(claims, "load_settings", return_value=Settings(api_key="fake")), \
                    patch.object(claims, "run") as run, \
                    patch.object(claims, "load_v4_config", wraps=claims.load_v4_config) as load_config:
                claims.main()
            self.assertEqual(run.call_args.kwargs["backends"], expected)
            self.assertEqual(run.call_args.args[0], Path("synthetic.jsonl"))
            load_config.assert_called_once_with(DEFAULT_V4_CONFIG_PATH)

    def test_current_default_runner_preserves_partial_completed_claims(self):
        def supported(text):
            return {"claim_text": text, "verdict": "SUPPORTED", "reasoning": "Explicit evidence.",
                    "citations": [{"index": 0, "quote": text}]}
        complete = {"claims": [supported("A exists."), supported("B exists.")]}
        partial = {"claims": [supported("A exists.")], "status": "partial",
                   "errors": [{"id": "c2", "code": "upstream_timeout", "message": "Timed out."}]}
        case = {"id": "synthetic", "split": "dev", "category": "supported",
                "input": {"context_passages": ["A exists. B exists."], "generated_answer": "A exists. B exists."},
                "expected": complete}
        def build(backend, settings, **kwargs):
            return Mock(verify=Mock(return_value=VerificationResult(
                partial if backend == "optimized-v4.0" else complete, {"calls": []})))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "cases.jsonl"
            dataset.write_text(json.dumps(case) + "\n", encoding="utf-8")
            with patch.object(claims, "build_verifier", side_effect=build), contextlib.redirect_stdout(io.StringIO()):
                report = claims.run(dataset, root / "run", Settings(), load_v4_config(DEFAULT_V4_CONFIG_PATH))
            self.assertEqual(set(report["backends"]), {"baseline", "minimal", "optimized-v4.0"})
            result = report["backends"]["optimized-v4.0"]
            self.assertEqual(result["status_counts"], {"partial": 1})
            self.assertEqual(result["completed_claim_count"], 1)
            self.assertEqual(result["gold_alignment_coverage"]["value"], 0.5)


if __name__ == "__main__":
    unittest.main()
