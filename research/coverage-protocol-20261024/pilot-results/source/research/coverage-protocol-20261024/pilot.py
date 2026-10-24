#!/usr/bin/env python3
"""Frozen, single-call M1 coverage-protocol pilot with durable call reservations."""
from __future__ import annotations

import argparse
from collections import Counter
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
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REL = Path("research/coverage-protocol-20261024")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.client import ChatClient, _redact
from grounding.config import Settings, load_settings
from grounding.contracts import VerificationError, VerificationRequest, strict_json_loads
from grounding.verifiers_v4 import _local_telemetry
from scripts.analyze_v4_nf import runtime_summary

SCHEMA = "coverage-protocol-initial-stage-pilot-v1"
SEED = "coverage-protocol-20261024-v1"
ARMS = ("legacy", "ledger_text", "ledger_id")
CASES = 20
REPETITIONS = 2
MAX_CALLS = CASES * REPETITIONS * len(ARMS)
WORKERS = 4
CASE_FILE = "cases.json"
IO_DELAYS = (0.05, 0.10, 0.20, 0.40)
_protocol = None


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       indent=2) + "\n").encode("utf-8", errors="backslashreplace")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def rank(*parts):
    return digest("|".join([SEED, *map(str, parts)]).encode("utf-8"))


def read_object(path):
    value = strict_json_loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return value


def retryable_io(exc):
    return (isinstance(exc, PermissionError) or
            getattr(exc, "errno", None) in (errno.EACCES, errno.EAGAIN, errno.EBUSY) or
            getattr(exc, "winerror", None) in (32, 33))


def bounded_io(operation):
    """Retry a safe I/O operation only; this must never wrap a model request."""
    for attempt in range(len(IO_DELAYS) + 1):
        try:
            return operation()
        except OSError as exc:
            if not retryable_io(exc) or attempt == len(IO_DELAYS):
                raise
            time.sleep(IO_DELAYS[attempt])


def write_exclusive_bytes(path, raw):
    """No overwrite. An interrupted or partial existing file stays an error."""
    path = Path(path)
    stream = bounded_io(lambda: path.open("xb"))
    try:
        # A write can partially succeed, so it is deliberately not retried.
        if stream.write(raw) != len(raw):
            raise OSError("Incomplete checkpoint write")
        bounded_io(stream.flush)
        bounded_io(lambda: os.fsync(stream.fileno()))
    finally:
        stream.close()
    if bounded_io(path.read_bytes) != raw:
        raise OSError("Checkpoint readback differs")


def write_new(path, value):
    write_exclusive_bytes(path, encoded(value))


