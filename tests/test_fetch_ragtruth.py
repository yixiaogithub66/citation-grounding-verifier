import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_ragtruth import fetch_snapshot, verify_bytes


class FetchRagtruthTests(unittest.TestCase):
    def test_corrupt_download_is_not_saved(self):
        expected = b"expected"
        blob = hashlib.sha1(b"blob 8\0" + expected).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("scripts.fetch_ragtruth.FILES", {"response.jsonl": ("dataset/response.jsonl", blob, None)}):
                with patch("scripts.fetch_ragtruth.urlopen", return_value=io.BytesIO(b"corrupt")):
                    with self.assertRaises(ValueError):
                        fetch_snapshot(root)
            self.assertFalse((root / "response.jsonl").exists())
            self.assertFalse((root / "provenance.json").exists())

    def test_both_hashes_are_enforced(self):
        data = b"x"
        blob = hashlib.sha1(b"blob 1\0x").hexdigest()
        with self.assertRaises(ValueError):
            verify_bytes(data, blob, "0" * 64)
        self.assertEqual(verify_bytes(data, blob, hashlib.sha256(data).hexdigest())["bytes"], 1)


if __name__ == "__main__":
    unittest.main()
