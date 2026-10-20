"""Local HTTP server: python -m grounding.server --backend optimized."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from grounding.config import load_settings
from grounding.contracts import VerificationError, VerificationRequest, strict_json_loads, validate_report
from grounding.factory import BACKENDS, build_verifier


LOGGER = logging.getLogger("grounding.server")
MAX_BODY_BYTES = 1_048_576
READ_TIMEOUT = 15


class VerificationServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, verifier, *, backend: str = "optimized", max_concurrent: int = 4):
        self.verifier = verifier
        self.backend = backend
        self.slots = threading.BoundedSemaphore(max_concurrent)
        super().__init__(address, VerificationHandler)


class VerificationHandler(BaseHTTPRequestHandler):
    server: VerificationServer
    protocol_version = "HTTP/1.0"
    server_version = "GroundingVerifier/1.0"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(READ_TIMEOUT)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Log status, not request bodies, URLs, keys or model responses.
        pass

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.send_json(code, {"error": {"code": "http_error", "message": message or "Invalid HTTP request."}})

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "backend": self.server.backend})
        elif self.path == "/verify":
            self.send_json(405, {"error": {"code": "method_not_allowed", "message": "Use POST /verify."}})
        else:
            self.send_json(404, {"error": {"code": "not_found", "message": "Unknown route."}})

    def do_POST(self) -> None:
        if self.path != "/verify":
            self.send_json(404, {"error": {"code": "not_found", "message": "Unknown route."}})
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise VerificationError("invalid_request", "Chunked request bodies are not supported.", 400)
            if self.headers.get_content_type() != "application/json":
                raise VerificationError("unsupported_media_type", "Use Content-Type: application/json.", 415)
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                raise VerificationError("invalid_request", "Exactly one Content-Length header is required.", 411)
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise VerificationError("invalid_request", "Invalid Content-Length.", 400) from exc
            if length < 0:
                raise VerificationError("invalid_request", "Invalid Content-Length.", 400)
            if length > MAX_BODY_BYTES:
                raise VerificationError("input_too_large", "JSON body exceeds 1 MiB.", 413)
            body = self.rfile.read(length)
            if len(body) != length:
                raise VerificationError("invalid_request", "Request body was truncated.", 400)
            try:
                payload = strict_json_loads(body.decode("utf-8"))
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise VerificationError("invalid_json", "Expected a valid UTF-8 JSON object.", 400) from exc
            request = VerificationRequest.from_dict(payload)
            if not self.server.slots.acquire(blocking=False):
                raise VerificationError("server_busy", "Too many concurrent verification requests.", 503)
            try:
                result = self.server.verifier.verify(request)
                validate_report(result.report, request.context_passages)
            finally:
                self.server.slots.release()
            self.send_json(200, result.report)
        except VerificationError as exc:
            self.send_json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        except (socket.timeout, TimeoutError):
            self.send_json(408, {"error": {"code": "request_timeout", "message": "Timed out reading the request."}})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            LOGGER.error("Unexpected verification failure.")
            self.send_json(500, {"error": {"code": "internal_error", "message": "Verification failed."}})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--backend", choices=BACKENDS, default="optimized")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-concurrent", type=int, default=4)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or not 1 <= args.max_concurrent <= 32:
        parser.error("Invalid port or concurrency limit.")
    try:
        settings = load_settings(args.env_file)
        verifier = build_verifier(args.backend, settings)
    except VerificationError as exc:
        parser.error(exc.message)
    with VerificationServer((args.host, args.port), verifier, backend=args.backend, max_concurrent=args.max_concurrent) as server:
        print(f"Serving {args.backend} at http://{args.host}:{server.server_port}/verify", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