def write_progress(path, value):
    """Replace a derived view. Callers tolerate failure; reservations are truth."""
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
        spec = importlib.util.spec_from_file_location("coverage_pilot_protocol", HERE / "protocol.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        if tuple(module.ARMS) != ARMS:
            raise ValueError("Protocol arms differ from this preregistered matrix")
        _protocol = module
    return _protocol


def prompts():
    values = protocol().prompts()
    if set(values) != set(ARMS) or not all(isinstance(v, str) and v.strip() for v in values.values()):
        raise ValueError("Each protocol arm requires a nonempty frozen prompt")
    return values


def pilot_settings(env_file):
    return load_settings(env_file, model="deepseek-flash", thinking="disabled",
                         max_output_tokens=8192, json_mode=True,
                         upstream_retries=0, repair_attempts=0, max_claims=64)


def inference_cases(path):
    """Whitelist just ID for scheduling and answer for inference; ignore all gold."""
    rows = read_object(path).get("cases")
    if not isinstance(rows, list) or len(rows) != CASES:
        raise ValueError("Exactly twenty new natural cases are required")
    cases, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
            raise ValueError("Missing or duplicate case id")
        seen.add(row["id"])
        request = VerificationRequest.from_dict({"context_passages": [],
                                                "generated_answer": row.get("generated_answer")})
        if not request.generated_answer.strip() or len(request.generated_answer) > 1200:
            raise ValueError("M1 cases must fit the unchanged one-chunk bound")
        cases.append({"id": row["id"], "generated_answer": request.generated_answer})
    return cases


def jobs(cases):
    tasks = []
    rotation = int(rank("arm-rotation")[:8], 16) % len(ARMS)
    for index, case in enumerate(sorted(cases, key=lambda row: rank("case", row["id"]))):
        for repetition in range(REPETITIONS):
            offset = (index * REPETITIONS + repetition + rotation) % len(ARMS)
            tasks.append({"case": case, "repetition": repetition,
                          "order": ARMS[offset:] + ARMS[:offset]})
    return sorted(tasks, key=lambda task: rank("job", task["case"]["id"], task["repetition"]))


def identity(case_id, arm, repetition):
    return {"probe": "natural", "case_id": case_id, "arm": arm, "repetition": repetition}


def identity_key(value):
    return digest(encoded({name: value[name] for name in ("probe", "case_id", "arm", "repetition")}))


def planned_requests(cases):
    """Freeze all model-facing requests before any provider call is possible."""
    prompt_map, planned = prompts(), []
    for task_index, task in enumerate(jobs(cases)):
        for position, arm in enumerate(task["order"]):
            case = task["case"]
            # Protocol receives no case identifier, domain, expected fact or gold.
            payload = protocol().payload(arm, case["generated_answer"])
            if not isinstance(payload, dict):
                raise ValueError("Model payload must be a JSON object")
            item = {**identity(case["id"], arm, task["repetition"]),
                    "task_index": task_index, "backend_order_index": position,
                    "payload": payload, "prompt_sha256": digest(prompt_map[arm].encode()),
                    "payload_sha256": digest(encoded(payload))}
            item["identity_key"] = identity_key(item)
            planned.append(item)
    if len(planned) != MAX_CALLS or len({row["identity_key"] for row in planned}) != MAX_CALLS:
        raise ValueError("Frozen identity matrix differs from the fixed call budget")
    return planned


def freeze(output, settings, project_root=ROOT):
    output, project_root = Path(output), Path(project_root)
    if output.exists():
        raise FileExistsError("Run directory already exists; no overwrite")
    cases = inference_cases(project_root / REL / CASE_FILE)
    inputs = [path for directory in ("grounding", "scripts")
              for path in (project_root / directory).rglob("*.py")]
    inputs += list((project_root / REL).glob("*.py"))
    inputs += [project_root / REL / name for name in ("PLAN.md", CASE_FILE)]
    required = {"pilot.py", "test_pilot.py", "protocol.py", "test_protocol.py", "PLAN.md", CASE_FILE}
    if not required.issubset({path.name for path in inputs if path.parent == project_root / REL}):
        raise ValueError("Protocol, runner, tests, plan and cases must all exist before freeze")
    hashes = {path.relative_to(project_root).as_posix(): sha(path) for path in sorted(set(inputs))}
    planned = planned_requests(cases)
    output.mkdir(parents=True)
    for name, expected in hashes.items():
        raw = (project_root / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError("Source changed during freeze")
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_exclusive_bytes(target, raw)
    write_new(output / "prompts.json", prompts())
    write_new(output / "planned-requests.json", {"schema_version": SCHEMA, "requests": planned})
    manifest = {"schema_version": SCHEMA, "frozen_at": now(), "project_root": str(project_root.resolve()),
                "python_version": platform.python_version(), "files_sha256": hashes,
                "settings": settings.public_dict(), "prompts_sha256": sha(output / "prompts.json"),
                "planned_requests_sha256": sha(output / "planned-requests.json"),
                "individual_prompt_sha256": {key: digest(text.encode()) for key, text in prompts().items()},
                "seed": SEED, "workers": WORKERS, "repetitions": REPETITIONS, "arms": list(ARMS),
                "max_model_calls": MAX_CALLS, "expected_records": MAX_CALLS,
                "io_attempts": len(IO_DELAYS) + 1, "io_retry_delays_seconds": list(IO_DELAYS),
                "qualification": "Synthetic M1 diagnostic only; no M3, fallback, model retry or semantic self-scoring. Structural coverage is not factual fidelity. AI-drafted labels are not author gold."}
    if any(sha(project_root / name) != expected for name, expected in hashes.items()):
        raise ValueError("Source changed during freeze")
    write_new(output / "freeze.json", manifest)
    write_exclusive_bytes(output / "freeze.sha256", (sha(output / "freeze.json") + "\n").encode("ascii"))
    return manifest


def check_imported_dependencies(source, hashes, modules):
    source = Path(source).resolve()
    for name, module in modules:
        if (name in ("grounding", "scripts", "coverage_pilot_protocol") or
                name.startswith(("grounding.", "scripts."))):
            location = getattr(module, "__file__", None)
            if not location or not Path(location).resolve().is_relative_to(source):
                raise ValueError("Project dependency escaped the frozen source: " + name)
            relative = Path(location).resolve().relative_to(source).as_posix()
            if hashes.get(relative) != sha(location):
                raise ValueError("Imported dependency is not bound to this freeze: " + name)


def check_freeze(output):
    output = Path(output)
    if sha(output / "freeze.json") != (output / "freeze.sha256").read_text().strip():
        raise ValueError("Frozen manifest changed")
    manifest = read_object(output / "freeze.json")
    if manifest["schema_version"] != SCHEMA or manifest["python_version"] != platform.python_version():
        raise ValueError("Frozen protocol or Python version differs")
    source = (output / "source").resolve()
    for name, expected in manifest["files_sha256"].items():
        target = (source / name).resolve()
        if not target.is_relative_to(source) or sha(target) != expected:
            raise ValueError("Frozen file changed: " + name)
    if sha(output / "prompts.json") != manifest["prompts_sha256"] or read_object(output / "prompts.json") != prompts():
        raise ValueError("Frozen prompts differ")
    if sha(output / "planned-requests.json") != manifest["planned_requests_sha256"]:
        raise ValueError("Frozen request matrix changed")
    planned = read_object(output / "planned-requests.json")["requests"]
    if planned != planned_requests(inference_cases(source / REL / CASE_FILE)):
        raise ValueError("Frozen request matrix differs from the frozen protocol")
    if ROOT.resolve() == source:
        check_imported_dependencies(source, manifest["files_sha256"], list(sys.modules.items()))
    return manifest


def single_call(client, settings, planned, answer):
    telemetry = _local_telemetry()
    started = time.monotonic()
    prompt = prompts()[planned["arm"]]
    record = {**deepcopy(planned), "started_at": now(),
              "messages": [{"role": "system", "content": prompt},
                           {"role": "user", "content": json.dumps(planned["payload"], ensure_ascii=False, allow_nan=False)}],
              "telemetry": telemetry, "status": "error", "raw_output": None,
              "validated_output": None, "error": None}
    try:
        raw = client.complete(record["messages"], "coverage_" + planned["arm"], telemetry)
        record["raw_output"] = deepcopy(raw)
        record["validated_output"] = protocol().validate(planned["arm"], raw, answer, max_claims=64)
        record["status"] = "valid"
    except VerificationError as exc:
        record["error"] = {"code": exc.code, "message": exc.message}
    except Exception as exc:
        record["error"] = {"code": "probe_execution_error", "message": type(exc).__name__ + ": " + str(exc)}
    finally:
        record["latency_seconds"] = time.monotonic() - started
        record["completed_at"] = now()
        for call in telemetry["calls"]:
            call.update(thinking="disabled", max_output_tokens=8192, phase="coverage")
        record["safe_quote_repairs"] = len(telemetry["citation_repairs"])
    return _redact(record, settings.api_key)


class RunLedger:
    """Each reservation and returned response is authoritative, exclusive and fsynced."""
    def __init__(self, output, planned):
        self.output = Path(output)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.planned = {row["identity_key"]: row for row in planned}
        self.reserved = set()
        self.records = {}
        self.warnings = []
        self.progress = {"schema_version": SCHEMA, "status": "running", "started_at": now(),
                         "record_count": 0, "model_calls_started": 0, "expected_records": MAX_CALLS,
                         "valid": 0, "error": 0, "gold_sent_to_model": False}
        # Any earlier start, reservation or journal blocks this run. No resume.
        if any((self.output / name).exists() for name in ("run-started.json", "reservations", "responses", "responses.events.jsonl", "responses.jsonl", "progress.json")):
            raise FileExistsError("A run already started; no resume, overwrite or resampling")
        write_new(self.output / "run-started.json", {"schema_version": SCHEMA, "started_at": now(),
                                                    "freeze_sha256": sha(self.output / "freeze.json")})
        (self.output / "reservations").mkdir()
        (self.output / "responses").mkdir()
        self.events = (self.output / "responses.events.jsonl").open("xb")
        self.event_journal_healthy = True
        self.snapshot()

    def warning(self, stage, exc):
        self.warnings.append({"at": now(), "stage": stage,
                              "error": type(exc).__name__ + ": " + str(exc)})

    def snapshot(self):
        self.progress["io_warning_count"] = len(self.warnings)
        try:
            write_progress(self.output / "progress.json", self.progress)
        except OSError as exc:
            # A locked GUI progress view must not lose a completed model response.
            self.warning("progress_view", exc)

    def reserve(self, planned):
        with self.lock:
            if self.stop.is_set():
                raise RuntimeError("Dispatch stopped after a durability failure")
            key = planned["identity_key"]
            if key not in self.planned or self.planned[key] != planned or key in self.reserved:
                raise ValueError("Unplanned or already reserved identity; never resend")
            if len(self.reserved) >= MAX_CALLS:
                raise RuntimeError("Frozen model call ceiling reached")
            try:
                write_new(self.output / "reservations" / (key + ".json"),
                          {"reserved_at": now(), "freeze_sha256": sha(self.output / "freeze.json"),
                           "request": planned})
            except BaseException:
                self.stop.set()
                raise
            self.reserved.add(key)
            self.progress["model_calls_started"] = len(self.reserved)
            self.snapshot()

    def record(self, value):
        with self.lock:
            key = value["identity_key"]
            if key not in self.reserved or key in self.records:
                raise ValueError("Unreserved or duplicate returned response")
            try:
                write_new(self.output / "responses" / (key + ".json"), value)
            except BaseException:
                self.stop.set()
                raise
            self.records[key] = value
            if self.event_journal_healthy:
                try:
                    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="backslashreplace") + b"\n"
                    if self.events.write(raw) != len(raw):
                        raise OSError("Incomplete event journal write")
                    bounded_io(self.events.flush)
                    bounded_io(lambda: os.fsync(self.events.fileno()))
                except OSError as exc:
                    # Already durably checkpointed. Final journal derives from those
                    # files; do not retry an uncertain append or the model call.
                    self.event_journal_healthy = False
                    self.warning("response_event_journal", exc)
            self.progress["record_count"] = len(self.records)
            self.progress[value["status"]] += 1
            self.snapshot()

    def finalize(self, complete):
        with self.lock:
            try:
                self.events.close()
            except OSError as exc:
                self.warning("close_event_journal", exc)
            self.progress.update(status="complete" if complete else "aborted", completed_at=now(),
                                 unknown_reservations=sorted(self.reserved - self.records.keys()))
            if complete:
                if set(self.records) != set(self.planned) or self.reserved != set(self.planned):
                    raise ValueError("Incomplete fixed-call checkpoint matrix")
                ordered = sorted(self.records.values(), key=lambda row: (row["task_index"], row["backend_order_index"]))
                raw = b"".join(json.dumps(row, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="backslashreplace") + b"\n" for row in ordered)
                write_exclusive_bytes(self.output / "responses.jsonl", raw)
                self.progress.update(responses_sha256=sha(self.output / "responses.jsonl"),
                                     frozen_artifacts_unchanged=True)
            # Try the derived view before sealing the authoritative completion,
            # so even a final display-write warning is retained in that seal.
            self.snapshot()
            completion = {**deepcopy(self.progress), "io_warnings": deepcopy(self.warnings),
                          "io_warning_count": len(self.warnings),
                          "freeze_sha256": sha(self.output / "freeze.json"),
                          "reservation_files_sha256": {p.name: sha(p) for p in sorted((self.output / "reservations").glob("*.json"))},
                          "response_files_sha256": {p.name: sha(p) for p in sorted((self.output / "responses").glob("*.json"))},
                          "event_journal_sha256": sha(self.output / "responses.events.jsonl"),
                          "event_journal_healthy": self.event_journal_healthy}
            write_new(self.output / ("run-complete.json" if complete else "run-aborted.json"), completion)
            return completion


def run(output, settings):
    output = Path(output)
    manifest = check_freeze(output)
    if ROOT.resolve() != (output / "source").resolve():
        raise ValueError("Run must execute the frozen source")
    if settings.public_dict() != manifest["settings"] or not settings.api_key:
        raise ValueError("Settings differ from freeze or API key is unavailable")
    cases = {row["id"]: row for row in inference_cases(HERE / CASE_FILE)}
    planned = read_object(output / "planned-requests.json")["requests"]
    ledger = RunLedger(output, planned)
    tasks = {}
    for request in planned:
        tasks.setdefault(request["task_index"], []).append(request)

    def worker(requests):
        for request in sorted(requests, key=lambda row: row["backend_order_index"]):
            if ledger.stop.is_set():
                return
            client = ChatClient(settings)
            ledger.reserve(request)
            result = single_call(client, settings, request, cases[request["case_id"]]["generated_answer"])
            ledger.record(result)

    failures = []
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(worker, tasks[index]) for index in sorted(tasks)]
            for future in as_completed(futures):
                try:
                    future.result()
                except BaseException as exc:
                    ledger.stop.set()
                    failures.append(exc)
        if failures:
            raise failures[0]
        check_freeze(output)
    except BaseException:
        ledger.stop.set()
        ledger.finalize(False)
        raise
    return ledger.finalize(True)


