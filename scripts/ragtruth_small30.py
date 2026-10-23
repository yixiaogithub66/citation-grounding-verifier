#!/usr/bin/env python3
"""Frozen exploratory RAGTruth 30-response evaluation, separate from formal v2.

Only freeze reads before raw-data selection; prepare/run/score execute frozen
copies. Runtime receives ordinary two-field requests, never sampling metadata.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.config_v4 import V4Config, load_v4_config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.contracts_v4 import validate_v4_report
from grounding.factory import build_verifier
from grounding.prompts_v4 import prompt_metadata
from scripts import ragtruth_data as adapter
from scripts.benchmark_ragtruth import (_canonical_sha, _citation_counts, _data,
    _jsonl, _now, _object, _redact, _selection, _sha, _write_json,
    public_settings, reserve_exposure, DATA_FILES)
from scripts.ragtruth_v4 import code_hashes, _exposure_snapshot
from scripts.benchmark_v4_nf import PRICES
from scripts.analyze_v4_nf import runtime_summary
from scripts.score_v4 import score_records, load_prediction_journal, render_report

SCHEMA = "ragtruth-exploratory-small30-v1"
SEED = "ragtruth-current-small30-20261023-v1"
BACKEND = "optimized-v4.0"


def _rank(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _snapshot(source: Path, target: Path, expected: str) -> None:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Frozen source changed during snapshot")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def freeze(output: Path, exclusions: Path, settings, config: V4Config, *,
           old_preparation: Path, raw_dir: Path, project_root: Path = ROOT) -> dict:
    """Bind code/config/seed/exclusions and opaque raw hashes before parsing raw."""
    if output.exists():
        raise FileExistsError("Exploratory evaluation directory already exists")
    audit = _object(exclusions)
    excluded = audit.get("excluded_source_ids")
    if (not isinstance(audit.get("schema_version"), str) or not isinstance(excluded, list)
            or any(not isinstance(s, str) or not s for s in excluded)
            or len(excluded) != len(set(excluded))):
        raise ValueError("Exclusion manifest needs schema_version and unique excluded_source_ids")
    for name, digest in audit.get("evidence_files_sha256", {}).items():
        if _sha(Path(name)) != digest:
            raise ValueError("Exposure audit evidence changed")
    ledger_dir = project_root / "results/ragtruth-ledger"
    exposed, ledger_hashes = _exposure_snapshot([ledger_dir])
    if exposed - set(excluded):
        raise ValueError("Exclusion audit misses a source from the canonical ledger")
    old = _object(old_preparation)
    if old.get("seed") != "ragtruth-blind-v1-20261022":
        raise ValueError("Pin raw bytes using original v1 preparation provenance")
    raw_hashes = {name: old["raw_files_sha256"][name]
                  for name in ("source_info.jsonl", "response.jsonl", "provenance.json")}
    for name, digest in raw_hashes.items():
        if _sha(raw_dir / name) != digest:
            raise ValueError("Pinned raw file hash mismatch")
    hashes = code_hashes(project_root)
    plan = project_root / "reports/ragtruth-small30-20261023/PLAN.md"
    plan_sha = _sha(plan)
    config.validate()
    settings.validate()
    output.mkdir(parents=True)
    for name, digest in hashes.items():
        _snapshot(project_root / name, output / "source" / name, digest)
    _snapshot(exclusions, output / "exposure-audit.json", _sha(exclusions))
    _snapshot(plan, output / "PLAN.md", plan_sha)
    value = {"schema_version": SCHEMA, "created_at": _now(),
        "qualification": "Exploratory 30 disjoint from known source registry; literature exposure remains unresolved, untouched status not certified; not formal v2 acceptance or a paired comparison",
        "project_root": str(project_root.resolve()), "raw_dir": str(raw_dir.resolve()),
        "backend": BACKEND, "settings": public_settings(settings), "v4_config": config.public_dict(),
        "prompts": prompt_metadata(), "python_version": platform.python_version(),
        "code_files_sha256": hashes, "upstream_raw_sha256": raw_hashes,
        "exposure_audit_sha256": _sha(output / "exposure-audit.json"),
        "plan_sha256": plan_sha, "not_certified_untouched": audit.get("not_certified_untouched", True),
        "exposure_ledger_files_sha256": ledger_hashes,
        "sampling": {"seed": SEED, "split": "test", "tasks": list(adapter.TASKS),
            "sources_per_task": 10, "responses_per_source": 1, "quality": "good",
            "source_order": "sha256(seed|task_type|source_id), source_id",
            "response_order": "sha256(seed|response|source_id|response_id), response_id",
            "excluded_source_ids": sorted(excluded),
            "eligibility": "At least one good response; all good responses must pass unchanged input contract. No truncation.",
            "labels_or_generator_used_for_selection": False},
        "run_options": {"workers": 4}, "price_reference": PRICES,
        "gold_policy": "No new raw records parsed before freeze; native labels validated only after selection; inference hashes gold as opaque bytes"}
    if code_hashes(project_root) != hashes:
        raise ValueError("Source changed during freeze")
    _write_json(output / "preselection.json", _redact(value, settings.api_key), exclusive=True)
    (output / "preselection.sha256").write_text(_sha(output / "preselection.json") + "\n", encoding="ascii")
    return value


def check_freeze(output: Path, *, bound: bool = False) -> dict:
    if _sha(output / "preselection.json") != (output / "preselection.sha256").read_text().strip():
        raise ValueError("Preselection manifest changed")
    frozen = _object(output / "preselection.json")
    if frozen.get("schema_version") != SCHEMA or frozen.get("backend") != BACKEND:
        raise ValueError("Unexpected exploratory evaluation schema/backend")
    if platform.python_version() != frozen["python_version"]:
        raise ValueError("Frozen Python version changed")
    for name, digest in frozen["code_files_sha256"].items():
        destination = (output / "source" / name).resolve()
        if not destination.is_relative_to((output / "source").resolve()) or _sha(destination) != digest:
            raise ValueError("Frozen code changed: " + name)
    if _sha(output / "exposure-audit.json") != frozen["exposure_audit_sha256"]:
        raise ValueError("Frozen source exclusions changed")
    if _sha(output / "PLAN.md") != frozen["plan_sha256"]:
        raise ValueError("Frozen evaluation plan changed")
    if bound:
        if _sha(output / "binding.json") != (output / "binding.sha256").read_text().strip():
            raise ValueError("Prepared data binding changed")
        binding = _object(output / "binding.json")
        if binding["preselection_sha256"] != _sha(output / "preselection.json"):
            raise ValueError("Prepared data refers to a different freeze")
        for name, digest in binding["data_files_sha256"].items():
            if name not in DATA_FILES or _sha(output / "data" / name) != digest:
                raise ValueError("Prepared dataset changed")
    return frozen


def _check_exposure(frozen: dict, own_sources: set[str] | None = None) -> None:
    exposed, hashes = _exposure_snapshot([Path(frozen["project_root"]) / "results/ragtruth-ledger"])
    if any(hashes.get(path) != digest for path, digest in frozen["exposure_ledger_files_sha256"].items()):
        raise ValueError("Prior exposure ledger changed")
    if exposed - set(frozen["sampling"]["excluded_source_ids"]) - (own_sources or set()):
        raise ValueError("Additional source exposure since freeze; refresh exclusions before selection")


def select_records(sources: list[dict], responses: list[dict], policy: dict) -> tuple[list[dict], list[dict]]:
    """Mechanical label-blind selection; no labels are validated or inspected here."""
    by_source, groups, splits, ids = {}, defaultdict(list), defaultdict(set), set()
    for source in sources:
        sid = adapter._identifier(source, "source_id")
        if sid in by_source or source.get("task_type") not in adapter.TASKS:
            raise ValueError("Duplicate source or unknown task")
        by_source[sid] = source
    for response in responses:
        sid, rid = adapter._identifier(response, "source_id"), adapter._identifier(response, "id")
        if rid in ids or sid not in by_source or response.get("split") not in ("train", "test"):
            raise ValueError("Invalid response identity/join/split")
        ids.add(rid)
        adapter._identifier(response, "quality")
        if not isinstance(response.get("response"), str):
            raise ValueError("Response must be text")
        groups[sid].append(response)
        splits[sid].add(response["split"])
    if any(len(values) != 1 for values in splits.values()):
        raise ValueError("Source crosses official splits")
    selected, exclusions = [], []
    excluded = set(policy["excluded_source_ids"])
    for task in policy["tasks"]:
        candidates = [sid for sid in groups if splits[sid] == {policy["split"]}
                      and by_source[sid]["task_type"] == task and sid not in excluded]
        ranked = sorted(candidates, key=lambda sid: (_rank(policy["seed"], task, sid), sid))
        count = 0
        for sid in ranked:
            good = [row for row in groups[sid] if row["quality"] == policy["quality"]]
            if not good:
                exclusions.append({"source_id": sid, "task_type": task, "reason": "no_good_response"})
                continue
            contexts, mapping = adapter._adapt_source(by_source[sid])
            sizes, failures = {}, []
            for row in good:
                failure, size = adapter._preflight({"context_passages": contexts, "generated_answer": row["response"]})
                sizes[row["id"]] = size
                if failure:
                    failures.append({"id": row["id"], "reason": failure})
            if failures:
                exclusions.append({"source_id": sid, "task_type": task,
                                   "reason": "source_group_input_limit", "failures": failures})
                continue
            chosen = min(good, key=lambda row: (_rank(policy["seed"], "response", sid, row["id"]), row["id"]))
            selected.append({"source_id": sid, "task_type": task, "response": chosen,
                "contexts": contexts, "adapter": mapping, "request_size": sizes[chosen["id"]],
                "source_sample_key": _rank(policy["seed"], task, sid),
                "response_sample_key": _rank(policy["seed"], "response", sid, chosen["id"])})
            count += 1
            if count == policy["sources_per_task"]:
                break
        if count != policy["sources_per_task"]:
            raise ValueError("Insufficient eligible unexposed sources for task " + task)
    return selected, exclusions


def prepare(output: Path) -> dict:
    frozen = check_freeze(output)
    if (output / "data").exists() or (output / "binding.json").exists():
        raise FileExistsError("Prepared data already exists")
    _check_exposure(frozen)
    raw_dir = Path(frozen["raw_dir"])
    for name, digest in frozen["upstream_raw_sha256"].items():
        if _sha(raw_dir / name) != digest:
            raise ValueError("Raw input changed after freeze")
    selected, exclusions = select_records(adapter.load_jsonl(raw_dir / "source_info.jsonl"),
                                          adapter.load_jsonl(raw_dir / "response.jsonl"), frozen["sampling"])
    inputs, manifest = [], []
    for item in selected:
        row = item["response"]
        request = {"context_passages": item["contexts"], "generated_answer": row["response"]}
        inputs.append({"id": row["id"], "input": request})
        manifest.append({"id": row["id"], "source_id": item["source_id"], "task_type": item["task_type"],
            "generator": adapter._identifier(row, "model"), "quality": row["quality"], "upstream_split": row["split"],
            "input_sha256": _canonical_sha(request), **{k: item[k] for k in
                ("adapter", "request_size", "source_sample_key", "response_sample_key")}})
    selection = _selection(inputs, manifest)
    if len(inputs) != 30 or len(selection["source_ids"]) != 30:
        raise ValueError("Small evaluation must contain thirty different sources")
    # Reserve before writing selected texts/labels. Aborted preparation remains exposed.
    ledger_path, ledger = reserve_exposure(selection, output,
        ledger_dir=Path(frozen["project_root"]) / "results/ragtruth-ledger", replicate=False, smoke=False,
        freeze_sha256=_sha(output / "preselection.json"), data_files_sha256={})
    ledger.update(mode="exploratory-source-disjoint-small30", status="selected_preparation_in_progress",
                  qualification=frozen["qualification"])
    _write_json(ledger_path, ledger)
    try:
        gold = [{"id": item["response"]["id"], "source_id": item["source_id"],
                 "labels": adapter._validate_labels(item["response"])} for item in selected]
        for row in gold:
            row["has_hallucination"] = bool(row["labels"])
        data = output / "data"
        data.mkdir()
        for name, rows in (("inputs.jsonl", inputs), ("manifest.jsonl", manifest), ("native_gold.jsonl", gold)):
            adapter._write_json(data / name, rows, lines=True)
        prep = {"schema_version": SCHEMA + "-preparation", "created_at": _now(),
            "sampling": frozen["sampling"], "selection": selection, "adapter_version": adapter.ADAPTER_VERSION,
            "eligibility_exclusions": exclusions, "raw_files_sha256": frozen["upstream_raw_sha256"],
            "counts": {"responses": 30, "sources": 30, "per_task": 10},
            "native_gold_policy": "Original selected annotations preserved; invalid selected labels abort without replacement",
            "artifacts_sha256": {name: _sha(data / name) for name in DATA_FILES if name != "preparation.json"}}
        adapter._write_json(data / "preparation.json", prep)
        binding = {"schema_version": SCHEMA + "-binding", "created_at": _now(),
            "preselection_sha256": _sha(output / "preselection.json"),
            "data_files_sha256": {name: _sha(data / name) for name in DATA_FILES},
            "selection": selection, "exposure_ledger": str(ledger_path.resolve()), "exposure_run_id": ledger["run_id"]}
        _write_json(output / "binding.json", binding, exclusive=True)
        (output / "binding.sha256").write_text(_sha(output / "binding.json") + "\n", encoding="ascii")
        ledger.update(status="prepared_exposed_no_model_calls", data_files_sha256=binding["data_files_sha256"])
        _write_json(ledger_path, ledger)
        return prep["counts"]
    except BaseException:
        ledger.update(status="preparation_failed_source_still_exposed", completed_at=_now())
        _write_json(ledger_path, ledger)
        raise


def infer_one(case: dict, meta: dict, settings, config: V4Config, factory=build_verifier) -> dict:
    started, stamp = time.monotonic(), _now()
    prediction, error, telemetry = None, None, {"calls": []}
    citations, validation_errors = {"citation_count": 0, "valid_citation_count": 0}, []
    try:
        request = VerificationRequest.from_dict(case["input"])
        result = factory(BACKEND, settings, v4_config=config).verify(request)
        prediction, telemetry = result.report, result.telemetry or telemetry
        validate_v4_report(prediction, request.context_passages)
        citations = _citation_counts(prediction, request.context_passages)
    except VerificationError as exc:
        if prediction is None:
            telemetry = exc.telemetry or telemetry
        prediction = None
        error = {"code": exc.code, "message": exc.message, "status": exc.status}
        if exc.code == "invalid_model_output":
            validation_errors = [exc.message]
    except Exception as exc:
        prediction = None
        error = {"code": "unexpected_error", "type": type(exc).__name__}
    return _redact({"id": case["id"], **{k: meta[k] for k in ("source_id", "task_type", "generator", "input_sha256")},
        "backend": BACKEND, "prediction": prediction, "error": error, "telemetry": telemetry,
        "schema_valid": error is None, "validation_errors": validation_errors, "citations": citations,
        "answer_chars": len(case["input"]["generated_answer"]), "latency_seconds": time.monotonic() - started,
        "started_at": stamp, "completed_at": _now()}, settings.api_key)


def run(output: Path, settings) -> dict:
    frozen = check_freeze(output, bound=True)
    if ROOT.resolve() != (output / "source").resolve():
        raise ValueError("Inference must execute the frozen runner")
    if public_settings(settings) != frozen["settings"] or not settings.api_key:
        raise ValueError("Actual model settings differ from freeze or key missing")
    inputs, manifest, _, hashes = _data(output / "data")
    binding = _object(output / "binding.json")
    if hashes != binding["data_files_sha256"] or _selection(inputs, manifest) != binding["selection"]:
        raise ValueError("Prepared run bindings differ")
    _check_exposure(frozen, set(binding["selection"]["source_ids"]))
    ledger_path = Path(binding["exposure_ledger"])
    ledger = _object(ledger_path)
    if ledger.get("run_id") != binding["exposure_run_id"] or ledger.get("status") != "prepared_exposed_no_model_calls":
        raise ValueError("Run reservation is not a fresh prepared exposure")
    for name in ("predictions.jsonl", "progress.json"):
        if (output / name).exists():
            raise FileExistsError("Refusing to rerun or overwrite inference")
    config = V4Config.from_dict(frozen["v4_config"])
    progress = {"status": "running", "expected_records": len(inputs), "completed_records": 0,
                "partial_records": 0, "error_records": 0, "started_at": _now(), "gold_loaded": False}
    _write_json(output / "progress.json", progress, exclusive=True)
    ledger.update(status="running", started_at=progress["started_at"])
    _write_json(ledger_path, ledger)
    try:
        with (output / "predictions.jsonl").open("xb") as journal, ThreadPoolExecutor(max_workers=frozen["run_options"]["workers"]) as pool:
            futures = [pool.submit(infer_one, case, meta, settings, config) for case, meta in zip(inputs, manifest)]
            for future in as_completed(futures):
                record = future.result()
                journal.write((json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n").encode())
                journal.flush()
                os.fsync(journal.fileno())
                progress["completed_records"] += 1
                progress["error_records"] += record["error"] is not None
                progress["partial_records"] += bool(record["prediction"] and record["prediction"].get("status") == "partial")
                _write_json(output / "progress.json", progress)
        check_freeze(output, bound=True)
        progress["status"] = "completed"
        progress["frozen_artifacts_unchanged"] = True
    except BaseException:
        progress["status"] = "interrupted_or_failed"
        raise
    finally:
        progress["completed_at"] = _now()
        _write_json(output / "progress.json", progress)
        ledger.update(status=progress["status"], completed_at=progress["completed_at"],
                      completed_records=progress["completed_records"], error_records=progress["error_records"])
        _write_json(ledger_path, ledger)
    return progress


def score(output: Path) -> dict:
    frozen = check_freeze(output, bound=True)
    if ROOT.resolve() != (output / "source").resolve():
        raise ValueError("Scoring must execute the frozen scorer")
    progress = _object(output / "progress.json")
    if (progress.get("status") != "completed" or progress.get("frozen_artifacts_unchanged") is not True
            or progress.get("completed_records") != 30):
        raise ValueError("Scoring requires all thirty records and unchanged frozen artifacts")
    inputs, manifest, _, _ = _data(output / "data")
    gold = _jsonl(output / "data/native_gold.jsonl")
    records = load_prediction_journal(output / "predictions.jsonl")
    expected = {(case["id"], BACKEND) for case in inputs}
    if len(records) != 30 or len(expected) != 30 or {(r.get("id"), r.get("backend")) for r in records} != expected:
        raise ValueError("Scoring journal must exactly match frozen thirty response/backend pairs")
    result = score_records(records, manifest, gold, backends=[BACKEND], inputs=inputs,
                           bootstrap_samples=2000, seed=20261023, prices=frozen["price_reference"])
    result["qualification"] = frozen["qualification"]
    result["runtime"] = runtime_summary(records, frozen["price_reference"])
    result["input_hashes"] = {"preselection.json": _sha(output / "preselection.json"),
        "binding.json": _sha(output / "binding.json"), "predictions.jsonl": _sha(output / "predictions.jsonl")}
    destination = output / "scored"
    destination.mkdir(exist_ok=False)
    _write_json(destination / "report.json", result, exclusive=True)
    (destination / "report.md").write_text(render_report(result), encoding="utf-8")
    return {"scored_records": len(records), "output_dir": str(destination), "model_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "prepare", "run", "score"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exclusion-manifest", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "tmp/ragtruth-upstream")
    parser.add_argument("--old-preparation", type=Path, default=ROOT / "dataset/ragtruth-blind-v1/recovery/preparation.json")
    parser.add_argument("--v4-config", type=Path, default=ROOT / "configs/optimized-v4.0.json")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if args.command != "freeze" and not args.frozen:
        check_freeze(output, bound=args.command in ("run", "score"))
        return subprocess.call([sys.executable, str(output / "source/scripts/ragtruth_small30.py"), args.command,
            "--output-dir", str(output), "--env-file", str(args.env_file.resolve()), "--frozen"], cwd=output / "source")
    if args.command == "freeze":
        if args.exclusion_manifest is None:
            parser.error("freeze requires --exclusion-manifest")
        settings = load_settings(env_file=args.env_file.resolve(), thinking="enabled")
        freeze(output, args.exclusion_manifest.resolve(), settings, load_v4_config(args.v4_config),
               old_preparation=args.old_preparation.resolve(), raw_dir=args.raw_dir.resolve())
        result = {"status": "frozen_before_selection", "output_dir": str(output), "model_calls": 0}
    elif args.command == "prepare":
        if ROOT.resolve() != (output / "source").resolve():
            raise ValueError("Preparation must execute frozen adapter")
        result = {"status": "prepared", "counts": prepare(output), "model_calls": 0}
    elif args.command == "run":
        result = run(output, load_settings(env_file=args.env_file.resolve(), thinking="enabled"))
    else:
        result = score(output)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
