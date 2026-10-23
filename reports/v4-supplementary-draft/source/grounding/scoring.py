"""Auditable lexical scoring; no model judge or count-based claim alignment."""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from scripts.validate_dataset import VERDICTS, validate_prediction


SIMILARITY_THRESHOLD = 0.88
SPAN_OVERLAP_THRESHOLD = 0.80
AMBIGUITY_MARGIN = 0.04


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def fraction(numerator: int | float, denominator: int | float) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _span(text: str, answer: str) -> tuple[int, int] | None:
    start = answer.find(text) if text else -1
    # Repeated spans are ambiguous without explicit occurrence offsets.
    if start < 0 or answer.find(text, start + 1) >= 0:
        return None
    return start, start + len(text)


def _critical_tokens(text: str) -> tuple[list[str], list[str], list[str]]:
    numbers = re.findall(r"(?<![A-Za-z0-9_])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text)
    negation = re.findall(
        r"\b(?:not|never|no|without)\b|不|无|未|没有|不能|并非",
        text.casefold(),
    )
    math_tokens = []
    if re.search(r"[=*/^<>≤≥≠]|(?<![A-Za-z])[A-Za-z]\s*[+\-]\s*[A-Za-z](?![A-Za-z])", text):
        math_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?|[α-ωΑ-Ω]|[+\-−*/^=<>≤≥≠()[\]{}]", text)
    return sorted(numbers), sorted(negation), math_tokens


def align_claims(
    gold: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    answer: str,
    *,
    approximate: bool,
) -> dict[str, Any]:
    """Match one-to-one, ignoring verdicts and rejecting ambiguous candidates."""
    pairs: list[dict[str, Any]] = []
    remaining_gold = set(range(len(gold)))
    remaining_predicted = set(range(len(predicted)))
    for gi, expected in enumerate(gold):
        exact = [
            pi for pi in sorted(remaining_predicted)
            if normalized_text(expected["claim_text"])
            == normalized_text(predicted[pi]["claim_text"])
        ]
        if exact:
            pi = exact[0]
            pairs.append({"gold_index": gi, "predicted_index": pi, "method": "exact_text", "similarity": 1.0})
            remaining_gold.remove(gi)
            remaining_predicted.remove(pi)

    candidates: list[dict[str, Any]] = []
    if approximate:
        for gi in sorted(remaining_gold):
            expected = gold[gi]
            gold_text = normalized_text(expected["claim_text"])
            answer_quote = expected.get("answer_quote", expected["claim_text"])
            gold_span = _span(answer_quote, answer)
            for pi in sorted(remaining_predicted):
                pred_text = normalized_text(predicted[pi]["claim_text"])
                pred_span = _span(predicted[pi]["claim_text"], answer)
                similarity = SequenceMatcher(None, gold_text, pred_text, autojunk=False).ratio()
                overlap = 0.0
                if gold_span and pred_span:
                    intersection = max(0, min(gold_span[1], pred_span[1]) - max(gold_span[0], pred_span[0]))
                    overlap = intersection / max(gold_span[1] - gold_span[0], pred_span[1] - pred_span[0])
                same_quote = pred_text == normalized_text(answer_quote)
                critical_match = _critical_tokens(gold_text) == _critical_tokens(pred_text)
                if not critical_match:
                    continue
                if same_quote:
                    method, confidence = "gold_answer_span", 1.0
                elif overlap >= SPAN_OVERLAP_THRESHOLD and similarity >= 0.70:
                    method, confidence = "answer_span_overlap", max(similarity, overlap)
                elif similarity >= SIMILARITY_THRESHOLD:
                    method, confidence = "high_text_similarity", similarity
                else:
                    continue
                candidates.append({
                    "gold_index": gi,
                    "predicted_index": pi,
                    "method": method,
                    "similarity": similarity,
                    "span_overlap": overlap,
                    "confidence": confidence,
                })

        # Mutual best with a margin avoids arbitrary matching of similar siblings.
        for candidate in sorted(candidates, key=lambda item: (-item["confidence"], item["gold_index"], item["predicted_index"])):
            gi, pi = candidate["gold_index"], candidate["predicted_index"]
            if gi not in remaining_gold or pi not in remaining_predicted:
                continue
            competitors = [
                other["confidence"] for other in candidates
                if other is not candidate
                and (other["gold_index"] == gi or other["predicted_index"] == pi)
            ]
            if competitors and candidate["confidence"] - max(competitors) < AMBIGUITY_MARGIN:
                continue
            pairs.append(candidate)
            remaining_gold.remove(gi)
            remaining_predicted.remove(pi)
    return {
        "pairs": sorted(pairs, key=lambda pair: pair["gold_index"]),
        "unmatched_gold_indices": sorted(remaining_gold),
        "unmatched_predicted_indices": sorted(remaining_predicted),
        "review_required": bool(remaining_gold or remaining_predicted or any(pair["method"] != "exact_text" for pair in pairs)),
        "candidate_pairs": candidates,
    }


def _alignment_score(
    gold: list[dict[str, Any]], predicted: list[dict[str, Any]], alignment: dict[str, Any], valid: bool,
) -> dict[str, Any]:
    matrix = {label: {column: 0 for column in (*VERDICTS, "MISSING")} for label in (*VERDICTS, "EXTRA")}
    correct = 0
    for pair in alignment["pairs"]:
        expected = gold[pair["gold_index"]]
        actual = predicted[pair["predicted_index"]]
        matrix[expected["verdict"]][actual["verdict"]] += 1
        correct += expected["verdict"] == actual["verdict"]
    for gi in alignment["unmatched_gold_indices"]:
        matrix[gold[gi]["verdict"]]["MISSING"] += 1
    for pi in alignment["unmatched_predicted_indices"]:
        matrix["EXTRA"][predicted[pi]["verdict"]] += 1
    return {
        "gold_claim_count": len(gold),
        "predicted_claim_count": len(predicted),
        "matched_claim_count": len(alignment["pairs"]),
        "correct_claim_count": correct,
        "missing_claim_count": len(alignment["unmatched_gold_indices"]),
        "extra_claim_count": len(alignment["unmatched_predicted_indices"]),
        "case_correct": valid and correct == len(gold) == len(predicted),
        "confusion_matrix": matrix,
        "alignment": alignment,
    }


def _citation_score(
    gold: list[dict[str, Any]], predicted: list[dict[str, Any]], pairs: list[dict[str, Any]],
) -> dict[str, int]:
    evidence_count = sum(claim["verdict"] != "UNSUPPORTED" for claim in gold)
    required_count = sum(bool(claim.get("required_passage_indices")) for claim in gold)
    quote_count = sum(len(claim["citations"]) for claim in gold)
    result = {
        "evidence_eligible": evidence_count,
        "passages_covered": 0,
        "required_passages_eligible": required_count,
        "required_passages_covered": 0,
        "gold_quote_eligible": quote_count,
        "gold_quote_contained": 0,
        "gold_quote_exact": 0,
    }
    for pair in pairs:
        expected, actual = gold[pair["gold_index"]], predicted[pair["predicted_index"]]
        if expected["verdict"] != actual["verdict"]:
            continue
        indices = {citation["index"] for citation in actual["citations"]}
        alternatives = expected.get("acceptable_evidence_sets", [[c["index"] for c in expected["citations"]]])
        required = set(expected.get("required_passage_indices", []))
        if expected["verdict"] != "UNSUPPORTED":
            result["passages_covered"] += bool(alternatives) and any(set(evidence) <= indices for evidence in alternatives)
        if required:
            result["required_passages_covered"] += required <= indices
        for citation in expected["citations"]:
            matching = [item["quote"] for item in actual["citations"] if item["index"] == citation["index"]]
            result["gold_quote_contained"] += any(citation["quote"] in quote for quote in matching)
            result["gold_quote_exact"] += citation["quote"] in matching
    return result


def score_case(case: dict[str, Any], prediction: Any, error: Any = None) -> dict[str, Any]:
    contexts = case["input"]["context_passages"]
    validation_errors = validate_prediction(prediction, contexts) if prediction is not None else []
    valid = error is None and prediction is not None and not validation_errors
    gold = case["expected"]["claims"]
    predicted = prediction["claims"] if valid else []
    strict_alignment = align_claims(gold, predicted, case["input"]["generated_answer"], approximate=False)
    approximate_alignment = align_claims(gold, predicted, case["input"]["generated_answer"], approximate=True)
    citation_count = 0
    valid_citation_count = 0
    if isinstance(prediction, dict) and isinstance(prediction.get("claims"), list):
        for claim in prediction["claims"]:
            if not isinstance(claim, dict) or not isinstance(claim.get("citations"), list):
                continue
            for citation in claim["citations"]:
                citation_count += 1
                if isinstance(citation, dict):
                    index, quote = citation.get("index"), citation.get("quote")
                    valid_citation_count += (
                        isinstance(index, int) and not isinstance(index, bool)
                        and 0 <= index < len(contexts)
                        and isinstance(quote, str) and bool(quote.strip()) and quote in contexts[index]
                    )
    return {
        "schema_valid": valid,
        "validation_errors": validation_errors,
        "strict": _alignment_score(gold, predicted, strict_alignment, valid),
        "approximate": _alignment_score(gold, predicted, approximate_alignment, valid),
        "citations": {
            "citation_count": citation_count,
            "valid_citation_count": valid_citation_count,
            "strict": _citation_score(gold, predicted, strict_alignment["pairs"]),
            "approximate": _citation_score(gold, predicted, approximate_alignment["pairs"]),
        },
    }


def _aggregate_alignment(scores: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {label: {column: 0 for column in (*VERDICTS, "MISSING")} for label in (*VERDICTS, "EXTRA")}
    for score in scores:
        for label, row in score["confusion_matrix"].items():
            for column, count in row.items():
                matrix[label][column] += count
    counts = {
        key: sum(score[key] for score in scores)
        for key in ("gold_claim_count", "predicted_claim_count", "matched_claim_count", "correct_claim_count", "missing_claim_count", "extra_claim_count")
    }
    per_label = {}
    for label in VERDICTS:
        tp = matrix[label][label]
        fp = sum(matrix[row][label] for row in matrix if row != label)
        fn = sum(value for column, value in matrix[label].items() if column != label)
        per_label[label] = {
            "tp": tp, "fp": fp, "fn": fn, "support": tp + fn,
            "precision": fraction(tp, tp + fp),
            "recall": fraction(tp, tp + fn),
            "f1": fraction(2 * tp, 2 * tp + fp + fn),
        }
    f1_values = [item["f1"]["value"] for item in per_label.values() if item["f1"]["value"] is not None]
    return {
        **counts,
        "claim_precision": fraction(counts["correct_claim_count"], counts["predicted_claim_count"]),
        "claim_recall": fraction(counts["correct_claim_count"], counts["gold_claim_count"]),
        "claim_f1": fraction(2 * counts["correct_claim_count"], counts["gold_claim_count"] + counts["predicted_claim_count"]),
        "extraction_precision": fraction(counts["matched_claim_count"], counts["predicted_claim_count"]),
        "extraction_recall": fraction(counts["matched_claim_count"], counts["gold_claim_count"]),
        "macro_f1": fraction(sum(f1_values), len(f1_values)),
        "case_accuracy": fraction(sum(score["case_correct"] for score in scores), len(scores)),
        "per_label": per_label,
        "confusion_matrix": matrix,
        "alignment_review_case_count": sum(score["alignment"]["review_required"] for score in scores),
        "nonexact_alignment_count": sum(pair["method"] != "exact_text" for score in scores for pair in score["alignment"]["pairs"]),
    }


def _aggregate_citations(scores: list[dict[str, Any]]) -> dict[str, Any]:
    result = {
        "exact_substring_rate": fraction(sum(s["valid_citation_count"] for s in scores), sum(s["citation_count"] for s in scores)),
    }
    for mode in ("strict", "approximate"):
        totals = Counter()
        for score in scores:
            totals.update(score[mode])
        result[mode] = {
            "passage_coverage": fraction(totals["passages_covered"], totals["evidence_eligible"]),
            "required_passage_coverage": fraction(totals["required_passages_covered"], totals["required_passages_eligible"]),
            "gold_quote_containment": fraction(totals["gold_quote_contained"], totals["gold_quote_eligible"]),
            "gold_quote_exact_match": fraction(totals["gold_quote_exact"], totals["gold_quote_eligible"]),
        }
    return result


def _token(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [call for record in records for call in record.get("telemetry", {}).get("calls", [])]
    result = {
        "calls": len(calls), "calls_with_usage": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0,
        "reasoning_tokens": 0, "cache_accounted_calls": 0, "reasoning_accounted_calls": 0,
        "usage_complete": True, "cache_usage_complete": True, "reasoning_usage_complete": True,
    }
    for call in calls:
        raw_usage = call.get("usage") if isinstance(call, dict) else None
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        prompt, completion = _token(usage.get("prompt_tokens")), _token(usage.get("completion_tokens"))
        if prompt is None or completion is None:
            result["usage_complete"] = False
            result["cache_usage_complete"] = False
            result["reasoning_usage_complete"] = False
            continue
        result["calls_with_usage"] += 1
        result["prompt_tokens"] += prompt
        result["completion_tokens"] += completion
        result["total_tokens"] += prompt + completion
        raw_details = usage.get("prompt_tokens_details")
        details = raw_details if isinstance(raw_details, dict) else {}
        hit = _token(usage.get("prompt_cache_hit_tokens", details.get("cached_tokens")))
        miss = _token(usage.get("prompt_cache_miss_tokens"))
        if hit is None and miss is not None and miss <= prompt:
            hit = prompt - miss
        if miss is None and hit is not None and hit <= prompt:
            miss = prompt - hit
        if hit is None or miss is None or hit + miss != prompt:
            result["cache_usage_complete"] = False
        else:
            result["cache_accounted_calls"] += 1
            result["prompt_cache_hit_tokens"] += hit
            result["prompt_cache_miss_tokens"] += miss
        raw_completion_details = usage.get("completion_tokens_details")
        completion_details = raw_completion_details if isinstance(raw_completion_details, dict) else {}
        reasoning = _token(completion_details.get("reasoning_tokens"))
        if reasoning is None:
            result["reasoning_usage_complete"] = False
        else:
            result["reasoning_accounted_calls"] += 1
            result["reasoning_tokens"] += reasoning
    return result


def cost_summary(usage: dict[str, Any], prices: dict[str, Any] | None) -> dict[str, Any]:
    prices = prices or {}
    complete = usage["usage_complete"]
    amount = None
    prompt_price, output_price = prices.get("input_per_million"), prices.get("output_per_million")
    cached_price = prices.get("cached_input_per_million")
    if not usage["calls"]:
        amount = 0.0
    elif prompt_price is not None and output_price is not None:
        if cached_price is None:
            amount = (usage["prompt_tokens"] * prompt_price + usage["completion_tokens"] * output_price) / 1_000_000
        elif usage["cache_usage_complete"]:
            amount = (
                usage["prompt_cache_miss_tokens"] * prompt_price
                + usage["prompt_cache_hit_tokens"] * cached_price
                + usage["completion_tokens"] * output_price
            ) / 1_000_000
        else:
            complete = False
    else:
        complete = False
    return {
        "estimated_amount": amount if complete else None,
        "known_usage_amount": amount,
        "currency": prices.get("currency", "USD"),
        "complete": complete and amount is not None,
        "prices": prices,
        "note": "Provider billing is not queried. Prices must be supplied explicitly; missing usage prevents a complete estimate. Without a cached price all input is charged at the supplied input rate.",
    }


def aggregate_backend(records: list[dict[str, Any]], prices: dict[str, Any] | None = None) -> dict[str, Any]:
    scores = [record["score"] for record in records]
    latencies = sorted(record["latency_seconds"] for record in records)
    usage = usage_summary(records)
    cost = cost_summary(usage, prices)
    if not records:
        cost.update(estimated_amount=None, known_usage_amount=None, complete=False)
        cost["note"] = "No completed records for this backend; cost is not yet known."
    result = {
        "case_count": len(records),
        "success_rate": fraction(sum(score["schema_valid"] for score in scores), len(records)),
        "error_count": sum(bool(record.get("error")) or not record["score"]["schema_valid"] for record in records),
        "strict": _aggregate_alignment([score["strict"] for score in scores]),
        "approximate": _aggregate_alignment([score["approximate"] for score in scores]),
        "citations": _aggregate_citations([score["citations"] for score in scores]),
        "latency": {
            "mean_seconds": statistics.mean(latencies) if latencies else None,
            "p50_seconds": latencies[max(0, math.ceil(0.50 * len(latencies)) - 1)] if latencies else None,
            "p95_seconds": latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else None,
            "total_seconds": sum(latencies),
        },
        "usage": usage,
        "cost": cost,
        "failures": [],
    }
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        categories[record["category"]].append(record["score"])
        score = record["score"]
        reasons = []
        if not score["schema_valid"]:
            reasons.append("request_or_contract_error")
        elif not score["strict"]["case_correct"]:
            reasons.append("strict_text_or_verdict_mismatch")
        alignment = score["approximate"]["alignment"]
        if alignment["unmatched_gold_indices"] or alignment["unmatched_predicted_indices"]:
            reasons.append("unresolved_alignment")
        if score["approximate"]["matched_claim_count"] != score["approximate"]["correct_claim_count"]:
            reasons.append("aligned_verdict_error")
        if score["citations"]["approximate"]["passages_covered"] < score["citations"]["approximate"]["evidence_eligible"]:
            reasons.append("missing_passage_or_unaligned_claim")
        if score["citations"]["approximate"]["gold_quote_contained"] < score["citations"]["approximate"]["gold_quote_eligible"]:
            reasons.append("gold_quote_anchor_not_covered_review_needed")
        if reasons:
            result["failures"].append({
                "id": record["id"], "category": record["category"], "reasons": reasons,
                "error": record.get("error"),
                "strict_case_correct": score["strict"]["case_correct"],
                "approximate_case_correct": score["approximate"]["case_correct"],
                "alignment": alignment,
            })
    result["by_category"] = {
        category: {
            "case_count": len(items),
            "strict": _aggregate_alignment([item["strict"] for item in items]),
            "approximate": _aggregate_alignment([item["approximate"] for item in items]),
        }
        for category, items in sorted(categories.items())
    }
    return result
