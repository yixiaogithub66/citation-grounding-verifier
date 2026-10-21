"""Answer-only semantic merging and anchored contradiction review for v3."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from grounding.contracts import VerificationError, VerificationRequest, VerificationResult, validate_report
from grounding.prompts_v3 import DECOMPOSE_PROMPT, MERGE_PROMPT, REVIEW_PROMPT, VERIFY_PROMPT, prompt_metadata
from grounding.verifiers import OptimizedVerifier, _invalid, _text


_RESTATEMENT = re.compile(r"\b(?:i\.?e\.?|in other words|that is)\b|\u5373|\u4e5f\u5c31\u662f", re.I)
_SENTENCE_END = re.compile(r"[\u3002\uff01\uff1f!?]|\.(?=\s|$)|\n")
_ABBREVIATION_END = re.compile(r"\b(?:i\.e|e\.g)\.$", re.I)
_TOKENS = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[=+\-*/^<>]|[\u4e0d\u975e\u65e0\u672a]")
_CORE_FIELDS = {"id", "claim_text", "verdict", "reasoning", "citations"}


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _sentences(answer: str) -> list[tuple[int, int]]:
    intervals = []
    start = 0
    for match in _SENTENCE_END.finditer(answer):
        if match.group() == "." and _ABBREVIATION_END.search(answer[max(0, match.end() - 8):match.end()]):
            continue
        intervals.append((start, match.end()))
        start = match.end()
    if start < len(answer):
        intervals.append((start, len(answer)))
    return intervals


def _bounds(claim: dict[str, str], answer: str) -> tuple[int, int]:
    if "source_start" in claim and "source_end" in claim:
        start, end = claim["source_start"], claim["source_end"]
        if isinstance(start, int) and isinstance(end, int) and answer[start:end] == claim["source_span"]:
            return start, end
        _invalid("Internal source offsets do not select the original source_span.")
    start = answer.find(claim["source_span"])
    if start < 0:
        _invalid("Claim source_span is not in generated_answer.")
    return start, start + len(claim["source_span"])


def _overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return max(left[0], right[0]) < min(left[1], right[1])


def _containing_sentence(interval: tuple[int, int], sentences: list[tuple[int, int]]) -> tuple[int, int] | None:
    return next((sentence for sentence in sentences if sentence[0] <= interval[0] and interval[1] <= sentence[1]), None)


def merge_candidates(claims: list[dict[str, str]], answer: str) -> list[dict[str, Any]]:
    """Find adjacent candidate runs; neither token equality nor a marker authorizes merging."""
    sentences = _sentences(answer)
    positions = [_bounds(claim, answer) for claim in claims]
    links: dict[int, list[str]] = {}
    for index, (left, right) in enumerate(zip(claims, claims[1:])):
        interval = (min(positions[index][0], positions[index + 1][0]), max(positions[index][1], positions[index + 1][1]))
        sentence = _containing_sentence(interval, sentences)
        triggers = []
        if _normalized(left["claim_text"]) == _normalized(right["claim_text"]):
            triggers.append("normalized_text_equal")
        if sentence and _RESTATEMENT.search(answer[sentence[0]:sentence[1]]):
            triggers.append("restatement_marker")
        left_tokens, right_tokens = set(_TOKENS.findall(left["claim_text"])), set(_TOKENS.findall(right["claim_text"]))
        if len(left_tokens) >= 2 and left_tokens == right_tokens and (sentence or _overlap(positions[index], positions[index + 1])):
            triggers.append("critical_token_set_equal")
        if triggers:
            links[index] = triggers
    candidates = []
    index = 0
    while index < len(claims) - 1:
        if index not in links:
            index += 1
            continue
        start, triggers = index, set()
        while index in links:
            triggers.update(links[index])
            index += 1
        candidates.append({
            "candidate_id": f"m{len(candidates) + 1}",
            "claim_ids": [claim["id"] for claim in claims[start:index + 1]],
            "triggers": sorted(triggers),
        })
    return candidates


def _evidence_error(evidence: Any, contexts: list[str], public: list[dict[str, Any]] | None = None) -> str | None:
    if not isinstance(evidence, list) or not evidence or len(evidence) > 32:
        return "Evidence must be a nonempty array with at most 32 quotes."
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"index", "quote"}:
            return "Evidence items must contain exactly index and quote."
        index, quote = item["index"], item["quote"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(contexts):
            return "Evidence index is not an in-bounds integer."
        if not _text(quote) or quote not in contexts[index]:
            return "Evidence quote is not an exact nonempty passage substring."
        if public is not None and not any(cite["index"] == index and quote in cite["quote"] for cite in public):
            return "Internal evidence must be covered by returned citations from the same passage."
    return None


def _conflict_error(claim: dict[str, Any], contexts: list[str]) -> str | None:
    conflict = claim.get("conflict")
    if not isinstance(conflict, dict) or set(conflict) != {"claim_span", "evidence", "kind", "explanation"}:
        return "CONTRADICTED lacks a complete structured conflict explanation."
    if not _text(conflict["claim_span"]) or conflict["claim_span"] not in claim["claim_text"]:
        return "Conflict claim_span is not an exact nonempty substring of claim_text."
    if conflict["kind"] not in ("direct", "calculation") or not _text(conflict["explanation"]):
        return "Conflict needs a direct/calculation kind and a nonempty explanation."
    return _evidence_error(conflict["evidence"], contexts, claim["citations"])


class OptimizedV3Verifier(OptimizedVerifier):
    def _extract(self, payload: dict[str, Any], answer: str) -> list[dict[str, Any]]:
        if not isinstance(payload, dict) or set(payload) != {"claims", "non_factual_spans"}:
            _invalid("Extraction must contain exactly claims and non_factual_spans.")
        claims, exclusions = payload["claims"], payload["non_factual_spans"]
        if not isinstance(claims, list) or not isinstance(exclusions, list):
            _invalid("Extraction claims and non_factual_spans must be arrays.")
        if len(claims) > self.settings.max_claims or len(exclusions) > 256:
            _invalid("Extraction exceeds configured claim or exclusion limits.")
        covered: set[int] = set()
        prior_occurrences: dict[tuple[str, str], int] = {}
        extracted = []
        previous_start = 0
        for item in claims:
            if (
                not isinstance(item, dict) or set(item) != {"claim_text", "source_span"}
                or not _text(item["claim_text"]) or not _text(item["source_span"])
            ):
                _invalid("Each extracted claim needs exactly nonempty claim_text and source_span.")
            pair = (item["claim_text"], item["source_span"])
            start = answer.find(item["source_span"], previous_start)
            if start < 0:
                _invalid("Extraction source spans must be exact substrings in answer order.")
            # Distinguish repeated source occurrences; a duplicate at one occurrence
            # remains a merge candidate rather than failing the v2 duplicate guard.
            if pair in prior_occurrences:
                later = answer.find(item["source_span"], max(previous_start, prior_occurrences[pair] + 1))
                if later >= 0:
                    start = later
            end = start + len(item["source_span"])
            prior_occurrences[pair] = previous_start = start
            covered.update(range(start, end))
            extracted.append({"id": f"c{len(extracted) + 1}", **item, "source_start": start, "source_end": end})
        for item in exclusions:
            if (
                not isinstance(item, dict) or set(item) != {"text", "reason"}
                or not _text(item["text"]) or not _text(item["reason"])
            ):
                _invalid("Each non_factual_spans item needs exactly nonempty text and reason.")
            start = answer.find(item["text"])
            if start < 0:
                _invalid("A non-factual span is not an exact answer substring.")
            while start >= 0:
                covered.update(range(start, start + len(item["text"])))
                start = answer.find(item["text"], start + 1)
        uncovered = [
            index for index, char in enumerate(answer)
            if (unicodedata.category(char)[0] in "LNMS" or char in "-*/") and index not in covered
        ]
        if uncovered:
            _invalid("Extraction left answer text unaccounted for near: " + repr(answer[uncovered[0]:uncovered[0] + 100]))
        return extracted

    def _merge_output(
        self, payload: dict[str, Any], candidates: list[dict[str, Any]],
        claims: list[dict[str, str]], answer: str, exclusions: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        if not isinstance(payload, dict) or set(payload) != {"decisions"} or not isinstance(payload["decisions"], list):
            _invalid("Merge output must contain exactly a decisions array.")
        if len(payload["decisions"]) != len(candidates):
            _invalid("Return one merge decision per candidate.")
        index_by_id = {claim["id"]: index for index, claim in enumerate(claims)}
        groups_by_start = {}
        for candidate, decision in zip(candidates, payload["decisions"]):
            if not isinstance(decision, dict) or set(decision) != {"candidate_id", "groups"}:
                _invalid("Each merge decision needs candidate_id and groups only.")
            if decision["candidate_id"] != candidate["candidate_id"] or not isinstance(decision["groups"], list):
                _invalid("Merge decisions must preserve candidate ids and order.")
            flattened = []
            for group in decision["groups"]:
                if not isinstance(group, dict) or set(group) != {"claim_ids", "reason"} or not _text(group["reason"]):
                    _invalid("Each merge group needs claim_ids and a nonempty semantic reason.")
                ids = group["claim_ids"]
                if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
                    _invalid("Merge claim_ids must be a nonempty array of supplied ids.")
                flattened.extend(ids)
            if flattened != candidate["claim_ids"]:
                _invalid("Merge groups must partition candidate ids exactly once in original order.")
            for group in decision["groups"]:
                groups_by_start[index_by_id[group["claim_ids"][0]]] = {**group, "candidate_id": candidate["candidate_id"]}

        positions = [_bounds(claim, answer) for claim in claims]
        sentences = _sentences(answer)
        blocks = []
        index = 0
        while index < len(claims):
            group = groups_by_start.get(index)
            count = len(group["claim_ids"]) if group else 1
            before = claims[index:index + count]
            after = [{"claim_text": row["claim_text"], "source_span": row["source_span"]} for row in before]
            action, guard = "keep", None
            if count > 1:
                selected = set(range(index, index + count))
                interval = (min(positions[item][0] for item in selected), max(positions[item][1] for item in selected))
                other_positions = [position for item, position in enumerate(positions) if item not in selected]
                identical_text = all(_normalized(row["claim_text"]) == _normalized(before[0]["claim_text"]) for row in before)
                identical_source = all(positions[item] == interval for item in selected)
                if any(_overlap(interval, other) for other in other_positions) and not (identical_text and identical_source):
                    action, guard = "keep_safety_guard", "Covering interval overlaps an unmerged assertion."
                else:
                    sentence = _containing_sentence(interval, sentences)
                    if sentence and not identical_text and not any(_overlap(sentence, other) for other in other_positions):
                        interval = sentence
                    span = answer[interval[0]:interval[1]].strip()
                    after = [{"claim_text": before[0]["claim_text"] if identical_text else span, "source_span": span}]
                    action = "merge"
            blocks.append({"group": group, "before": before, "after": after, "action": action, "guard": guard})
            index += count

        # Reuse the original coverage/order/limit checks after deterministic span selection.
        merged = self._extract({
            "claims": [item for block in blocks for item in block["after"]],
            "non_factual_spans": exclusions,
        }, answer)
        audits, offset = [], 0
        for block in blocks:
            after = merged[offset:offset + len(block["after"])]
            offset += len(after)
            group = block["group"]
            if group:
                audits.append({
                    "candidate_id": group["candidate_id"], "claim_ids": group["claim_ids"],
                    "input_claim_ids": group["claim_ids"], "output_claim_ids": [row["id"] for row in after],
                    "input_count": len(block["before"]), "output_count": len(after),
                    "merged": block["action"] == "merge", "decision": block["action"],
                    "reason": group["reason"], "safety_guard": block["guard"],
                    "before_claims": block["before"], "after_claims": after,
                })
        return merged, audits

    def _verify_output(
        self, payload: dict[str, Any], claims: list[dict[str, str]], contexts: list[str], *, review: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not isinstance(payload, dict) or set(payload) != {"claims"} or not isinstance(payload["claims"], list):
            _invalid("Verification must contain exactly a claims array.")
        allowed = _CORE_FIELDS | {"conflict"} | ({"review_evidence"} if review else set())
        for row in payload["claims"]:
            if not isinstance(row, dict) or not _CORE_FIELDS <= set(row) or set(row) - allowed:
                _invalid("Verified claim has incorrect fields.")
            if row.get("verdict") != "CONTRADICTED" and row.get("conflict") is not None:
                _invalid("Non-contradicted claims must use conflict:null.")
        report = self._verified({"claims": [
            {key: value for key, value in row.items() if key in _CORE_FIELDS}
            for row in payload["claims"]
        ]}, claims, contexts)
        checks = []
        for row in payload["claims"]:
            if review:
                evidence_error = _evidence_error(
                    row.get("review_evidence"), contexts,
                    row["citations"] if row["verdict"] != "UNSUPPORTED" else None,
                )
                if evidence_error:
                    _invalid("Contradiction review evidence: " + evidence_error)
            if row["verdict"] == "CONTRADICTED":
                error = _conflict_error(row, contexts)
                if review and error:
                    _invalid("Contradiction review still lacks valid conflict evidence: " + error)
                checks.append({
                    "claim_id": row["id"], "passed": error is None,
                    "reason": error, "conflict": row.get("conflict"),
                })
        return report, checks

    def verify(self, request: VerificationRequest) -> VerificationResult:
        telemetry: dict[str, Any] = {
            "backend": "optimized-v3", "prompts": prompt_metadata(), "calls": [], "repairs": [],
            "extraction": None, "merge_audits": [], "merge_candidate_count": 0,
            "contradiction_checks": [], "contradiction_reviews": [],
            "gate_limitation": "Conflict anchors and quote coverage are checked; semantic or algebraic incompatibility is not proven by code.",
        }
        started = time.monotonic()
        try:
            if not request.generated_answer.strip():
                return VerificationResult({"claims": []}, telemetry)

            def extract(value: dict[str, Any]) -> list[dict[str, str]]:
                claims = self._extract(value, request.generated_answer)
                telemetry["extraction"] = {
                    "claims": claims, "non_factual_spans": value["non_factual_spans"],
                    "coverage_check": "Every letter, number, mark, symbol and mathematical operator is covered by a claim or classified non-factual span.",
                    "limitation": "Lexical coverage does not prove correct atomicity, semantic equivalence or completeness.",
                }
                return claims

            claims = self._stage("decompose", DECOMPOSE_PROMPT, {
                "generated_answer": request.generated_answer, "max_claims": self.settings.max_claims,
            }, extract, telemetry)
            candidates = merge_candidates(claims, request.generated_answer)
            telemetry["merge_candidate_count"] = len(candidates)
            if candidates:
                claims, telemetry["merge_audits"] = self._stage("merge", MERGE_PROMPT, {
                    "generated_answer": request.generated_answer, "claims": claims, "candidates": candidates,
                }, lambda value: self._merge_output(
                    value, candidates, claims, request.generated_answer,
                    telemetry["extraction"]["non_factual_spans"],
                ), telemetry)
            telemetry["extraction"]["claims_after_merge"] = claims
            if not claims:
                report = {"claims": []}
            elif not any(passage.strip() for passage in request.context_passages):
                report = {"claims": [{
                    "claim_text": claim["claim_text"], "verdict": "UNSUPPORTED",
                    "reasoning": "No nonempty context passage was supplied to verify this factual claim.", "citations": [],
                } for claim in claims]}
            else:
                contexts = [{"index": index, "text": text} for index, text in enumerate(request.context_passages)]
                report, checks = self._stage("verify", VERIFY_PROMPT, {
                    "context_passages": contexts, "claims": claims,
                }, lambda value: self._verify_output(value, claims, request.context_passages), telemetry)
                telemetry["contradiction_checks"] = checks
                failed = {check["claim_id"]: check["reason"] for check in checks if not check["passed"]}
                if failed:
                    review_claims = [claim for claim in claims if claim["id"] in failed]
                    events = [{
                        "claim_id": claim["id"], "before_verdict": "CONTRADICTED", "after_verdict": None,
                        "trigger": failed[claim["id"]], "reviewed": True, "evidence": [],
                    } for claim in review_claims]
                    telemetry["contradiction_reviews"] = events
                    reviewed_evidence: dict[str, Any] = {}

                    def review_output(value: dict[str, Any]) -> dict[str, Any]:
                        reviewed, _ = self._verify_output(value, review_claims, request.context_passages, review=True)
                        reviewed_evidence.update({row["id"]: row["review_evidence"] for row in value["claims"]})
                        return reviewed

                    try:
                        reviewed = self._stage("contradiction_review", REVIEW_PROMPT, {
                            "context_passages": contexts, "claims": review_claims,
                            "previous_results": [
                                {"id": claim["id"], **result}
                                for claim, result in zip(claims, report["claims"]) if claim["id"] in failed
                            ],
                            "review_triggers": failed,
                        }, review_output, telemetry)
                    except VerificationError as exc:
                        for event in events:
                            event["error"] = {"code": exc.code, "message": exc.message}
                        raise
                    replacements = {claim["id"]: result for claim, result in zip(review_claims, reviewed["claims"])}
                    report["claims"] = [replacements.get(claim["id"], result) for claim, result in zip(claims, report["claims"])]
                    for event in events:
                        event["after_verdict"] = replacements[event["claim_id"]]["verdict"]
                        event["evidence"] = reviewed_evidence[event["claim_id"]]
            validate_report(report, request.context_passages)
            return VerificationResult(report, telemetry)
        except VerificationError as exc:
            exc.telemetry = telemetry
            raise
        finally:
            telemetry["latency_seconds"] = time.monotonic() - started
