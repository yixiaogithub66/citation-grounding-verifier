#!/usr/bin/env python3
"""Frozen, journaled RAGTruth inference. Native gold is only hashed, never parsed.

Prepare data and freeze this runner before formal inference. Scoring is a separate
process, so annotations cannot enter a verifier request through this module.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import threading
import time
from typing import Any, Callable
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import Settings, load_settings
from grounding.contracts import VerificationError, VerificationRequest, validate_report
from grounding.factory import build_verifier, frozen_v2_provenance
from scripts.validate_dataset import strict_json_loads, validate_prediction

PRIMARY_BACKENDS = ("baseline", "minimal", "optimized-v3")
DEFAULT_SEED = 20261022
DATA_FILES = ("inputs.jsonl", "manifest.jsonl", "preparation.json", "native_gold.jsonl")
SUPPORT_FILES = ("scripts/fetch_ragtruth.py", "scripts/ragtruth_data.py", "scripts/ragtruth_score.py",
                 "scripts/benchmark_ragtruth.py")
INITIAL_FREEZE = ROOT / "reports" / "ragtruth-inference-freeze.json"
FREEZE_SCHEMA = "ragtruth-benchmark-freeze-v1"
RUN_SCHEMA = "ragtruth-inference-run-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    # Reading bytes does not deserialize or expose native annotations.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _redact(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "<redacted>") if secret else value
    if isinstance(value, (list, tuple)):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {_redact(str(key), secret): _redact(item, secret) for key, item in value.items()}
    return value


def _object(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path.name}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"Blank record in {path.name} at line {number}")
            value = strict_json_loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object in {path.name} at line {number}")
            values.append(value)
    return values


def _write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows readers, indexers, and antivirus can briefly deny replacement.
        # Retry the atomic publish, never truncate the last complete snapshot.
        for attempt in range(6):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * 2 ** attempt)


def public_settings(settings: Settings) -> dict[str, Any]:
    settings.validate()
    return _redact({key: value for key, value in settings.public_dict().items()
                    if key != "api_key_configured"}, settings.api_key)


def implementation_provenance(initial_freeze: Path = INITIAL_FREEZE) -> dict[str, Any]:
    original = _object(initial_freeze)
    expected = original.get("files")
    paths = sorted((ROOT / "grounding").glob("*.py"))
    paths.extend([ROOT / "grounding" / "frozen_v2.json", ROOT / "scripts" / "validate_dataset.py"])
    current = {path.relative_to(ROOT).as_posix(): _sha(path) for path in paths}
    if (original.get("schema_version") != "ragtruth-inference-freeze-v1"
            or original.get("backends") != list(PRIMARY_BACKENDS) or expected != current):
        raise ValueError("Inference implementation differs from the initial RAGTruth freeze")
    frozen_v2 = frozen_v2_provenance()
    if not frozen_v2.get("verified"):
        raise ValueError("Frozen v2 provenance failed verification")
    support = {name: _sha(ROOT / name) for name in SUPPORT_FILES}
    initial_path = initial_freeze.resolve()
    initial_binding = initial_path.relative_to(ROOT).as_posix() if initial_path.is_relative_to(ROOT) else str(initial_path)
    return {
        "initial_freeze": {"path": initial_binding, "sha256": _sha(initial_freeze)},
        "inference_files_sha256": current,
        "support_files_sha256": support,
        "frozen_v2": frozen_v2,
        "python_version": platform.python_version(),
    }


def _data(data_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    hashes = {name: _sha(data_dir / name) for name in DATA_FILES}
    inputs, manifest = _jsonl(data_dir / "inputs.jsonl"), _jsonl(data_dir / "manifest.jsonl")
    preparation = _object(data_dir / "preparation.json")
    if not inputs or len(inputs) != len(manifest):
        raise ValueError("Inputs and manifest must have matching nonempty records")
    seen: set[str] = set()
    for case, meta in zip(inputs, manifest):
        identifier = case.get("id")
        if (set(case) != {"id", "input"} or not isinstance(identifier, str) or not identifier
                or identifier in seen or identifier != meta.get("id")):
            raise ValueError("Inputs require unique IDs aligned with the manifest")
        seen.add(identifier)
        # All request limits and two-key isolation are validated before any call.
        VerificationRequest.from_dict(case["input"])
        for key in ("source_id", "task_type", "generator"):
            if not isinstance(meta.get(key), str) or not meta[key]:
                raise ValueError(f"Manifest requires nonempty {key}")
        if meta.get("input_sha256") != _canonical_sha(case["input"]):
            raise ValueError("Input hash differs from its manifest binding")
    # Detect changes during preparation reads (the gold file remains opaque).
    if hashes != {name: _sha(data_dir / name) for name in DATA_FILES}:
        raise ValueError("Data changed while validating its bindings")
    return inputs, manifest, preparation, hashes


def _selection(inputs: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, set[str]] = {}
    for meta in manifest:
        by_task.setdefault(meta["task_type"], set()).add(meta["source_id"])
    return {
        "response_ids": [case["id"] for case in inputs],
        "source_ids": sorted({meta["source_id"] for meta in manifest}),
        "source_ids_by_task": {task: sorted(ids) for task, ids in sorted(by_task.items())},
    }


def _run_options(workers: int, seed: int) -> dict[str, Any]:
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
        raise ValueError("workers must be an integer within [1, 64]")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    return {"workers": workers, "seed": seed, "case_order": "inputs.jsonl order",
            "backend_order": "random.Random(sha256(seed:response_id).hexdigest()).shuffle",
            "scheduling": "concurrent cases; sequential backends within each case",
            "verifier_lifetime": "one new verifier per response/backend"}


def _prices(prices: dict[str, Any] | None) -> dict[str, Any] | None:
    if prices is None:
        return None
    values = dict(prices)
    for name in ("input_per_million", "cached_input_per_million", "output_per_million"):
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("All three reference prices must be finite nonnegative numbers")
    return values


def create_freeze(data_dir: Path, freeze_manifest: Path, settings: Settings, *,
                  workers: int = 4, seed: int = DEFAULT_SEED,
                  prices: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind opaque gold bytes, inputs, selection, code, settings, and run order."""
    data_dir, freeze_manifest = Path(data_dir).resolve(), Path(freeze_manifest).resolve()
    if freeze_manifest.exists():
        raise FileExistsError("Freeze manifest already exists; it will not be overwritten")
    options, config = _run_options(workers, seed), public_settings(settings)
    if config["thinking"] != "enabled":
        raise ValueError("Formal RAGTruth inference requires thinking=enabled")
    inputs, manifest, preparation, hashes = _data(data_dir)
    if preparation.get("split") != "test":
        raise ValueError("A formal freeze requires the test split")
    value = {
        "schema_version": FREEZE_SCHEMA, "created_at": _now(),
        "data_dir": str(data_dir), "data_files_sha256": hashes,
        "selection": _selection(inputs, manifest), "backends": list(PRIMARY_BACKENDS),
        "settings": config, "run_options": options, "price_reference": _prices(prices),
        "provenance": implementation_provenance(),
        "gold_policy": "native_gold.jsonl hashed as opaque bytes; no labels parsed by inference runner",
    }
    freeze_manifest.parent.mkdir(parents=True, exist_ok=True)
    _write_json(freeze_manifest, _redact(value, settings.api_key), exclusive=True)
    return value


