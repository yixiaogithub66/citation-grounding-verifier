"""Bounded standard-library Chat Completions client with sanitized telemetry."""

from __future__ import annotations

import json
import socket
import time
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from grounding.config import Settings
from grounding.contracts import VerificationError, strict_json_loads


MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected API request must never forward its Bearer token elsewhere.
        return None


def urlopen(request: Request, *, timeout: float):
    """Keep a single injectable transport boundary while rejecting every redirect."""
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _redact(value: Any, secret: str) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        return {_redact(key, secret): _redact(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    return value


class ChatClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings.validate()

    def complete(
        self, messages: list[dict[str, str]], stage: str, telemetry: dict[str, Any],
    ) -> dict[str, Any]:
        settings = self.settings
        body: dict[str, Any] = {
            "model": settings.model, "messages": messages,
            "max_tokens": settings.max_output_tokens,
        }
        if settings.json_mode:
            body["response_format"] = {"type": "json_object"}
        if settings.temperature is not None:
            body["temperature"] = settings.temperature
        if settings.thinking is not None:
            body["thinking"] = {"type": settings.thinking}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if settings.api_key:
            headers["Authorization"] = "Bearer " + settings.api_key
        request = Request(
            settings.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        attempts = 1 + settings.upstream_retries
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            trace: dict[str, Any] = {
                "stage": stage, "attempt": attempt, "latency_seconds": 0.0,
                "http_status": None, "usage": None, "finish_reason": None,
                "response_text": None, "model": None, "system_fingerprint": None,
            }
            telemetry.setdefault("calls", []).append(trace)
            retryable = False
            retry_delay = min(0.25 * 2 ** (attempt - 1), 2.0)
            try:
                with urlopen(request, timeout=settings.timeout) as response:
                    trace["http_status"] = response.status
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise VerificationError("invalid_model_output", "Upstream response exceeds 8 MiB.")
                try:
                    envelope = strict_json_loads(raw.decode("utf-8"))
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise VerificationError("invalid_model_output", "Upstream returned invalid JSON.") from exc
                if not isinstance(envelope, dict):
                    raise VerificationError("invalid_model_output", "Upstream response must be an object.")
                trace["usage"] = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else None
                for name in ("model", "system_fingerprint"):
                    value = envelope.get(name)
                    trace[name] = value if isinstance(value, str) else None
                choices = envelope.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise VerificationError("invalid_model_output", "Upstream response has no completion choice.")
                choice = choices[0]
                trace["finish_reason"] = choice.get("finish_reason")
                message = choice.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                # Never retain provider reasoning_content or the raw response envelope.
                trace["response_text"] = content if isinstance(content, str) else None
                if trace["finish_reason"] != "stop":
                    raise VerificationError(
                        "invalid_model_output", "Completion did not finish normally.",
                    )
                if not isinstance(content, str) or not content.strip():
                    raise VerificationError("invalid_model_output", "Completion has no final text.")
                try:
                    parsed = strict_json_loads(content)
                except (ValueError, RecursionError) as exc:
                    raise VerificationError("invalid_model_output", "Completion is not strict JSON.") from exc
                if not isinstance(parsed, dict):
                    raise VerificationError("invalid_model_output", "Completion JSON must be an object.")
                if _redact(parsed, settings.api_key) != parsed:
                    raise VerificationError("invalid_model_output", "Completion contains configured credentials.")
                return parsed
            except HTTPError as exc:
                trace["http_status"] = exc.code
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if exc.headers:
                    try:
                        retry_delay = max(0.0, min(float(exc.headers.get("Retry-After", retry_delay)), 2.0))
                    except (ValueError, TypeError):
                        pass
                exc.close()
                failure = VerificationError(
                    "upstream_http_error", f"Upstream API returned HTTP {exc.code}.",
                    503 if exc.code == 429 else 502, telemetry,
                )
            except (TimeoutError, socket.timeout) as exc:
                retryable = True
                failure = VerificationError("upstream_timeout", "Upstream API timed out.", 504, telemetry)
            except URLError as exc:
                retryable = True
                timeout = isinstance(exc.reason, (TimeoutError, socket.timeout))
                failure = VerificationError(
                    "upstream_timeout" if timeout else "upstream_connection_error",
                    "Upstream API timed out." if timeout else "Could not connect to upstream API.",
                    504 if timeout else 502, telemetry,
                )
            except (HTTPException, OSError) as exc:
                retryable = True
                failure = VerificationError(
                    "upstream_connection_error", "Upstream response could not be read completely.", 502, telemetry,
                )
            except VerificationError as exc:
                failure = exc
                failure.telemetry = telemetry
            finally:
                trace["latency_seconds"] = time.monotonic() - started
                if settings.api_key:
                    sanitized = _redact(trace, settings.api_key)
                    trace.clear()
                    trace.update(sanitized)
            trace["error"] = {"code": failure.code, "message": failure.message}
            if not retryable or attempt == attempts:
                raise failure
            time.sleep(retry_delay)
        raise AssertionError("Unreachable retry state")
