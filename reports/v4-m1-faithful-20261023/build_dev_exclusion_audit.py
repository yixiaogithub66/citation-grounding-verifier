"""Offline candidate inventory for an AI audit; never imported by inference/scoring.

Selection uses answer offsets and string equality, not labels or dataset gold.
Candidate presence is not a semantic judgment. Human-style AI assessments are
maintained separately in dev-exclusion-reviews.json and never alter predictions.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / "results/v4-m1-faithful-20261023/dev"
OLD, NEW = "optimized-v4.0", "optimized-v4-m1-faithful"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text):
    return " ".join(text.split())


def detection(row):
    prediction = row.get("prediction")
    if row.get("error") or prediction is None:
        return "error"
    if any(claim["verdict"] in ("CONTRADICTED", "UNSUPPORTED")
           for claim in prediction.get("claims", [])):
        return "positive"
    return "unknown" if prediction.get("errors") else "negative"


config = read(RUN / "config.json")
data_path = Path(config["data_dir"]) / "inputs.jsonl"
inputs = {row["id"]: row for row in (
    json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines())}
raw = (RUN / "predictions.jsonl").read_bytes()
rows, incomplete_last_line = [], False
lines = raw.splitlines()
for number, line in enumerate(lines):
    try:
        rows.append(json.loads(line))
    except json.JSONDecodeError:
        if number != len(lines) - 1:
            raise
        incomplete_last_line = True
paired = {}
for row in rows:
    paired.setdefault(row["id"], {})[row["backend"]] = row
reviews_path = OUT / "dev-exclusion-reviews.json"
reviews = read(reviews_path) if reviews_path.exists() else {}
candidates = []
counts = Counter()
for identifier, pair in paired.items():
    if OLD not in pair or NEW not in pair:
        continue
    counts["paired_inputs"] += 1
    old, new = pair[OLD], pair[NEW]
    old_e, new_e = (row["telemetry"].get("extraction") or {} for row in (old, new))
    exclusions = new_e.get("non_factual_spans", [])
    counts["new_exclusion_entries"] += len(exclusions)
    if exclusions:
        counts["paired_inputs_with_new_exclusions"] += 1
    old_claims = old_e.get("claims", [])
    new_claims = new_e.get("claims", [])
    for claim in old_claims:
        if claim.get("extraction_fallback"):
            counts["old_fallback_claims_not_screened"] += 1
            continue
        counts["old_ordinary_claims_screened"] += 1
        if any(normalize(claim["claim_text"]) == normalize(item["claim_text"])
               for item in new_claims):
            counts["old_claims_exactly_retained"] += 1
            continue
        overlaps = []
        seen = set()
        for excluded in exclusions:
            start = max(claim["source_start"], excluded["source_start"])
            end = min(claim["source_end"], excluded["source_end"])
            if end <= start:
                continue
            fragment = excluded["text"][start - excluded["source_start"]:end - excluded["source_start"]]
            meaningful = sum(unicodedata.category(char)[0] in "LNM" for char in fragment)
            if meaningful >= 8:
                key = (excluded["source_start"], excluded["source_end"], excluded["text"])
                if key not in seen:
                    seen.add(key)
                    overlaps.append({**excluded, "overlap_substantive_characters": meaningful})
        if not overlaps:
            continue
        key = identifier + ":" + claim["id"]
        candidate = {
            "key": key, "id": identifier, "old_claim_id": claim["id"],
            "old_claim": claim["claim_text"], "old_source_span": claim["source_span"],
            "new_overlapping_exclusions": overlaps,
            "answer": inputs[identifier]["input"]["generated_answer"],
            "new_claims": [item["claim_text"] for item in new_claims],
            "old_detection": detection(old), "new_detection": detection(new),
            "detection_unchanged": detection(old) == detection(new),
            "review": reviews.get(key),
        }
        candidates.append(candidate)
counts["candidates"] = len(candidates)
counts["candidate_inputs"] = len({row["id"] for row in candidates})
counts["reviewed_candidates"] = sum(row["review"] is not None for row in candidates)
counts["unreviewed_candidates"] = len(candidates) - counts["reviewed_candidates"]
counts["candidates_with_unchanged_detection"] = sum(row["detection_unchanged"] for row in candidates)
inventory = {
    "schema_version": "m1-dev-exclusion-targeted-ai-audit-v1",
    "status": "AI diagnostic audit; no author approval, gold changes or rescoring",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "run_progress_at_snapshot": read(RUN / "progress.json"),
    "snapshot": {"parsed_response_records": len(rows), "incomplete_last_line_ignored": incomplete_last_line,
                 "predictions_prefix_bytes": len(raw), "predictions_prefix_sha256": hashlib.sha256(raw).hexdigest(),
                 "inputs_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest()},
    "selection": [
        "Only inputs with both frozen backend outputs available are screened.",
        "Select old ordinary extracted claims; old extraction_fallback skeletons are excluded.",
        "Skip claims exactly retained after whitespace-only normalization in any new claim.",
        "Require an old claim source-span/new non-factual span intersection containing at least eight Unicode L/N/M characters.",
        "Deduplicate repeated exclusion spans; retain one candidate per old claim. The threshold is an offline review-load filter, not a runtime parameter or semantic oracle.",
        "AI review then checks the full original answer and all new claims, distinguishing retained paraphrases, permissible advice filtering, lost premises/attribution, and ambiguous boundaries.",
    ],
    "limitations": [
        "No native or adjudicated gold labels are used for selection or AI extraction judgments.",
        "The old backend is a comparison, not a gold extractor; a selected candidate is not automatically a missing fact.",
        "Unselected inputs/spans, short overlaps, both-backend omissions, fallback-only claims and omissions without new non-factual overlap are not cleared by this audit.",
        "Only one sampled output per backend/input; judgments are AI diagnoses, not author-final annotations.",
    ],
    "counts": dict(counts),
    "review_categories": dict(Counter(row["review"]["category"] for row in candidates if row["review"])),
    "candidates": candidates,
}
(OUT / "dev-exclusion-audit.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"counts": inventory["counts"], "categories": inventory["review_categories"],
                  "unreviewed_keys": [row["key"] for row in candidates if row["review"] is None]}, ensure_ascii=True))
