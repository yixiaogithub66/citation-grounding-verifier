#!/usr/bin/env python3
"""Frozen component experiment. No scoring, adaptive sampling, or model retries.

Initial responses are saved before their production-triggered review is entered.
A reserved request without its result is UNKNOWN and is never re-issued, even
with --resume. All model-facing inputs are made from a strict request whitelist.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.client import ChatClient, _redact
from grounding.config import Settings, load_settings
from grounding.contracts import VerificationError, VerificationRequest, strict_json_loads
from grounding.verifiers_v4 import _local_telemetry

SCHEMA = "stage-attribution-pilot-v1"
M1_ARMS = ("concise", "current")
M3_ARMS = ("simple", "current")
CASE_COUNT = 20
FACTUAL_CASE_COUNT = 15
CLAIM_COUNT = 45
REPETITIONS = 2
MAX_REVIEW_CALLS_PER_CLAIM = 6  # C + U, format retry each, one shared targeted requery.
IO_DELAYS = (0.05, 0.10, 0.20, 0.40)
_protocol = None


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       indent=2) + "\n").encode("utf-8", errors="backslashreplace")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def read_json(path):
    return strict_json_loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_error(exc):
    if isinstance(exc, VerificationError):
        return {"code": exc.code, "message": exc.message}
    return {"code": type(exc).__name__, "message": str(exc)}


def bounded_io(operation):
    """Bounded filesystem retries only; never wrap a provider request."""
    for attempt in range(len(IO_DELAYS) + 1):
        try:
            return operation()
        except OSError as exc:
            retryable = (isinstance(exc, PermissionError) or
                         exc.errno in (errno.EACCES, errno.EAGAIN, errno.EBUSY) or
                         getattr(exc, "winerror", None) in (32, 33))
            if not retryable or attempt == len(IO_DELAYS):
                raise
            time.sleep(IO_DELAYS[attempt])


def write_new(path, value):
    """Publish a fully fsynced file atomically without overwriting any record."""
    path = Path(path)
    raw = encoded(value)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with bounded_io(lambda: temp.open("xb")) as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Incomplete durable write")
            bounded_io(stream.flush)
            bounded_io(lambda: os.fsync(stream.fileno()))
        # A same-directory hard link atomically fails if the destination exists.
        bounded_io(lambda: os.link(temp, path))
        if bounded_io(path.read_bytes) != raw:
            raise OSError("Durable checkpoint readback differs")
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def write_view(path, value):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        write_new(temp, value)
        bounded_io(lambda: os.replace(temp, path))
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def protocol():
    global _protocol
    if _protocol is None:
        spec = importlib.util.spec_from_file_location("stage_attribution_protocol", HERE / "protocol.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _protocol = module
    return _protocol


def pilot_settings(env_file):
    return load_settings(env_file, model="deepseek-flash", thinking="disabled",
                         max_output_tokens=8192, json_mode=True,
                         upstream_retries=0, repair_attempts=0, max_claims=64)


def inference_cases(path):
    """Reject metadata rather than silently allowing annotations into inference."""
    value = read_json(path)
    if isinstance(value, dict) and set(value) == {"cases"}:
        value = value["cases"]
    if not isinstance(value, list) or len(value) != CASE_COUNT:
        raise ValueError("Exactly twenty request-only cases are required")
    cases, ids = [], set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"id", "generated_answer", "context_passages", "claims"}:
            raise ValueError("Cases may contain only id, generated_answer, context_passages, claims")
        if not isinstance(row["id"], str) or not row["id"].strip() or row["id"] in ids:
            raise ValueError("Missing or duplicate scheduling case id")
        ids.add(row["id"])
        request = VerificationRequest.from_dict({key: row[key] for key in ("generated_answer", "context_passages")})
        if not request.generated_answer.strip() or len(request.generated_answer) > 1200:
            raise ValueError("Every answer must fit the unchanged 1200-character single-chunk limit")
        if not isinstance(row["claims"], list) or len(row["claims"]) > 3:
            raise ValueError("Each fixed-claim batch must have at most three claims")
        claim_ids = set()
        claims = []
        for claim in row["claims"]:
            if not isinstance(claim, dict) or set(claim) != {"id", "claim_text"}:
                raise ValueError("Fixed claims may contain only id and claim_text")
            if any(not isinstance(claim[key], str) or not claim[key].strip() for key in ("id", "claim_text")):
                raise ValueError("Fixed claims require nonempty id and text")
            if claim["id"] in claim_ids:
                raise ValueError("Duplicate fixed claim id")
            claim_ids.add(claim["id"])
            claims.append(deepcopy(claim))
        cases.append({"id": row["id"], "generated_answer": request.generated_answer,
                      "context_passages": request.context_passages, "claims": claims})
    if sum(bool(row["claims"]) for row in cases) != FACTUAL_CASE_COUNT or sum(len(row["claims"]) for row in cases) != CLAIM_COUNT:
        raise ValueError("The frozen matrix requires fifteen three-claim cases and five no-claim cases")
    return cases


def identity(stage, case_id, arm, repetition, claim_id=None):
    value = {"stage": stage, "case_id": case_id, "arm": arm, "repetition": repetition}
    if claim_id is not None:
        value["claim_id"] = claim_id
    value["key"] = digest(encoded(value))
    return value


def checked_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ValueError("Protocol must return nonempty chat messages")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"} or message["role"] not in ("system", "user", "assistant"):
            raise ValueError("Unexpected model message shape")
        if not isinstance(message["content"], str) or not message["content"].strip():
            raise ValueError("Model message content must be nonempty text")
    return deepcopy(messages)


def plans(cases, seed, repetitions=REPETITIONS):
    if repetitions != REPETITIONS:
        raise ValueError("This preregistered pilot has exactly two repetitions")
    initial, reviews = [], []
    for case in cases:
        for repetition in range(repetitions):
            for arm in M1_ARMS:
                initial.append({**identity("m1", case["id"], arm, repetition),
                                "messages": checked_messages(protocol().make_m1_messages(arm, case["generated_answer"]))})
            if case["claims"]:
                for arm in M3_ARMS:
                    initial.append({**identity("m3", case["id"], arm, repetition),
                                    "messages": checked_messages(protocol().make_m3_messages(arm, deepcopy(case["context_passages"]), deepcopy(case["claims"])))})
                for claim in case["claims"]:
                    reviews.append({**identity("review", case["id"], "current", repetition, claim["id"]),
                                    "initial_key": identity("m3", case["id"], "current", repetition)["key"]})
    initial.sort(key=lambda task: digest((seed + "|" + task["key"]).encode()))
    for index, item in enumerate(initial):
        item["schedule_index"] = index
        item["messages_sha256"] = digest(encoded(item["messages"]))
    if len(initial) != 140 or len(reviews) != 90:
        raise ValueError("Unexpected frozen component matrix")
    return initial, reviews


def check_freeze(freeze_path, cases_path=None, settings=None, seed=None, repetitions=None, root=ROOT):
    root, freeze_path = Path(root).resolve(), Path(freeze_path)
    value = read_json(freeze_path)
    hashes = value.get("files", value.get("files_sha256"))
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("FROZEN.json requires nonempty files SHA256 mapping")
    for name, expected in hashes.items():
        if isinstance(expected, dict):
            expected = expected.get("sha256")
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not isinstance(expected, str) or sha(path) != expected:
            raise ValueError("Frozen source changed or escaped project root: " + str(name))
    if cases_path is not None:
        relative = Path(cases_path).resolve().relative_to(root).as_posix()
        if relative not in hashes:
            raise ValueError("Request-only cases must be hash-bound before provider access")
    if settings is not None and value.get("settings") != settings.public_dict():
        raise ValueError("Model settings differ from FROZEN.json")
    if seed is not None and value.get("seed") != seed:
        raise ValueError("Schedule seed differs from FROZEN.json")
    if repetitions is not None and value.get("repetitions") != repetitions:
        raise ValueError("Repetition count differs from FROZEN.json")
    return value


def check_imports(manifest):
    hashes = manifest.get("files", manifest.get("files_sha256"))
    files = [Path(__file__).resolve(), HERE / "protocol.py"]
    files.extend(Path(module.__file__).resolve() for name, module in list(sys.modules.items())
                 if (name in ("grounding", "scripts") or name.startswith(("grounding.", "scripts.")))
                 and getattr(module, "__file__", None))
    for path in files:
        if not path.is_relative_to(ROOT):
            raise ValueError("Imported source escaped project root")
        key = path.relative_to(ROOT).as_posix()
        expected = hashes.get(key)
        if isinstance(expected, dict):
            expected = expected.get("sha256")
        if expected != sha(path):
            raise ValueError("Inference dependency is not in the source freeze: " + key)


class DurabilityError(RuntimeError):
    pass


class Ledger:
    """Durable reservations are authority; progress.json is only a derived view."""
    def __init__(self, output, manifest, planned, *, resume=False, secret=""):
        self.output, self.secret = Path(output), secret
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.warnings = []
        if resume:
            if not self.output.is_dir() or read_json(self.output / "run-manifest.json") != manifest:
                raise ValueError("Resume requires the exact original run manifest")
            if read_json(self.output / "planned-requests.json") != planned:
                raise ValueError("Resume request matrix differs")
        else:
            self.output.mkdir(parents=True, exist_ok=False)
            write_new(self.output / "run-manifest.json", manifest)
            write_new(self.output / "planned-requests.json", planned)
            for directory in ("stage-reservations", "stage-results", "call-reservations", "call-results", "operations"):
                (self.output / directory).mkdir()
        self.operation("resume_started" if resume else "run_started", {})
        self.validate_existing(planned)

    def operation(self, kind, details):
        write_new(self.output / "operations" / (uuid.uuid4().hex + ".json"),
                  _redact({"at": now(), "kind": kind, "details": details}, self.secret))

    def path(self, directory, key):
        return self.output / directory / (key + ".json")

    def validate_existing(self, planned):
        allowed = {item["key"]: item for item in planned["initial"] + planned["reviews"]}
        for path in (self.output / "stage-reservations").glob("*.json"):
            value = read_json(path)
            if path.stem not in allowed or value["task"] != allowed[path.stem]:
                raise ValueError("Unplanned or altered stage reservation")
        for path in (self.output / "stage-results").glob("*.json"):
            if not self.path("stage-reservations", path.stem).exists():
                raise ValueError("Result without reservation")
            if read_json(path).get("key") != path.stem:
                raise ValueError("Changed stage-result identity")
        for path in (self.output / "call-reservations").glob("*.json"):
            value = read_json(path)
            if value.get("stage_key") not in allowed or value.get("key") != path.stem:
                raise ValueError("Unplanned call reservation")
            if not self.path("stage-reservations", value["stage_key"]).exists():
                raise ValueError("Provider call without stage reservation")
        for path in (self.output / "call-results").glob("*.json"):
            if not self.path("call-reservations", path.stem).exists() or read_json(path).get("key") != path.stem:
                raise ValueError("Invalid provider result identity")

    def disposition(self, task):
        if self.path("stage-results", task["key"]).exists():
            return "finished"
        if self.path("stage-reservations", task["key"]).exists():
            return "unknown"
        return "unreserved"

    def reserve(self, directory, key, value):
        with self.lock:
            if self.stop.is_set():
                raise DurabilityError("Dispatch stopped after a durability failure")
            try:
                write_new(self.path(directory, key), _redact(value, self.secret))
            except Exception as exc:
                self.stop.set()
                raise DurabilityError("Could not durably reserve; no provider call is permitted") from exc

    def result(self, directory, key, value):
        with self.lock:
            try:
                write_new(self.path(directory, key), _redact(value, self.secret))
            except Exception as exc:
                self.stop.set()
                raise DurabilityError("Provider result was not durably recorded; never resend") from exc

    def stage_result(self, task):
        return read_json(self.path("stage-results", task["key"]))

    def progress(self):
        with self.lock:
            stage_reserved = {p.stem for p in (self.output / "stage-reservations").glob("*.json")}
            stage_done = {p.stem for p in (self.output / "stage-results").glob("*.json")}
            call_reserved = {p.stem for p in (self.output / "call-reservations").glob("*.json")}
            call_done = {p.stem for p in (self.output / "call-results").glob("*.json")}
            value = {"at": now(), "stage_reservations": len(stage_reserved), "stage_results": len(stage_done),
                     "provider_reservations": len(call_reserved), "provider_results": len(call_done),
                     "unknown_stage_keys": sorted(stage_reserved - stage_done),
                     "unknown_provider_keys": sorted(call_reserved - call_done), "io_warnings": deepcopy(self.warnings)}
            try:
                write_view(self.output / "progress.json", value)
            except OSError as exc:
                self.warnings.append({"at": now(), "kind": "derived_progress_write", "error": safe_error(exc)})
            return value


class RecordingFactory:
    def __init__(self, ledger, task, max_calls, client_factory=ChatClient):
        self.ledger, self.task, self.max_calls = ledger, task, max_calls
        self.client_factory, self.count = client_factory, 0

    def __call__(self, settings):
        if settings.upstream_retries != 0:
            raise ValueError("Hidden transport retries are forbidden in this experiment")
        return RecordingClient(self, settings, self.client_factory(settings))


class RecordingClient:
    def __init__(self, owner, settings, client):
        self.owner, self.settings, self.client = owner, settings, client

    def complete(self, messages, stage, telemetry):
        owner = self.owner
        if owner.count >= owner.max_calls:
            raise ValueError("Frozen physical call ceiling exceeded")
        ordinal = owner.count
        owner.count += 1
        key = digest(encoded({"stage_key": owner.task["key"], "ordinal": ordinal}))
        request = {"key": key, "stage_key": owner.task["key"], "ordinal": ordinal,
                   "provider_stage": stage, "settings": self.settings.public_dict(),
                   "messages": checked_messages(messages), "reserved_at": now()}
        owner.ledger.reserve("call-reservations", key, request)
        first_trace = len(telemetry.setdefault("calls", []))
        started = time.monotonic()
        value, error = None, None
        try:
            value = self.client.complete(messages, stage, telemetry)
            return value
        except Exception as exc:
            error = safe_error(exc)
            raise
        finally:
            for trace in telemetry["calls"][first_trace:]:
                trace.update(thinking=self.settings.thinking, max_output_tokens=self.settings.max_output_tokens)
            traces = deepcopy(telemetry["calls"][first_trace:])
            record = {"key": key, "stage_key": owner.task["key"], "ordinal": ordinal,
                      "provider_stage": stage, "completed_at": now(), "latency_seconds": time.monotonic() - started,
                      "raw_output": deepcopy(value), "error": error, "calls": traces,
                      "provider_attempt_count": len(traces)}
            owner.ledger.result("call-results", key, record)
            if len(traces) != 1:
                owner.ledger.stop.set()
                raise DurabilityError("Exactly one trace is required per reserved provider invocation")


def initial_stage(task, case, settings, ledger, client_factory=ChatClient):
    state = ledger.disposition(task)
    if state != "unreserved":
        return ledger.stage_result(task) if state == "finished" else None
    ledger.reserve("stage-reservations", task["key"], {"task": task, "reserved_at": now()})
    telemetry = _local_telemetry()
    started = time.monotonic()
    record = {key: deepcopy(value) for key, value in task.items() if key != "messages"}
    record.update(started_at=now(), status="error", raw_output=None, validated_output=None, error=None, telemetry=telemetry)
    factory = RecordingFactory(ledger, task, 1, client_factory)
    try:
        raw = factory(settings).complete(task["messages"], task["stage"] + "_" + task["arm"], telemetry)
        record["raw_output"] = deepcopy(raw)
        if task["stage"] == "m1":
            record["validated_output"] = protocol().validate_m1(raw, case["generated_answer"])
            record["status"] = "valid"
        else:
            value = protocol().validate_m3(task["arm"], raw, deepcopy(case["claims"]), deepcopy(case["context_passages"]))
            record["validated_output"] = value
            record["status"] = "valid" if not value["errors"] else ("partial" if value["rows"] else "invalid")
    except DurabilityError:
        raise
    except Exception as exc:
        record["error"] = safe_error(exc)
        record["status"] = "invalid" if isinstance(exc, VerificationError) and exc.code == "invalid_model_output" else "error"
    record.update(completed_at=now(), latency_seconds=time.monotonic() - started, physical_calls=factory.count)
    ledger.result("stage-results", task["key"], record)
    ledger.progress()
    return record


def review_stage(task, case, settings, ledger, client_factory=ChatClient):
    state = ledger.disposition(task)
    if state != "unreserved":
        return ledger.stage_result(task) if state == "finished" else None
    initial_path = ledger.path("stage-results", task["initial_key"])
    if not initial_path.exists():
        return None  # An UNKNOWN initial call cannot be replaced or reviewed.
    initial = read_json(initial_path)  # Deliberately read the saved initial, never resample it.
    claim = next(row for row in case["claims"] if row["id"] == task["claim_id"])
    rows = (initial.get("validated_output") or {}).get("rows", {})
    before = rows.get(claim["id"])
    ledger.reserve("stage-reservations", task["key"], {"task": task, "reserved_at": now()})
    started = time.monotonic()
    record = {**deepcopy(task), "started_at": now(), "initial_result_sha256": sha(initial_path),
              "before": deepcopy(before), "after": None, "telemetry": _local_telemetry(),
              "status": "ineligible", "triggered": False, "error": None}
    factory = RecordingFactory(ledger, task, MAX_REVIEW_CALLS_PER_CLAIM, client_factory)
    if before is None:
        record["ineligible_reason"] = "Initial row did not meet the frozen eligibility validation"
    else:
        try:
            after, telemetry, error = protocol().review_existing(deepcopy(before), deepcopy(claim),
                deepcopy(case["context_passages"]), settings, client_factory=factory)
            record.update(after=after, telemetry=telemetry, error=error,
                          status="valid" if after is not None and error is None else "error")
        except DurabilityError:
            raise
        except Exception as exc:
            record.update(status="error", error=safe_error(exc))
        record["triggered"] = bool(record["telemetry"].get("contradiction_reviews") or
                                    record["telemetry"].get("unsupported_reviews") or factory.count)
    record.update(completed_at=now(), latency_seconds=time.monotonic() - started, physical_calls=factory.count)
    ledger.result("stage-results", task["key"], record)
    ledger.progress()
    return record


def run(cases_path, output, settings, *, freeze_path=HERE / "FROZEN.json", workers=4,
        repetitions=REPETITIONS, seed, resume=False, client_factory=ChatClient):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("Concurrency must be within [1, 4]")
    if (settings.thinking, settings.max_output_tokens, settings.upstream_retries, settings.repair_attempts) != ("disabled", 8192, 0, 0):
        raise ValueError("Initial generation must use disabled thinking, 8192 tokens and no retry")
    frozen = check_freeze(freeze_path, cases_path, settings, seed, repetitions)
    cases = inference_cases(cases_path)
    initial, reviews = plans(cases, seed, repetitions)
    check_imports(frozen)
    frozen_hash = sha(freeze_path)
    matrix = {"initial": initial, "reviews": reviews}
    manifest = {"schema_version": SCHEMA, "freeze_sha256": frozen_hash, "cases_sha256": sha(cases_path),
                "settings": settings.public_dict(), "seed": seed, "repetitions": repetitions,
                "workers": workers, "python_version": platform.python_version(),
                "expected_initial_stages": len(initial), "expected_review_stages": len(reviews),
                "maximum_physical_model_calls": len(initial) + len(reviews) * MAX_REVIEW_CALLS_PER_CLAIM,
                "request_matrix_sha256": digest(encoded(matrix)), "gold_sent_to_model": False}
    ledger = Ledger(output, manifest, matrix, resume=resume, secret=settings.api_key)
    by_case = {case["id"]: case for case in cases}
    reviews_by_initial = {}
    for task in reviews:
        reviews_by_initial.setdefault(task["initial_key"], []).append(task)

    def worker(task):
        if ledger.stop.is_set():
            return
        initial_stage(task, by_case[task["case_id"]], settings, ledger, client_factory)
        for review in reviews_by_initial.get(task["key"], []):
            if ledger.stop.is_set():
                return
            review_stage(review, by_case[review["case_id"]], settings, ledger, client_factory)

    failures = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(worker, task) for task in initial]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    ledger.stop.set()
                    failures.append(safe_error(exc))
        check_freeze(freeze_path, cases_path, settings, seed, repetitions)
        check_imports(frozen)
        if sha(freeze_path) != frozen_hash:
            raise ValueError("FROZEN.json changed while inference ran")
    except Exception as exc:
        ledger.stop.set()
        failures.append(safe_error(exc))
    progress = ledger.progress()
    outstanding = [task["key"] for task in initial + reviews if ledger.disposition(task) != "finished"]
    summary = {"schema_version": SCHEMA, "completed_at": now(), "freeze_sha256": frozen_hash,
               "status": "complete" if not outstanding and not failures else "incomplete",
               "progress": progress, "outstanding_stage_keys": outstanding, "failures": failures,
               "source_freeze_verified_after_run": not failures,
               "no_reserved_request_resampled": True, "semantic_scores": None,
               "qualification": "AI-authored component diagnostic; not author gold or an end-to-end benchmark."}
    ledger.operation("run_finished", summary)
    write_view(Path(output) / "summary.json", _redact(summary, settings.api_key))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--freeze", type=Path, default=HERE / "FROZEN.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=REPETITIONS)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    settings = pilot_settings(args.env_file.resolve())
    if not settings.api_key:
        raise ValueError("An API credential must be configured; it is never persisted")
    result = run(args.cases.resolve(), args.output.resolve(), settings, freeze_path=args.freeze.resolve(),
                 workers=args.workers, repetitions=args.repeat, seed=args.seed, resume=args.resume)
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()),
                      "stages": result["progress"]["stage_results"],
                      "provider_calls": result["progress"]["provider_reservations"],
                      "unknown": len(result["progress"]["unknown_provider_keys"])}, ensure_ascii=False))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
