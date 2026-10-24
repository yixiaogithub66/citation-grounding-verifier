#!/usr/bin/env python3
"""Build a versioned pending review package from exposed RAGTruth v1 only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_ragtruth import _jsonl, _object, _sha, _write_json, _now
from scripts.ragtruth_score import score_records

BACKENDS = ("minimal", "optimized-v3")


def build_package(records: list[dict], inputs: list[dict], manifest: list[dict], gold: list[dict]) -> dict:
    selected_records = [r for r in records if r.get("backend") in BACKENDS]
    report = score_records(selected_records, manifest, gold, backends=BACKENDS, bootstrap_samples=0)
    cases = {r["id"]: r["input"] for r in inputs}
    if len(cases) != len(inputs) or set(cases) != {m["id"] for m in manifest}:
        raise ValueError("Unique inputs must exactly match manifest")
    natives = {g["id"]: g for g in gold}
    observations = {(r["id"], r["backend"]): r for r in report["case_results"]}
    predictions = {(r["id"], r["backend"]): r for r in selected_records}
    pending = []
    for meta in manifest:
        rid = meta["id"]
        rows = [observations[(rid, b)] for b in BACKENDS]
        fp_backends = [r["backend"] for r in rows if r["success"] and not r["y_true"] and r["y_pred"]]
        disagreement = len({(r["success"], r["y_pred"]) for r in rows}) > 1
        if not fp_backends and not disagreement:
            continue
        claims = []
        backend_results = {}
        for backend in BACKENDS:
            row = predictions.get((rid, backend), {})
            obs = observations[(rid, backend)]
            prediction = row.get("prediction")
            backend_results[backend] = {"native_outcome": "error" if not obs["success"] else
                                       ("TP" if obs["y_true"] else "FP") if obs["y_pred"] else
                                       ("FN" if obs["y_true"] else "TN"),
                                       "prediction": prediction, "error": row.get("error")}
            if not obs["success"]:
                continue
            for index, claim in enumerate(prediction["claims"]):
                if claim["verdict"] not in ("CONTRADICTED", "UNSUPPORTED"):
                    continue
                identifier = hashlib.sha256(f"{rid}|{backend}|{index}|{claim['claim_text']}".encode()).hexdigest()[:20]
                claims.append({"review_id": identifier, "backend": backend, "claim_index": index,
                               "reported_claim": claim,
                               "ai_review": {"status": "pending_ai", "proposed_verdict": None,
                                             "reasoning": None, "citations": []},
                               "author_review": {"status": "pending_author", "verdict": None,
                                                 "reasoning": None, "citations": [], "approved_at": None}})
        pending.append({"id": rid, "source_id": meta["source_id"], "task_type": meta["task_type"],
                        "generator": meta["generator"], "input": cases[rid], "native_gold": natives[rid],
                        "selection_reasons": {"native_fp_backends": fp_backends, "backend_disagreement": disagreement},
                        "backend_results": backend_results, "reported_claims_for_review": claims,
                        "case_review_status": "pending_author", "case_adjudicated_positive": None})
    return {"schema_version": "ragtruth-v1-adjudication-v4.0", "created_at": _now(),
            "status": "pending_ai_and_author", "backends": list(BACKENDS), "cases": pending,
            "counts": {"cases": len(pending), "reported_claims": sum(len(c["reported_claims_for_review"]) for c in pending),
                       "union_native_fp_cases": sum(bool(c["selection_reasons"]["native_fp_backends"]) for c in pending),
                       "disagreement_cases": sum(c["selection_reasons"]["backend_disagreement"] for c in pending)},
            "policy": {"source": "exposed RAGTruth v1 development only", "native_gold_modified": False,
                       "approval": "AI proposals are not author approval; null is unreviewed, not a negative label",
                       "coverage": "selected FP/disagreement cases and reported C/U claims, not complete new gold",
                       "acceptance": "No true-FP improvement or adjudicated FN=0 acceptance claim before author review",
                       "scoring": "separate adjudication table; native response metrics never overwritten"}}


def create_package(data_dir: Path, run_dir: Path, output_dir: Path) -> dict:
    prep = _object(data_dir / "preparation.json")
    if prep.get("seed") != "ragtruth-blind-v1-20261022":
        raise ValueError("This tool accepts exposed RAGTruth v1 only, never new test selections")
    config = _object(run_dir / "config.json")
    hashes = {name: _sha(data_dir / name) for name in ("inputs.jsonl", "manifest.jsonl", "native_gold.jsonl", "preparation.json")}
    if hashes != config.get("data_files_sha256"):
        raise ValueError("Old run/data hash mismatch")
    result = build_package(_jsonl(run_dir / "predictions.jsonl"), _jsonl(data_dir / "inputs.jsonl"),
                           _jsonl(data_dir / "manifest.jsonl"), _jsonl(data_dir / "native_gold.jsonl"))
    result["provenance"] = {"data_files_sha256": hashes, "predictions_sha256": _sha(run_dir / "predictions.jsonl"),
                            "run_config_sha256": _sha(run_dir / "config.json"), "builder_sha256": _sha(Path(__file__))}
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "pending.json", result, exclusive=True)
    (output_dir / "README.md").write_text(
        "# RAGTruth v1 待裁定包\n\n这是旧180条中的原生FP并集与后端分歧，不是新金标。\n\n"
        "每条被举报的C/U声明包含原始证据、来源ID和原始标签。AI草案与作者裁定分开，当前均未完成。"
        "原生标签及历史报告不修改。未审项不能当作真FP或已证明的FN=0。"
        "本包只覆盖挑出的案例及被举报声明，不支持完整召回率结论；确认FN还需独立检查漏报。\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dataset/ragtruth-blind-v1/recovery")
    parser.add_argument("--run-dir", type=Path, default=ROOT / "reports/ragtruth-blind-v1-recovery")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = create_package(args.data_dir, args.run_dir, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "counts": result["counts"], "status": result["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
