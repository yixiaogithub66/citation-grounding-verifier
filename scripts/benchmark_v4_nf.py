#!/usr/bin/env python3
"""Frozen, offline-only pre/post NF occurrence experiment on exposed inputs.

Prepare performs no model calls. Run executes this script's frozen copy, with
separate module globals for the two implementations; no production alias changes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.config_v4 import V4Config, load_v4_config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.contracts_v4 import validate_v4_report
from grounding.prompts_v4 import prompt_metadata
from scripts.benchmark_ragtruth import (
    _citation_counts, _data, _jsonl, _now, _redact, _selection, _sha,
    _write_json, public_settings, reserve_exposure,
)
from scripts.ragtruth_v4 import code_hashes

SCHEMA = "v4-nf-occurrence-fresh-paired-exposed-v1"
PRE_COMMIT = "1106c2b"
POST_COMMIT = "e78fa35"
VARIANTS = ("pre_fix", "post_fix")
PRICES = {"input_per_million": 0.30, "cached_input_per_million": 0.006,
          "output_per_million": 1.20, "currency": "USD",
          "reference": "fixed prior experiment reference, not current pricing or billing"}


def _copy(source: Path, target: Path) -> str:
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def balanced_schedule(cases: list[dict], seed: int) -> list[dict]:
    """Freeze exact balance within evaluator strata; never expose strata to models."""
    groups = defaultdict(list)
    for case in cases:
        if case["dataset"] == "dev":
            group = "dev:" + case["meta"]["source_id"]
        elif case["dataset"] == "behavior":
            group = "behavior:" + case["meta"]["pair_id"]
        elif case["dataset"] == "physics":
            group = "physics:all"
        else:
            raise ValueError("Unregistered scheduling dataset")
        groups[group].append(case)
    schedule = {}
    for group, rows in groups.items():
        if len(rows) % 2:
            raise ValueError("Balanced scheduling requires an even stratum size")
        ranked = sorted(rows, key=lambda row: hashlib.sha256(
            f"{seed}:{group}:{row['dataset']}:{row['id']}".encode("utf-8")).hexdigest())
        for index, row in enumerate(ranked):
            schedule[(row["dataset"], row["id"])] = (group, list(VARIANTS if index < len(ranked) // 2 else VARIANTS[::-1]))
    return [{**case, "schedule_group": schedule[(case["dataset"], case["id"])][0],
             "backend_order": schedule[(case["dataset"], case["id"])][1]} for case in cases]


def prepare(output_dir: Path, settings, config: V4Config, *, project_root=ROOT) -> dict:
    """Freeze all executable dependencies and opaque evaluation artifacts."""
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError("Refusing to overwrite an experiment directory")
    settings.validate()
    config.validate()
    dev = project_root / "dataset/ragtruth-blind-v1/recovery"
    inputs, manifest, prep, data_hashes = _data(dev)  # Native gold is not parsed.
    if prep.get("seed") != "ragtruth-blind-v1-20261022" or len(inputs) != 180:
        raise ValueError("This registered experiment requires the exposed v1 180 inputs")
    auxiliary_paths = {"data/behavior/pairs.jsonl": project_root / "dataset/v4-behavioral-ai-draft/pairs.jsonl",
                       "data/physics/cases.jsonl": project_root / "dataset/cphos28/cases.jsonl"}
    auxiliary_hashes = {name: _sha(path) for name, path in auxiliary_paths.items()}
    behavior = _jsonl(auxiliary_paths["data/behavior/pairs.jsonl"])
    physics = _jsonl(auxiliary_paths["data/physics/cases.jsonl"])
    if len(behavior) != 24 or len(physics) != 46:
        raise ValueError("This registered experiment requires 24 behavior pairs and 46 physics inputs")
    requests = [{"dataset": "dev", "id": c["id"], "input": c["input"],
                 "meta": {k: m[k] for k in ("source_id", "task_type", "generator", "input_sha256")}}
                for c, m in zip(inputs, manifest)]
    requests += [{"dataset": "behavior", "id": p["id"] + "/" + side,
                  "input": p[side]["input"], "meta": {"pair_id": p["id"], "side": side}}
                 for p in behavior for side in ("base", "variant")]
    requests += [{"dataset": "physics", "id": c["id"], "input": c["input"], "meta": {}}
                 for c in physics]
    if len({(c["dataset"], c["id"]) for c in requests}) != len(requests):
        raise ValueError("Duplicate request identity")
    for case in requests:
        VerificationRequest.from_dict(case["input"])
    requests = balanced_schedule(requests, 20261023)
    commit = subprocess.check_output(["git", "rev-parse", PRE_COMMIT], cwd=project_root, text=True).strip()
    post_commit = subprocess.check_output(["git", "rev-parse", POST_COMMIT], cwd=project_root, text=True).strip()
    old_module = subprocess.check_output(["git", "show", commit + ":grounding/verifiers_v4.py"], cwd=project_root)
    post_module = subprocess.check_output(["git", "show", post_commit + ":grounding/verifiers_v4.py"], cwd=project_root)
    if post_module != (project_root / "grounding/verifiers_v4.py").read_bytes():
        raise ValueError("Post-fix inference differs from its registered commit")
    plan = project_root / "reports/v4-nf-live-20261023/plan.md"
    if not plan.is_file():
        raise ValueError("Register the experiment plan before preparing")
    hashes = code_hashes(project_root)
    # Both arms use identical shared dependencies, not a partial version hybrid.
    for name in hashes:
        if (name.startswith("grounding/") and name != "grounding/verifiers_v4.py") or name == "scripts/validate_dataset.py":
            old = subprocess.check_output(["git", "show", commit + ":" + name], cwd=project_root)
            if old != (project_root / name).read_bytes():
                raise ValueError("Shared inference dependency differs from pre-fix commit: " + name)
    output_dir.mkdir(parents=True, exist_ok=False)
    bound = {}
    for name, digest in hashes.items():
        relative = "source/" + name
        bound[relative] = _copy(project_root / name, output_dir / relative)
        if bound[relative] != digest:
            raise ValueError("Source changed during freeze: " + name)
    old_path = output_dir / "pre_fix/grounding/verifiers_v4.py"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(old_module)
    bound[old_path.relative_to(output_dir).as_posix()] = _sha(old_path)
    for name, digest in data_hashes.items():
        relative = "data/dev/" + name
        bound[relative] = _copy(dev / name, output_dir / relative)
        if bound[relative] != digest:
            raise ValueError("Data changed during freeze: " + name)
    for relative, source in auxiliary_paths.items():
        bound[relative] = _copy(source, output_dir / relative)
        if bound[relative] != auxiliary_hashes[relative]:
            raise ValueError("Supplementary data changed during freeze: " + relative)
    bound["plan.md"] = _copy(plan, output_dir / "plan.md")
    request_path = output_dir / "requests.jsonl"
    with request_path.open("x", encoding="utf-8", newline="\n") as stream:
        for case in requests:
            stream.write(json.dumps(case, ensure_ascii=True, allow_nan=False) + "\n")
    bound["requests.jsonl"] = _sha(request_path)
    _write_json(output_dir / "v4-config.json", config.public_dict(), exclusive=True)
    bound["v4-config.json"] = _sha(output_dir / "v4-config.json")
    if code_hashes(project_root) != hashes:
        raise ValueError("Source changed during freeze; no inference started")
    metadata = {
        "schema_version": SCHEMA, "status": "prepared_no_model_calls", "created_at": _now(),
        "project_root": str(project_root), "pre_fix_commit": commit,
        "post_fix_commit": post_commit,
        "runner_checkout_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root, text=True).strip(),
        "qualification": "Exposed development/regression comparison; not unseen or author adjudication",
        "intervention": "Only NF occurrence accounting in original optimized-v4.0; unchanged M1/M3 prompts and budgets",
        "backends": list(VARIANTS), "settings": public_settings(settings), "v4_config": config.public_dict(),
        "prompts": prompt_metadata(), "python_version": platform.python_version(),
        "run_options": {"workers": 4, "seed": 20261023,
                        "per_case_variant_order": "sha256-ranked exact 50/50 first-variant balance per dev source, behavior pair, physics full group; sequential variants"},
        "expected_cases": 274, "expected_records": 548, "case_counts": {"dev": 180, "behavior": 48, "physics": 46},
        "price_reference": PRICES, "selection": _selection(inputs, manifest),
        "data_files_sha256": data_hashes, "files_sha256": bound,
        "gold_loaded_by_inference": False,
        "label_policy": "Native gold is opaque; behavior/physics annotations are loaded only to select ordinary inputs, never supplied to inference",
        "shared_inference_dependencies_byte_identical": True,
    }
    _write_json(output_dir / "config.json", _redact(metadata, settings.api_key), exclusive=True)
    (output_dir / "config.sha256").write_text(_sha(output_dir / "config.json") + "\n", encoding="ascii")
    verify_freeze(output_dir)
    return metadata


def verify_freeze(run_dir: Path) -> dict:
    if _sha(run_dir / "config.json") != (run_dir / "config.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Experiment manifest changed")
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if config.get("schema_version") != SCHEMA or config.get("backends") != list(VARIANTS):
        raise ValueError("Unexpected experiment schema or variant pair")
    for relative, digest in config["files_sha256"].items():
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir.resolve()) or _sha(path) != digest:
            raise ValueError("Frozen artifact mismatch: " + relative)
    return config


def frozen_factory(run_dir: Path):
    from grounding.verifiers_v4 import OptimizedV4Verifier
    spec = importlib.util.spec_from_file_location("grounding._nf_pre_fix", run_dir / "pre_fix/grounding/verifiers_v4.py")
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen pre-fix implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    classes = {"pre_fix": module.OptimizedV4Verifier, "post_fix": OptimizedV4Verifier}
    def build(variant, settings, config):
        return classes[variant](settings, config=config)
    return build


def run_records(cases, run_dir, settings, config, factory, *, workers=4, seed=20261023):
    """Inference-only journal. Factory receives no dataset, identity or labels."""
    progress = {"status": "running", "completed_records": 0, "expected_records": len(cases) * 2,
                "error_records": 0, "partial_records": 0, "started_at": _now()}
    _write_json(run_dir / "progress.json", progress, exclusive=True)
    lock = threading.Lock()
    def work(case, stream):
        order = case["backend_order"]
        if sorted(order) != sorted(VARIANTS):
            raise ValueError("Every case requires both variants exactly once")
        for position, variant in enumerate(order):
            started, started_at = time.monotonic(), _now()
            prediction, error, telemetry = None, None, {"calls": []}
            citations, validation_errors = {"citation_count": 0, "valid_citation_count": 0}, []
            try:
                request = VerificationRequest.from_dict(case["input"])
                result = factory(variant, settings, config).verify(request)
                prediction, telemetry = result.report, result.telemetry
                validate_v4_report(prediction, request.context_passages)
                citations = _citation_counts(prediction, request.context_passages)
            except VerificationError as exc:
                # Public validation errors have an empty default telemetry;
                # retain the already returned calls and their usage in that case.
                if prediction is None:
                    telemetry = exc.telemetry or telemetry
                prediction = None
                error = {"code": exc.code, "message": exc.message, "status": exc.status}
                if exc.code == "invalid_model_output":
                    validation_errors = [exc.message]
            except Exception as exc:
                prediction = None
                error = {"code": "unexpected_error", "type": type(exc).__name__}
            record = _redact({"dataset": case["dataset"], "id": case["id"], **case.get("meta", {}),
                              "backend": variant, "variant": variant, "prediction": prediction,
                              "error": error, "telemetry": telemetry, "schema_valid": error is None,
                              "validation_errors": validation_errors, "citations": citations,
                              "answer_chars": len(case["input"]["generated_answer"]),
                              "latency_seconds": time.monotonic() - started, "started_at": started_at,
                              "completed_at": _now(), "backend_order": order, "backend_order_index": position}, settings.api_key)
            with lock:
                stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                progress["completed_records"] += 1
                progress["error_records"] += error is not None
                progress["partial_records"] += bool(prediction and prediction.get("status") == "partial")
                _write_json(run_dir / "progress.json", progress)
                print(f"[{progress['completed_records']}/{progress['expected_records']}] {case['dataset']} {variant} stored", flush=True)
    try:
        with (run_dir / "responses.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = [pool.submit(work, case, stream) for case in cases]
                for job in as_completed(jobs):
                    job.result()
        progress["status"] = "completed"
    except BaseException as exc:
        progress["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        raise
    finally:
        progress["completed_at"] = _now()
        _write_json(run_dir / "progress.json", progress)
    return progress


def run_frozen(run_dir: Path, settings) -> dict:
    metadata = verify_freeze(run_dir)
    if ROOT.resolve() != (run_dir / "source").resolve():
        raise ValueError("Real inference must execute the frozen runner")
    if public_settings(settings) != metadata["settings"] or not settings.api_key:
        raise ValueError("Model settings changed after freeze or key missing")
    if platform.python_version() != metadata["python_version"]:
        raise ValueError("Python version changed after freeze")
    if (run_dir / "progress.json").exists() or (run_dir / "responses.jsonl").exists():
        raise FileExistsError("Run already started; no selective reruns or overwrite")
    cases = _jsonl(run_dir / "requests.jsonl")
    if len(cases) != metadata["expected_cases"]:
        raise ValueError("Frozen request count mismatch")
    if cases != balanced_schedule(cases, metadata["run_options"]["seed"]):
        raise ValueError("Frozen balanced schedule mismatch")
    config = V4Config.from_dict(metadata["v4_config"])
    factory = frozen_factory(run_dir)
    ledger_path, ledger = reserve_exposure(metadata["selection"], run_dir,
        ledger_dir=Path(metadata["project_root"]) / "results/ragtruth-ledger", replicate=True, smoke=False,
        freeze_sha256=_sha(run_dir / "config.json"), data_files_sha256=metadata["data_files_sha256"], secret=settings.api_key)
    ledger["mode"] = "exposed-dev-nf-occurrence-pre-post"
    _write_json(ledger_path, ledger)
    progress = {"status": "failed", "completed_records": 0}
    try:
        progress = run_records(cases, run_dir, settings, config, factory, **{
            k: metadata["run_options"][k] for k in ("workers", "seed")})
        verify_freeze(run_dir)
        progress["frozen_artifacts_unchanged"] = True
        _write_json(run_dir / "progress.json", progress)
        return progress
    except BaseException:
        if (run_dir / "progress.json").exists():
            progress = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
        if progress["status"] == "completed":
            progress["status"] = "invalidated_changed_artifacts"
            progress["frozen_artifacts_unchanged"] = False
            _write_json(run_dir / "progress.json", progress)
        raise
    finally:
        ledger.update(status=progress["status"], completed_at=_now(), completed_records=progress["completed_records"])
        _write_json(ledger_path, ledger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--v4-config", type=Path, default=ROOT / "configs/optimized-v4.0.json")
    prep.add_argument("--env-file", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--env-file", type=Path, required=True)
    run.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == "run" and not args.frozen:
        run_dir = args.run_dir.resolve()
        verify_freeze(run_dir)
        command = [sys.executable, str(run_dir / "source/scripts/benchmark_v4_nf.py"), "run",
                   "--run-dir", str(run_dir), "--env-file", str(args.env_file.resolve()), "--frozen"]
        raise SystemExit(subprocess.call(command, cwd=run_dir / "source"))
    settings = load_settings(env_file=args.env_file.resolve(), thinking="enabled")
    result = (prepare(args.output_dir, settings, load_v4_config(args.v4_config)) if args.command == "prepare"
              else run_frozen(args.run_dir.resolve(), settings))
    print(json.dumps({k: result[k] for k in ("status", "expected_records") if k in result}, ensure_ascii=True))


if __name__ == "__main__":
    main()
