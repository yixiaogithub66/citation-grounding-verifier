#!/usr/bin/env python3
"""Run a frozen, source-held-out three-backend comparison exactly once per pair.

Only request-only inputs and scheduling metadata are decoded during inference.
Native labels are hashed as opaque bytes. Reservations precede verification;
an orphan reservation is UNKNOWN, never a reason to repeat a provider call.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
import errno
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
from types import SimpleNamespace
import uuid

SCHEMA = "ragtruth-fresh180-durable-run-v1"
BACKENDS = ("baseline", "minimal", "optimized-v4.0")
DATA_FILES = ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json")
IO_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    def reject(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_constant=reject)


def object_json(path):
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: " + Path(path).name)
    return value


def redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, dict):
        return {redact(str(k), secret): redact(v, secret) for k, v in value.items()}
    return value


def bounded_io(operation):
    for attempt in range(len(IO_DELAYS) + 1):
        try:
            return operation()
        except OSError as exc:
            retryable = isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EAGAIN, errno.EBUSY) or getattr(exc, "winerror", None) in (32, 33)
            if not retryable or attempt == len(IO_DELAYS):
                raise
            time.sleep(IO_DELAYS[attempt])


def write_bytes_new(path, raw):
    """Same-directory hardlink publishes complete bytes without replacement."""
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with bounded_io(lambda: temporary.open("xb")) as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Incomplete durable write")
            bounded_io(stream.flush)
            bounded_io(lambda: os.fsync(stream.fileno()))
        bounded_io(lambda: os.link(temporary, path))
        if bounded_io(path.read_bytes) != raw:
            raise OSError("Durable file failed readback")
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def write_new(path, value):
    write_bytes_new(path, encoded(value))


def write_view(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        write_new(temporary, value)
        bounded_io(lambda: os.replace(temporary, path))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_source(preselection_path, preselection):
    source = Path(preselection["source_root"])
    return source.resolve() if source.is_absolute() else (Path(preselection_path).parent / source).resolve()


def check_freeze(preselection_path, binding_path, data_dir):
    """Hash all bindings first; no native annotations are deserialized."""
    for path in (Path(preselection_path), Path(binding_path)):
        if path.with_suffix(".sha256").read_text(encoding="ascii").strip() != sha(path):
            raise ValueError("Freeze/binding manifest differs from its immutable SHA256 sidecar")
    pre, bound = object_json(preselection_path), object_json(binding_path)
    if bound.get("preselection_freeze_sha256", bound.get("preselection_sha256")) != sha(preselection_path):
        raise ValueError("Binding does not match preselection freeze")
    if pre.get("backends") != list(BACKENDS):
        raise ValueError("Exactly baseline/minimal/optimized-v4.0 are preregistered")
    if pre.get("python_version") != platform.python_version():
        raise ValueError("Python version changed after freeze")
    if pre.get("runner_sha256") != sha(__file__):
        raise ValueError("Runner changed after preselection freeze")
    if pre.get("run_options", {}).get("workers") != 4:
        raise ValueError("Frozen protocol requires four case workers")
    if "seed" not in pre["run_options"]:
        raise ValueError("Missing frozen backend-order seed")
    source = resolve_source(preselection_path, pre)
    hashes = pre.get("code_files_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("Missing complete frozen source manifest")
    for name, expected in hashes.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or sha(path) != expected:
            raise ValueError("Frozen source changed or escaped its root: " + name)
    actual = {name: sha(Path(data_dir) / name) for name in DATA_FILES}
    if bound.get("data_files_sha256") != actual:
        raise ValueError("Prepared dataset binding changed")
    return pre, bound, source


def frozen_imports(source, expected):
    """Import solely from the immutable snapshot, never the working checkout."""
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    def guard():
        for name, module in list(sys.modules.items()):
            if not (name in ("grounding", "scripts") or name.startswith(("grounding.", "scripts."))):
                continue
            location = getattr(module, "__file__", None)
            if not location:
                raise ValueError("Frozen project module has no source file: " + name)
            path = Path(location).resolve()
            if not path.is_relative_to(source) or expected.get(path.relative_to(source).as_posix()) != sha(path):
                raise ValueError("Project module escaped or changed from the freeze: " + name)
    guard()
    config = importlib.import_module("grounding.config")
    config_v4 = importlib.import_module("grounding.config_v4")
    contracts = importlib.import_module("grounding.contracts")
    contracts_v4 = importlib.import_module("grounding.contracts_v4")
    factory = importlib.import_module("grounding.factory")
    helper = importlib.import_module("scripts.benchmark_ragtruth")
    for name in ("grounding.baseline", "grounding.verifiers", "grounding.verifiers_v4"):
        importlib.import_module(name)
    guard()
    return SimpleNamespace(config=config, config_v4=config_v4, contracts=contracts,
                           validate=contracts_v4.validate_v4_report,
                           factory=factory.build_verifier, helper=helper, guard=guard)


def frozen_settings(api, values, env_file):
    """Read only credentials locally; all behavior comes from the freeze."""
    public = dict(values)
    public.pop("api_key_configured", None)
    if "api_key" in public:
        raise ValueError("A public freeze must not contain an API key")
    if public.get("thinking") != "enabled" or public.get("max_output_tokens") != 16384:
        raise ValueError("Registered minimal comparator is thinking enabled / 16384")
    credentials = api.config.read_env_file(Path(env_file)) if env_file is not None else {}
    credentials.update({key: os.environ[key] for key in ("LLM_API_KEY", "DEEPSEEK_API_KEY") if key in os.environ})
    secret = credentials.get("LLM_API_KEY") or credentials.get("DEEPSEEK_API_KEY", "")
    return api.config.Settings(**public, api_key=secret).validate()


def load_requests(data_dir, api, preselection, *, expected_count=180):
    inputs = api.helper._jsonl(Path(data_dir) / "inputs.jsonl")
    manifest = api.helper._jsonl(Path(data_dir) / "manifest.jsonl")
    if len(inputs) != expected_count or len(manifest) != expected_count:
        raise ValueError("Exactly 180 request/metadata pairs are required")
    ids = set()
    for case, meta in zip(inputs, manifest):
        identifier = case.get("id")
        if set(case) != {"id", "input"} or not isinstance(identifier, str) or not identifier or identifier in ids or identifier != meta.get("id"):
            raise ValueError("Inputs require unique IDs aligned with manifest")
        ids.add(identifier)
        # VerificationRequest rejects keys beyond the two public request fields.
        api.contracts.VerificationRequest.from_dict(case["input"])
        if set(case["input"]) != {"context_passages", "generated_answer"}:
            raise ValueError("Inference input must contain only the public request")
        if any(not isinstance(meta.get(key), str) or not meta[key] for key in ("source_id", "task_type", "generator")):
            raise ValueError("Missing scheduling metadata")
        if meta.get("input_sha256") != api.helper._canonical_sha(case["input"]):
            raise ValueError("Request differs from its metadata hash")
    if expected_count == 180:
        groups = Counter(m["source_id"] for m in manifest)
        by_task = {task: {m["source_id"] for m in manifest if m["task_type"] == task} for task in {m["task_type"] for m in manifest}}
        if len(groups) != 30 or set(groups.values()) != {6} or len(by_task) != 3 or {len(v) for v in by_task.values()} != {10}:
            raise ValueError("Frozen matrix requires 30 sources, 6 responses each, 10 sources per task")
        if any(len({m["task_type"] for m in manifest if m["source_id"] == sid}) != 1 for sid in groups):
            raise ValueError("A source cannot span task types")
        expected_tasks = preselection.get("sampling", {}).get("tasks")
        if expected_tasks is not None and set(by_task) != set(expected_tasks):
            raise ValueError("Task types differ from the frozen sampling policy")
    excluded = set(preselection.get("sampling", {}).get("excluded_source_ids", []))
    if excluded.intersection(m["source_id"] for m in manifest):
        raise ValueError("Selected sources overlap the frozen exposure exclusion list")
    return inputs, manifest


def schedule(inputs, manifest, seed):
    plans = []
    for case, meta in zip(inputs, manifest):
        order = sorted(BACKENDS, key=lambda backend: (hashlib.sha256(f"{seed}|{case['id']}|{backend}".encode()).hexdigest(), backend))
        for ordinal, backend in enumerate(order):
            identity = {"id": case["id"], "backend": backend}
            plans.append({**identity, "key": hashlib.sha256(encoded(identity)).hexdigest(),
                          "source_id": meta["source_id"], "input_sha256": meta["input_sha256"],
                          "backend_order": order, "backend_order_index": ordinal})
    return plans


def infer_one(case, meta, task, settings, v4_config, api):
    started, stamp = time.monotonic(), now()
    prediction, error, telemetry = None, None, {"calls": []}
    citations, validation_errors = {"citation_count": 0, "valid_citation_count": 0}, []
    backend = task["backend"]
    try:
        request = api.contracts.VerificationRequest.from_dict(case["input"])
        effective = replace(settings, upstream_retries=0, repair_attempts=0) if backend == "minimal" else settings
        instance = api.factory(backend, effective, v4_config=v4_config) if backend == "optimized-v4.0" else api.factory(backend, effective)
        result = instance.verify(request)
        prediction, telemetry = result.report, result.telemetry or telemetry
        api.validate(prediction, request.context_passages)
        citations = api.helper._citation_counts(prediction, request.context_passages)
    except api.contracts.VerificationError as exc:
        telemetry = getattr(exc, "telemetry", None) or telemetry
        prediction = None
        error = {"code": exc.code, "message": exc.message, "type": type(exc).__name__}
        if exc.code == "invalid_model_output":
            validation_errors = [exc.message]
    except Exception as exc:
        prediction = None
        telemetry = getattr(exc, "telemetry", None) or telemetry
        error = {"code": "unexpected_error", "type": type(exc).__name__}
    calls = telemetry.get("calls", [])
    if (backend == "baseline" and len(calls) != 0) or (backend == "minimal" and len(calls) > 1):
        prediction = None
        error = {"code": "call_budget_violation", "message": "Baseline must make zero model attempts; minimal at most one."}
    return redact({"id": case["id"], **{k: meta[k] for k in ("source_id", "task_type", "generator", "input_sha256")},
                   "backend": backend, "prediction": prediction, "error": error, "telemetry": telemetry,
                   "schema_valid": error is None, "validation_errors": validation_errors, "citations": citations,
                   "answer_chars": len(case["input"]["generated_answer"]), "latency_seconds": time.monotonic() - started,
                   "started_at": stamp, "completed_at": now(), "backend_order": task["backend_order"],
                   "backend_order_index": task["backend_order_index"], "pair_key": task["key"]}, settings.api_key)


class DurabilityError(RuntimeError):
    pass


class Ledger:
    def __init__(self, output, run_manifest, planned, *, resume=False, secret=""):
        self.output, self.secret = Path(output), secret
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.allowed = {task["key"]: task for task in planned}
        if len(self.allowed) != len(planned):
            raise ValueError("Duplicate planned pair")
        self.warnings, self.status = [], "running"
        if resume:
            if object_json(self.output / "config.json") != run_manifest or read_json(self.output / "planned-pairs.json") != planned:
                raise ValueError("Resume requires exact original bindings and schedule")
        else:
            self.output.mkdir(parents=True, exist_ok=False)
            write_new(self.output / "config.json", run_manifest)
            write_new(self.output / "planned-pairs.json", planned)
            (self.output / "reservations").mkdir()
            (self.output / "records").mkdir()
            (self.output / "operations").mkdir()
        self.reserved, self.done = set(), {}
        self.validate_existing()
        write_new(self.output / "operations" / (uuid.uuid4().hex + ".json"), {"at": now(), "operation": "resume" if resume else "run", "previous_records": len(self.done), "previous_orphan_reservations": len(self.reserved - set(self.done))})

    def path(self, directory, key):
        return self.output / directory / (key + ".json")

    def validate_existing(self):
        for path in (self.output / "reservations").glob("*.json"):
            value = object_json(path)
            if path.stem not in self.allowed or value.get("task") != self.allowed[path.stem]:
                raise ValueError("Reservation differs from the frozen plan")
            self.reserved.add(path.stem)
        for path in (self.output / "records").glob("*.json"):
            row = object_json(path)
            if path.stem not in self.reserved:
                raise ValueError("A result exists without reservation")
            task = self.allowed[path.stem]
            if row.get("pair_key") != path.stem or any(row.get(k) != task[k] for k in ("id", "backend", "source_id", "input_sha256", "backend_order", "backend_order_index")):
                raise ValueError("Saved result identity differs from the frozen plan")
            self.done[path.stem] = {"backend": row["backend"], "error": row.get("error") is not None,
                                   "partial": bool(row.get("prediction") and row["prediction"].get("status") == "partial")}

    def disposition(self, task):
        with self.lock:
            return "finished" if task["key"] in self.done else "unknown" if task["key"] in self.reserved else "unreserved"

    def reserve(self, task):
        with self.lock:
            if self.stop.is_set() or self.disposition(task) != "unreserved":
                raise DurabilityError("Dispatch stopped or pair was already reserved")
            try:
                write_new(self.path("reservations", task["key"]), redact({"task": task, "reserved_at": now()}, self.secret))
                self.reserved.add(task["key"])
            except Exception as exc:
                self.stop.set()
                raise DurabilityError("Reservation failed; verification must not be called") from exc

    def result(self, task, record):
        with self.lock:
            if task["key"] not in self.reserved:
                raise DurabilityError("Result has no reservation")
            try:
                write_new(self.path("records", task["key"]), redact(record, self.secret))
                self.done[task["key"]] = {"backend": record["backend"], "error": record.get("error") is not None,
                                           "partial": bool(record.get("prediction") and record["prediction"].get("status") == "partial")}
            except Exception as exc:
                self.stop.set()
                raise DurabilityError("Result was not durably recorded; never resend this pair") from exc

    def progress(self, **extra):
        with self.lock:
            rows = list(self.done.values())
            value = {"schema_version": SCHEMA, "status": self.status, "updated_at": now(), "gold_loaded": False,
                     "expected_records": len(self.allowed), "reserved_pairs": len(self.reserved),
                     "completed_records": len(self.done), "error_records": sum(r["error"] for r in rows),
                     "partial_records": sum(r["partial"] for r in rows),
                     "unknown_reserved_pairs": sorted(self.reserved - set(self.done)),
                     "never_reserved_pairs": len(self.allowed) - len(self.reserved),
                     "by_backend": {b: {"completed_records": sum(r["backend"] == b for r in rows),
                                         "error_records": sum(r["backend"] == b and r["error"] for r in rows),
                                         "partial_records": sum(r["backend"] == b and r["partial"] for r in rows)} for b in BACKENDS},
                     "io_warnings": list(self.warnings), **extra}
            try:
                write_view(self.output / "progress.json", value)
            except OSError as exc:
                self.warnings.append({"at": now(), "kind": "derived_progress_write", "error_type": type(exc).__name__})
            return value


def unknown_record(task, case, meta, reservation):
    # No fake empty calls list: cost/usage must remain unknown after a crash.
    return {"id": case["id"], **{k: meta[k] for k in ("source_id", "task_type", "generator", "input_sha256")},
            "backend": task["backend"], "prediction": None,
            "error": {"code": "reserved_result_unknown", "message": "Reservation exists without a durable result; pair was not repeated."},
            "telemetry": {"usage_unknown": True}, "schema_valid": False, "validation_errors": [],
            "citations": {"citation_count": 0, "valid_citation_count": 0},
            "answer_chars": len(case["input"]["generated_answer"]), "latency_seconds": None,
            "started_at": reservation["reserved_at"], "completed_at": None,
            "backend_order": task["backend_order"], "backend_order_index": task["backend_order_index"], "pair_key": task["key"]}


def finalize(ledger, planned, inputs, manifest):
    if set(ledger.allowed) != ledger.reserved:
        raise ValueError("Cannot finalize while some pairs were never reserved; resume only those pairs")
    cases = {c["id"]: c for c in inputs}
    metadata = {m["id"]: m for m in manifest}
    records, checksums = [], {}
    for task in planned:
        path = ledger.path("records", task["key"])
        if task["key"] in ledger.done:
            row = object_json(path)
            checksums["records/" + path.name] = sha(path)
        else:
            row = unknown_record(task, cases[task["id"]], metadata[task["id"]], object_json(ledger.path("reservations", task["key"])))
        records.append(row)
        reservation = ledger.path("reservations", task["key"])
        checksums["reservations/" + reservation.name] = sha(reservation)
    raw = b"".join(encoded(row) for row in records)
    integrity = {"predictions_sha256": hashlib.sha256(raw).hexdigest(), "record_count": len(records),
                 "durable_result_count": len(ledger.done), "unknown_count": len(ledger.reserved - set(ledger.done)),
                 "files_sha256": checksums}
    # A crash during final assembly is recoverable without any new verification.
    for path, payload in ((ledger.output / "predictions.jsonl", raw), (ledger.output / "result-integrity.json", encoded(integrity))):
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("Final artifact differs from durable records: " + path.name)
        else:
            write_bytes_new(path, payload)
    ledger.status = "completed_with_unknown" if ledger.reserved - set(ledger.done) else "completed"
    return ledger.progress(frozen_artifacts_unchanged=True, finalized_records=len(records))


def execute(inputs, manifest, planned, settings, v4_config, api, ledger, *, workers=4):
    """Four answer workers; the three backends for one answer run sequentially."""
    tasks = {}
    for task in planned:
        tasks.setdefault(task["id"], []).append(task)
    def work(case, meta):
        for task in tasks[case["id"]]:
            if ledger.stop.is_set():
                return
            if ledger.disposition(task) != "unreserved":
                continue
            ledger.reserve(task)
            record = infer_one(case, meta, task, settings, v4_config, api)
            ledger.result(task, record)
            ledger.progress()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fresh180") as pool:
        futures = [pool.submit(work, case, meta) for case, meta in zip(inputs, manifest)]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            ledger.stop.set()
            ledger.status = "interrupted_or_failed"
            for future in futures:
                future.cancel()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "run"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preselection-freeze", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    pre, bound, source = check_freeze(args.preselection_freeze, args.binding, args.data_dir)
    api = frozen_imports(source, pre["code_files_sha256"])
    settings = frozen_settings(api, pre["settings"], args.env_file)
    v4 = api.config_v4.V4Config.from_dict(pre["v4_config"])
    inputs, manifest = load_requests(args.data_dir, api, pre)
    planned = schedule(inputs, manifest, pre["run_options"]["seed"])
    api.guard()
    check_freeze(args.preselection_freeze, args.binding, args.data_dir)
    if args.command == "check":
        print(json.dumps({"status": "checked", "cases": len(inputs), "pairs": len(planned), "model_calls": 0, "gold_loaded": False}))
        return 0
    if not settings.api_key:
        raise ValueError("Model credentials are missing before any reservation")
    run_manifest = {"schema_version": SCHEMA, "preselection_freeze_sha256": sha(args.preselection_freeze),
                    "binding_sha256": sha(args.binding), "data_files_sha256": bound["data_files_sha256"],
                    "code_files_sha256": pre["code_files_sha256"], "runner_sha256": pre["runner_sha256"],
                    "settings": pre["settings"], "v4_config": pre["v4_config"], "backends": list(BACKENDS),
                    "run_options": pre["run_options"], "price_reference": pre.get("price_reference"),
                    "gold_loaded": False, "no_rerun_policy": "Only never-reserved pairs may be dispatched; orphan reservations remain UNKNOWN."}
    ledger = Ledger(args.output_dir, run_manifest, planned, resume=args.resume, secret=settings.api_key)
    ledger.progress()
    try:
        execute(inputs, manifest, planned, settings, v4, api, ledger)
        api.guard()
        check_freeze(args.preselection_freeze, args.binding, args.data_dir)
        result = finalize(ledger, planned, inputs, manifest)
    except BaseException:
        ledger.stop.set()
        ledger.status = "interrupted_or_failed"
        ledger.progress()
        raise
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
