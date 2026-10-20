#!/usr/bin/env python3
"""Run baseline, minimal, and optimized verifiers with isolated gold scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.contracts import VerificationError, VerificationRequest
from grounding.factory import build_verifier
from grounding.scoring import (
    AMBIGUITY_MARGIN, SIMILARITY_THRESHOLD, SPAN_OVERLAP_THRESHOLD,
    aggregate_backend, score_case,
)
from scripts.validate_dataset import check_dataset


BACKENDS = ("baseline", "minimal", "optimized")
LIMITATIONS = [
    "Strict metrics require NFC/whitespace-normalized claim text equality. They penalize missing claims and extra predictions, including failures.",
    "Approximate metrics are deterministic alignment diagnostics, not semantic accuracy. Alignment ignores verdicts and rejects ambiguous or low-similarity candidates; inspect per-case audits.",
    "Exact substring validity does not establish that a citation entails a claim. Evidence-set coverage and gold-quote containment measure annotated evidence recall, not semantic citation precision.",
    "Gold labels and transcriptions are AI-assisted and await user review. Formula equivalence, legitimate alternate decomposition, and paraphrase identity can require human adjudication.",
    "Latency includes every stage and retry. Backends run sequentially in fixed order per case; provider caching and network conditions can affect comparisons.",
    "Token counts include every recorded upstream attempt. Missing upstream usage is unknown, not zero. Cost estimates require explicit prices and are not provider billing.",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _redact(value: Any, secret: str | None) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "<redacted>") if secret else value
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item, secret) for key, item in value.items()}
    return value


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def provenance(dataset: Path, sources: Path, check_local: bool) -> dict[str, Any]:
    code_paths = sorted((ROOT / "grounding").glob("*.py"))
    code_paths += [ROOT / "scripts" / "benchmark.py", ROOT / "scripts" / "validate_dataset.py"]
    prompt_paths = sorted((ROOT / "prompts").glob("**/*"))
    prompt_paths = [path for path in prompt_paths if path.is_file()]
    hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): _sha(path) for path in code_paths + prompt_paths}
    combined = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()
    source_data = json.loads(sources.read_text(encoding="utf-8-sig"))
    return {
        "dataset_path": str(dataset.resolve()),
        "dataset_sha256": _sha(dataset),
        "sources_path": str(sources.resolve()),
        "sources_sha256": _sha(sources),
        "source_documents": [
            {"id": item.get("id"), "sha256": item.get("sha256")}
            for item in source_data.get("documents", [])
        ],
        "local_source_hashes_rechecked": check_local,
        "code_and_prompt_files_sha256": hashes,
        "implementation_sha256": combined,
        "python_version": sys.version.split()[0],
    }


def _format(value: Any, *, percent: bool = False) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    if value is None:
        return "n/a"
    if percent:
        return f"{100 * value:.1f}%"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    config = report["config"]
    lines = [
        "# Three-approach benchmark",
        "",
        f"Run `{report['run_id']}`; status **{report['status']}**; split `{config['split']}`.",
        f"Completed {report['completed_records']} / {report['planned_records']} case/backend records.",
        f"Model `{config['settings'].get('model', 'unspecified')}`. All LLM backends share the saved model and generation settings.",
        "",
        "| Approach | Cases | Valid | Strict claim F1 | Strict macro F1 | Approx. claim F1* | Exact source quote | Passage coverage* | Mean s | P50 s | P95 s | Input / output tokens | Estimated cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["backends"].items():
        usage, cost = summary["usage"], summary["cost"]
        cost_text = f"{_format(cost['estimated_amount'])} {cost['currency']}" if cost["estimated_amount"] is not None else "not priced / unknown"
        lines.append(
            f"| {name} | {summary['case_count']} | {_format(summary['success_rate'], percent=True)}"
            f" | {_format(summary['strict']['claim_f1'], percent=True)}"
            f" | {_format(summary['strict']['macro_f1'], percent=True)}"
            f" | {_format(summary['approximate']['claim_f1'], percent=True)}"
            f" | {_format(summary['citations']['exact_substring_rate'], percent=True)}"
            f" | {_format(summary['citations']['approximate']['passage_coverage'], percent=True)}"
            f" | {_format(summary['latency']['mean_seconds'])} | {_format(summary['latency']['p50_seconds'])}"
            f" | {_format(summary['latency']['p95_seconds'])}"
            f" | {usage['prompt_tokens']} / {usage['completion_tokens']} | {cost_text} |"
        )
    lines += [
        "",
        "*Approximate alignment and associated passage coverage are diagnostics, not semantic claim or citation accuracy. Strict and approximate scores include omissions/extras; no single-claim count shortcut is used.",
        "",
        "## Evidence and alignment audit",
        "",
        "| Approach | Strict passage coverage | Approx. passage coverage | Approx. gold quote containment | Approx. gold quote exact match | Alignment review cases | Nonexact pairs | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["backends"].items():
        cites = summary["citations"]
        lines.append(
            f"| {name} | {_format(cites['strict']['passage_coverage'], percent=True)}"
            f" | {_format(cites['approximate']['passage_coverage'], percent=True)}"
            f" | {_format(cites['approximate']['gold_quote_containment'], percent=True)}"
            f" | {_format(cites['approximate']['gold_quote_exact_match'], percent=True)}"
            f" | {summary['approximate']['alignment_review_case_count']}"
            f" | {summary['approximate']['nonexact_alignment_count']} | {summary['error_count']} |"
        )
    lines += ["", "## Recorded failures", "", "| Approach | Case | Category | Diagnosis |", "|---|---|---|---|"]
    failure_count = 0
    for name, summary in report["backends"].items():
        for failure in summary["failures"]:
            failure_count += 1
            lines.append(f"| {name} | {failure['id']} | {failure['category']} | {', '.join(failure['reasons'])} |")
    if not failure_count:
        lines.append("| All | - | - | No scored failures in completed records |")
    if "minimal" in report["backends"] and "optimized" in report["backends"]:
        paired = report.get("paired_comparison", {})
        lines += [
            "", "## Minimal to optimized comparison", "",
            f"Comparable completed cases: {paired.get('paired_case_count', 0)}.",
            f"Strict complete-case improvements: {paired.get('strict_improved_case_ids', [])}.",
            f"Strict complete-case regressions: {paired.get('strict_regressed_case_ids', [])}.",
            f"Approximate diagnostic improvements: {paired.get('approximate_improved_case_ids', [])}.",
            f"Approximate diagnostic regressions: {paired.get('approximate_regressed_case_ids', [])}.",
            "These are observed comparisons, not evidence that the optimized system is always better. Inspect the per-case response and alignment audit before attributing a change to prompting.",
        ]
    lines += ["", "## Reproducibility and limitations", ""]
    lines += [f"- {limitation}" for limitation in report["limitations"]]
    lines += [
        f"- Dataset SHA-256: `{report['provenance']['dataset_sha256']}`.",
        f"- Implementation SHA-256: `{report['provenance']['implementation_sha256']}`.",
        "- `config.json` is immutable within this run. `responses.jsonl` contains each completed result, stage trace, usage, and score; report files are checkpointed after each record.",
        "- `report.json` retains metric numerators/denominators, missing/extra confusion cells, category breakdowns, cache usage, and all alignment audits.",
        "",
    ]
    return "\n".join(lines)


def make_report(
    records: list[dict[str, Any]], config: dict[str, Any], source_info: dict[str, Any],
    run_id: str, status: str,
) -> dict[str, Any]:
    backend_names = config["backends"]
    by_backend = {
        name: aggregate_backend([record for record in records if record["backend"] == name], config["prices"])
        for name in backend_names
    }
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": config["created_at"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "config": config,
        "provenance": source_info,
        "selected_case_ids": config["selected_case_ids"],
        "planned_records": len(config["selected_case_ids"]) * len(backend_names),
        "completed_records": len(records),
        "backends": by_backend,
        "alignment_policy": {
            "strict": "NFC plus collapsed whitespace; otherwise exact case-sensitive claim text",
            "approximate": "strict first, then gold answer span, span overlap, or high SequenceMatcher similarity; mutual-best margin; matching ignores verdict",
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "span_overlap_threshold": SPAN_OVERLAP_THRESHOLD,
            "ambiguity_margin": AMBIGUITY_MARGIN,
            "critical_tokens": "Numeric, negation, and ordered mathematical token mismatch prevents approximate alignment; identifiers and operators remain case-sensitive.",
        },
        "limitations": LIMITATIONS,
    }
    minimal = {r["id"]: r for r in records if r["backend"] == "minimal"}
    optimized = {r["id"]: r for r in records if r["backend"] == "optimized"}
    comparable = sorted(minimal.keys() & optimized.keys())
    report["paired_comparison"] = {"paired_case_count": len(comparable)}
    for mode in ("strict", "approximate"):
        report["paired_comparison"][f"{mode}_improved_case_ids"] = [
            key for key in comparable if not minimal[key]["score"][mode]["case_correct"] and optimized[key]["score"][mode]["case_correct"]
        ]
        report["paired_comparison"][f"{mode}_regressed_case_ids"] = [
            key for key in comparable if minimal[key]["score"][mode]["case_correct"] and not optimized[key]["score"][mode]["case_correct"]
        ]
    return report


def run_cases(
    cases: list[dict[str, Any]], verifiers: dict[str, Any], output_dir: Path,
    config: dict[str, Any], source_info: dict[str, Any], *, secret: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    run_id = output_dir.name

    def checkpoint(status: str) -> dict[str, Any]:
        report = _redact(make_report(records, config, source_info, run_id, status), secret)
        _write_json(output_dir / "report.json", report)
        temporary = output_dir / "report.md.tmp"
        temporary.write_text(render_markdown(report), encoding="utf-8")
        temporary.replace(output_dir / "report.md")
        return report

    checkpoint("running")
    try:
        with (output_dir / "responses.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for case in cases:
                for name, verifier in verifiers.items():
                    started = time.perf_counter()
                    prediction, telemetry, error = None, {"calls": []}, None
                    try:
                        # Build a fresh request for every backend. Gold and metadata stay here.
                        request = VerificationRequest.from_dict({
                            "context_passages": list(case["input"]["context_passages"]),
                            "generated_answer": case["input"]["generated_answer"],
                        })
                        result = verifier.verify(request)
                        prediction, telemetry = result.report, result.telemetry
                    except VerificationError as exc:
                        error = {
                            "code": exc.code,
                            "message": getattr(exc, "message", str(exc)),
                            "status": getattr(exc, "status", 502),
                        }
                        telemetry = getattr(exc, "telemetry", None) or {"calls": []}
                    except Exception as exc:
                        # Unknown exception text may contain an endpoint or credential.
                        error = {"code": "internal_error", "message": type(exc).__name__, "status": 500}
                    duration = time.perf_counter() - started
                    record = _redact({
                        "id": case["id"], "split": case["split"], "category": case["category"],
                        "backend": name,
                        "input_sha256": hashlib.sha256(json.dumps(case["input"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                        "prediction": prediction, "telemetry": telemetry or {"calls": []},
                        "error": error, "latency_seconds": duration,
                        "score": score_case(case, prediction, error),
                    }, secret)
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    records.append(record)
                    checkpoint("running")
                    state = "valid" if record["score"]["schema_valid"] else "error"
                    print(f"[{len(records)}/{len(cases) * len(verifiers)}] {name} {case['id']}: {state}, {duration:.3f}s", flush=True)
    except KeyboardInterrupt:
        report = checkpoint("interrupted")
        print("Interrupted. Completed records and partial reports have been preserved.", file=sys.stderr)
        return report
    except BaseException:
        checkpoint("failed")
        raise
    return checkpoint("complete")


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset" / "cphos28" / "cases.jsonl")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--check-local-sources", action="store_true")
    parser.add_argument("--split", choices=("dev", "test", "edge", "all"), default="dev")
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--thinking", choices=("api-default", "enabled", "disabled"))
    parser.add_argument("--repair-attempts", type=int)
    parser.add_argument("--upstream-retries", type=int)
    parser.add_argument("--json-mode", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--output-dir", type=Path, help="A new or empty directory; prior runs are never overwritten")
    parser.add_argument("--input-price-per-million", type=_nonnegative_float)
    parser.add_argument("--cached-input-price-per-million", type=_nonnegative_float)
    parser.add_argument("--output-price-per-million", type=_nonnegative_float)
    parser.add_argument("--currency", default="USD")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if len(args.backends) != len(set(args.backends)):
        parser.error("--backends must not contain duplicates")
    overrides = {
        key: getattr(args, key) for key in
        ("model", "base_url", "timeout", "max_output_tokens", "thinking", "repair_attempts", "upstream_retries", "json_mode", "temperature")
        if getattr(args, key) is not None
    }
    try:
        settings = load_settings(env_file=args.env_file, **overrides)
    except (VerificationError, ValueError, OSError) as exc:
        print(f"Configuration error: {type(exc).__name__}. Check .env and CLI settings.", file=sys.stderr)
        return 2
    if any(name != "baseline" for name in args.backends) and not settings.api_key:
        print("Configuration error: LLM_API_KEY is missing. Set it in the project .env or environment; --backends baseline needs no key.", file=sys.stderr)
        return 2
    cases, validation = check_dataset(args.dataset, args.sources, check_local_sources=args.check_local_sources)
    if not validation["valid"]:
        print(json.dumps({"dataset_validation": validation}, ensure_ascii=False), file=sys.stderr)
        return 2
    cases = [case for case in cases if args.split == "all" or case["split"] == args.split]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        parser.error("No cases selected")
    sources = args.sources or args.dataset.with_name("sources.json")
    created = datetime.now(timezone.utc)
    output_dir = args.output_dir or ROOT / "results" / "benchmark" / created.strftime("%Y%m%dT%H%M%S.%fZ")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        parser.error("--output-dir must be new or empty; existing results are immutable")
    output_dir.mkdir(parents=True, exist_ok=True)
    prices = {
        "input_per_million": args.input_price_per_million,
        "cached_input_per_million": args.cached_input_price_per_million,
        "output_per_million": args.output_price_per_million,
        "currency": args.currency,
    }
    config = _redact({
        "created_at": created.isoformat(),
        "split": args.split, "backends": args.backends, "limit": args.limit,
        "selected_case_ids": [case["id"] for case in cases],
        "settings": settings.public_dict(),
        "prices": prices,
    }, settings.api_key)
    source_info = provenance(args.dataset, sources, args.check_local_sources)
    with (output_dir / "config.json").open("x", encoding="utf-8") as stream:
        json.dump({"config": config, "provenance": source_info}, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    verifiers = {name: build_verifier(name, settings) for name in args.backends}
    report = run_cases(cases, verifiers, output_dir, config, source_info, secret=settings.api_key)
    print(json.dumps({"report": str((output_dir / "report.json").resolve()), "status": report["status"], "completed_records": report["completed_records"]}))
    if report["status"] != "complete":
        return 130
    return 1 if any(summary["error_count"] for summary in report["backends"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
