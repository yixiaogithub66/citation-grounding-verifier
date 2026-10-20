#!/usr/bin/env python3
"""Validate source-grounded gold cases and export endpoint-only requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED")
CLAIM_FIELDS = {"claim_text", "verdict", "reasoning", "citations"}
GOLD_FIELDS = CLAIM_FIELDS | {
    "claim_id", "answer_quote", "acceptable_evidence_sets", "required_passage_indices"
}


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def issue(errors: list[dict[str, str]], location: str, message: str) -> None:
    errors.append({"location": location, "message": message})


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def strict_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> Any:
        raise ValueError("Non-JSON numeric constant: " + value)

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds the finite float range: " + value)
        return number

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key: " + ascii(key))
            result[key] = value
        return result

    try:
        result = json.loads(
            text, parse_constant=reject_constant, parse_float=finite_float,
            object_pairs_hook=unique_object,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported limit") from exc
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON nesting exceeds 64 levels")
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON strings must not contain unpaired Unicode surrogates") from exc
        elif isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.keys())
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return result


def check_fields(
    value: dict[str, Any], required: set[str], location: str,
    errors: list[dict[str, str]], *, exact: bool = True,
) -> None:
    missing = required - value.keys()
    extra = value.keys() - required
    if missing:
        issue(errors, location, "Missing fields: " + ", ".join(sorted(missing)))
    if exact and extra:
        issue(errors, location, "Unexpected fields: " + ", ".join(sorted(extra)))


def validate_prediction(
    payload: Any, contexts: list[str], *, gold: bool = False,
    location: str = "response",
) -> list[dict[str, str]]:
    """Check the endpoint contract; this does not prove semantic entailment."""
    errors: list[dict[str, str]] = []
    if not isinstance(payload, dict):
        issue(errors, location, "Must be an object")
        return errors
    check_fields(payload, {"claims"}, location, errors)
    claims = payload.get("claims")
    if not isinstance(claims, list):
        issue(errors, location + ".claims", "Must be an array")
        return errors
    for claim_index, claim in enumerate(claims):
        prefix = f"{location}.claims[{claim_index}]"
        if not isinstance(claim, dict):
            issue(errors, prefix, "Must be an object")
            continue
        check_fields(claim, GOLD_FIELDS if gold else CLAIM_FIELDS, prefix, errors)
        for field in ("claim_text", "reasoning"):
            if not nonempty_string(claim.get(field)):
                issue(errors, prefix + "." + field, "Must be a nonempty string")
        verdict = claim.get("verdict")
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            issue(errors, prefix + ".verdict", "Must be one of " + ", ".join(VERDICTS))
        citations = claim.get("citations")
        if not isinstance(citations, list):
            issue(errors, prefix + ".citations", "Must be an array")
            continue
        if verdict in ("SUPPORTED", "CONTRADICTED") and not citations:
            issue(errors, prefix + ".citations", "This verdict requires evidence")
        if verdict == "UNSUPPORTED" and citations:
            issue(errors, prefix + ".citations", "UNSUPPORTED must have no citations")
        for citation_index, citation in enumerate(citations):
            cite_prefix = f"{prefix}.citations[{citation_index}]"
            if not isinstance(citation, dict):
                issue(errors, cite_prefix, "Must be an object")
                continue
            check_fields(citation, {"index", "quote"}, cite_prefix, errors, exact=False)
            unexpected = citation.keys() - {"index", "quote", "start_char", "end_char"}
            if unexpected:
                issue(errors, cite_prefix, "Unexpected fields: " + ", ".join(sorted(unexpected)))
            index, quote = citation.get("index"), citation.get("quote")
            valid_index = is_int(index) and 0 <= index < len(contexts)
            if not valid_index:
                issue(errors, cite_prefix + ".index", "Must be an in-bounds integer (not boolean)")
            if not nonempty_string(quote):
                issue(errors, cite_prefix + ".quote", "Must be a nonempty string")
            elif valid_index and quote not in contexts[index]:
                issue(errors, cite_prefix + ".quote", "Must be an exact substring of the indexed passage")
            has_start, has_end = "start_char" in citation, "end_char" in citation
            if has_start != has_end:
                issue(errors, cite_prefix, "Optional offsets require both start_char and end_char")
            elif has_start:
                start, end = citation["start_char"], citation["end_char"]
                valid_offsets = is_int(start) and is_int(end) and 0 <= start < end
                if not valid_offsets:
                    issue(errors, cite_prefix, "Offsets must be integers (not booleans) with 0 <= start_char < end_char")
                elif valid_index:
                    if end > len(contexts[index]):
                        issue(errors, cite_prefix, "Offsets exceed the indexed passage's Unicode character length")
                    elif contexts[index][start:end] != quote:
                        issue(errors, cite_prefix, "Offsets must select quote exactly using 0-based Unicode character positions [start_char, end_char)")
    return errors


def read_jsonl(path: Path, errors: list[dict[str, str]]) -> list[Any]:
    rows: list[Any] = []
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    issue(errors, f"{path.name}:{line_number}", "Blank JSONL lines are not permitted")
                    continue
                try:
                    rows.append(strict_json_loads(line))
                except ValueError as exc:
                    issue(errors, f"{path.name}:{line_number}", f"Invalid JSON: {exc}")
    except (OSError, UnicodeError) as exc:
        issue(errors, str(path), str(exc))
    return rows


def _index_array(
    values: Any, contexts: list[str], location: str, errors: list[dict[str, str]],
    *, allow_empty: bool = True,
) -> set[int] | None:
    if not isinstance(values, list):
        issue(errors, location, "Must be an array of passage indices")
        return None
    if not allow_empty and not values:
        issue(errors, location, "Evidence sets must not be empty")
    result: set[int] = set()
    for index in values:
        if not is_int(index) or not 0 <= index < len(contexts):
            issue(errors, location, "Each index must be an in-bounds integer (not boolean)")
        elif index in result:
            issue(errors, location, f"Duplicate passage index: {index}")
        else:
            result.add(index)
    return result


def check_dataset(
    cases_path: Path, sources_path: Path | None = None, *, check_local_sources: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    sources_path = sources_path or cases_path.with_name("sources.json")
    cases = read_jsonl(cases_path, errors)
    try:
        sources = strict_json_loads(sources_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        issue(errors, str(sources_path), str(exc))
        sources = {}
    if not isinstance(sources, dict):
        issue(errors, "sources", "Must be an object")
        sources = {}
    documents = sources.get("documents")
    passages = sources.get("passages")
    if not isinstance(documents, list):
        issue(errors, "sources.documents", "Must be an array")
        documents = []
    if not isinstance(passages, list):
        issue(errors, "sources.passages", "Must be an array")
        passages = []

    document_map: dict[str, dict[str, Any]] = {}
    for row, document in enumerate(documents):
        prefix = f"sources.documents[{row}]"
        if not isinstance(document, dict):
            issue(errors, prefix, "Must be an object")
            continue
        check_fields(document, {"id", "path", "sha256", "page_count"}, prefix, errors, exact=False)
        document_id = document.get("id")
        for field in ("id", "path"):
            if not nonempty_string(document.get(field)):
                issue(errors, prefix + "." + field, "Must be a nonempty string")
        digest = document.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            issue(errors, prefix + ".sha256", "Must be a 64-character SHA-256 hex digest")
        page_count = document.get("page_count")
        if not is_int(page_count) or page_count <= 0:
            issue(errors, prefix + ".page_count", "Must be a positive integer")
        if nonempty_string(document_id):
            if document_id in document_map:
                issue(errors, prefix + ".id", "Duplicate document id: " + document_id)
            document_map[document_id] = document
        if check_local_sources and nonempty_string(document.get("path")):
            local_path = Path(document["path"])
            if not local_path.is_absolute():
                local_path = sources_path.parent / local_path
            try:
                with local_path.open("rb") as handle:
                    hasher = hashlib.sha256()
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        hasher.update(chunk)
                    actual = hasher.hexdigest()
                if isinstance(digest, str) and actual.lower() != digest.lower():
                    issue(errors, prefix + ".sha256", "Local PDF hash does not match")
            except OSError as exc:
                issue(errors, prefix + ".path", str(exc))

    passage_map: dict[str, dict[str, Any]] = {}
    for row, passage in enumerate(passages):
        prefix = f"sources.passages[{row}]"
        if not isinstance(passage, dict):
            issue(errors, prefix, "Must be an object")
            continue
        check_fields(passage, {"id", "document_id", "pages", "text", "normalization", "locator"}, prefix, errors, exact=False)
        passage_id, document_id = passage.get("id"), passage.get("document_id")
        for field in ("id", "document_id", "text"):
            if not nonempty_string(passage.get(field)):
                issue(errors, prefix + "." + field, "Must be a nonempty string")
        if not isinstance(document_id, str) or document_id not in document_map:
            issue(errors, prefix + ".document_id", "Unknown document id")
        pages = passage.get("pages")
        if not isinstance(pages, list) or not pages:
            issue(errors, prefix + ".pages", "Must be a nonempty array of 1-based page numbers")
        else:
            page_count = document_map.get(document_id, {}).get("page_count") if isinstance(document_id, str) else None
            for page in pages:
                if not is_int(page) or page < 1 or (is_int(page_count) and page > page_count):
                    issue(errors, prefix + ".pages", "Page number is outside the source document")
            valid_pages = [page for page in pages if is_int(page)]
            if len(valid_pages) != len(set(valid_pages)):
                issue(errors, prefix + ".pages", "Duplicate page numbers")
        for field in ("normalization", "locator"):
            value = passage.get(field)
            if not ((isinstance(value, str) and value.strip()) or (isinstance(value, (dict, list)) and value)):
                issue(errors, prefix + "." + field, "Must describe source location or transcription normalization")
        if nonempty_string(passage_id):
            if passage_id in passage_map:
                issue(errors, prefix + ".id", "Duplicate passage id: " + passage_id)
            passage_map[passage_id] = passage

    case_ids: set[str] = set()
    problem_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    verdict_counts: Counter[str] = Counter()
    for row, case in enumerate(cases):
        prefix = f"cases[{row}]"
        if not isinstance(case, dict):
            issue(errors, prefix, "Must be an object")
            continue
        check_fields(case, {"id", "split", "category", "topic", "problem_id", "context_passage_ids", "input", "expected"}, prefix, errors, exact=False)
        for field in ("id", "split", "category", "topic", "problem_id"):
            if not nonempty_string(case.get(field)):
                issue(errors, prefix + "." + field, "Must be a nonempty string")
        case_id = case.get("id")
        if nonempty_string(case_id):
            if case_id in case_ids:
                issue(errors, prefix + ".id", "Duplicate case id: " + case_id)
            case_ids.add(case_id)
        split, category, problem_id = case.get("split"), case.get("category"), case.get("problem_id")
        if nonempty_string(split):
            split_counts[split] += 1
        if nonempty_string(category):
            category_counts[category] += 1
        if nonempty_string(problem_id) and nonempty_string(split):
            problem_splits[problem_id].add(split)
        request = case.get("input")
        if not isinstance(request, dict):
            issue(errors, prefix + ".input", "Must be an object")
            continue
        check_fields(request, {"context_passages", "generated_answer"}, prefix + ".input", errors)
        contexts, answer = request.get("context_passages"), request.get("generated_answer")
        if not isinstance(contexts, list) or any(not isinstance(text, str) for text in contexts):
            issue(errors, prefix + ".input.context_passages", "Must be an array of strings")
            continue
        if not isinstance(answer, str):
            issue(errors, prefix + ".input.generated_answer", "Must be a string")
            continue
        context_ids = case.get("context_passage_ids")
        if not isinstance(context_ids, list) or any(not nonempty_string(item) for item in context_ids):
            issue(errors, prefix + ".context_passage_ids", "Must be an array of source passage ids")
        else:
            if len(context_ids) != len(contexts):
                issue(errors, prefix + ".context_passage_ids", "Must have one source id for each context passage")
            for index, passage_id in enumerate(context_ids):
                if passage_id not in passage_map:
                    issue(errors, prefix + f".context_passage_ids[{index}]", "Unknown passage id")
                elif index < len(contexts) and passage_map[passage_id].get("text") != contexts[index]:
                    issue(errors, prefix + f".input.context_passages[{index}]", "Must match the source passage text exactly")
        expected = case.get("expected")
        errors.extend(validate_prediction(expected, contexts, gold=True, location=prefix + ".expected"))
        gold_claims = expected.get("claims", []) if isinstance(expected, dict) else []
        if not isinstance(gold_claims, list):
            continue
        claim_ids: set[str] = set()
        multi_passage_claim = False
        for claim_index, claim in enumerate(gold_claims):
            claim_prefix = prefix + f".expected.claims[{claim_index}]"
            if not isinstance(claim, dict):
                continue
            claim_id = claim.get("claim_id")
            if not nonempty_string(claim_id):
                issue(errors, claim_prefix + ".claim_id", "Must be a nonempty string")
            elif claim_id in claim_ids:
                issue(errors, claim_prefix + ".claim_id", "Duplicate claim id in this case")
            else:
                claim_ids.add(claim_id)
            answer_quote = claim.get("answer_quote")
            if not nonempty_string(answer_quote) or answer_quote not in answer:
                issue(errors, claim_prefix + ".answer_quote", "Must be a nonempty exact substring of generated_answer")
            verdict = claim.get("verdict")
            if isinstance(verdict, str) and verdict in VERDICTS:
                verdict_counts[verdict] += 1
            required = _index_array(claim.get("required_passage_indices"), contexts, claim_prefix + ".required_passage_indices", errors)
            if required is not None and len(required) >= 2:
                multi_passage_claim = True
            evidence_sets = claim.get("acceptable_evidence_sets")
            parsed_sets: list[set[int]] = []
            if not isinstance(evidence_sets, list):
                issue(errors, claim_prefix + ".acceptable_evidence_sets", "Must be an array of alternative passage-index arrays")
            else:
                for set_index, evidence_set in enumerate(evidence_sets):
                    parsed = _index_array(evidence_set, contexts, claim_prefix + f".acceptable_evidence_sets[{set_index}]", errors, allow_empty=False)
                    if parsed is not None:
                        parsed_sets.append(parsed)
                        if required is not None and not required.issubset(parsed):
                            issue(errors, claim_prefix + ".acceptable_evidence_sets", "Every acceptable evidence set must contain all required passage indices")
            if verdict == "UNSUPPORTED":
                if required or evidence_sets:
                    issue(errors, claim_prefix, "UNSUPPORTED must have empty evidence sets and required indices")
            elif isinstance(verdict, str) and verdict in VERDICTS:
                if not parsed_sets:
                    issue(errors, claim_prefix + ".acceptable_evidence_sets", "This verdict requires at least one acceptable evidence set")
                citations = claim.get("citations")
                cited = {item["index"] for item in citations if isinstance(item, dict) and is_int(item.get("index"))} if isinstance(citations, list) else set()
                if required is not None and not required.issubset(cited):
                    issue(errors, claim_prefix + ".citations", "Gold citations must cover all required passages")
                if parsed_sets and not any(item.issubset(cited) for item in parsed_sets):
                    issue(errors, claim_prefix + ".citations", "Gold citations must cover at least one acceptable evidence set")
        normalized_category = category.lower().replace("-", "_") if isinstance(category, str) else ""
        if ("multi_passage" in normalized_category or "cross_passage" in normalized_category) and not multi_passage_claim:
            issue(errors, prefix + ".expected", "Multi-passage cases require a claim with at least two required passage indices")
    for problem_id, splits in sorted(problem_splits.items()):
        if len(splits) > 1:
            issue(errors, "splits", f"Problem {problem_id} occurs in multiple splits: {', '.join(sorted(splits))}")
    if not cases:
        issue(errors, "cases", "Dataset must contain at least one case")
    if not check_local_sources:
        warnings.append("Source PDF availability and hashes were not rechecked; use --check-local-sources to do so.")
    report = {
        "valid": not errors,
        "dataset": str(cases_path.resolve()),
        "sources": str(sources_path.resolve()),
        "case_count": len(cases),
        "document_count": len(documents),
        "passage_count": len(passages),
        "split_counts": dict(sorted(split_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "gold_verdict_counts": dict(sorted(verdict_counts.items())),
        "problem_splits": {key: sorted(value) for key, value in sorted(problem_splits.items())},
        "errors": errors,
        "warnings": warnings,
        "manual_review_required": [
            "Whether every factual statement in each generated_answer has been decomposed into atomic claims.",
            "Whether verdicts, transcribed formulas, and acceptable or required evidence sets are semantically correct.",
            "Whether each transcription accurately represents the indicated PDF pages and figures.",
        ],
    }
    return cases, report


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def export_dataset(cases: list[dict[str, Any]], directory: Path) -> list[str]:
    paths = [directory / name for name in ("inputs.jsonl", "manifest.jsonl", "gold.jsonl")]
    write_jsonl(paths[0], [case["input"] for case in cases])
    write_jsonl(paths[1], [
        {"row_index": row, "line_number": row + 1, **{field: case[field] for field in ("id", "split", "category", "topic", "problem_id")}}
        for row, case in enumerate(cases)
    ])
    write_jsonl(paths[2], [{"id": case["id"], "expected": case["expected"]} for case in cases])
    return [str(path.resolve()) for path in paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset" / "cphos28" / "cases.jsonl")
    parser.add_argument("--sources", type=Path, help="Defaults to sources.json next to the dataset")
    parser.add_argument("--check-local-sources", action="store_true", help="Require local source files and verify their SHA-256 hashes")
    parser.add_argument("--export", action="store_true", help="Regenerate inputs.jsonl, manifest.jsonl, and gold.jsonl after validation")
    parser.add_argument("--export-dir", type=Path, help="Defaults to the dataset directory")
    parser.add_argument("--output-report", type=Path, help="Write the complete machine-readable validation report")
    args = parser.parse_args()
    cases, report = check_dataset(args.dataset, args.sources, check_local_sources=args.check_local_sources)
    if report["valid"] and args.export:
        report["exports"] = export_dataset(cases, args.export_dir or args.dataset.parent)
    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
