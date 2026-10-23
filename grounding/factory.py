"""Construct the same verifier implementation used by HTTP and benchmark."""

import hashlib
import json
from pathlib import Path

from grounding.config import Settings
from grounding.contracts import VerificationError


# Historical confirmation scripts bind this four-way order. New evaluation
# protocols select v4 explicitly instead of retroactively changing that manifest.
CANONICAL_BACKENDS = ("baseline", "minimal", "optimized-v2", "optimized-v3")
BACKENDS = (*CANONICAL_BACKENDS, "optimized-v4.0", "optimized-v4-combined", "optimized-v4-m1-faithful", "optimized", "optimized-v4")
DEFAULT_BACKENDS = ("baseline", "minimal", "optimized-v3")
FROZEN_V2_COMMIT = "cfadeca69f907aa91eaa4f825b78f02ac5da0e92"
FROZEN_V2_FILES = {
    "grounding/prompts.py", "grounding/verifiers.py", "grounding/client.py",
    "grounding/contracts.py", "grounding/config.py", "scripts/validate_dataset.py",
}


def normalize_backend(name: str) -> str:
    if name not in BACKENDS:
        raise VerificationError("configuration_error", f"Unknown backend: {name}", 503)
    if name == "optimized-v4":
        return "optimized-v4.0"
    return "optimized-v3" if name == "optimized" else name


def frozen_v2_provenance(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[1]
    path = root / "grounding" / "frozen_v2.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        expected = manifest["files"]
        if (
            manifest.get("schema_version") != "1.0"
            or manifest.get("origin_commit") != FROZEN_V2_COMMIT
            or manifest.get("hash_method") != "sha256-raw-bytes"
            or not isinstance(expected, dict) or set(expected) != FROZEN_V2_FILES
        ):
            raise ValueError("Invalid frozen-v2 manifest")
        actual = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in sorted(expected)
        }
        mismatches = [name for name in sorted(expected) if actual[name] != expected[name]]
        return {
            "verified": not mismatches,
            "origin_commit": FROZEN_V2_COMMIT,
            "scope": manifest.get("scope"),
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected_files_sha256": expected,
            "actual_files_sha256": actual,
            "mismatched_files": mismatches,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "verified": False, "origin_commit": FROZEN_V2_COMMIT,
            "error": "Frozen-v2 manifest or its reference files are missing or invalid.",
        }


def build_verifier(name: str, settings: Settings, *, v4_config=None):
    name = normalize_backend(name)
    if name == "baseline":
        from grounding.baseline import BaselineVerifier
        return BaselineVerifier(settings)
    if not settings.api_key:
        raise VerificationError("configuration_error", "Set LLM_API_KEY in the environment or project .env.", 503)
    if name == "optimized-v4.0":
        from grounding.verifiers_v4 import OptimizedV4Verifier
        return OptimizedV4Verifier(settings, config=v4_config)
    if name == "optimized-v4-combined":
        from grounding.verifiers_combined import OptimizedV4CombinedVerifier
        return OptimizedV4CombinedVerifier(settings, config=v4_config)
    if name == "optimized-v4-m1-faithful":
        from grounding.verifiers_m1_faithful import OptimizedV4M1FaithfulVerifier
        return OptimizedV4M1FaithfulVerifier(settings, config=v4_config)
    if name == "optimized-v2" and not frozen_v2_provenance()["verified"]:
        raise VerificationError("configuration_error", "Frozen optimized-v2 inference files do not match the recorded commit.", 503)
    if name == "optimized-v3":
        from grounding.verifiers_v3 import OptimizedV3Verifier
        return OptimizedV3Verifier(settings)
    from grounding.verifiers import MinimalVerifier, OptimizedVerifier
    return {"minimal": MinimalVerifier, "optimized-v2": OptimizedVerifier}[name](settings)
