"""Construct the same verifier implementation used by HTTP and benchmark."""

from grounding.config import Settings
from grounding.contracts import VerificationError


BACKENDS = ("baseline", "minimal", "optimized")


def build_verifier(name: str, settings: Settings):
    if name == "baseline":
        from grounding.baseline import BaselineVerifier
        return BaselineVerifier(settings)
    if name not in BACKENDS:
        raise VerificationError("configuration_error", f"Unknown backend: {name}", 503)
    if not settings.api_key:
        raise VerificationError("configuration_error", "Set LLM_API_KEY in the environment or project .env.", 503)
    from grounding.verifiers import MinimalVerifier, OptimizedVerifier
    return {"minimal": MinimalVerifier, "optimized": OptimizedVerifier}[name](settings)
