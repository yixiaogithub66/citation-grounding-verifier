"""Version aliases and frozen-v2 checks work without Git history or a network."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from grounding.config import Settings
from grounding.contracts import VerificationError
from grounding import factory


class BackendVersionTests(unittest.TestCase):
    def test_optimized_alias_selects_v3(self) -> None:
        self.assertEqual(factory.normalize_backend("optimized"), "optimized-v3")
        implementation = Mock()
        with patch.dict("sys.modules", {"grounding.verifiers_v3": Mock(OptimizedV3Verifier=implementation)}):
            result = factory.build_verifier("optimized", Settings(api_key="test-key"))
        self.assertIs(result, implementation.return_value)
        implementation.assert_called_once()

    def test_v2_uses_frozen_original_class(self) -> None:
        from grounding.verifiers import OptimizedVerifier
        self.assertIsInstance(factory.build_verifier("optimized-v2", Settings(api_key="test-key")), OptimizedVerifier)

    def test_frozen_manifest_matches_actual_files(self) -> None:
        result = factory.frozen_v2_provenance()
        self.assertTrue(result["verified"])
        self.assertEqual(result["origin_commit"], factory.FROZEN_V2_COMMIT)
        self.assertEqual(set(result["actual_files_sha256"]), factory.FROZEN_V2_FILES)

    def test_tampered_frozen_file_is_detected_without_git(self) -> None:
        project = Path(factory.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in [*factory.FROZEN_V2_FILES, "grounding/frozen_v2.json"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project / name, target)
            self.assertTrue(factory.frozen_v2_provenance(root)["verified"])
            (root / "grounding" / "prompts.py").write_text("changed\n", encoding="utf-8")
            result = factory.frozen_v2_provenance(root)
            self.assertFalse(result["verified"])
            self.assertEqual(result["mismatched_files"], ["grounding/prompts.py"])

    def test_v2_execution_fails_closed_if_reference_mismatches(self) -> None:
        with patch.object(factory, "frozen_v2_provenance", return_value={"verified": False}):
            with self.assertRaisesRegex(VerificationError, "do not match"):
                factory.build_verifier("optimized-v2", Settings(api_key="test-key"))


if __name__ == "__main__":
    unittest.main()
