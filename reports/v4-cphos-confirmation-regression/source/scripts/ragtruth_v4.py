#!/usr/bin/env python3
"""Separate v4 freeze, source-held-out preparation and durable inference tools.

No command is run on import. Preselection freezes never parse test text or labels;
the inference runner hashes gold as opaque bytes. Historical tools stay unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import Settings, load_settings
from grounding.config_v4 import V4Config, load_v4_config
from grounding.contracts import VerificationError, VerificationRequest
from grounding.contracts_v4 import validate_v4_report
from grounding.factory import build_verifier
from scripts import ragtruth_data as adapter
from scripts.benchmark_ragtruth import (_canonical_sha, _citation_counts, _data, _jsonl, _now,
    _object, _prices, _redact, _run_options, _selection, _sha, _write_json, backend_order,
    public_settings, reserve_exposure, DATA_FILES)

BACKENDS = ("baseline", "minimal", "optimized-v3", "optimized-v4.0")
SELECTION_SEED = "ragtruth-blind-v2-20261022"
PRE_SCHEMA = "ragtruth-v4-preselection-freeze-v1"
FREEZE_SCHEMA = "ragtruth-v4-run-freeze-v1"
RUN_SCHEMA = "ragtruth-v4-inference-v1"


def code_hashes(root: Path = ROOT) -> dict[str, str]:
    """Hash every shared/new Python dependency, including adapters and scorers."""
    paths = [p for folder in ("grounding", "scripts") for p in (root / folder).rglob("*.py")]
    paths += list((root / "grounding").glob("*.json"))
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(paths)}


def _v4_public(config: V4Config | dict) -> dict:
    return (config if isinstance(config, V4Config) else V4Config.from_dict(config)).public_dict()


def _ledger_dirs(project_root: Path, extra: Path | None = None) -> list[Path]:
    return sorted({(project_root / "results/ragtruth-ledger").resolve(), *([extra.resolve()] if extra else [])})


def _exposure_snapshot(directories: list[Path]) -> tuple[set[str], dict[str, str]]:
    sources, hashes = set(), {}
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            value = _object(path)
            if (value.get("schema_version") != "ragtruth-exposure-v1" or not isinstance(value.get("source_ids"), list)
                    or any(not isinstance(s, str) or not s for s in value["source_ids"])):
                raise ValueError("Unknown source exposure ledger")
            sources.update(value["source_ids"])
            hashes[str(path.resolve())] = _sha(path)
    return sources, hashes


def create_preselection_freeze(old_data_dir: Path, path: Path, settings: Settings,
                              v4_config: V4Config | dict, *, ledger_dir: Path | None = None,
                              workers: int = 4, seed: int = 20261022,
                              selection_seed: str = SELECTION_SEED, prices: dict | None = None,
                              project_root: Path = ROOT) -> dict:
    if path.exists():
        raise FileExistsError("Preselection freeze already exists")
    if "v2" not in selection_seed or not selection_seed.strip():
        raise ValueError("New selection seed must contain v2")
    preparation = _object(old_data_dir / "preparation.json")
    if preparation.get("seed") != "ragtruth-blind-v1-20261022":
        raise ValueError("Exclude sources from the original exposed v1 selection")
    manifest = _jsonl(old_data_dir / "manifest.jsonl")
    if preparation.get("artifacts_sha256", {}).get("manifest.jsonl") != _sha(old_data_dir / "manifest.jsonl"):
        raise ValueError("Old v1 manifest no longer matches its preparation binding")
    old_groups = {task: sorted({m["source_id"] for m in manifest if m.get("task_type") == task}) for task in adapter.TASKS}
    recorded_groups = preparation.get("selected_source_ids", {})
    if (len(manifest) != 180 or len({m["id"] for m in manifest}) != 180
            or any(len(ids) != 10 for ids in old_groups.values())
            or any(count != 6 for count in Counter(m["source_id"] for m in manifest).values())
            or set(recorded_groups) != set(adapter.TASKS)
            or any(old_groups[task] != sorted(recorded_groups[task]) for task in adapter.TASKS)):
        raise ValueError("Old v1 manifest must preserve all thirty source groups and 180 responses")
    excluded = {m["source_id"] for m in manifest}
    ledger_dirs = _ledger_dirs(project_root, ledger_dir)
    exposed, ledger_hashes = _exposure_snapshot(ledger_dirs)
    excluded.update(exposed)
    common = public_settings(settings)
    if common["thinking"] != "enabled":
        raise ValueError("Comparators require the registered thinking=enabled setting")
    expected_raw = preparation["raw_files_sha256"]
    value = {"schema_version": PRE_SCHEMA, "created_at": _now(),
             "code_files_sha256": code_hashes(project_root), "python_version": platform.python_version(),
             "settings": common, "v4_config": _v4_public(v4_config), "backends": list(BACKENDS),
             "run_options": _run_options(workers, seed), "price_reference": _prices(prices),
             "sampling": {"seed": selection_seed, "split": "test", "sources_per_task": 10,
                          "quality": "good", "responses_per_source": 6, "tasks": list(adapter.TASKS),
                          "ordering": "sha256(seed|task_type|source_id), then source_id",
                          "excluded_source_ids": sorted(excluded), "gold_used_for_selection": False,
                          "incomplete_group_policy": "exclude sources without exactly six good responses before ranking"},
             "old_manifest_sha256": _sha(old_data_dir / "manifest.jsonl"),
             "old_preparation_sha256": _sha(old_data_dir / "preparation.json"),
             "exposure_ledger_files_sha256": ledger_hashes,
             "exposure_ledger_dirs": [str(directory) for directory in ledger_dirs],
             "upstream_raw_sha256": {name: expected_raw[name] for name in
                                     ("source_info.jsonl", "response.jsonl", "provenance.json")},
             "gold_policy": "No new test records or labels parsed before this freeze; raw hashes inherited from pinned v1 provenance"}
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, _redact(value, settings.api_key), exclusive=True)
    return value


def check_preselection(path: Path, *, project_root: Path = ROOT, allow_exposed_sources: set[str] | None = None) -> dict:
    value = _object(path)
    if value.get("schema_version") != PRE_SCHEMA or value.get("code_files_sha256") != code_hashes(project_root):
        raise ValueError("Preselection freeze code mismatch")
    if value.get("python_version") != platform.python_version():
        raise ValueError("Preselection freeze Python version mismatch")
    V4Config.from_dict(value["v4_config"])
    directories = sorted({(project_root / "results/ragtruth-ledger").resolve(),
                          *(Path(p).resolve() for p in value.get("exposure_ledger_dirs", []))})
    exposed, current_hashes = _exposure_snapshot(directories)
    for name, digest in value.get("exposure_ledger_files_sha256", {}).items():
        if current_hashes.get(name) != digest:
            raise ValueError("Frozen exposure ledger changed or disappeared")
    if exposed - set(value["sampling"]["excluded_source_ids"]) - (allow_exposed_sources or set()):
        raise ValueError("New source exposure after preselection freeze; create a fresh exclusion freeze")
    return value


def prepare_dataset(raw_dir: Path, output_dir: Path, preselection_freeze: Path, *,
                    project_root: Path = ROOT) -> dict:
    """Mechanical new selection only after code/config freeze. Never prints text."""
    frozen = check_preselection(preselection_freeze, project_root=project_root)
    if output_dir.exists():
        raise FileExistsError("Dataset destination already exists")
    for name, expected in frozen["upstream_raw_sha256"].items():
        if _sha(raw_dir / name) != expected:
            raise ValueError("Pinned raw input hash mismatch")
    sources = {}
    for row in adapter.load_jsonl(raw_dir / "source_info.jsonl"):
        sid = adapter._identifier(row, "source_id")
        if sid in sources or row.get("task_type") not in adapter.TASKS:
            raise ValueError("Duplicate source or unknown task")
        sources[sid] = row
    groups, splits = defaultdict(list), defaultdict(set)
    ids = set()
    for row in adapter.load_jsonl(raw_dir / "response.jsonl"):
        rid, sid = adapter._identifier(row, "id"), adapter._identifier(row, "source_id")
        if rid in ids or sid not in sources or row.get("split") not in ("train", "test"):
            raise ValueError("Invalid response join or split")
        if not isinstance(row.get("response"), str):
            raise ValueError("Response must be text")
        adapter._identifier(row, "model")
        adapter._identifier(row, "quality")
        ids.add(rid)
        groups[sid].append(row)
        splits[sid].add(row["split"])
    if any(len(s) != 1 for s in splits.values()):
        raise ValueError("Source crosses official splits")
    policy = frozen["sampling"]
    excluded = set(policy["excluded_source_ids"])
    eligible = {task: [] for task in adapter.TASKS}
    candidates, exclusions = {}, []
    for sid in sorted(groups):
        if splits[sid] != {"test"}:
            continue
        task = sources[sid]["task_type"]
        good = sorted((r for r in groups[sid] if r["quality"] == "good"), key=lambda r: r["id"])
        reason = "previously_exposed_source" if sid in excluded else "not_six_good_responses" if len(good) != 6 else None
        if reason:
            exclusions.append({"source_id": sid, "task_type": task, "reason": reason})
            continue
        contexts, mapping = adapter._adapt_source(sources[sid])
        sizes, failures = {}, []
        for row in good:
            failure, size = adapter._preflight({"context_passages": contexts, "generated_answer": row["response"]})
            sizes[row["id"]] = size
            if failure:
                failures.append({"id": row["id"], "reason": failure})
        if failures:
            exclusions.append({"source_id": sid, "task_type": task, "reason": "source_group_input_limit", "failures": failures})
            continue
        eligible[task].append(sid)
        candidates[sid] = good, contexts, mapping, sizes
    def rank(task: str, sid: str) -> tuple[str, str]:
        return hashlib.sha256(f"{policy['seed']}|{task}|{sid}".encode()).hexdigest(), sid
    selected = {task: sorted(eligible[task], key=lambda sid: rank(task, sid))[:10] for task in adapter.TASKS}
    if any(len(sids) != 10 for sids in selected.values()):
        raise ValueError("Fewer than ten eligible unexposed six-response sources in a task")
    inputs, manifest, gold = [], [], []
    for task in adapter.TASKS:
        for sid in selected[task]:
            good, contexts, mapping, sizes = candidates[sid]
            for row in good:
                labels = adapter._validate_labels(row)  # Only after final source selection.
                request = {"context_passages": contexts, "generated_answer": row["response"]}
                inputs.append({"id": row["id"], "input": request})
                manifest.append({"id": row["id"], "source_id": sid, "task_type": task,
                                 "generator": row["model"], "quality": "good", "upstream_split": "test",
                                 "input_sha256": _canonical_sha(request), "adapter": mapping,
                                 "request_size": sizes[row["id"]], "source_sample_key": rank(task, sid)[0]})
                gold.append({"id": row["id"], "source_id": sid, "labels": labels, "has_hallucination": bool(labels)})
    preparation = {"schema_version": "ragtruth-v2-preparation-v4.0", "split": "test", "seed": policy["seed"],
                   "sampling_policy": policy, "selected_source_ids": selected, "exclusions": exclusions,
                   "preselection_freeze_sha256": _sha(preselection_freeze),
                   "raw_files_sha256": frozen["upstream_raw_sha256"], "adapter_version": adapter.ADAPTER_VERSION,
                   "counts": {"selected_sources": 30, "selected_responses": len(inputs),
                              "selected_responses_by_task": {task: 60 for task in adapter.TASKS}},
                   "native_gold_policy": "Original labels preserved; invalid selected offsets abort without replacement"}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ragtruth-v4-stage-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        for name, rows in (("inputs.jsonl", inputs), ("manifest.jsonl", manifest), ("native_gold.jsonl", gold)):
            adapter._write_json(staging / name, rows, lines=True)
        preparation["artifacts_sha256"] = {name: _sha(staging / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl")}
        adapter._write_json(staging / "preparation.json", preparation)
        output_dir.mkdir()
        created = []
        try:
            for name in DATA_FILES:
                os.link(staging / name, output_dir / name)
                created.append(output_dir / name)
        except OSError:
            for path in created:
                path.unlink()
            output_dir.rmdir()
            raise
    return preparation


def create_run_freeze(data_dir: Path, path: Path, preselection_freeze: Path, *, project_root: Path = ROOT) -> dict:
    frozen = check_preselection(preselection_freeze, project_root=project_root)
    inputs, manifest, prep, hashes = _data(data_dir)  # native gold only hashed.
    if prep.get("preselection_freeze_sha256") != _sha(preselection_freeze):
        raise ValueError("Prepared data not bound to this preselection freeze")
    selection = _selection(inputs, manifest)
    if set(selection["source_ids"]) & set(frozen["sampling"]["excluded_source_ids"]):
        raise ValueError("Prepared data overlaps exposed sources")
    if (len(inputs) != 180 or set(selection["source_ids_by_task"]) != set(adapter.TASKS)
            or any(len(ids) != 10 for ids in selection["source_ids_by_task"].values())
            or any(count != 6 for count in Counter(m["source_id"] for m in manifest).values())):
        raise ValueError("Formal v2 requires 180 answers from ten sources in each task")
    if prep.get("artifacts_sha256") != {name: hashes[name] for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl")}:
        raise ValueError("Prepared artifacts changed after selection")
    if prep.get("sampling_policy") != frozen["sampling"]:
        raise ValueError("Prepared sampling policy differs from preselection freeze")
    value = {"schema_version": FREEZE_SCHEMA, "created_at": _now(),
             "preselection_freeze": str(preselection_freeze.resolve()), "preselection_freeze_sha256": _sha(preselection_freeze),
             "data_files_sha256": hashes, "selection": selection, "settings": frozen["settings"],
             "v4_config": frozen["v4_config"], "backends": frozen["backends"],
             "run_options": frozen["run_options"], "price_reference": frozen["price_reference"],
             "code_files_sha256": frozen["code_files_sha256"], "python_version": frozen["python_version"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, value, exclusive=True)
    return value


def run_benchmark(data_dir: Path, output_dir: Path, settings: Settings, v4_config: V4Config | dict, *,
                  mode: str = "dev", freeze_manifest: Path | None = None, backends: tuple[str, ...] = BACKENDS,
                  workers: int = 4, seed: int = 20261022, replicate: bool = False,
                  ledger_dir: Path | None = None, verifier_factory: Callable = build_verifier,
                  project_root: Path = ROOT, ids: list[str] | None = None, limit: int | None = None,
                  prices: dict | None = None) -> dict:
    backends = tuple(backends)
    if not backends or len(set(backends)) != len(backends) or any(b not in BACKENDS for b in backends):
        raise ValueError("Invalid or duplicate backend")
    options, common, v4 = _run_options(workers, seed), public_settings(settings), _v4_public(v4_config)
    if common["thinking"] != "enabled":
        raise ValueError("Comparators require thinking=enabled")
    if mode == "test" and (ids is not None or limit is not None):
        raise ValueError("Formal test forbids IDs/limit filtering")
    inputs, manifest, prep, hashes = _data(data_dir)
    if ids is not None:
        if not ids or len(set(ids)) != len(ids) or set(ids) - {row["id"] for row in inputs}:
            raise ValueError("Dev IDs must be unique known response IDs")
        pairs = [(c, m) for c, m in zip(inputs, manifest) if c["id"] in set(ids)]
        inputs, manifest = [c for c, _ in pairs], [m for _, m in pairs]
    if limit is not None:
        if type(limit) is not int or limit < 1:
            raise ValueError("Dev limit must be a positive integer")
        inputs, manifest = inputs[:limit], manifest[:limit]
    selection = _selection(inputs, manifest)
    frozen = pre = None
    if mode == "test":
        if freeze_manifest is None:
            raise ValueError("Formal test needs a post-preparation run freeze")
        frozen = _object(freeze_manifest)
        prepath = Path(frozen["preselection_freeze"])
        pre = check_preselection(prepath, project_root=project_root,
                                 allow_exposed_sources=set(selection["source_ids"]) if replicate else None)
        if ledger_dir is not None and str(ledger_dir.resolve()) not in pre["exposure_ledger_dirs"]:
            raise ValueError("Formal supplemental ledger must be bound by the preselection freeze")
        expected = {"schema_version": FREEZE_SCHEMA, "settings": common, "v4_config": v4,
                    "run_options": options, "selection": selection, "data_files_sha256": hashes,
                    "backends": list(backends), "code_files_sha256": code_hashes(project_root),
                    "preselection_freeze_sha256": _sha(prepath)}
        for name, value in expected.items():
            if frozen.get(name) != value:
                raise ValueError(f"Formal run freeze mismatch: {name}")
        if list(backends) != pre["backends"] or prep.get("preselection_freeze_sha256") != _sha(prepath):
            raise ValueError("Formal preselection binding mismatch")
    elif mode != "dev" or prep.get("seed") != "ragtruth-blind-v1-20261022":
        raise ValueError("Dev mode is restricted to exposed RAGTruth v1 data")
    if verifier_factory is build_verifier and any(b != "baseline" for b in backends) and not settings.api_key:
        raise ValueError("Model backends require an API key before reserving any exposure")
    if output_dir.exists():
        raise FileExistsError("Run output must be a new directory")
    output_dir.mkdir(parents=True)
    config = {"schema_version": RUN_SCHEMA, "created_at": _now(), "mode": mode,
              "data_files_sha256": hashes, "selection": selection, "backends": list(backends),
              "settings": common, "v4_config": v4, "run_options": options,
              "code_files_sha256": code_hashes(project_root), "python_version": platform.python_version(),
              "freeze_manifest": str(freeze_manifest.resolve()) if freeze_manifest else None,
              "freeze_sha256": _sha(freeze_manifest) if freeze_manifest else None,
              "price_reference": frozen.get("price_reference") if frozen else _prices(prices), "gold_loaded": False,
              "dev_subset": {"ids": ids, "limit": limit} if mode == "dev" else None,
              "qualification": "project-held-out v2" if mode == "test" else "exposed v1 development/regression; not unseen"}
    # Preserve the exact local implementation even when it has no Git commit.
    # Refuse a concurrently changed source before reserving exposure or calls.
    snapshot_root = output_dir / "source"
    for name, expected in config["code_files_sha256"].items():
        source_bytes = (project_root / name).read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != expected:
            raise ValueError("Source changed while creating run snapshot: " + name)
        destination = snapshot_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_bytes)
        if _sha(destination) != expected:
            raise ValueError("Run source snapshot hash mismatch: " + name)
    config["source_snapshot"] = {"directory": "source", "hashes": "code_files_sha256",
                                 "policy": "Exact frozen local bytes; no API keys or data copied"}
    _write_json(output_dir / "config.json", _redact(config, settings.api_key), exclusive=True)
    canonical_ledger = project_root / "results/ragtruth-ledger"
    directories = sorted(set(_ledger_dirs(project_root, ledger_dir)) |
                         ({Path(p).resolve() for p in pre["exposure_ledger_dirs"]} if pre else set()))
    all_exposed, _ = _exposure_snapshot(directories)
    primary_exposed, _ = _exposure_snapshot([canonical_ledger])
    source_set = set(selection["source_ids"])
    overlaps = source_set & all_exposed
    if overlaps and not replicate:
        raise ValueError("Previously exposed sources require --replicate, including supplemental ledgers")
    if replicate and not overlaps:
        raise ValueError("--replicate requires prior recorded source exposure")
    ledger_path, ledger = reserve_exposure(selection, output_dir,
        ledger_dir=canonical_ledger, replicate=bool(source_set & primary_exposed), smoke=False,
        freeze_sha256=config["freeze_sha256"], data_files_sha256=hashes, secret=settings.api_key)
    if overlaps - primary_exposed:
        ledger["role"] = "replicate"
        ledger["prior_overlaps"].append({"run_id": "supplemental-ledger", "source_ids": sorted(overlaps - primary_exposed),
                                         "response_ids": [], "status": "recorded_in_supplemental_ledger"})
        _write_json(ledger_path, _redact(ledger, settings.api_key))
    config["exposure"] = {"run_id": ledger["run_id"], "role": ledger["role"], "prior_overlaps": ledger["prior_overlaps"]}
    if mode == "test" and ledger["prior_overlaps"]:
        config["qualification"] = "v2 replication; previously exposed sources, not a new independent test"
    _write_json(output_dir / "config.json", _redact(config, settings.api_key))
    progress = {"schema_version": RUN_SCHEMA, "status": "running", "expected_records": len(inputs) * len(backends),
                "completed_records": 0, "partial_records": 0, "error_records": 0, "snapshot_write_failures": 0,
                "gold_loaded": False, "started_at": _now()}
    lock, stop = threading.Lock(), threading.Event()
    def snapshot():
        try:
            _write_json(output_dir / "progress.json", progress)
        except OSError:
            progress["snapshot_write_failures"] += 1
    with (output_dir / "predictions.jsonl").open("xb") as journal:
        def append(record):
            with lock:
                # Broken model traces may contain unpaired surrogate escapes.
                # ASCII JSON preserves them without breaking durable UTF-8 logs.
                journal.write((json.dumps(_redact(record, settings.api_key), ensure_ascii=True, allow_nan=False) + "\n").encode())
                journal.flush()
                os.fsync(journal.fileno())
                progress["completed_records"] += 1
                progress["error_records"] += record["error"] is not None
                progress["partial_records"] += bool(record["prediction"] and record["prediction"].get("status") == "partial")
                snapshot()
        def work(case, meta):
            order = backend_order(case["id"], seed, backends)
            for index, backend in enumerate(order):
                if stop.is_set():
                    return
                started, started_at = time.monotonic(), _now()
                prediction, error, telemetry = None, None, {"calls": []}
                citations, validation_errors = {"citation_count": 0, "valid_citation_count": 0}, []
                try:
                    request = VerificationRequest.from_dict(case["input"])
                    instance = verifier_factory(backend, settings, v4_config=V4Config.from_dict(v4)) if backend == "optimized-v4.0" else verifier_factory(backend, settings)
                    result = instance.verify(request)
                    prediction, telemetry = result.report, result.telemetry or {"calls": []}
                    citations = _citation_counts(prediction, request.context_passages)
                    validate_v4_report(prediction, request.context_passages)
                except VerificationError as exc:
                    prediction = None
                    telemetry = getattr(exc, "telemetry", None) or telemetry
                    error = {"code": exc.code, "message": exc.message, "type": type(exc).__name__}
                    if exc.code == "invalid_model_output":
                        validation_errors = [exc.message]
                except Exception as exc:
                    prediction = None
                    telemetry = getattr(exc, "telemetry", None) or telemetry
                    error = {"code": "unexpected_error", "type": type(exc).__name__}
                append({"id": case["id"], "source_id": meta["source_id"], "task_type": meta["task_type"],
                        "generator": meta["generator"], "input_sha256": meta["input_sha256"], "backend": backend,
                        "prediction": prediction, "error": error, "telemetry": telemetry, "schema_valid": error is None,
                        "validation_errors": validation_errors, "citations": citations,
                        "answer_chars": len(case["input"]["generated_answer"]),
                        "latency_seconds": time.monotonic() - started, "started_at": started_at, "completed_at": _now(),
                        "backend_order": order, "backend_order_index": index})
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ragtruth-v4")
        futures = []
        try:
            futures = [executor.submit(work, case, meta) for case, meta in zip(inputs, manifest)]
            for future in as_completed(futures):
                future.result()
            progress["status"] = "completed"
        except BaseException as exc:
            progress["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
            stop.set()
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            progress["completed_at"] = _now()
            snapshot()
            ledger.update(status=progress["status"], completed_at=progress["completed_at"],
                          completed_records=progress["completed_records"], error_records=progress["error_records"])
            _write_json(ledger_path, _redact(ledger, settings.api_key))
    return progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-preselection", "prepare", "freeze-run", "run"))
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dataset/ragtruth-blind-v1/recovery")
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--preselection-freeze", type=Path)
    parser.add_argument("--v4-config", type=Path)
    parser.add_argument("--mode", choices=("dev", "test"), default="dev")
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--selection-seed", default=SELECTION_SEED)
    parser.add_argument("--ledger-dir", type=Path)
    parser.add_argument("--replicate", action="store_true")
    parser.add_argument("--ids", nargs="+", help="Exposed dev response IDs only; forbidden for formal test")
    parser.add_argument("--limit", type=int, help="First N exposed dev cases only; forbidden for formal test")
    parser.add_argument("--price-input", type=float)
    parser.add_argument("--price-cached-input", type=float)
    parser.add_argument("--price-output", type=float)
    args = parser.parse_args(argv)
    def require(*names):
        if any(getattr(args, name) is None for name in names):
            parser.error("Required for this command: " + ", ".join("--" + n.replace("_", "-") for n in names))
    if args.command == "prepare":
        require("raw_dir", "output_dir", "preselection_freeze")
        result = prepare_dataset(args.raw_dir, args.output_dir, args.preselection_freeze)
        printed = {"counts": result["counts"], "output_dir": str(args.output_dir), "model_calls": 0}
    elif args.command == "freeze-run":
        require("freeze_manifest", "preselection_freeze")
        create_run_freeze(args.data_dir, args.freeze_manifest, args.preselection_freeze)
        printed = {"freeze": str(args.freeze_manifest), "model_calls": 0}
    else:
        settings, v4 = load_settings(thinking="enabled"), load_v4_config(args.v4_config)
        price_values = (args.price_input, args.price_cached_input, args.price_output)
        prices = None if all(v is None for v in price_values) else {
            "input_per_million": args.price_input, "cached_input_per_million": args.price_cached_input,
            "output_per_million": args.price_output, "currency": "USD", "reference": "standardized user reference, not billing"}
        if args.command == "freeze-preselection":
            require("freeze_manifest")
            create_preselection_freeze(args.data_dir, args.freeze_manifest, settings, v4, workers=args.workers,
                seed=args.seed, selection_seed=args.selection_seed, ledger_dir=args.ledger_dir, prices=prices)
            printed = {"freeze": str(args.freeze_manifest), "model_calls": 0}
        else:
            require("output_dir")
            printed = run_benchmark(args.data_dir, args.output_dir, settings, v4, mode=args.mode,
                freeze_manifest=args.freeze_manifest, backends=tuple(args.backends), workers=args.workers,
                seed=args.seed, replicate=args.replicate, ledger_dir=args.ledger_dir,
                ids=args.ids, limit=args.limit, prices=prices)
    print(json.dumps(printed, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
