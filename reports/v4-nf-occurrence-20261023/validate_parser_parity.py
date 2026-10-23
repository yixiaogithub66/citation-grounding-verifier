"""Compare frozen-audit NF parsing with production, including exact error text."""
import ast
import collections
import hashlib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AUDIT = OUT / "audit_frozen_nf.py"

# Execute only the audit's pure-parser setup; do not run its report writer.
prefix = []
for node in ast.parse(AUDIT.read_text(encoding="utf-8")).body:
    if isinstance(node, ast.FunctionDef) and node.name == "positions":
        break
    prefix.append(node)
namespace = {"__file__": str(AUDIT)}
exec(compile(ast.Module(body=prefix, type_ignores=[]), str(AUDIT), "exec"), namespace)

source = ROOT / "grounding/verifiers_v4.py"
names = {"_invalid", "_text", "_meaningful", "extract_claims"}
production_namespace = {
    "Any": object,
    "VerificationError": namespace["VerificationError"],
    "unicodedata": unicodedata,
}
tree = ast.parse(source.read_text(encoding="utf-8"))
module = ast.Module(
    body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names],
    type_ignores=[],
)
exec(compile(module, str(source), "exec"), production_namespace)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def outcome(parser, payload, answer):
    try:
        return {"ok": True, "value": parser(payload, answer, max_claims=64)}
    except namespace["VerificationError"] as error:
        return {"ok": False, "code": error.code, "message": error.message}


frozen = ROOT / "results/v4-m1-faithful-20261023"
paths = {
    "dev": ROOT / "dataset/ragtruth-blind-v1/recovery/inputs.jsonl",
    "behavior": frozen / "behavior/pairs.jsonl",
    "physics": ROOT / "dataset/cphos28/cases.jsonl",
}
counts = collections.Counter()
mismatches = []
for suite, path in paths.items():
    input_rows = read_jsonl(path)
    if suite == "behavior":
        inputs = {(row["id"], side): row[side]["input"]["generated_answer"]
                  for row in input_rows for side in ("base", "variant")}
    else:
        inputs = {row["id"]: row["input"]["generated_answer"] for row in input_rows}
    responses = frozen / suite / ("predictions.jsonl" if suite == "dev" else "responses.jsonl")
    for row in read_jsonl(responses):
        counts["records"] += 1
        record_id = row.get("id") or row.get("pair_id")
        key = (record_id, row.get("side")) if suite == "behavior" else record_id
        answer = inputs[key]
        telemetry = row.get("telemetry") or {}
        chunks = {chunk["chunk_id"]: chunk
                  for chunk in (telemetry.get("extraction") or {}).get("chunks", [])}
        for index, call in enumerate(telemetry.get("calls", [])):
            if not call.get("stage", "").startswith("decompose"):
                continue
            counts["decompose_calls"] += 1
            try:
                payload = json.loads(call.get("response_text") or "")
            except (ValueError, TypeError):
                counts["invalid_json"] += 1
                continue
            if not isinstance(payload, dict):
                counts["non_object"] += 1
                continue
            chunk = chunks[call["chunk_id"]]
            text = answer[chunk["source_start"]:chunk["source_end"]]
            proposed = outcome(namespace["extract_proposed"], payload, text)
            production = outcome(production_namespace["extract_claims"], payload, text)
            counts["compared"] += 1
            if production == proposed:
                counts["exact_match"] += 1
            else:
                mismatches.append({"suite": suite, "id": record_id, "backend": row["backend"],
                                   "call": index, "proposed": proposed, "production": production})

report = {
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "audit_script_sha256": hashlib.sha256(AUDIT.read_bytes()).hexdigest(),
    "comparison": "Exact success values or exact error codes and messages; no wording exemption.",
    "counts": dict(counts),
    "mismatches": mismatches,
    "limitation": "Fixed exposed responses only; no new model calls or estimate of new repair/completion or semantic accuracy.",
}
(OUT / "production-parser-parity.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
)
print(json.dumps(report, ensure_ascii=False, indent=2))
if mismatches:
    raise SystemExit(1)
