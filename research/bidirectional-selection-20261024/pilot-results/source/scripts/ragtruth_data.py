#!/usr/bin/env python3
"""Prepare a deterministic, source-grouped RAGTruth benchmark without inference.

Gold is kept in a separate native-label artifact. Sampling and input eligibility
never consult labels. The input contract has no question field, so QA questions
are deliberately omitted and that difference is recorded in every QA mapping.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.contracts import VerificationError, VerificationRequest
from grounding.server import MAX_BODY_BYTES


TASKS = ("QA", "Summary", "Data2txt")
DEFAULT_SEED = "ragtruth-blind-v1-20261022"
LABEL_TYPES = frozenset({
    "Evident Conflict", "Evident Baseless Info", "Subtle Conflict", "Subtle Baseless Info",
})
ADAPTER_VERSION = "ragtruth-native-v1"


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ValueError("Non-finite JSON number.")


def _loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_json_object, parse_constant=_nonfinite)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load strict JSON objects, without embedding record content in errors."""
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = _loads(line)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid JSON object in {Path(path).name}, line {number}.") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object in {Path(path).name}, line {number}.")
            rows.append(value)
    return rows


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_input_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def input_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_input_bytes(value)).hexdigest()


def _identifier(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing or invalid {key}.")
    return value


def _qa_passages(original: str) -> tuple[list[str], dict[str, Any]]:
    # Only the upstream's explicit, sequential, blank-line-separated markers
    # count as boundaries. An ambiguous block remains one exact original string.
    markers = list(re.finditer(r"(?m)^passage ([1-9][0-9]*):", original))
    broad_markers = list(re.finditer(r"(?m)^passage [^\r\n:]*:", original))
    unambiguous = (
        len(markers) >= 2 and len(markers) == len(broad_markers)
        and markers[0].start() == 0
        and [int(marker.group(1)) for marker in markers] == list(range(1, len(markers) + 1))
        and all(original[:marker.start()].endswith(("\n\n", "\r\n\r\n"))
                for marker in markers[1:])
    )
    starts = [marker.start() for marker in markers] if unambiguous else [0]
    ends = starts[1:] + [len(original)]
    passages = [original[start:end] for start, end in zip(starts, ends)]
    return passages, {
        "evidence_field": "source_info.passages",
        "mapping": "exact_numbered_slices" if unambiguous else "exact_original_block",
        "offset_unit": "python_unicode_characters",
        "offset_convention": "[start,end)",
        "passage_offsets": [{"start": start, "end": end} for start, end in zip(starts, ends)],
        "preserves_all_characters": True,
        "question_included": False,
        "question_omission_reason": "VerificationRequest has no question field; QA questions are not evidence.",
        "contract_difference": "Upstream QA question omitted from verifier input.",
    }


def _adapt_source(source: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    task, raw = source["task_type"], source.get("source_info")
    if task == "QA":
        if not isinstance(raw, dict) or not isinstance(raw.get("passages"), str):
            raise ValueError("QA source_info.passages must be a string.")
        contexts, metadata = _qa_passages(raw["passages"])
    elif task == "Summary":
        if not isinstance(raw, str):
            raise ValueError("Summary source_info must be a string.")
        contexts = [raw]
        metadata = {
            "evidence_field": "source_info", "mapping": "exact_original_block",
            "offset_unit": "python_unicode_characters", "offset_convention": "[start,end)",
            "passage_offsets": [{"start": 0, "end": len(raw)}], "preserves_all_characters": True,
        }
    else:
        if not isinstance(raw, dict):
            raise ValueError("Data2txt source_info must be a JSON object.")
        contexts = [json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)]
        metadata = {
            "evidence_field": "source_info", "mapping": "deterministic_json_serialization",
            "json_serialization": {"ensure_ascii": False, "sort_keys": True, "indent": 2, "allow_nan": False},
            "null_and_boolean_preserved": True,
        }
    metadata.update({"version": ADAPTER_VERSION, "response_field": "response",
                     "response_unchanged": True, "labels_used_as_evidence": False,
                     "prompt_used_as_evidence": False})
    return contexts, metadata


def _preflight(request: dict[str, Any]) -> tuple[str | None, dict[str, int]]:
    try:
        VerificationRequest.from_dict(request)
    except VerificationError as exc:
        if exc.code == "input_too_large":
            return "verification_request_too_large", {}
        raise ValueError("Input fails VerificationRequest validation.") from exc
    # The second representation is conservative for clients using json.dumps
    # defaults; the canonical UTF-8 representation is used for the input hash.
    sizes = {
        "canonical_utf8_bytes": len(canonical_input_bytes(request)),
        "default_json_bytes": len(json.dumps(request, allow_nan=False).encode("utf-8")),
    }
    if max(sizes.values()) > MAX_BODY_BYTES:
        return "http_body_too_large", sizes
    return None, sizes


def _validate_labels(row: dict[str, Any]) -> list[dict[str, Any]]:
    labels = row.get("labels")
    if not isinstance(labels, list):
        raise ValueError("Selected response labels must be an array.")
    answer = row["response"]
    for index, label in enumerate(labels):
        prefix = f"Invalid selected label {index} (response id {row['id']})."
        if not isinstance(label, dict):
            raise ValueError(prefix + " Expected object.")
        start, end = label.get("start"), label.get("end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(answer):
            raise ValueError(prefix + " Invalid Python character [start,end) bounds.")
        if not isinstance(label.get("text"), str) or answer[start:end] != label["text"]:
            raise ValueError(prefix + " Text does not match the exact response slice.")
        if label.get("label_type") not in LABEL_TYPES:
            raise ValueError(prefix + " Unknown native label_type.")
    return labels


def _write_json(path: Path, value: Any, *, lines: bool = False) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        if lines:
            for row in value:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False) + "\n")
        else:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def prepare_dataset(raw_dir: Path, output_dir: Path, *, split: str = "test",
                    sources_per_task: int = 10, seed: str = DEFAULT_SEED) -> dict[str, Any]:
    """Write an exclusive new artifact directory; never run a model or read .env.

    A source is eligible only when every quality=='good' response passes input
    limits. Excluding the whole source preserves the required response grouping.
    Native labels are validated only after sampling, and any error aborts output.
    """
    raw_dir, output_dir = Path(raw_dir), Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("Output directory already exists; refusing to overwrite.")
    if split not in {"train", "test"}:
        raise ValueError("split must be train or test.")
    if type(sources_per_task) is not int or sources_per_task < 0:
        raise ValueError("sources_per_task must be a nonnegative integer.")
    if not isinstance(seed, str) or not seed:
        raise ValueError("seed must be a nonempty string.")
    try:
        upstream = _loads((raw_dir / "provenance.json").read_text(encoding="utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid upstream provenance JSON.") from exc
    if not isinstance(upstream, dict):
        raise ValueError("Upstream provenance must be an object.")
    provenance_files = upstream.get("files")
    if not isinstance(provenance_files, dict):
        raise ValueError("Upstream provenance must bind raw files to SHA256 digests.")
    raw_hashes = {}
    for name in ("source_info.jsonl", "response.jsonl"):
        binding = provenance_files.get(name)
        expected = binding.get("sha256") if isinstance(binding, dict) else None
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("Upstream provenance has a missing or invalid raw-file SHA256.")
        actual = file_sha256(raw_dir / name)
        if actual != expected:
            raise ValueError("Raw file SHA256 does not match upstream provenance.")
        raw_hashes[name] = actual
    raw_hashes["provenance.json"] = file_sha256(raw_dir / "provenance.json")
    source_rows = load_jsonl(raw_dir / "source_info.jsonl")
    response_rows = load_jsonl(raw_dir / "response.jsonl")

    sources: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        sid = _identifier(row, "source_id")
        if sid in sources:
            raise ValueError("Duplicate source_id in source_info.jsonl.")
        if row.get("task_type") not in TASKS:
            raise ValueError("Unknown source task_type.")
        sources[sid] = row
    ids: set[str] = set()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_splits: dict[str, set[str]] = defaultdict(set)
    for row in response_rows:
        rid, sid = _identifier(row, "id"), _identifier(row, "source_id")
        if rid in ids:
            raise ValueError("Duplicate response id.")
        ids.add(rid)
        if sid not in sources:
            raise ValueError("Response source_id has no source_info join.")
        if row.get("split") not in {"train", "test"}:
            raise ValueError("Unknown official response split.")
        if not isinstance(row.get("response"), str):
            raise ValueError("Response must be a string.")
        _identifier(row, "quality")
        _identifier(row, "model")
        source_splits[sid].add(row["split"])
        grouped[sid].append(row)
    if any(len(values) != 1 for values in source_splits.values()):
        raise ValueError("A source_id crosses official train/test splits.")

    eligible: dict[str, list[str]] = {task: [] for task in TASKS}
    candidates: dict[str, tuple[list[dict[str, Any]], list[str], dict[str, Any], dict[str, dict[str, int]]]] = {}
    exclusions: list[dict[str, Any]] = []
    available_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()
    for sid in sorted(grouped):
        if source_splits[sid] != {split}:
            continue
        task = sources[sid]["task_type"]
        available_counts[task] += 1
        rows = sorted(grouped[sid], key=lambda row: row["id"])
        quality_counts.update(row["quality"] for row in rows)
        good = [row for row in rows if row["quality"] == "good"]
        if not good:
            exclusions.append({"source_id": sid, "task_type": task, "reason": "no_good_responses",
                               "excluded_good_response_count": 0})
            continue
        contexts, metadata = _adapt_source(sources[sid])
        failures, sizes_by_id = [], {}
        for row in good:
            reason, sizes = _preflight({"context_passages": contexts, "generated_answer": row["response"]})
            if reason:
                failures.append({"id": row["id"], "reason": reason})
            sizes_by_id[row["id"]] = sizes
        if failures:
            exclusions.append({"source_id": sid, "task_type": task, "reason": "source_group_input_limit",
                               "excluded_good_response_count": len(good), "failed_responses": failures})
            continue
        eligible[task].append(sid)
        candidates[sid] = good, contexts, metadata, sizes_by_id

    def sample_key(task: str, sid: str) -> tuple[str, str]:
        return hashlib.sha256(f"{seed}|{task}|{sid}".encode("utf-8")).hexdigest(), sid

    selected: dict[str, list[str]] = {}
    for task in TASKS:
        ordered = sorted(eligible[task], key=lambda sid: sample_key(task, sid))
        if sources_per_task and len(ordered) < sources_per_task:
            raise ValueError(f"Insufficient eligible {task} source groups for requested sample.")
        selected[task] = ordered[:sources_per_task] if sources_per_task else ordered

    inputs, manifests, gold = [], [], []
    selected_counts: Counter[str] = Counter()
    for task in TASKS:
        for sid in selected[task]:
            good, contexts, metadata, sizes_by_id = candidates[sid]
            for row in good:
                # Selection is complete before gold is inspected. Invalid gold
                # fails the run; no replacement source or response is sampled.
                labels = _validate_labels(row)
                request = {"context_passages": list(contexts), "generated_answer": row["response"]}
                inputs.append({"id": row["id"], "input": request})
                manifests.append({
                    "id": row["id"], "source_id": sid, "task_type": task,
                    "generator": row["model"], "upstream_split": row["split"], "quality": row["quality"],
                    "input_sha256": input_sha256(request), "adapter": metadata,
                    "request_size": sizes_by_id[row["id"]], "source_sample_key": sample_key(task, sid)[0],
                })
                gold.append({"id": row["id"], "source_id": sid, "labels": labels,
                             "has_hallucination": bool(labels)})
                selected_counts[task] += 1

    preparation = {
        "schema_version": "1.0", "kind": "ragtruth-preparation", "adapter_version": ADAPTER_VERSION,
        "split": split, "seed": seed, "sources_per_task": sources_per_task,
        "sampling_policy": {
            "unit": "source_id", "tasks": list(TASKS), "quality_filter": "quality == 'good'",
            "quality_is_hallucination_label": False,
            "ordering": "sha256(seed + '|' + task_type + '|' + source_id), then source_id",
            "selection": "first N eligible sources per task; N=0 means all",
            "retain_all_good_responses_for_selected_source": True, "uses_gold_labels": False,
            "input_limit_policy": "exclude entire source before sampling if any good response is too large; never truncate",
        },
        "native_gold_policy": {
            "labels_preserved": True, "offset_unit": "python_unicode_characters", "offset_convention": "[start,end)",
            "invalid_selected_labels": "abort; no repairs, drops, or replacements",
            "mapped_to_gist_claims": False, "has_hallucination": "bool(original labels)",
        },
        "counts": {
            "upstream_sources": len(source_rows), "upstream_responses": len(response_rows),
            "unreferenced_sources": len(set(sources) - set(grouped)),
            "split_sources_by_task": {task: available_counts[task] for task in TASKS},
            "split_response_quality": dict(sorted(quality_counts.items())),
            "eligible_sources_by_task": {task: len(eligible[task]) for task in TASKS},
            "selected_sources_by_task": {task: len(selected[task]) for task in TASKS},
            "selected_responses_by_task": {task: selected_counts[task] for task in TASKS},
            "selected_responses": len(inputs), "excluded_sources": len(exclusions),
        },
        "selected_source_ids": selected, "exclusions": exclusions,
        "upstream_provenance": upstream,
        "raw_files_sha256": raw_hashes,
        "adapter_code_sha256": file_sha256(Path(__file__)),
        "preflight": {"contract": "grounding.contracts.VerificationRequest.from_dict",
                      "contract_sha256": file_sha256(ROOT / "grounding" / "contracts.py"),
                      "http_max_body_bytes": MAX_BODY_BYTES,
                      "http_serializations_checked": ["canonical UTF-8 JSON", "json.dumps defaults"]},
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    reserved = False
    with tempfile.TemporaryDirectory(prefix=".ragtruth-stage-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        for name, rows in (("inputs.jsonl", inputs), ("manifest.jsonl", manifests), ("native_gold.jsonl", gold)):
            _write_json(staging / name, rows, lines=True)
        preparation["artifacts_sha256"] = {
            name: file_sha256(staging / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl")
        }
        _write_json(staging / "preparation.json", preparation)
        try:
            output_dir.mkdir()  # Exclusive reservation, including on POSIX.
            reserved = True
            for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json"):
                destination = output_dir / name
                # Hard links publish each fully flushed file atomically and fail
                # rather than overwrite. preparation.json is the commit marker.
                os.link(staging / name, destination)
                created.append(destination)
        except OSError:
            for destination in created:
                destination.unlink(missing_ok=True)
            if reserved:
                output_dir.rmdir()
            raise
    return preparation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "test"), default="test")
    parser.add_argument("--sources-per-task", type=int, default=10, help="0 selects all eligible sources")
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    try:
        manifest = prepare_dataset(args.raw_dir, args.output_dir, split=args.split,
                                   sources_per_task=args.sources_per_task, seed=args.seed)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Never display raw records, answers, evidence, labels, or arbitrary
        # exception messages from external data during a blind preparation.
        print(f"RAGTruth preparation failed ({type(exc).__name__}); no benchmark inference was run.", file=sys.stderr)
        return 2
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "counts": manifest["counts"],
                      "model_calls": 0}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
