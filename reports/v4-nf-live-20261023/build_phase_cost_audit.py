"""Reproduce descriptive per-phase costs with the frozen analysis implementation."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/v4-nf-live-20261023"
sys.path.insert(0, str(RUN / "source"))
from scripts.benchmark_v4_nf import verify_freeze
from scripts.analyze_v4_nf import runtime_summary

config = verify_freeze(RUN)
progress = json.loads((RUN / "progress.json").read_text(encoding="utf-8"))
if progress.get("status") != "completed" or not progress.get("frozen_artifacts_unchanged"):
    raise ValueError("A complete frozen run is required")
raw = (RUN / "responses.jsonl").read_bytes()
rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
if len(rows) != config["expected_records"]:
    raise ValueError("Incomplete journal")
groups = {}
for variant in config["backends"]:
    groups[variant] = {}
    for phase in ("decompose", "verify", "review"):
        calls = [call for row in rows if row["variant"] == variant
                 for call in row.get("telemetry", {}).get("calls", []) if call.get("phase") == phase]
        metrics = runtime_summary([{"telemetry": {"calls": calls}, "latency_seconds": 0}], config["price_reference"])
        groups[variant][phase] = {"calls": len(calls), "usage": metrics["usage"],
                                  "reference_cost": metrics["reference_cost"]}
report = {"journal_sha256": hashlib.sha256(raw).hexdigest(), "groups": groups,
          "scope": "Known per-phase reference costs; missing calls are not zero cost. Descriptive, not a causal attribution."}
Path(__file__).with_name("phase-cost-audit.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