def _check_freeze(path: Path, hashes: dict[str, str], selection: dict[str, Any],
                  config: dict[str, Any], options: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    freeze = _object(path)
    checks = {"schema_version": FREEZE_SCHEMA, "data_files_sha256": hashes,
              "selection": selection, "backends": list(PRIMARY_BACKENDS), "settings": config,
              "run_options": options, "provenance": provenance}
    for name, expected in checks.items():
        if freeze.get(name) != expected:
            raise ValueError(f"Formal freeze mismatch: {name}")
    _prices(freeze.get("price_reference"))
    return freeze


def reserve_exposure(selection: dict[str, Any], output_dir: Path, *, ledger_dir: Path,
                     replicate: bool, smoke: bool, freeze_sha256: str | None,
                     data_files_sha256: dict[str, str], secret: str = "") -> tuple[Path, dict[str, Any]]:
    """Reserve all selected sources before calls; overlap is always a replicate.

    A short exclusive lock makes overlap checking and reservation atomic across
    runners. A stale lock is deliberately fail-closed and requires inspection.
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)
    lock = ledger_dir / ".reservation.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Exposure ledger is locked; inspect any active or interrupted reservation") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        sources, responses = set(selection["source_ids"]), set(selection["response_ids"])
        overlaps = []
        for path in sorted(ledger_dir.glob("*.json")):
            prior = _object(path)
            if prior.get("schema_version") != "ragtruth-exposure-v1":
                raise ValueError("Unrecognized exposure ledger record")
            common_sources = sorted(sources.intersection(prior["source_ids"]))
            common_responses = sorted(responses.intersection(prior["response_ids"]))
            if common_sources or common_responses:
                overlaps.append({"run_id": prior["run_id"], "source_ids": common_sources,
                                 "response_ids": common_responses, "status": prior["status"]})
        if overlaps and not replicate:
            raise ValueError("Previously exposed sources or responses require --replicate and a fresh output directory")
        if replicate and not overlaps:
            raise ValueError("--replicate requires prior source or response exposure")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:12]
        value = {
            "schema_version": "ragtruth-exposure-v1", "run_id": run_id, "created_at": _now(),
            "status": "reserved", "role": "replicate" if overlaps else "first-run",
            "mode": "train-smoke" if smoke else "formal", "output_dir": str(output_dir.resolve()),
            "source_ids": selection["source_ids"], "response_ids": selection["response_ids"],
            "prior_overlaps": overlaps, "freeze_sha256": freeze_sha256,
            "data_files_sha256": data_files_sha256,
            "scope": "Exposure reservations in this checkout only; includes incomplete runs and local baselines.",
        }
        path = ledger_dir / (run_id + ".json")
        _write_json(path, _redact(value, secret), exclusive=True)
        return path, value
    finally:
        os.close(descriptor)
        lock.unlink()


def _citation_counts(prediction: Any, contexts: list[str]) -> dict[str, int]:
    total = valid = 0
    claims = prediction.get("claims", []) if isinstance(prediction, dict) else []
    if not isinstance(claims, list):
        claims = []
    for claim in claims:
        citations = claim.get("citations", []) if isinstance(claim, dict) else []
        if not isinstance(citations, list):
            continue
        for citation in citations:
            total += 1
            if not isinstance(citation, dict):
                continue
            index, quote = citation.get("index"), citation.get("quote")
            if (isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(contexts)
                    and isinstance(quote, str) and quote and quote in contexts[index]):
                start, end = citation.get("start_char"), citation.get("end_char")
                if "start_char" not in citation and "end_char" not in citation:
                    valid += 1
                elif (isinstance(start, int) and not isinstance(start, bool)
                      and isinstance(end, int) and not isinstance(end, bool)
                      and 0 <= start < end <= len(contexts[index]) and contexts[index][start:end] == quote):
                    valid += 1
    return {"citation_count": total, "valid_citation_count": valid}


def backend_order(identifier: str, seed: int, backends: tuple[str, ...]) -> list[str]:
    order = list(backends)
    random.Random(hashlib.sha256(f"{seed}:{identifier}".encode("utf-8")).hexdigest()).shuffle(order)
    return order


def _resume_records(old_dir: Path, *, inputs: list[dict[str, Any]], manifest: list[dict[str, Any]],
                    hashes: dict[str, str], selection: dict[str, Any], config: dict[str, Any],
                    options: dict[str, Any], provenance: dict[str, Any], freeze_manifest: Path,
                    price_reference: dict[str, Any] | None, secret: str) -> tuple[bytes, list[dict[str, Any]], dict[str, Any]]:
    """Validate a stopped journal without changing it or parsing any native gold."""
    old_dir = old_dir.resolve()
    config_path, progress_path, journal_path = (old_dir / name for name in
                                               ("config.json", "progress.json", "predictions.jsonl"))
    old_config, old_progress = _object(config_path), _object(progress_path)
    if (old_config.get("schema_version") != RUN_SCHEMA or old_config.get("mode") != "formal"
            or old_config.get("gold_loaded") is not False
            or old_progress.get("schema_version") != RUN_SCHEMA
            or old_progress.get("status") not in ("failed", "interrupted")
            or old_progress.get("gold_loaded") is not False):
        raise ValueError("Recovery requires a failed or interrupted formal run with gold unopened")
    old_freeze_name = old_config.get("freeze_manifest")
    if not isinstance(old_freeze_name, str) or not old_freeze_name:
        raise ValueError("Recovery origin has no freeze binding")
    old_freeze_path = Path(old_freeze_name)
    if not old_freeze_path.is_absolute():
        old_freeze_path = old_dir / old_freeze_path
    old_freeze_path = old_freeze_path.resolve()
    if _sha(old_freeze_path) != old_config.get("freeze_sha256"):
        raise ValueError("Recovery origin freeze hash mismatch")
    if old_freeze_path == freeze_manifest.resolve() or _sha(freeze_manifest) == old_config["freeze_sha256"]:
        raise ValueError("Recovery requires a new freeze manifest binding the current recorder")
    old_provenance = old_config.get("provenance")
    if not isinstance(old_provenance, dict):
        raise ValueError("Recovery origin provenance is missing")
    # Only the recorder implementation may differ; model code, adapter, scorer,
    # downloader, Python version, and original inference freeze stay identical.
    def without_recorder(value: dict[str, Any]) -> dict[str, Any]:
        result = dict(value)
        support = result.get("support_files_sha256")
        if not isinstance(support, dict) or "scripts/benchmark_ragtruth.py" not in support:
            raise ValueError("Recovery provenance lacks a recorder binding")
        result["support_files_sha256"] = {key: digest for key, digest in support.items()
                                          if key != "scripts/benchmark_ragtruth.py"}
        return result
    if without_recorder(old_provenance) != without_recorder(provenance):
        raise ValueError("Recovery changed inference, adapter, scorer, downloader, or runtime provenance")
    old_freeze = _check_freeze(old_freeze_path, hashes, selection, config, options, old_provenance)
    expected = {"data_files_sha256": hashes, "selection": selection, "settings": config,
                "run_options": options, "backends": list(PRIMARY_BACKENDS), "price_reference": price_reference}
    for name, value in expected.items():
        if old_config.get(name) != value or old_freeze.get(name) != value:
            raise ValueError(f"Recovery origin configuration mismatch: {name}")
    original_bytes = journal_path.read_bytes()
    if original_bytes and not original_bytes.endswith(b"\n"):
        raise ValueError("Recovery journal has an incomplete final line; refusing to repair it")
    if secret and secret.encode("utf-8") in original_bytes:
        raise ValueError("Recovery journal contains configured credentials; exact copying is unsafe")
    rows = []
    cases, metas = {row["id"]: row for row in inputs}, {row["id"]: row for row in manifest}
    seen = set()
    for number, line in enumerate(original_bytes.decode("utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError("Recovery journal has a blank line")
        row = strict_json_loads(line)
        if not isinstance(row, dict):
            raise ValueError("Recovery journal contains a non-object record")
        identifier, backend = row.get("id"), row.get("backend")
        if not isinstance(identifier, str) or identifier not in metas or backend not in PRIMARY_BACKENDS:
            raise ValueError("Recovery journal has an unknown ID or backend")
        pair = identifier, backend
        if pair in seen:
            raise ValueError("Recovery journal has a duplicate ID/backend pair")
        seen.add(pair)
        meta, case = metas[identifier], cases[identifier]
        for key in ("source_id", "task_type", "generator", "input_sha256"):
            if row.get(key) != meta[key]:
                raise ValueError(f"Recovery journal metadata mismatch: {key}")
        order = backend_order(identifier, options["seed"], PRIMARY_BACKENDS)
        if (row.get("backend_order") != order or row.get("backend_order_index") != order.index(backend)
                or row.get("answer_chars") != len(case["input"]["generated_answer"])):
            raise ValueError("Recovery journal has mismatched order or answer-length metadata")
        if (not isinstance(row.get("schema_valid"), bool) or "error" not in row
                or not isinstance(row.get("telemetry"), dict) or not isinstance(row["telemetry"].get("calls"), list)):
            raise ValueError("Recovery journal has invalid result metadata")
        if row["error"] is None:
            if row["schema_valid"] is not True or row.get("validation_errors"):
                raise ValueError("Recovery journal success has inconsistent validation metadata")
            validate_report(row.get("prediction"), case["input"]["context_passages"])
        elif not isinstance(row["error"], dict) or row["schema_valid"] or row.get("prediction") is not None:
            raise ValueError("Recovery journal failure has inconsistent validation metadata")
        rows.append(row)
    proof = {
        "origin_run_dir": str(old_dir), "origin_status": old_progress["status"],
        "origin_config_sha256": _sha(config_path), "origin_progress_sha256": _sha(progress_path),
        "origin_freeze_manifest": str(old_freeze_path), "origin_freeze_sha256": old_config["freeze_sha256"],
        "origin_predictions_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "origin_predictions_bytes": len(original_bytes), "reused_records": len(rows),
        "reused_errors": sum(row["error"] is not None for row in rows),
        "old_recorder_sha256": old_provenance["support_files_sha256"]["scripts/benchmark_ragtruth.py"],
        "new_recorder_sha256": provenance["support_files_sha256"]["scripts/benchmark_ragtruth.py"],
        "copy_policy": "Original journal bytes copied exactly; every durable pair including failures is retained and skipped.",
    }
    if journal_path.read_bytes() != original_bytes:
        raise ValueError("Recovery origin journal changed during validation")
    return original_bytes, rows, proof


def run_benchmark(data_dir: Path, output_dir: Path, settings: Settings, *,
                  freeze_manifest: Path | None = None, smoke: bool = False,
                  backends: tuple[str, ...] = PRIMARY_BACKENDS, workers: int = 4,
                  seed: int = DEFAULT_SEED, replicate: bool = False,
                  ledger_dir: Path | None = None,
                  resume_from: Path | None = None,
                  verifier_factory: Callable[..., Any] = build_verifier,
                  progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Run inference with a durable per-result journal and no native gold reads."""
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    backends = tuple(backends)
    options, config = _run_options(workers, seed), public_settings(settings)
    if resume_from is not None and (smoke or not replicate):
        raise ValueError("--resume-from is restricted to formal --replicate runs in a fresh output directory")
    if not backends or len(set(backends)) != len(backends) or any(name not in PRIMARY_BACKENDS for name in backends):
        raise ValueError("Backends must be unique members of baseline, minimal, optimized-v3")
    if config["thinking"] != "enabled":
        raise ValueError("RAGTruth inference requires thinking=enabled")
    if verifier_factory is build_verifier and any(name != "baseline" for name in backends) and not settings.api_key:
        raise ValueError("An API key is required for model backends")
    inputs, manifest, preparation, hashes = _data(data_dir)
    selection, provenance = _selection(inputs, manifest), implementation_provenance()
    freeze = None
    if smoke:
        if preparation.get("split") != "train":
            raise ValueError("Smoke inference is restricted to the train split")
        if freeze_manifest is not None:
            raise ValueError("Smoke inference does not accept a formal freeze")
    else:
        if backends != PRIMARY_BACKENDS or preparation.get("split") != "test" or freeze_manifest is None:
            raise ValueError("Formal inference requires all three primary backends, test data, and a freeze manifest")
        freeze_manifest = Path(freeze_manifest).resolve()
        freeze = _check_freeze(freeze_manifest, hashes, selection, config, options, provenance)
    reused_bytes, reused_records, resume_proof = b"", [], None
    if resume_from is not None:
        reused_bytes, reused_records, resume_proof = _resume_records(Path(resume_from), inputs=inputs,
            manifest=manifest, hashes=hashes, selection=selection, config=config, options=options,
            provenance=provenance, freeze_manifest=freeze_manifest,
            price_reference=freeze.get("price_reference"), secret=settings.api_key)
    reused_pairs = {(record["id"], record["backend"]) for record in reused_records}
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise FileExistsError("Output directory must be new or empty; interrupted runs require a fresh directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    # Even an empty precreated directory is claimed exclusively by its config.
    run_config = {"schema_version": RUN_SCHEMA, "created_at": _now(), "mode": "train-smoke" if smoke else "formal",
                  "data_dir": str(data_dir), "data_files_sha256": hashes, "settings": config,
                  "selection": selection, "backends": list(backends), "run_options": options,
                  "provenance": provenance, "freeze_manifest": str(freeze_manifest) if freeze_manifest else None,
                  "freeze_sha256": _sha(freeze_manifest) if freeze_manifest else None,
                  "price_reference": freeze.get("price_reference") if freeze else None,
                  "gold_loaded": False}
    if resume_proof is not None:
        run_config["resume"] = resume_proof
    _write_json(output_dir / "config.json", _redact(run_config, settings.api_key), exclusive=True)
    ledger_path, ledger = reserve_exposure(selection, output_dir,
        ledger_dir=Path(ledger_dir) if ledger_dir is not None else ROOT / "results" / "ragtruth-ledger",
        replicate=replicate, smoke=smoke, freeze_sha256=run_config["freeze_sha256"],
        data_files_sha256=hashes, secret=settings.api_key)
    run_config.update(exposure={"ledger_path": str(ledger_path.resolve()), "run_id": ledger["run_id"],
                                "role": ledger["role"], "prior_overlaps": ledger["prior_overlaps"]})
    _write_json(output_dir / "config.json", _redact(run_config, settings.api_key))
    progress = {"schema_version": RUN_SCHEMA, "status": "running", "started_at": _now(),
                "updated_at": _now(), "expected_records": len(inputs) * len(backends),
                "completed_records": 0, "error_records": 0, "gold_loaded": False,
                "reused_records": len(reused_records), "reused_error_records": 0,
                "new_records": 0, "snapshot_write_failures": 0,
                "by_backend": {name: {"completed": 0, "errors": 0} for name in backends}}
    for record in reused_records:
        progress["completed_records"] += 1
        progress["by_backend"][record["backend"]]["completed"] += 1
        if record["error"] is not None:
            progress["error_records"] += 1
            progress["reused_error_records"] += 1
            progress["by_backend"][record["backend"]]["errors"] += 1
    _write_json(output_dir / "progress.json", progress)
    lock, stop = threading.Lock(), threading.Event()
    journal = (output_dir / "predictions.jsonl").open("xb")
    if reused_bytes:
        journal.write(reused_bytes)
        journal.flush()
        os.fsync(journal.fileno())

    def snapshot() -> None:
        try:
            _write_json(output_dir / "progress.json", progress)
        except OSError:
            # The fsynced journal is authoritative. A best-effort progress
            # snapshot must never abort inference or lose an already paid call.
            progress["snapshot_write_failures"] += 1

    def append(record: dict[str, Any]) -> None:
        safe = _redact(record, settings.api_key)
        encoded = json.dumps(safe, ensure_ascii=False, allow_nan=False)
        with lock:
            journal.write((encoded + "\n").encode("utf-8"))
            journal.flush()
            os.fsync(journal.fileno())
            progress["completed_records"] += 1
            progress["new_records"] += 1
            progress["by_backend"][record["backend"]]["completed"] += 1
            if record["error"] is not None:
                progress["error_records"] += 1
                progress["by_backend"][record["backend"]]["errors"] += 1
            progress["updated_at"] = _now()
            snapshot()
            if progress_callback is not None and progress["completed_records"] % 10 == 0:
                progress_callback(json.loads(json.dumps(progress)))

    def work(case: dict[str, Any], meta: dict[str, Any]) -> None:
        order = backend_order(case["id"], seed, backends)
        for index, backend in enumerate(order):
            if stop.is_set():
                return
            if (case["id"], backend) in reused_pairs:
                continue
            started_at, started = _now(), time.monotonic()
            prediction, telemetry, error = None, {"calls": []}, None
            validation_errors: list[dict[str, str]] = []
            citations = {"citation_count": 0, "valid_citation_count": 0}
            try:
                request = VerificationRequest.from_dict(case["input"])
                result = verifier_factory(backend, settings).verify(request)
                prediction, telemetry = result.report, result.telemetry or {"calls": []}
                citations = _citation_counts(prediction, request.context_passages)
                validation_errors = validate_prediction(prediction, request.context_passages)
                validate_report(prediction, request.context_passages)
            except VerificationError as exc:
                prediction = None
                # Returned-result validation must not discard the API's telemetry.
                if getattr(exc, "telemetry", {}).get("calls") or telemetry == {"calls": []}:
                    telemetry = getattr(exc, "telemetry", None) or {"calls": []}
                error = {"code": exc.code, "message": exc.message, "type": type(exc).__name__}
                if exc.code == "invalid_model_output" and not validation_errors:
                    validation_errors = [{"location": "response", "message": exc.message}]
            except Exception as exc:
                prediction = None
                telemetry = getattr(exc, "telemetry", None) or telemetry
                error = {"code": "unexpected_error", "type": type(exc).__name__}
            append({"id": case["id"], "source_id": meta["source_id"], "task_type": meta["task_type"],
                    "generator": meta["generator"], "backend": backend,
                    "prediction": prediction, "telemetry": telemetry, "error": error,
                    "schema_valid": error is None, "validation_errors": validation_errors,
                    "citations": citations, "answer_chars": len(case["input"]["generated_answer"]),
                    "input_sha256": meta["input_sha256"], "latency_seconds": time.monotonic() - started,
                    "started_at": started_at, "completed_at": _now(),
                    "backend_order": order, "backend_order_index": index})

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ragtruth")
    futures = []
    status = "completed"
    try:
        futures = [executor.submit(work, case, meta) for case, meta in zip(inputs, manifest)]
        for future in as_completed(futures):
            future.result()
    except KeyboardInterrupt:
        status = "interrupted"
        stop.set()
        for future in futures:
            future.cancel()
    except BaseException:
        status = "failed"
        stop.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        # In-flight calls complete and are journaled; no further backend starts.
        executor.shutdown(wait=True, cancel_futures=True)
        journal.close()
        progress.update(status=status, updated_at=_now(), completed_at=_now())
        snapshot()
        ledger.update(status=status, completed_at=progress["completed_at"],
                      completed_records=progress["completed_records"], error_records=progress["error_records"])
        _write_json(ledger_path, _redact(ledger, settings.api_key))
    return progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--thinking", choices=("enabled",), default="enabled")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--backends", nargs="+", choices=PRIMARY_BACKENDS, default=list(PRIMARY_BACKENDS))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--replicate", action="store_true")
    parser.add_argument("--resume-from", type=Path, help="Copy durable pairs from a stopped formal run; requires --replicate")
    parser.add_argument("--ledger-dir", type=Path)
    parser.add_argument("--price-input", type=float)
    parser.add_argument("--price-cached-input", type=float)
    parser.add_argument("--price-output", type=float)
    args = parser.parse_args(argv)
    secret = ""
    try:
        settings = load_settings(thinking=args.thinking)
        secret = settings.api_key
        if args.command == "freeze":
            if args.smoke or args.replicate or args.resume_from is not None or tuple(args.backends) != PRIMARY_BACKENDS:
                raise ValueError("Formal freeze requires all primary backends and no smoke or replicate flags")
            prices = None
            if any(value is not None for value in (args.price_input, args.price_cached_input, args.price_output)):
                prices = {"input_per_million": args.price_input, "cached_input_per_million": args.price_cached_input,
                          "output_per_million": args.price_output, "currency": "USD",
                          "reference": "User-specified reference tariff; not verified current pricing or provider billing"}
            target = args.freeze_manifest or args.data_dir / "freeze.json"
            value = create_freeze(args.data_dir, target, settings, workers=args.workers, seed=args.seed, prices=prices)
            print(json.dumps({"status": "frozen", "freeze_manifest": str(target.resolve()),
                              "responses": len(value["selection"]["response_ids"]),
                              "sources": len(value["selection"]["source_ids"])}, ensure_ascii=False))
        else:
            if args.output_dir is None:
                raise ValueError("run requires --output-dir")
            if any(value is not None for value in (args.price_input, args.price_cached_input, args.price_output)):
                raise ValueError("Price references must be recorded at freeze time")
            progress = run_benchmark(args.data_dir, args.output_dir, settings,
                freeze_manifest=None if args.smoke else args.freeze_manifest or args.data_dir / "freeze.json",
                smoke=args.smoke, backends=tuple(args.backends), workers=args.workers, seed=args.seed,
                replicate=args.replicate, ledger_dir=args.ledger_dir,
                resume_from=args.resume_from,
                progress_callback=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
            print(json.dumps(progress, ensure_ascii=False), flush=True)
            if progress["status"] != "completed":
                return 130
        return 0
    except (ValueError, VerificationError, FileNotFoundError, FileExistsError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": _redact(str(exc), secret)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as exc:
        # Unknown exception messages can contain provider bodies or credentials.
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