def analyze(output):
    """Mechanical diagnostics only; source expected semantics remain scorer-only."""
    output = Path(output)
    manifest = check_freeze(output)
    complete = read_object(output / "run-complete.json")
    if complete["status"] != "complete" or complete["freeze_sha256"] != sha(output / "freeze.json"):
        raise ValueError("Analysis requires a complete, matching run checkpoint")
    if complete["unknown_reservations"] or sha(output / "responses.jsonl") != complete["responses_sha256"]:
        raise ValueError("Unknown provider outcome or changed response journal")
    for directory, field in (("reservations", "reservation_files_sha256"), ("responses", "response_files_sha256")):
        files = {p.name: sha(p) for p in (output / directory).glob("*.json")}
        if files != complete[field] or len(files) != MAX_CALLS:
            raise ValueError("Durable checkpoint matrix changed: " + directory)
    planned = {row["identity_key"]: row for row in read_object(output / "planned-requests.json")["requests"]}
    records = [strict_json_loads(line) for line in (output / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(records) != MAX_CALLS or {r["identity_key"] for r in records} != set(planned):
        raise ValueError("Journal coverage or identity mismatch")
    for record in records:
        key = record["identity_key"]
        if identity_key(record) != key or any(record[name] != value for name, value in planned[key].items()):
            raise ValueError("Journal request differs from frozen request")
        if record != read_object(output / "responses" / (key + ".json")):
            raise ValueError("Journal differs from durable response checkpoint")
        reservation = read_object(output / "reservations" / (key + ".json"))
        if reservation["request"] != planned[key] or reservation["freeze_sha256"] != complete["freeze_sha256"]:
            raise ValueError("Reservation differs from frozen request")
        if len(record["telemetry"].get("calls", [])) != 1:
            raise ValueError("Each dispatched request must retain exactly one provider attempt")
    summary = {"schema_version": SCHEMA, "created_at": now(), "freeze_sha256": sha(output / "freeze.json"),
               "responses_sha256": complete["responses_sha256"], "arms": {}, "semantic_scores": None,
               "io_warning_count": len(complete["io_warnings"]), "event_journal_healthy": complete["event_journal_healthy"],
               "qualification": "Structural validity and coverage are not semantic correctness. Independent semantic review required. Synthetic AI-drafted material is not author adjudication or a held-out benchmark."}
    for arm in ARMS:
        selected = [r for r in records if r["arm"] == arm]
        valid = [r for r in selected if r["status"] == "valid"]
        summary["arms"][arm] = {"records": len(selected), "statuses": dict(Counter(r["status"] for r in selected)),
                                 "claim_count": sum(len(r["validated_output"]["claims"]) for r in valid),
                                 "non_factual_span_count": sum(len(r["validated_output"]["non_factual_spans"]) for r in valid),
                                 "runtime": runtime_summary(selected),
                                 "by_execution_position": {str(p): runtime_summary([r for r in selected if r["backend_order_index"] == p]) for p in range(len(ARMS))}}
    summary["runtime"] = runtime_summary(records)
    if summary["runtime"]["usage"]["calls"] != manifest["max_model_calls"] or complete["model_calls_started"] != MAX_CALLS:
        raise ValueError("Provider call accounting differs from fixed call ceiling")
    write_new(output / "analysis.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "analyze"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output, env_file = args.output_dir.resolve(), args.env_file.resolve()
    if args.command != "freeze" and not args.frozen:
        check_freeze(output)
        return subprocess.call([sys.executable, str(output / "source" / REL / "pilot.py"), args.command,
                                "--output-dir", str(output), "--env-file", str(env_file), "--frozen"],
                               cwd=output / "source")
    if args.command != "freeze" and ROOT.resolve() != (output / "source").resolve():
        raise ValueError("Non-freeze operation must use frozen source")
    if args.command == "freeze":
        result = freeze(output, pilot_settings(env_file))
    elif args.command == "run":
        result = run(output, pilot_settings(env_file))
    else:
        result = analyze(output)
    print(json.dumps({"command": args.command, "output_directory": str(output),
                      "schema_version": result["schema_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
