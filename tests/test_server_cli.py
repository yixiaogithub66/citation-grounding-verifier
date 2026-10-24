"""Public backend/config selection is independent of the launch directory."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grounding import server
from grounding.config import Settings
from grounding.config_v4 import load_v4_config
from grounding.factory import DEFAULT_V4_CONFIG_PATH


class ServerCliTests(unittest.TestCase):
    def launch(self, arguments):
        with patch("sys.argv", ["grounding.server", *arguments]), \
                patch.object(server, "load_settings", return_value=Settings(api_key="synthetic")) as settings, \
                patch.object(server, "build_verifier") as build, \
                patch.object(server, "VerificationServer") as listener, \
                contextlib.redirect_stdout(io.StringIO()):
            listener.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
            server.main()
            return settings, build, listener

    def test_default_and_optimized_alias_load_repository_config_from_another_directory(self):
        expected = load_v4_config(DEFAULT_V4_CONFIG_PATH)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                for arguments in ([], ["--backend", "optimized"], ["--backend", "optimized-v4"]):
                    with self.subTest(arguments=arguments):
                        _, build, listener = self.launch(arguments)
                        self.assertEqual(build.call_args.args[0], "optimized-v4.0")
                        self.assertEqual(build.call_args.kwargs["v4_config"], expected)
                        self.assertEqual(listener.call_args.kwargs["backend"], "optimized-v4.0")
            finally:
                os.chdir(previous)

    def test_explicit_config_overrides_repository_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stages.json"
            path.write_text(json.dumps({"review": {"thinking": "disabled", "max_output_tokens": 4096}}), encoding="utf-8")
            _, build, _ = self.launch(["--v4-config", str(path)])
            self.assertEqual(build.call_args.kwargs["v4_config"].review.max_output_tokens, 4096)
            self.assertEqual(build.call_args.kwargs["v4_config"].review.thinking, "disabled")

    def test_explicit_legacy_backend_does_not_load_v4_config(self):
        with patch.object(server, "load_v4_config") as config:
            _, build, listener = self.launch(["--backend", "optimized-v3"])
        config.assert_not_called()
        self.assertEqual(build.call_args.args[0], "optimized-v3")
        self.assertNotIn("v4_config", build.call_args.kwargs)
        self.assertEqual(listener.call_args.kwargs["backend"], "optimized-v3")

    def test_v4_config_for_baseline_is_rejected_before_loading_credentials(self):
        with patch("sys.argv", ["grounding.server", "--backend", "baseline", "--v4-config", "unused.json"]), \
                patch.object(server, "load_settings") as settings, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                server.main()
        self.assertEqual(raised.exception.code, 2)
        settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
