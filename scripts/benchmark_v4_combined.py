#!/usr/bin/env python3
"""Paired exposed-dev experiment; never selects or qualifies an unseen dataset.

The two inference backends see only VerificationRequest. All identity, sampling,
source, generator and gold metadata remains outside the inference boundary.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
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
from grounding.factory import build_verifier
from scripts.benchmark_ragtruth import (
    _citation_counts, _data, _now, _prices, _redact, _run_options, _selection,
    _sha, _write_json, backend_order, public_settings, reserve_exposure,
)
from scripts.ragtruth_v4 import code_hashes

BACKENDS = ("optimized-v4.0", "optimized-v4-combined")
SCHEMA = "v4-combined-paired-exposed-dev-v1"


def run(data_dir: Path, output_dir: Path, settings, config: V4Config, *,
        workers: int = 4, seed: int = 20261023, limit: int | None = None,
        prices: dict | None = None, verifier_factory=build_verifier,
        project_root: Path = ROOT) -> dict:
    options = _run_options(workers, seed)
    common = public_settings(settings)
    config.validate()
    if common["thinking"] != "enabled":
        raise ValueError("Use the registered common thinking=enabled setting")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Limit must be a positive integer")
    inputs, manifest, prep, hashes = _data(data_dir)  # Gold hashed, not parsed.
    if prep.get("seed") != "ragtruth-blind-v1-20261022":
        raise ValueError("Combined experiment accepts only the exposed v1 development slice")
    if limit is not None:
        inputs, manifest = inputs[:limit], manifest[:limit]
    if not inputs:
        raise ValueError("Empty development selection")
    if verifier_factory is build_verifier and not settings.api_key:
        raise ValueError("Configure the model key before creating a run")
    price_reference = _prices(prices)
    selection = _selection(inputs, manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    source_hashes = code_hashes(project_root)
    for name, digest in source_hashes.items():
        raw = (project_root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Source changed during snapshot; no inference started: " + name)
        target = output_dir / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    metadata = {
        "schema_version": SCHEMA, "created_at": _now(), "mode": "dev",
        "qualification": "exposed v1 paired development experiment; not unseen or author-adjudicated",
        "data_dir": str(data_dir.resolve()), "data_files_sha256": hashes,
        "selection": selection, "backends": list(BACKENDS), "settings": common,
        "v4_config": config.public_dict(), "run_options": options,
        "code_files_sha256": source_hashes, "python_version": platform.python_version(),
        "price_reference": price_reference, "gold_loaded": False,
        "dev_subset": {"ids": None, "limit": limit},
        "intervention": "H1+H2+H3 in combined runtime; H4 is a separate offline behavioral evaluation",
        "attribution_limit": "A joint experiment cannot identify an individual hypothesis effect",
        "order_policy": "Deterministic per-response shuffled backend order; same request and budgets",
        "source_snapshot": {"directory": "source", "hashes": "code_files_sha256"},
    }
    _write_json(output_dir / "config.json", _redact(metadata, settings.api_key), exclusive=True)
    ledger_path, ledger = reserve_exposure(
        selection, output_dir, ledger_dir=project_root / "results/ragtruth-ledger",
        replicate=True, smoke=False, freeze_sha256=_sha(output_dir / "config.json"),
        data_files_sha256=hashes, secret=settings.api_key,
    )
    ledger["mode"] = "exposed-dev-combined"
    _write_json(ledger_path, _redact(ledger, settings.api_key))
    progress = {"status": "running", "completed_records": 0,
                "expected_records": len(inputs) * len(BACKENDS),
                "partial_records": 0, "error_records": 0, "started_at": _now()}
    _write_json(output_dir / "progress.json", progress, exclusive=True)
    journal_lock = threading.Lock()

    def append(record):
        with journal_lock:
            stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            progress["completed_records"] += 1
            progress["error_records"] += record["error"] is not None
            progress["partial_records"] += bool(record["prediction"] and record["prediction"].get("status") == "partial")
            _write_json(output_dir / "progress.json", progress)
            print(f"[{progress['completed_records']}/{progress['expected_records']}] {record['backend']} stored", flush=True)

    def work(case, meta):
        order = backend_order(case["id"], seed, BACKENDS)
        for position, backend in enumerate(order):
            started, started_at = time.monotonic(), _now()
            prediction, error, telemetry = None, None, {"calls": []}
            citations = {"citation_count": 0, "valid_citation_count": 0}
            validation_errors = []
            try:
                request = VerificationRequest.from_dict(case["input"])
                verifier = verifier_factory(backend, settings, v4_config=config)
                result = verifier.verify(request)
                prediction, telemetry = result.report, result.telemetry
                citations = _citation_counts(prediction, request.context_passages)
                validate_v4_report(prediction, request.context_passages)
            except VerificationError as exc:
                prediction = None
                telemetry = exc.telemetry or telemetry
                error = {"code": exc.code, "message": exc.message, "status": exc.status}
                if exc.code == "invalid_model_output":
                    validation_errors = [exc.message]
            except Exception as exc:
                prediction = None
                error = {"code": "unexpected_error", "type": type(exc).__name__}
            append(_redact({
                "id": case["id"], "backend": backend, "source_id": meta["source_id"],
                "task_type": meta["task_type"], "generator": meta["generator"],
                "input_sha256": meta["input_sha256"], "prediction": prediction,
                "error": error, "telemetry": telemetry, "schema_valid": error is None,
                "validation_errors": validation_errors, "citations": citations,
                "answer_chars": len(case["input"]["generated_answer"]),
                "latency_seconds": time.monotonic() - started, "started_at": started_at,
                "completed_at": _now(), "backend_order": order, "backend_order_index": position,
            }, settings.api_key))

    try:
        with (output_dir / "predictions.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = [pool.submit(work, case, meta) for case, meta in zip(inputs, manifest)]
                for future in as_completed(pending):
                    future.result()
        progress["source_unchanged"] = code_hashes(project_root) == source_hashes
        progress["data_unchanged"] = all(_sha(data_dir / name) == digest for name, digest in hashes.items())
        progress["status"] = "completed" if progress["source_unchanged"] and progress["data_unchanged"] else "invalidated_changed_inputs"
    except BaseException as exc:
        progress["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        raise
    finally:
        progress["completed_at"] = _now()
        _write_json(output_dir / "progress.json", progress)
        ledger.update(status=progress["status"], completed_at=progress["completed_at"],
                      completed_records=progress["completed_records"], error_records=progress["error_records"])
        _write_json(ledger_path, _redact(ledger, settings.api_key))
    return progress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dataset/ragtruth-blind-v1/recovery")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--v4-config", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--price-input", type=float)
    parser.add_argument("--price-cached-input", type=float)
    parser.add_argument("--price-output", type=float)
    args = parser.parse_args()
    prices = None if all(v is None for v in (args.price_input, args.price_cached_input, args.price_output)) else {
        "input_per_million": args.price_input, "cached_input_per_million": args.price_cached_input,
        "output_per_million": args.price_output, "currency": "USD", "reference": "fixed experiment reference; not billing",
    }
    result = run(args.data_dir, args.output_dir, load_settings(thinking="enabled"), load_v4_config(args.v4_config),
                 workers=args.workers, seed=args.seed, limit=args.limit, prices=prices)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
