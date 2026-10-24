#!/usr/bin/env python3
"""Append-only recovery amendment; never retries a journaled inference attempt."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
REL = Path("research/bidirectional-selection-20261024")
SCHEMA = "bidirectional-selection-recovery-v1"
NEW_CALL_CEILING = 102
WORKERS = 4


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode("utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def identity(row):
    return row["probe"], row["case_id"], row["arm"], row["repetition"]


def read_journal(path):
    raw = Path(path).read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Original journal has a partial trailing record; stop for explicit recovery")
    rows = [json.loads(line) for line in raw.splitlines()]
    keys = [identity(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate inference identity in journal")
    return raw, rows


def load_pilot(output):
    source = (Path(output) / "source").resolve()
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location("frozen_recovery_pilot", source / REL / "pilot.py")
    pilot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pilot)
    pilot.check_freeze(output)
    return pilot


def check_recovery(output, pilot):
    output = Path(output)
    manifest = read(output / "recovery.json")
    if sha(output / "recovery.json") != (output / "recovery.sha256").read_text().strip():
        raise ValueError("Recovery amendment manifest changed")
    if manifest["schema_version"] != SCHEMA:
        raise ValueError("Recovery schema mismatch")
    for name, expected in manifest["recovery_files_sha256"].items():
        if sha(output / "recovery-source" / name) != expected:
            raise ValueError("Recovery source changed")
    if sha(output / "original-responses.jsonl") != manifest["original_journal_sha256"]:
        raise ValueError("Preserved original journal changed")
    if sha(output / "original-progress.json") != manifest["original_progress_sha256"]:
        raise ValueError("Preserved original progress changed")
    if sha(output / "freeze.json") != manifest["original_freeze_sha256"]:
        raise ValueError("Original freeze binding changed")
    original = Path(manifest["original_run_directory"])
    for name, expected in manifest["original_files_sha256"].items():
        if sha(original / name) != expected:
            raise ValueError("Original run was modified after recovery preparation")
    pilot.check_freeze(output)
    return manifest


def prepare(original, output, project_root=ROOT):
    original, output, project_root = Path(original).resolve(), Path(output).resolve(), Path(project_root)
    if output.exists():
        raise FileExistsError("Recovery directory exists; no overwrite")
    if output == original or output.is_relative_to(original):
        raise ValueError("Recovery destination must be independent of original run")
    progress = read(original / "progress.json")
    if progress.get("status") != "aborted":
        raise ValueError("Recovery requires a stopped aborted original run")
    raw, rows = read_journal(original / "responses.jsonl")
    # Hash and copy without rewriting any original run artifact.
    original_hashes = {path.relative_to(original).as_posix(): sha(path)
                       for path in sorted(original.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}
    shutil.copytree(original, output, ignore=shutil.ignore_patterns("__pycache__"))
    (output / "original-responses.jsonl").write_bytes(raw)
    shutil.copyfile(original / "progress.json", output / "original-progress.json")
    pilot = load_pilot(output)
    cases, seeds = pilot.inference_cases(output / "source" / REL / pilot.CASE_FILE)
    expected = pilot.expected_identities(cases, seeds)
    present = {identity(row) for row in rows}
    if not present <= expected:
        raise ValueError("Original journal contains unexpected identities")
    missing = sorted(expected - present)
    if len(missing) > NEW_CALL_CEILING or len(rows) + len(missing) != 152:
        raise ValueError("Recovery exceeds fixed new-call ceiling")
    for row in rows:
        if len(row.get("telemetry", {}).get("calls", [])) != 1:
            raise ValueError("Original journal record does not retain one attempt")
    recovery_source = output / "recovery-source"
    recovery_source.mkdir()
    files = ("recovery.py", "test_recovery.py", "RECOVERY_PLAN.md")
    for name in files:
        shutil.copyfile(project_root / REL / name, recovery_source / name)
    manifest = {"schema_version": SCHEMA, "frozen_at": now(),
                "original_run_directory": str(original), "original_files_sha256": original_hashes,
                "original_journal_sha256": sha(original / "responses.jsonl"),
                "original_progress_sha256": sha(original / "progress.json"),
                "original_freeze_sha256": sha(original / "freeze.json"),
                "original_completed_records": len(rows),
                "original_started_counter": progress["model_calls_started"],
                "original_unjournaled_started_counter": max(0, progress["model_calls_started"] - len(rows)),
                "original_unknown_attempt_overhead": "Unjournaled started-counter reservations cannot establish whether a provider request occurred; preserve this uncertainty separately from completed records.",
                "missing_identities": [list(key) for key in missing], "maximum_new_calls": len(missing),
                "hard_new_call_ceiling": NEW_CALL_CEILING, "workers": WORKERS,
                "recovery_files_sha256": {name: sha(recovery_source / name) for name in files},
                "qualification": "Infrastructure amendment after interruption, not a fresh untouched experiment. All journaled failures and successes are preserved. No model, prompt, case, expected semantics or frozen inference source changes."}
    write_new(output / "recovery.json", manifest)
    with (output / "recovery.sha256").open("x", encoding="ascii", newline="\n") as stream:
        stream.write(sha(output / "recovery.json") + "\n")
    check_recovery(output, pilot)
    return manifest


def write_progress(output, value, retries=12, delay=0.1):
    """Only progress-file I/O retries; never wraps inference or journal writes."""
    output = Path(output)
    temporary = output / ("progress." + uuid.uuid4().hex + ".tmp")
    write_new(temporary, value)
    for attempt in range(retries):
        try:
            os.replace(temporary, output / "progress.json")
            return True
        except PermissionError:
            if attempt + 1 < retries:
                time.sleep(delay)
    # Durable checkpoints retain progress even when another reader holds the
    # conventional progress pathname. The reservation/response journals govern.
    fallback = output / ("progress-checkpoint." + uuid.uuid4().hex + ".json")
    os.replace(temporary, fallback)
    return False


def append_sync(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="backslashreplace") + b"\n")
    stream.flush()
    os.fsync(stream.fileno())


def run(output, env_file):
    output = Path(output).resolve()
    if Path(__file__).resolve() != (output / "recovery-source" / "recovery.py").resolve():
        raise ValueError("Recovery run must execute its frozen amendment")
    pilot = load_pilot(output)
    manifest = check_recovery(output, pilot)
    settings = pilot.pilot_settings(env_file)
    if settings.public_dict() != pilot.read_object(output / "freeze.json")["settings"] or not settings.api_key:
        raise ValueError("Settings differ or credentials unavailable")
    if sha(output / "responses.jsonl") != manifest["original_journal_sha256"]:
        raise ValueError("Recovery already wrote responses or copied journal changed")
    write_new(output / "recovery-started.json", {"started_at": now(), "schema_version": SCHEMA})
    _, rows = read_journal(output / "responses.jsonl")
    by_id = {identity(row): row for row in rows}
    cases, seeds = pilot.inference_cases(output / "source" / REL / pilot.CASE_FILE)
    lock = threading.Lock()
    progress = {"schema_version": pilot.SCHEMA, "recovery_schema": SCHEMA, "status": "running", "started_at": now(),
                "record_count": len(rows), "model_calls_started": len(rows), "new_reservations": 0,
                "original_unjournaled_started_counter": manifest["original_unjournaled_started_counter"],
                "physical_provider_attempts_exact": None, "expected_records": 152,
                "valid": sum(row["status"] == "valid" for row in rows),
                "error": sum(row["status"] == "error" for row in rows), "progress_replace_fallbacks": 0,
                "gold_sent_to_model": False}
    def publish():
        if not write_progress(output, progress):
            progress["progress_replace_fallbacks"] += 1
    publish()
    with (output / "responses.jsonl").open("ab") as journal, (output / "reservations.jsonl").open("xb") as reservations:
        def call(probe, case, arm, repetition, payload, order_index):
            key = (probe, case["id"], arm, repetition)
            with lock:
                if key in by_id:
                    return by_id[key]
                if progress["new_reservations"] >= manifest["maximum_new_calls"] or progress["new_reservations"] >= NEW_CALL_CEILING:
                    raise RuntimeError("New-call ceiling reached")
                reservation = {"identity": list(key), "reserved_at": now(),
                               "new_attempt_sequence": progress["new_reservations"] + 1,
                               "payload_sha256": pilot.digest(pilot.encoded(payload)),
                               "prompt_sha256": pilot.digest(pilot.prompts()[arm].encode())}
                append_sync(reservations, reservation)
                progress["new_reservations"] += 1
                progress["model_calls_started"] += 1
                publish()
            record = pilot.single_call(pilot.ChatClient(settings), settings, probe, case["id"], arm,
                                       repetition, payload, pilot.prompts()[arm],
                                       lambda raw, tel: pilot.validate_extraction(raw, case), order_index)
            with lock:
                append_sync(journal, record)
                by_id[key] = record
                progress["record_count"] += 1
                progress[record["status"]] += 1
                publish()
            return record

        def worker(task):
            case, probe, repetition = task["case"], task["probe"], task["repetition"]
            if probe == "natural":
                base = call(probe, case, "base", repetition, pilot.extraction_payload(case), 0)
                state = pilot.draft_from_record(base, case)
            else:
                state = case["draft"]
            payload = pilot.revision_payload(case, state)
            for position, arm in enumerate(task["order"], start=1 if probe == "natural" else 0):
                selected = pilot.extraction_payload(case) if arm == "fresh" else payload
                call(probe, case, arm, repetition, selected, position)
        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                list(pool.map(worker, pilot.jobs(cases, seeds)))
            check_recovery(output, pilot)
            if set(by_id) != pilot.expected_identities(cases, seeds) or progress["record_count"] != 152:
                raise RuntimeError("Recovery incomplete")
            if progress["new_reservations"] != manifest["maximum_new_calls"]:
                raise RuntimeError("Recovery reservation accounting mismatch")
            progress.update(status="complete", completed_at=now(), frozen_artifacts_unchanged=True,
                            responses_sha256=sha(output / "responses.jsonl"),
                            recorded_provider_attempts=sum(len(row["telemetry"]["calls"]) for row in by_id.values()),
                            physical_provider_attempts_exact=None,
                            physical_attempts_note="Recorded attempts exclude the original unjournaled started-counter uncertainty; do not claim an exact total physical attempt count.")
        except BaseException:
            progress.update(status="aborted", completed_at=now())
            raise
        finally:
            publish()
    return progress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--original-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    output, env_file = args.output_dir.resolve(), args.env_file.resolve()
    if args.command == "prepare":
        if args.original_dir is None:
            parser.error("prepare needs --original-dir")
        result = prepare(args.original_dir, output)
    elif Path(__file__).resolve() != (output / "recovery-source" / "recovery.py").resolve():
        return subprocess.call([sys.executable, str(output / "recovery-source" / "recovery.py"), "run",
                                "--output-dir", str(output), "--env-file", str(env_file)], cwd=output / "source")
    else:
        result = run(output, env_file)
    print(json.dumps({"command": args.command, "output": str(output), "schema_version": result["schema_version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
