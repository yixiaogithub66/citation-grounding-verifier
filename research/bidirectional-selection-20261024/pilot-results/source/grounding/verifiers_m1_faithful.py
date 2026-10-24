"""Experimental answer-faithful extraction with the original v4 judgment path.

Only the decomposition system prompt changes. Extraction schema, chunking,
fallbacks, budgets, quotation handling, retries and reviews are inherited intact.
No dataset identity or evaluation information is accepted by this adapter.
"""

from grounding.contracts import VerificationError, VerificationRequest, VerificationResult
from grounding.prompts_m1_faithful import DECOMPOSE_PROMPT, prompt_metadata
from grounding.verifiers_v4 import OptimizedV4Verifier


class OptimizedV4M1FaithfulVerifier(OptimizedV4Verifier):
    def _format_stage(self, prompt, payload, stage, phase, validate, telemetry):
        if phase == "decompose":
            prompt = DECOMPOSE_PROMPT
        return super()._format_stage(prompt, payload, stage, phase, validate, telemetry)

    @staticmethod
    def _experiment_metadata(telemetry: dict) -> None:
        telemetry["backend"] = "optimized-v4-m1-faithful"
        telemetry["prompts"] = prompt_metadata()
        telemetry["experimental_intervention"] = {
            "scope": "decomposition system prompt only",
            "hypothesis": "Preserve assertions actually made by the answer, including their truth conditions, without inventing assertions or dropping embedded facts.",
            "control": "Original v4 extraction schema, runtime, stage configuration and judgment prompts.",
            "limitation": "A prompt instruction and exact text accounting do not certify semantic extraction precision or recall.",
        }

    def verify(self, request: VerificationRequest) -> VerificationResult:
        try:
            result = super().verify(request)
        except VerificationError as exc:
            self._experiment_metadata(exc.telemetry)
            raise
        self._experiment_metadata(result.telemetry)
        return result
