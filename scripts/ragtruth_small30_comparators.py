#!/usr/bin/env python3
"""Run unchanged baseline/minimal on the already selected exploratory thirty.

The only imported project modules come from the original v4 frozen source.
Freeze/run never deserialize native gold; score is a separate command.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ragtruth-small30-comparators-v1"
NEW_BACKENDS = ("baseline", "minimal")
ALL_BACKENDS = (*NEW_BACKENDS, "optimized-v4.0")
SEED = "ragtruth-small30-comparator-schedule-20261023-v1"
ORIGIN_FILES = ("preselection.json", "preselection.sha256", "binding.json", "binding.sha256",
                "data/inputs.jsonl", "data/manifest.jsonl", "data/native_gold.jsonl",
                "data/preparation.json", "predictions.jsonl", "progress.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


def bind_frozen_imports(source_run):
    """Fail closed if a current-checkout project module entered this process."""
    source = (source_run / "source").resolve()
    sys.path.insert(0, str(source))
    def guard():
        expected = read_object(source_run / "preselection.json")["code_files_sha256"]
        for name, module in list(sys.modules.items()):
            if not (name in ("grounding", "scripts") or name.startswith(("grounding.", "scripts."))):
                continue
            location = getattr(module, "__file__", None)
            if not location:
                raise ValueError("Project module has no frozen file: " + name)
            path = Path(location).resolve()
            if not path.is_relative_to(source):
                raise ValueError("Non-frozen project import: " + name)
            key = path.relative_to(source).as_posix()
            if expected.get(key) != sha(path):
                raise ValueError("Imported module is absent from the original freeze: " + name)
    guard()
    helper = importlib.import_module("scripts.ragtruth_small30")
    config = importlib.import_module("grounding.config")
    contracts = importlib.import_module("grounding.contracts")
    prompts = importlib.import_module("grounding.prompts")
    # Load both implementations now so their file paths are checked before calls.
    importlib.import_module("grounding.baseline")
    importlib.import_module("grounding.verifiers")
    guard()
    helper.check_freeze(source_run, bound=True)
    return SimpleNamespace(helper=helper, config=config, contracts=contracts, prompts=prompts, guard=guard)


def frozen_settings(api, values, env_file=None):
    """Read only the credential from local configuration, never model overrides."""
    secret = ""
    if env_file is not None:
        local = api.config.read_env_file(env_file)
        local.update({key: os.environ[key] for key in ("LLM_API_KEY", "DEEPSEEK_API_KEY") if key in os.environ})
        secret = local.get("LLM_API_KEY") or local.get("DEEPSEEK_API_KEY", "")
    return api.config.Settings(**values, api_key=secret).validate()


def snapshot(source, destination):
    raw = Path(source).read_bytes()
    with Path(destination).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def freeze(output, source_run, plan, tests, api):
    if output.exists():
        raise FileExistsError("Comparator directory already exists")
    original = api.helper.check_freeze(source_run, bound=True)
    progress = read_object(source_run / "progress.json")
    if (progress.get("status") != "completed" or progress.get("completed_records") != 30
            or progress.get("frozen_artifacts_unchanged") is not True):
        raise ValueError("Original thirty-record v4 run must be complete")
    inputs, manifest, _, _ = api.helper._data(source_run / "data")
    if len(inputs) != 30 or len({m["source_id"] for m in manifest}) != 30:
        raise ValueError("Expected thirty fixed requests from thirty sources")
    settings = frozen_settings(api, original["settings"])
    output.mkdir(parents=True)
    copies = {"runner.py": snapshot(Path(__file__), output / "runner.py"),
              "tests.py": snapshot(tests, output / "tests.py"),
              "PLAN.md": snapshot(plan, output / "PLAN.md")}
    value = {"schema_version": SCHEMA, "created_at": api.helper._now(),
        "source_run": str(source_run.resolve()), "python_version": platform.python_version(),
        "origin_files_sha256": {name: sha(source_run / name) for name in ORIGIN_FILES},
        "original_code_files_sha256": original["code_files_sha256"],
        "wrapper_files_sha256": copies,
        "new_backends": list(NEW_BACKENDS), "all_scored_backends": list(ALL_BACKENDS),
        "request_count": 30, "expected_new_records": 60,
        "settings": api.helper.public_settings(settings),
        "backend_execution": {
            "baseline": {"llm": False, "prompt": None, "provider_calls": 0,
                         "implementation_sha256": original["code_files_sha256"]["grounding/baseline.py"]},
            "minimal": {"llm": True, "prompts": api.prompts.prompt_metadata("minimal"),
                        "max_provider_attempts_per_nonempty_request": 1,
                        "effective_upstream_retries": 0, "effective_format_repairs": 0,
                        "implementation_sha256": original["code_files_sha256"]["grounding/verifiers.py"]}},
        "run_options": {"workers": 4, "seed": SEED,
            "schedule": "sha256(seed|source_id|response_id|backend), response_id, backend",
            "verifier_lifetime": "one new verifier per response/backend; no reruns"},
        "price_reference": original["price_reference"],
        "qualification": "Same thirty requests; exposed exploratory comparison, not new unseen acceptance. Original v4 predictions reused unchanged; runs are not contemporaneous or randomized/interleaved across all three backends. Runtime/cost differences can include provider time and cache effects.",
        "gold_policy": "Only opaque hashes before score; inference receives context_passages and generated_answer only",
        "original_not_certified_untouched": original["not_certified_untouched"]}
    api.helper._write_json(output / "freeze.json", value, exclusive=True)
    (output / "freeze.sha256").write_text(sha(output / "freeze.json") + "\n", encoding="ascii", newline="\n")
    check(output, api, require_copy=False)
    return {"status": "frozen", "new_records": 60, "reused_v4_records": 30, "model_calls": 0}


def check(output, api, *, require_copy=True):
    if sha(output / "freeze.json") != (output / "freeze.sha256").read_text().strip():
        raise ValueError("Comparator freeze changed")
    value = read_object(output / "freeze.json")
    if value.get("schema_version") != SCHEMA or value.get("new_backends") != list(NEW_BACKENDS):
        raise ValueError("Unexpected comparator schema/backends")
    if value["python_version"] != platform.python_version():
        raise ValueError("Python changed since freeze")
    source_run = Path(value["source_run"])
    original = api.helper.check_freeze(source_run, bound=True)
    if original["code_files_sha256"] != value["original_code_files_sha256"]:
        raise ValueError("Original frozen source manifest changed")
    for name, digest in value["origin_files_sha256"].items():
        if sha(source_run / name) != digest:
            raise ValueError("Original artifact changed: " + name)
    for name, digest in value["wrapper_files_sha256"].items():
        if sha(output / name) != digest:
            raise ValueError("Comparator wrapper/plan changed: " + name)
    if require_copy and Path(__file__).resolve() != (output / "runner.py").resolve():
        raise ValueError("Execution must use the copied frozen wrapper")
    api.guard()
    return value


def infer_one(case, meta, backend, settings, api, factory=None):
    if backend not in NEW_BACKENDS:
        raise ValueError("Only new comparator backends may run")
    factory = factory or api.helper.build_verifier
    started, stamp = time.monotonic(), api.helper._now()
    prediction, error, telemetry = None, None, {"calls": []}
    citations, validation_errors = {"citation_count": 0, "valid_citation_count": 0}, []
    try:
        request = api.contracts.VerificationRequest.from_dict(case["input"])
        result = factory(backend, settings).verify(request)
        prediction, telemetry = result.report, result.telemetry or telemetry
        api.contracts.validate_report(prediction, request.context_passages)
        citations = api.helper._citation_counts(prediction, request.context_passages)
    except api.contracts.VerificationError as exc:
        if prediction is None:
            telemetry = exc.telemetry or telemetry
        prediction = None
        error = {"code": exc.code, "message": exc.message, "status": exc.status}
        if exc.code == "invalid_model_output":
            validation_errors = [exc.message]
    except Exception as exc:
        prediction = None
        error = {"code": "unexpected_error", "type": type(exc).__name__}
        telemetry = getattr(exc, "telemetry", None) or telemetry
    return api.helper._redact({"id": case["id"],
        **{k: meta[k] for k in ("source_id", "task_type", "generator", "input_sha256")},
        "backend": backend, "prediction": prediction, "error": error, "telemetry": telemetry,
        "schema_valid": error is None, "validation_errors": validation_errors, "citations": citations,
        "answer_chars": len(case["input"]["generated_answer"]), "latency_seconds": time.monotonic() - started,
        "started_at": stamp, "completed_at": api.helper._now()}, settings.api_key)


def require_pairs(records, inputs, backends):
    ids = [case["id"] for case in inputs]
    expected = {(identifier, backend) for identifier in ids for backend in backends}
    actual = [(row.get("id"), row.get("backend")) for row in records]
    if (len(ids) != len(set(ids)) or len(actual) != len(expected)
            or len(actual) != len(set(actual)) or set(actual) != expected):
        raise ValueError("Journal must contain each expected response/backend exactly once")


def combine_records(new, original, inputs):
    require_pairs(new, inputs, NEW_BACKENDS)
    require_pairs(original, inputs, ("optimized-v4.0",))
    # Neither the old journal nor its objects are changed or relabelled.
    return [*new, *original]


def run(output, env_file, api):
    value = check(output, api)
    settings = frozen_settings(api, value["settings"], env_file)
    if not settings.api_key:
        raise ValueError("Model credential is missing")
    inputs, manifest, _, _ = api.helper._data(Path(value["source_run"]) / "data")
    for name in ("predictions.jsonl", "progress.json"):
        if (output / name).exists():
            raise FileExistsError("Refusing to rerun or overwrite comparator inference")
    jobs = [(case, meta, backend) for case, meta in zip(inputs, manifest) for backend in NEW_BACKENDS]
    jobs.sort(key=lambda job: (hashlib.sha256("|".join((SEED, job[1]["source_id"], job[0]["id"], job[2])).encode()).hexdigest(), job[0]["id"], job[2]))
    progress = {"status": "running", "started_at": api.helper._now(), "gold_loaded": False,
        "expected_records": 60, "completed_records": 0, "error_records": 0,
        "by_backend": {b: {"completed_records": 0, "error_records": 0} for b in NEW_BACKENDS}}
    api.helper._write_json(output / "progress.json", progress, exclusive=True)
    try:
        with (output / "predictions.jsonl").open("xb") as journal, ThreadPoolExecutor(max_workers=value["run_options"]["workers"]) as pool:
            futures = [pool.submit(infer_one, case, meta, backend, settings, api) for case, meta, backend in jobs]
            for future in as_completed(futures):
                record = future.result()
                journal.write((json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n").encode())
                journal.flush()
                os.fsync(journal.fileno())
                progress["completed_records"] += 1
                progress["error_records"] += record["error"] is not None
                progress["by_backend"][record["backend"]]["completed_records"] += 1
                progress["by_backend"][record["backend"]]["error_records"] += record["error"] is not None
                api.helper._write_json(output / "progress.json", progress)
        check(output, api)
        progress.update(status="completed", frozen_artifacts_unchanged=True)
    except BaseException:
        progress["status"] = "interrupted_or_failed"
        raise
    finally:
        progress["completed_at"] = api.helper._now()
        api.helper._write_json(output / "progress.json", progress)
    return progress


def score(output, api):
    value = check(output, api)
    progress = read_object(output / "progress.json")
    if (progress.get("status") != "completed" or progress.get("completed_records") != 60
            or progress.get("frozen_artifacts_unchanged") is not True):
        raise ValueError("Scoring requires all sixty comparator records")
    source_run = Path(value["source_run"])
    inputs, manifest, _, _ = api.helper._data(source_run / "data")
    records = combine_records(api.helper.load_prediction_journal(output / "predictions.jsonl"),
        api.helper.load_prediction_journal(source_run / "predictions.jsonl"), inputs)
    gold = api.helper._jsonl(source_run / "data/native_gold.jsonl")
    result = api.helper.score_records(records, manifest, gold, backends=list(ALL_BACKENDS), inputs=inputs,
        bootstrap_samples=2000, seed=20261023, prices=value["price_reference"])
    result["qualification"] = value["qualification"]
    result["runtime_by_backend"] = {backend: api.helper.runtime_summary(
        [r for r in records if r["backend"] == backend], value["price_reference"]) for backend in ALL_BACKENDS}
    result["input_hashes"] = {"freeze.json": sha(output / "freeze.json"),
        "new_predictions.jsonl": sha(output / "predictions.jsonl"),
        "original_predictions.jsonl": sha(source_run / "predictions.jsonl"),
        "native_gold.jsonl": sha(source_run / "data/native_gold.jsonl")}
    check(output, api)
    destination = output / "scored"
    destination.mkdir(exist_ok=False)
    api.helper._write_json(destination / "report.json", result, exclusive=True)
    (destination / "report.md").write_text(api.helper.render_report(result), encoding="utf-8", newline="\n")
    return {"scored_records": len(records), "new_records": 60, "reused_v4_records": 30,
            "output_dir": str(destination), "model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "score"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, default=ROOT / "results/ragtruth-small30-20261023")
    parser.add_argument("--plan", type=Path, default=ROOT / "reports/ragtruth-small30-comparators-20261023/PLAN.md")
    parser.add_argument("--tests", type=Path, default=ROOT / "tests/test_ragtruth_small30_comparators.py")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if args.command != "freeze" and not args.frozen:
        value = read_object(output / "freeze.json")
        if (sha(output / "freeze.json") != (output / "freeze.sha256").read_text().strip()
                or value.get("schema_version") != SCHEMA
                or sha(output / "runner.py") != value["wrapper_files_sha256"]["runner.py"]):
            raise ValueError("Cannot execute a changed frozen wrapper")
        return subprocess.call([sys.executable, str(output / "runner.py"), args.command,
            "--output-dir", str(output), "--env-file", str(args.env_file.resolve()), "--frozen"], cwd=output)
    source_run = args.source_run.resolve() if args.command == "freeze" else Path(read_object(output / "freeze.json")["source_run"])
    api = bind_frozen_imports(source_run)
    if args.command == "freeze":
        result = freeze(output, source_run, args.plan.resolve(), args.tests.resolve(), api)
    elif args.command == "run":
        result = run(output, args.env_file.resolve(), api)
    else:
        result = score(output, api)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
