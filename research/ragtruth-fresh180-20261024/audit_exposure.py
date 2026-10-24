"""Evaluation-only source exposure audit; never imported by inference.

Matches already exposed examples to pinned official records mechanically.
No labels, new source text, or new response text are emitted. No sampling.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RAW = ROOT / "tmp/ragtruth-upstream"
CACHE = ROOT / "tmp/ragtruth-exposure-map-20261024"
sys.path.insert(0, str(ROOT))
from scripts.ragtruth_data import _adapt_source


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_at(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def jsonl(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    provenance = object_at(RAW / "provenance.json")
    assert provenance["revision"] == "c103204b9ce28d6bbad859304bf30de72b8ed8fe"
    for name in ("source_info.jsonl", "response.jsonl"):
        assert sha(RAW / name) == provenance["files"][name]["sha256"]
    sources = {row["source_id"]: row for row in jsonl(RAW / "source_info.jsonl")}
    # Native label fields are neither accessed nor retained by the audit.
    responses = {row["id"]: {k: row[k] for k in ("id", "source_id", "split", "quality", "response")}
                 for row in jsonl(RAW / "response.jsonl")}
    evidence_hashes = {}
    evidence = defaultdict(list)
    known_rids = set()
    known_sids = set()

    def witness(path, rids=(), sids=(), kind="existing_execution_registry"):
        path = Path(path)
        rel = path.relative_to(ROOT).as_posix()
        evidence_hashes[str(path.resolve())] = sha(path)
        for rid in rids:
            assert rid in responses, (rel, rid)
            known_rids.add(rid)
            sid = responses[rid]["source_id"]
            known_sids.add(sid)
            item = {"path": rel, "response_id": rid, "kind": kind}
            if item not in evidence[sid]:
                evidence[sid].append(item)
        for sid in sids:
            assert sid in sources, (rel, sid)
            known_sids.add(sid)
            item = {"path": rel, "kind": kind}
            if item not in evidence[sid]:
                evidence[sid].append(item)

    ledgers = sorted((ROOT / "results/ragtruth-ledger").glob("*.json"))
    for path in ledgers:
        row = object_at(path)
        witness(path, row["response_ids"], row["source_ids"])
    manifest_paths = [ROOT / name for name in (
        "dataset/ragtruth-blind-v1/manifest.jsonl",
        "dataset/ragtruth-blind-v1/recovery/manifest.jsonl",
        "dataset/ragtruth-small30-20261023/manifest.jsonl",
        "results/ragtruth-small30-20261023/data/manifest.jsonl",
        "tmp/ragtruth-train-smoke/manifest.jsonl")]
    for path in manifest_paths:
        for row in jsonl(path):
            assert responses[row["id"]]["source_id"] == row["source_id"]
        witness(path, [r["id"] for r in jsonl(path)], kind="existing_prepared_manifest")
    registry_rids, registry_sids = set(known_rids), set(known_sids)

    # Supplemental broad check: exact complete response strings already present
    # in JSON/JSONL materials, including generic dev logs and review packets.
    text_index = defaultdict(set)
    for rid, row in responses.items():
        if len(row["response"]) >= 50:
            text_index[row["response"]].add(rid)
    scanned, parse_failures, matched_files = [], [], []
    skip_parts = {"source", "__pycache__", "pilot-results", "node_modules", ".git", OUT.name}

    def visit(value, found):
        if isinstance(value, dict):
            for key, item in value.items():
                # Do not inspect gold/span annotations even in old material.
                if key not in {"labels", "native_gold", "gold", "expected_claims"}:
                    visit(item, found)
        elif isinstance(value, list):
            for item in value:
                visit(item, found)
        elif isinstance(value, str):
            found.update(text_index.get(value, ()))

    for dirname in ("dataset", "reports", "results", "research", "docs", "reviews"):
        for path in sorted((ROOT / dirname).rglob("*")):
            if (not path.is_file() or path.suffix not in {".json", ".jsonl", ".ndjson"}
                    or set(path.relative_to(ROOT).parts) & skip_parts
                    or path.name == "native_gold.jsonl"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            scanned.append(rel)
            try:
                data = object_at(path) if path.suffix == ".json" else jsonl(path)
            except (ValueError, UnicodeError) as exc:
                parse_failures.append({"path": rel, "error_type": type(exc).__name__})
                continue
            found = set()
            visit(data, found)
            if found:
                witness(path, found, kind="exact_response_string_in_existing_material")
                matched_files.append({"path": rel, "response_ids": sorted(found)})
    extra_before_literature = sorted(known_sids - registry_sids)

    paper_record = ROOT / "research/v4-generality-20261023/research_exposure.json"
    hf_record = ROOT / "research/conjecture-review-20261023/research_exposure.json"
    evidence_hashes[str(paper_record.resolve())] = sha(paper_record)
    evidence_hashes[str(hf_record.resolve())] = sha(hf_record)
    evidence_hashes[str((ROOT / "scripts/ragtruth_data.py").resolve())] = sha(ROOT / "scripts/ragtruth_data.py")
    paper_text = (CACHE / "rt4chart-exposed-section.txt").read_text(encoding="utf-8")
    # These are only the already observed paper examples, plus #57 discovered
    # alongside them while retrieving the same section; it is excluded too.
    paper_quotes = {
        "879": ["100 passengers and 5 crew"],
        "587": ["John Doe"],
        "25": ["had purchased a visa to Turkey, a common route to Syria for joining the terrorist group."],
        "57": ["limited due to the fact that it is not a public figure", "cannot demonstrate actual financial harm"],
    }
    literature = []
    for rid, quotes in paper_quotes.items():
        verified = []
        for quote in quotes:
            assert quote in paper_text
            matching = [other for other, row in responses.items() if quote in row["response"]]
            assert matching == [rid], (rid, matching)
            verified.append({"quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                             "quote_chars": len(quote), "matching_response_ids": matching})
        witness(paper_record, [rid], kind="literature_example_exact_unique_quote")
        literature.append({"record": paper_record.relative_to(ROOT).as_posix(),
            "external_id": rid, "response_id": rid, "source_id": responses[rid]["source_id"],
            "status": "resolved_exact_unique_quote",
            "observed_during_this_mapping": rid == "57", "quote_matches": verified,
            "response_sha256": hashlib.sha256(responses[rid]["response"].encode()).hexdigest()})

    hf_meta = object_at(CACHE / "hf-info.json")
    messages = list(csv.DictReader((CACHE / "messages.csv").open(encoding="utf-8")))
    spans = list(csv.DictReader((CACHE / "hallucination_spans.csv").open(encoding="utf-8")))
    for uid in object_at(hf_record)["snippet_identifier_candidates"]:
        selected = [r for r in messages if r["stable_id"] == uid]
        assert len(selected) == 1
        message = selected[0]
        assert any(s["message_stable_id"] == uid for s in spans)
        rid = json.loads(message["meta"])["original_id"]
        assert message["text"] == responses[rid]["response"]
        witness(hf_record, [rid], kind="literature_snippet_uuid_metadata_and_exact_response")
        literature.append({"record": hf_record.relative_to(ROOT).as_posix(),
            "external_id": uid, "response_id": rid, "source_id": responses[rid]["source_id"],
            "status": "resolved_original_id_and_exact_full_response",
            "response_sha256": hashlib.sha256(message["text"].encode()).hexdigest()})

    # Exact input de-duplication is independent of labels and model outputs.
    context_hashes = {sid: canonical_sha(_adapt_source(row)[0]) for sid, row in sources.items()}
    exposed_contexts = {context_hashes[sid] for sid in known_sids}
    context_aliases = []
    for sid, digest in context_hashes.items():
        if sid not in known_sids and digest in exposed_contexts:
            originals = sorted(other for other in known_sids if context_hashes[other] == digest)
            context_aliases.append({"source_id": sid, "context_sha256": digest,
                                    "exposed_alias_source_ids": originals})
    for item in context_aliases:
        known_sids.add(item["source_id"])
        evidence[item["source_id"]].append({"kind": "identical_adapted_context_alias", **item})
    used_requests = {}
    for rid in sorted(known_rids):
        response = responses[rid]
        contexts = _adapt_source(sources[response["source_id"]])[0]
        used_requests[rid] = canonical_sha({"context_passages": contexts, "generated_answer": response["response"]})
    # A matching full request necessarily has an equal adapted context, so source
    # aliases were already excluded above; still verify this explicitly.
    used_request_set = set(used_requests.values())
    request_aliases = []
    all_request_hashes = dict(used_requests)
    for rid, response in responses.items():
        if rid in known_rids:
            continue
        contexts = _adapt_source(sources[response["source_id"]])[0]
        digest = canonical_sha({"context_passages": contexts, "generated_answer": response["response"]})
        all_request_hashes[rid] = digest
        if digest in used_request_set:
            assert response["source_id"] in known_sids
            request_aliases.append({"response_id": rid, "source_id": response["source_id"], "request_sha256": digest})

    groups = defaultdict(list)
    for row in responses.values():
        groups[row["source_id"]].append(row)
    duplicate_request_groups = []
    eligible_context_groups = defaultdict(list)
    eligibility_excluded = set()
    for sid, rows in groups.items():
        if sid in known_sids or {r["split"] for r in rows} != {"test"}:
            continue
        good = [r for r in rows if r["quality"] == "good"]
        if len(good) != 6:
            continue
        hashes = defaultdict(list)
        for row in good:
            hashes[all_request_hashes[row["id"]]].append(row["id"])
        if len(hashes) != 6:
            eligibility_excluded.add(sid)
            duplicate_request_groups.append({"source_id": sid,
                "reason": "duplicate_request_within_group",
                "duplicates": [{"request_sha256": digest, "response_ids": sorted(rids)}
                               for digest, rids in hashes.items() if len(rids) > 1]})
        else:
            eligible_context_groups[context_hashes[sid]].append(sid)
    candidate_context_aliases = []
    for digest, sids in eligible_context_groups.items():
        ordered = sorted(sids)
        for sid in ordered[1:]:
            eligibility_excluded.add(sid)
            candidate_context_aliases.append({"source_id": sid, "representative_source_id": ordered[0],
                "context_sha256": digest, "rule": "lexicographically_first_source_id"})
    all_excluded = known_sids | eligibility_excluded
    by_task = defaultdict(Counter)
    for sid, rows in groups.items():
        splits = {r["split"] for r in rows}
        assert len(splits) == 1
        if splits != {"test"}:
            continue
        counts = by_task[sources[sid]["task_type"]]
        counts["official_test_source_groups"] += 1
        if sid in all_excluded:
            counts["excluded_source_groups"] += 1
        else:
            counts["remaining_source_groups"] += 1
            if len(rows) == 6 and all(r["quality"] == "good" for r in rows):
                counts["remaining_six_good_responses"] += 1
    upstream_hashes = {name: sha(RAW / name) for name in
                       ("source_info.jsonl", "response.jsonl", "provenance.json")}
    cache_meta = {name: {"sha256": sha(CACHE / name), "bytes": (CACHE / name).stat().st_size}
                  for name in ("rt4chart.html", "rt4chart-exposed-section.txt", "hf-info.json", "hf-tree.json",
                               "messages.csv", "hallucination_spans.csv", "README.md")}
    result = {
        "schema_version": "ragtruth-fresh180-exposure-audit-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "upstream_repository": provenance["repository"], "upstream_revision": provenance["revision"],
        "upstream_raw_sha256": upstream_hashes,
        "scope": "existing execution registry, prepared manifests, exact-response scan of local JSON materials, and named literature exposure mappings",
        "known_registry_source_count": len(registry_sids), "known_registry_response_count": len(registry_rids),
        "excluded_source_ids": sorted(all_excluded), "excluded_source_count": len(all_excluded),
        "known_exposed_source_ids": sorted(known_sids), "known_exposed_source_count": len(known_sids),
        "eligibility_only_excluded_source_ids": sorted(eligibility_excluded),
        "known_response_ids": sorted(known_rids), "known_response_count": len(known_rids),
        "additional_local_sources_not_in_registry": extra_before_literature,
        "evidence_files_sha256": evidence_hashes,
        "exposed_context_sha256": sorted(exposed_contexts),
        "used_request_sha256": sorted(used_request_set),
        "unresolved_exposures": [],
        "source_evidence": dict(sorted(evidence.items())), "literature_mappings": literature,
        "input_deduplication": {"canonical_hash_definition": "sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))",
            "context_value": "adapted context_passages list, retaining order and all original characters",
            "request_value": "object with only context_passages and generated_answer",
            "adapter_file_sha256": sha(ROOT / "scripts/ragtruth_data.py"),
            "exposed_context_sha256": sorted(exposed_contexts),
            "exposed_source_context_sha256": {sid: context_hashes[sid] for sid in sorted(known_sids)},
            "known_response_request_sha256": used_requests,
            "exposed_request_sha256": sorted(used_request_set),
            "additional_source_aliases": context_aliases, "additional_response_aliases": request_aliases,
            "candidate_context_aliases": candidate_context_aliases,
            "duplicate_request_within_group_exclusions": duplicate_request_groups,
            "candidate_internal_deduplication_rule": "Before sampling exclude test source groups having exactly six good responses but duplicate full requests; among remaining non-exposed exactly-six-good groups with identical adapted-context hashes, retain lexicographically first source_id and exclude the rest. Final sampler verifies 30 unique context hashes and 180 unique full request hashes before model calls."},
        "unresolved_literature_exposures": [], "named_literature_mappings_all_resolved": True,
        "new_adjacent_literature_example_conservatively_excluded": {"response_id": "57", "source_id": "15601"},
        "mapping_downloads": {"rt4chart_url": "https://arxiv.org/html/2603.27752v1",
            "ragtruth_plus_plus_revision": hf_meta["sha"], "opaque_cache_files": cache_meta,
            "handling": "Only four previously observed UUID records matched; other downloaded message/span rows were not shown to the implementation agent or used for selection. No native labels inspected."},
        "supplemental_scan": {"files_scanned": len(scanned), "parse_failures": parse_failures,
            "exact_response_matching_files": matched_files,
            "scope_limit": "Exact full-response strings in structured artifacts; not a proof of no unrecorded external or human exposure. Native gold files and source-code snapshots excluded."},
        "remaining_pool_metadata_only": dict(by_task),
        "remaining_enough_for_ten_sources_per_task": all(v["remaining_six_good_responses"] >= 10 for v in by_task.values()),
        "contract_size_eligibility": "Not applied here; final frozen sampler must apply unchanged input contract mechanically before selection.",
        "untouched_qualification": "Disjoint from all recorded project exposures including resolved named literature examples. Cannot certify unknown human/model-training exposure.",
        "runtime_boundary": "All IDs/mappings are evaluation bookkeeping only; never supply to inference or choose prompts/configuration from them.",
        "model_calls": 0, "sampling_performed": False, "native_gold_fields_inspected": False,
    }
    (OUT / "exposure-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ["# RAGTruth fresh-180 exposure audit", "", "Evaluation bookkeeping only; no inference changes, model calls, or sample selection.", "",
        f"Pinned upstream: `{provenance['revision']}`; both raw-file hashes match the existing provenance.",
        f"Existing ledger/manifests: {len(registry_sids)} source groups / {len(registry_rids)} responses.",
        f"Known exposed: **{len(known_sids)} source groups** / {len(known_rids)} explicitly observed responses; exclude every answer from each source group.",
        f"Additional input-only duplicate exclusions: {len(eligibility_excluded)}; total excluded source groups: **{len(all_excluded)}**.",
        f"Structured artifact exact-response scan: {len(scanned)} files; additional source groups beyond registry: {extra_before_literature}.", "",
        "| Exposure | Response | Source | Match |", "|---|---|---|---|"]
    summary += [f"| {v['external_id']} | {v['response_id']} | {v['source_id']} | {v['status']} |" for v in literature]
    summary += ["", "RT4CHART #57 was visible beside the three logged examples during the same-section mapping; conservatively excluded as a new audit-time exposure. Old exposure logs are preserved unchanged.", "",
                "All named RAGTruth literature exposures are now mapped. RAGTruth++ mappings use metadata original_id plus exact complete response equality, not assumed UUID arithmetic or new labels.", "",
                "| Task | Official test sources | Excluded | Remaining | Remaining groups with 6 good responses |", "|---|---:|---:|---:|---:|"]
    summary += [f"| {task} | {v['official_test_source_groups']} | {v['excluded_source_groups']} | {v['remaining_source_groups']} | {v['remaining_six_good_responses']} |" for task, v in sorted(by_task.items())]
    summary += ["", f"Source aliases to exposed contexts: {len(context_aliases)}; duplicate full requests in six-good-answer groups: {len(duplicate_request_groups)} source groups; duplicate candidate contexts removed: {len(candidate_context_aliases)} source groups.", "",
                "At least ten eligible-by-count source groups remain per task. Input-size eligibility remains the frozen sampler's mechanical responsibility. No unexcluded candidate response text or native labels were emitted; the adjacent paper example #57 is explicitly recorded and excluded.", "",
                "The conclusion is disjointness from recorded project exposure, not a claim about unrecorded human exposure or foundation-model pretraining. Non-RAGTruth illustrations from other research sources remain outside this RAGTruth mapping.", "",
                "Machine-readable exclusions, record hashes and per-source provenance: [exposure-audit.json](exposure-audit.json)."]
    (OUT / "exposure-audit.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("excluded_source_count", "known_response_count", "additional_local_sources_not_in_registry", "remaining_pool_metadata_only", "remaining_enough_for_ten_sources_per_task")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
