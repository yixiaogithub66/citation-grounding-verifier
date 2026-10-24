"""Regression checks for stage boundaries, bounded repair and upstream failures."""

from __future__ import annotations

import io
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from grounding.client import ChatClient
from grounding.config import Settings
from grounding.contracts import VerificationError, VerificationRequest
from grounding.verifiers import MinimalVerifier, OptimizedVerifier


class FakeClient:
    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.inputs: list[dict] = []

    def complete(self, messages: list, stage: str, telemetry: dict) -> dict:
        self.inputs.append({"messages": list(messages), "stage": stage})
        output = self.outputs.pop(0)
        telemetry["calls"].append({
            "stage": stage, "attempt": 1, "response_text": None,
            "latency_seconds": 0.01, "http_status": 200, "usage": None,
            "finish_reason": "stop",
        })
        if isinstance(output, Exception):
            raise output
        telemetry["calls"][-1]["response_text"] = json.dumps(output)
        return output


class StubResponse(io.BytesIO):
    status = 200


def extraction(text: str = "The speed is 2 m/s.") -> dict:
    return {"claims": [{"claim_text": text, "source_span": text}], "non_factual_spans": []}


def verdict(*, quote: str = "The speed is 2 m/s.", include_id: bool = True) -> dict:
    claim = {
        "claim_text": "The speed is 2 m/s.", "verdict": "SUPPORTED",
        "reasoning": "The passage explicitly gives the speed.", "citations": [{"index": 0, "quote": quote}],
    }
    if include_id:
        claim["id"] = "c1"
    return {"claims": [claim]}


def completion(content: str, **extra: object) -> StubResponse:
    payload = {
        "choices": [{"message": {"content": content, "reasoning_content": "PRIVATE_REASONING"}, "finish_reason": "stop"}],
        "model": "actual-model", "system_fingerprint": "fingerprint",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 3},
        **extra,
    }
    return StubResponse(json.dumps(payload).encode("utf-8"))


class VerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(base_url="http://example.test/v1", model="test", api_key="secret")
        self.request = VerificationRequest(["The speed is 2 m/s."], "The speed is 2 m/s.")

    def test_minimal_is_one_call_and_no_repair(self) -> None:
        client = FakeClient([verdict(quote="invented text", include_id=False)])
        with self.assertRaises(VerificationError) as raised:
            MinimalVerifier(self.settings, client).verify(self.request)
        self.assertEqual(len(client.inputs), 1)
        self.assertEqual(raised.exception.code, "invalid_model_output")
        self.assertEqual(raised.exception.telemetry["backend"], "minimal")

    def test_minimal_valid_report_preserved(self) -> None:
        expected = verdict(include_id=False)
        result = MinimalVerifier(self.settings, FakeClient([expected])).verify(self.request)
        self.assertEqual(result.report, expected)
        self.assertIn("minimal_sha256", result.telemetry["prompts"])

    def test_literal_empty_answer_shortcuts_both_systems(self) -> None:
        for cls in (MinimalVerifier, OptimizedVerifier):
            with self.subTest(cls=cls.__name__):
                client = FakeClient([])
                result = cls(self.settings, client).verify(VerificationRequest(["A fact."], " \n"))
                self.assertEqual(result.report, {"claims": []})
                self.assertEqual(client.inputs, [])

    def test_semantic_no_facts_requires_extraction(self) -> None:
        client = FakeClient([{
            "claims": [], "non_factual_spans": [{"text": "Thank you!", "reason": "Greeting."}],
        }])
        result = OptimizedVerifier(self.settings, client).verify(VerificationRequest([], "Thank you!"))
        self.assertEqual(result.report, {"claims": []})
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose"])
        self.assertEqual(result.telemetry["extraction"]["non_factual_spans"][0]["text"], "Thank you!")

    def test_empty_context_returns_extracted_facts_as_unsupported(self) -> None:
        client = FakeClient([extraction()])
        result = OptimizedVerifier(self.settings, client).verify(
            VerificationRequest([" \n"], self.request.generated_answer),
        )
        self.assertEqual(result.report["claims"][0]["verdict"], "UNSUPPORTED")
        self.assertEqual(result.report["claims"][0]["citations"], [])
        self.assertEqual(len(client.inputs), 1)

    def test_extraction_never_receives_context_or_gold(self) -> None:
        client = FakeClient([extraction(), verdict()])
        result = OptimizedVerifier(self.settings, client).verify(self.request)
        extraction_input = json.loads(client.inputs[0]["messages"][1]["content"])
        self.assertEqual(set(extraction_input), {"generated_answer", "max_claims"})
        verification_input = json.loads(client.inputs[1]["messages"][1]["content"])
        self.assertEqual(verification_input["context_passages"], [{"index": 0, "text": self.request.context_passages[0]}])
        self.assertEqual(verification_input["claims"][0]["id"], "c1")
        self.assertNotIn("id", result.report["claims"][0])
        self.assertNotIn("source_span", result.report["claims"][0])
        self.assertEqual(result.telemetry["extraction"]["claims"][0]["source_span"], self.request.generated_answer)

    def test_invalid_quote_is_repaired_once_with_validation_feedback(self) -> None:
        client = FakeClient([extraction(), verdict(quote="The speed is 3 m/s."), verdict()])
        result = OptimizedVerifier(self.settings, client).verify(self.request)
        self.assertEqual(result.report["claims"][0]["verdict"], "SUPPORTED")
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "verify", "verify_repair_1"])
        self.assertIn("exact substring", client.inputs[-1]["messages"][-1]["content"])
        self.assertEqual(len(result.telemetry["repairs"]), 1)

    def test_failed_repair_is_error_never_unsupported(self) -> None:
        client = FakeClient([extraction(), verdict(quote="missing"), verdict(quote="missing again")])
        with self.assertRaises(VerificationError) as raised:
            OptimizedVerifier(self.settings, client).verify(self.request)
        self.assertEqual(len(client.inputs), 3)
        self.assertEqual(raised.exception.code, "invalid_model_output")
        self.assertEqual(len(raised.exception.telemetry["repairs"]), 1)

    def test_invalid_json_error_can_be_repaired(self) -> None:
        client = FakeClient([
            VerificationError("invalid_model_output", "Completion is not strict JSON."),
            extraction(), verdict(),
        ])
        result = OptimizedVerifier(self.settings, client).verify(self.request)
        self.assertEqual([item["stage"] for item in client.inputs], ["decompose", "decompose_repair_1", "verify"])
        self.assertEqual(len(result.report["claims"]), 1)

    def test_upstream_error_is_not_a_format_repair(self) -> None:
        for code, status in (("upstream_timeout", 504), ("upstream_http_error", 503)):
            with self.subTest(code=code):
                client = FakeClient([VerificationError(code, "upstream unavailable", status)])
                with self.assertRaises(VerificationError) as raised:
                    OptimizedVerifier(self.settings, client).verify(self.request)
                self.assertEqual(len(client.inputs), 1)
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(raised.exception.telemetry["repairs"], [])

    def test_omitted_answer_text_triggers_extraction_repair(self) -> None:
        answer = "The speed is 2 m/s. The mass is 3 kg."
        second = {"claim_text": "The mass is 3 kg.", "source_span": "The mass is 3 kg."}
        full = extraction()
        full["claims"].append(second)
        client = FakeClient([extraction(), full])
        result = OptimizedVerifier(self.settings, client).verify(VerificationRequest([], answer))
        self.assertEqual(len(result.report["claims"]), 2)
        self.assertIn("unaccounted", client.inputs[-1]["messages"][-1]["content"])

    def test_fabricated_source_span_rejected(self) -> None:
        wrong = extraction("The speed is 3 m/s.")
        client = FakeClient([wrong, wrong])
        with self.assertRaisesRegex(VerificationError, "exact substring"):
            OptimizedVerifier(self.settings, client).verify(self.request)

    def test_claim_text_or_ids_cannot_change_during_verification(self) -> None:
        for field, replacement in (("id", "c2"), ("claim_text", "The speed is about 2 m/s.")):
            with self.subTest(field=field):
                bad = verdict()
                bad["claims"][0][field] = replacement
                client = FakeClient([extraction(), bad, bad])
                with self.assertRaisesRegex(VerificationError, "preserve"):
                    OptimizedVerifier(self.settings, client).verify(self.request)

    def test_a_claim_cannot_be_removed_to_repair_a_quote(self) -> None:
        client = FakeClient([extraction(), verdict(quote="missing"), {"claims": []}])
        with self.assertRaisesRegex(VerificationError, "exactly one result"):
            OptimizedVerifier(self.settings, client).verify(self.request)


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(base_url="http://example.test/v1", model="test", api_key="secret")
        self.messages = [{"role": "user", "content": "Return JSON."}]

    def test_usage_final_text_and_model_are_logged_but_not_reasoning_or_key(self) -> None:
        telemetry: dict = {"calls": []}
        with patch("grounding.client.urlopen", return_value=completion('{"claims":[]}')) as mocked:
            result = ChatClient(self.settings).complete(self.messages, "verify", telemetry)
        self.assertEqual(result, {"claims": []})
        trace = telemetry["calls"][0]
        self.assertEqual(trace["model"], "actual-model")
        self.assertEqual(trace["usage"]["prompt_cache_hit_tokens"], 3)
        self.assertNotIn("PRIVATE_REASONING", json.dumps(telemetry))
        self.assertNotIn("secret", json.dumps(telemetry))
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_invalid_json_variants_are_not_retried_by_transport(self) -> None:
        for content in (
            "not JSON", '{"claims":[],"claims":[]}', '{"x":1e999}', r'{"x":"\ud800"}', "[]",
        ):
            with self.subTest(content=content):
                telemetry: dict = {"calls": []}
                with patch("grounding.client.urlopen", return_value=completion(content)) as mocked:
                    with self.assertRaises(VerificationError) as raised:
                        ChatClient(self.settings).complete(self.messages, "verify", telemetry)
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(raised.exception.code, "invalid_model_output")
                self.assertEqual(telemetry["calls"][0]["error"]["code"], "invalid_model_output")

    def test_recursion_errors_from_envelope_and_content_are_invalid_outputs(self) -> None:
        envelope = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        for parsed in ([RecursionError("nested envelope")], [envelope, RecursionError("nested content")]):
            with self.subTest(stage="envelope" if len(parsed) == 1 else "content"):
                with (
                    patch("grounding.client.urlopen", return_value=StubResponse(b"{}")),
                    patch("grounding.client.strict_json_loads", side_effect=parsed),
                ):
                    with self.assertRaises(VerificationError) as raised:
                        ChatClient(self.settings).complete(self.messages, "verify", {"calls": []})
                self.assertEqual(raised.exception.code, "invalid_model_output")

    def test_truncated_completion_is_not_accepted_as_valid_json(self) -> None:
        response = completion('{"claims":[]}', choices=[{
            "message": {"content": '{"claims":[]}'}, "finish_reason": "length",
        }])
        with patch("grounding.client.urlopen", return_value=response):
            with self.assertRaisesRegex(VerificationError, "finish normally"):
                ChatClient(self.settings).complete(self.messages, "verify", {"calls": []})

    def test_echoed_credentials_are_redacted_in_errors_trace_values_and_keys(self) -> None:
        token = "fake-test-credential-123456"
        settings = Settings(base_url="http://example.test/v1", api_key=token)
        responses = [
            completion('{"' + token + '":0,"' + token + '":1}'),
            completion('{"claims":[]}', model=token, usage={token: {token: token}},
                       choices=[{"message": {"content": '{"claims":[]}'}, "finish_reason": token}]),
            completion(json.dumps({"answer": token})),
        ]
        for response in responses:
            with self.subTest(response=response):
                telemetry: dict = {"calls": []}
                with patch("grounding.client.urlopen", return_value=response):
                    with self.assertRaises(VerificationError) as raised:
                        ChatClient(settings).complete(self.messages, "verify", telemetry)
                self.assertNotIn(token, str(raised.exception))
                self.assertNotIn(token, raised.exception.message)
                self.assertNotIn(token, json.dumps(raised.exception.telemetry))
                self.assertNotIn(token, json.dumps(telemetry))
                self.assertIn("[REDACTED]", json.dumps(telemetry))

    def test_429_retries_once_with_capped_retry_after(self) -> None:
        error = HTTPError("http://example.test", 429, "Rate limited", {"Retry-After": "999"}, io.BytesIO())
        telemetry: dict = {"calls": []}
        with (
            patch("grounding.client.urlopen", side_effect=[error, completion('{"claims":[]}')]) as mocked,
            patch("grounding.client.time.sleep") as sleep,
        ):
            ChatClient(self.settings).complete(self.messages, "verify", telemetry)
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once_with(2.0)
        self.assertEqual([call["http_status"] for call in telemetry["calls"]], [429, 200])

    def test_permanent_http_error_does_not_retry_or_log_body(self) -> None:
        error = HTTPError("http://example.test", 401, "Unauthorized", {}, io.BytesIO(b"secret API key"))
        telemetry: dict = {"calls": []}
        with patch("grounding.client.urlopen", side_effect=error) as mocked:
            with self.assertRaises(VerificationError):
                ChatClient(self.settings).complete(self.messages, "verify", telemetry)
        self.assertEqual(mocked.call_count, 1)
        self.assertNotIn("secret", json.dumps(telemetry))

    def test_timeout_retries_are_bounded_and_preserve_status(self) -> None:
        for error in (socket.timeout(), URLError(socket.timeout())):
            with self.subTest(error=type(error).__name__):
                telemetry: dict = {"calls": []}
                with (
                    patch("grounding.client.urlopen", side_effect=error) as mocked,
                    patch("grounding.client.time.sleep"),
                ):
                    with self.assertRaises(VerificationError) as raised:
                        ChatClient(self.settings).complete(self.messages, "verify", telemetry)
                self.assertEqual(mocked.call_count, 2)
                self.assertEqual(raised.exception.status, 504)
                self.assertEqual(len(telemetry["calls"]), 2)

    def test_minimal_transport_disables_even_configured_retries(self) -> None:
        request = VerificationRequest([], "The mass is 3 kg.")
        with patch("grounding.client.urlopen", side_effect=socket.timeout()) as mocked:
            with self.assertRaises(VerificationError):
                MinimalVerifier(self.settings).verify(request)
        self.assertEqual(mocked.call_count, 1)

    def test_http_redirect_never_forwards_authorization_to_another_origin(self) -> None:
        received: list[tuple[str, str | None]] = []

        class Destination(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(("destination", self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_GET

            def log_message(self, *args) -> None:
                pass

        destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                # Drain the real POST before closing this HTTP/1.0 fixture.
                # Closing with unread request data can reset the Windows
                # connection before the client observes the redirect response.
                self.rfile.read(int(self.headers["Content-Length"]))
                received.append(("configured-origin", self.headers.get("Authorization")))
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/leak")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        servers = [destination, redirect]
        threads = [
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            for server in servers
        ]
        for thread in threads:
            thread.start()
        try:
            settings = Settings(
                base_url=f"http://127.0.0.1:{redirect.server_port}", model="test",
                # Keep this a single redirect attempt, not a transport-retry
                # test; Windows localhost startup can exceed two seconds under
                # the full concurrent test workload.
                api_key="fake-test-only-token", timeout=5, upstream_retries=0,
            )
            telemetry: dict = {"calls": []}
            with self.assertRaises(VerificationError) as raised:
                ChatClient(settings).complete(self.messages, "verify", telemetry)
            self.assertEqual(raised.exception.code, "upstream_http_error")
            self.assertEqual(telemetry["calls"][0]["http_status"], 302)
            self.assertEqual(len(telemetry["calls"]), 1)
            self.assertEqual(received, [("configured-origin", "Bearer fake-test-only-token")])
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
