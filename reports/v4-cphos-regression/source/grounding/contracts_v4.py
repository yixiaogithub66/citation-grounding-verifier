"""Additive partial-result contract, without changing the historical validator."""

from typing import Any
from grounding.contracts import VerificationError, validate_report

def validate_v4_report(report: Any, contexts: list[str]) -> None:
    if not isinstance(report, dict):
        raise VerificationError("invalid_model_output", "Expected a verification report object.")
    if set(report) == {"claims"}:
        validate_report(report, contexts)
        return
    if set(report) != {"claims", "status", "errors"} or report["status"] != "partial":
        raise VerificationError("invalid_model_output", "Extended report needs claims, status:partial and errors.")
    validate_report({"claims": report["claims"]}, contexts)
    if not report["claims"] or not isinstance(report["errors"], list) or not report["errors"]:
        raise VerificationError("invalid_model_output", "Partial reports require both completed claims and errors.")
    seen = set()
    for error in report["errors"]:
        if (not isinstance(error, dict) or not {"id", "code", "message"} <= set(error)
                or set(error) - {"id", "code", "message", "claim_text", "stage"}
                or any(not isinstance(error[key], str) or not error[key].strip() for key in error)
                or error["id"] in seen):
            raise VerificationError("invalid_model_output", "Each unfinished claim needs a unique id and nonempty error reason.")
        seen.add(error["id"])

def validate_endpoint_report(report: Any, contexts: list[str]) -> None:
    """Dispatch only the explicit partial extension; legacy complete validation is unchanged."""
    validate_v4_report(report, contexts)
