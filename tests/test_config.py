import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grounding.config import Settings, load_settings
from grounding.contracts import VerificationError


class ConfigurationTests(unittest.TestCase):
    def test_env_file_is_data_not_shell_and_process_env_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / ".env"
            path.write_text('LLM_API_KEY="literal$(not-executed)"\nLLM_MODEL=file-model\n', encoding="utf-8")
            settings = load_settings(path)
            self.assertEqual(settings.api_key, "literal$(not-executed)")
            self.assertNotIn(settings.api_key, repr(settings))
            self.assertNotIn("api_key", settings.public_dict())
            with patch.dict(os.environ, {"LLM_MODEL": "env-model"}):
                self.assertEqual(load_settings(path).model, "env-model")
                self.assertEqual(load_settings(path, model="cli-model").model, "cli-model")

    def test_bad_values_and_unclosed_quote(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / ".env"
            for content in ('LLM_TIMEOUT=nan', 'LLM_JSON_MODE=maybe', 'LLM_API_KEY="never-print'):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(VerificationError) as raised:
                    load_settings(path)
                self.assertNotIn("never-print", str(raised.exception))

    def test_public_url_cannot_contain_credentials(self):
        with self.assertRaises(VerificationError):
            Settings(base_url="https://name:key@example.com").validate()

    def test_api_default_and_retry_bounds(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / ".env"
            path.write_text("LLM_THINKING=api-default\n", encoding="utf-8")
            self.assertIsNone(load_settings(path).thinking)
            with self.assertRaises(VerificationError):
                load_settings(path, repair_attempts=99)


if __name__ == "__main__":
    unittest.main()
