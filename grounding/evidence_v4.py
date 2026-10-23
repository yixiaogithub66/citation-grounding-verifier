"""Conservative citation location and numeric signals for optimized-v4.0.

Only an exact location or a unique formatting-only match can repair a quote.
Fuzzy windows are *proposals for a new model judgment*, never replacements.
Offsets are Python/Unicode code-point offsets, not UTF-8 bytes or UTF-16 units.
No function in this module assigns or changes a semantic verdict.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import math
import re
import unicodedata
from typing import Any


NORMALIZATION_VERSION = "v4-safe-format-1"
MAX_CANDIDATES = 8
MAX_FUZZY_WINDOWS = 512
MAX_FUZZY_CHARS = 4096
MAX_WINDOW_TOKENS = 256
_TOKENS = re.compile(r"\w+|[^\w\s]", re.UNICODE)
# This whitelist deliberately excludes dash/minus, slash, prime, multiplication,
# superscripts, letters, digits, and compatibility symbols. No punctuation is
# deleted. Restrict NFKC to these presentation variants of ordinary delimiters.
_PRESENTATION_PUNCTUATION = frozenset("，。：；！？（）［］｛｝")
_QUOTE_PAIRS = (("“", "”", '"'), ("‘", "’", "'"))
_SENTENCE = re.compile(r"[。！？!?;；]|\.(?=\s|$)|\n+")
_NUMBER = re.compile(r"(?<![\w.^])[-+]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?(?![0-9]|\.[0-9])")
_UNIT = re.compile(r"\s*(?P<unit>(?:[^\W\d_]+|%|°[^\W\d_]+)(?:[/·][^\W\d_]+(?:[²³]|[0-9]+)?)*)", re.UNICODE)


def _quote_substitutions(text: str) -> dict[int, str]:
    """Fold paired typographical delimiters, never a standalone apostrophe/prime.

    Delimiters immediately beside numbers or mathematical operators are retained
    because their role may be mathematical. Matching is intentionally conservative.
    """
    substitutions: dict[int, str] = {}
    for opening, closing, target in _QUOTE_PAIRS:
        start = 0
        while (left := text.find(opening, start)) >= 0:
            right = text.find(closing, left + 1)
            if right < 0:
                break
            neighbors = [text[p] for p in (left - 1, left + 1, right - 1, right + 1) if 0 <= p < len(text)]
            if not any(char.isnumeric() or unicodedata.category(char) == "Sm" for char in neighbors):
                substitutions[left] = substitutions[right] = target
            start = right + 1
    return substitutions


def _normalize(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Return safe normalization with a reversible map to original characters.

    A whitespace run becomes one space, not zero spaces. NFKC is only evaluated
    on a fixed punctuation whitelist. Every letter and number survives verbatim.
    """
    chars: list[str] = []
    positions: list[tuple[int, int]] = []
    quote_substitutions = _quote_substitutions(text)
    for offset, original in enumerate(text):
        if original.isspace():
            if chars and chars[-1] == " ":
                positions[-1] = (positions[-1][0], offset + 1)
            else:
                chars.append(" ")
                positions.append((offset, offset + 1))
            continue
        character = quote_substitutions.get(offset, original)
        if original in _PRESENTATION_PUNCTUATION:
            character = unicodedata.normalize("NFKC", original)
        chars.append(character)
        positions.append((offset, offset + 1))
    return "".join(chars), positions


def _occurrences(text: str, needle: str, *, limit: int = MAX_CANDIDATES + 1) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    start = 0
    while len(found) < limit and (start := text.find(needle, start)) >= 0:
        found.append((start, start + len(needle)))
        start += 1
    return found


def _locations(quote: str, contexts: list[str], *, normalized: bool) -> list[dict[str, Any]]:
    needle = _normalize(quote)[0] if normalized else quote
    if not needle or not needle.strip():
        return []
    found: list[dict[str, Any]] = []
    for index, paragraph in enumerate(contexts):
        text, offsets = _normalize(paragraph) if normalized else (paragraph, [])
        for start, end in _occurrences(text, needle, limit=MAX_CANDIDATES + 1 - len(found)):
            if normalized:
                start, end = offsets[start][0], offsets[end - 1][1]
            found.append({"index": index, "quote": paragraph[start:end], "start": start, "end": end,
                          "method": "safe_format" if normalized else "exact", "score": 1.0})
        # A second match already prevents automatic repair. Keep bounded examples
        # for the model without materializing thousands of identical locations.
        if len(found) > MAX_CANDIDATES:
            break
    return found


def _fuzzy_candidates(quote: str, paragraph: str, index: int, threshold: float, window_tokens: int) -> list[dict[str, Any]]:
    """Bound work by token-window count and compared characters per window.

    Rare exact tokens select windows anywhere in the paragraph, so the budget
    does not merely search a prefix. No vocabulary or domain-specific trigger is
    involved. Missing a proposal is safe: the claim is still sent for rejudgment.
    """
    normalized_quote = _normalize(quote)[0]
    query = [match.group() for match in _TOKENS.finditer(normalized_quote)]
    if not query or len(query) > window_tokens or len(normalized_quote) > MAX_FUZZY_CHARS:
        return []
    normalized_text, offsets = _normalize(paragraph)
    matches = list(_TOKENS.finditer(normalized_text))
    tokens = [match.group() for match in matches]
    if not tokens:
        return []
    postings: dict[str, list[int]] = defaultdict(list)
    for position, token in enumerate(tokens):
        postings[token].append(position)
    anchors = sorted((len(postings[token]), position, token) for position, token in enumerate(query)
                     if token in postings)
    starts: list[int] = []
    seen_starts: set[int] = set()
    for _, query_position, token in anchors[:3]:
        for occurrence in postings[token]:
            for shift in (0, -1, 1, -2, 2):
                start = occurrence - query_position + shift
                if 0 <= start < len(tokens) and start not in seen_starts:
                    seen_starts.add(start)
                    starts.append(start)
                    if len(starts) >= MAX_FUZZY_WINDOWS:
                        break
            if len(starts) >= MAX_FUZZY_WINDOWS:
                break
        if len(starts) >= MAX_FUZZY_WINDOWS:
            break
    proposals: list[dict[str, Any]] = []
    compared = 0
    lengths = [length for length in (len(query), len(query) - 1, len(query) + 1, len(query) - 2, len(query) + 2)
               if 1 <= length <= window_tokens]
    for start in starts:
        for length in lengths:
            if compared >= MAX_FUZZY_WINDOWS:
                break
            end = start + length
            if end > len(tokens):
                continue
            left, right = matches[start].start(), matches[end - 1].end()
            if right - left > MAX_FUZZY_CHARS:
                continue
            compared += 1
            score = SequenceMatcher(None, query, tokens[start:end], autojunk=False).ratio()
            if score < threshold:
                continue
            raw_start, raw_end = offsets[left][0], offsets[right - 1][1]
            proposals.append({"index": index, "quote": paragraph[raw_start:raw_end], "start": raw_start,
                              "end": raw_end, "method": "fuzzy_candidate", "score": round(score, 6)})
        if compared >= MAX_FUZZY_WINDOWS:
            break
    proposals.sort(key=lambda item: (-item["score"], item["start"], item["end"]))
    # Suppress overlapping near-identical windows to keep rejudgment payload small.
    unique: list[dict[str, Any]] = []
    for proposal in proposals:
        if not any(max(proposal["start"], prior["start"]) < min(proposal["end"], prior["end"]) for prior in unique):
            unique.append(proposal)
            if len(unique) == MAX_CANDIDATES:
                break
    return unique


def repair_citations(
    citations: Any, contexts: list[str], *, fuzzy_threshold: float = 0.92, window_tokens: int = 80,
) -> dict[str, Any]:
    """Locate one claim's citations without throwing on malformed model output.

    ``citations`` contains only retained or safely repaired entries. If *any*
    entry needs rejudgment, ``needs_requery`` is true; the shortened list must not
    be treated as a completed claim. Errors and proposals can be fed to that
    claim's bounded retry. Events include exact original-text code-point spans.
    """
    result: dict[str, Any] = {"citations": [], "events": [], "needs_requery": False, "candidates": [], "errors": []}

    def error(position: int | None, code: str, message: str) -> None:
        result["needs_requery"] = True
        result["errors"].append({"citation_index": position, "code": code, "message": message})

    if not isinstance(contexts, list) or any(not isinstance(text, str) for text in contexts):
        error(None, "invalid_contexts", "Contexts must be a string array.")
        return result
    if not isinstance(citations, list) or len(citations) > 32:
        error(None, "invalid_citations", "Citations must be an array of at most 32 items.")
        return result
    if (isinstance(fuzzy_threshold, bool) or not isinstance(fuzzy_threshold, (int, float))
            or not math.isfinite(fuzzy_threshold) or not 0 <= fuzzy_threshold <= 1
            or isinstance(window_tokens, bool) or not isinstance(window_tokens, int)
            or not 1 <= window_tokens <= MAX_WINDOW_TOKENS):
        error(None, "invalid_repair_config", "Invalid fuzzy threshold or window token bound.")
        return result
    for position, citation in enumerate(citations):
        if not isinstance(citation, dict) or set(citation) not in (
            {"index", "quote"}, {"index", "quote", "start_char", "end_char"},
        ):
            error(position, "invalid_citation", "Each citation needs index/quote and optionally both start_char/end_char.")
            continue
        index, quote = citation["index"], citation["quote"]
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(quote, str) or not quote.strip():
            error(position, "invalid_citation", "Citation index must be an integer and quote a nonempty string.")
            continue
        in_bounds = 0 <= index < len(contexts)
        exact_start = contexts[index].find(quote) if in_bounds else -1
        if exact_start >= 0:
            after = dict(citation)
            method = None
            if "start_char" in citation:
                start, end = citation["start_char"], citation["end_char"]
                if (not isinstance(start, bool) and isinstance(start, int)
                        and not isinstance(end, bool) and isinstance(end, int)
                        and 0 <= start < end <= len(contexts[index]) and contexts[index][start:end] == quote):
                    exact_start = start
                elif len(_occurrences(contexts[index], quote, limit=2)) == 1:
                    after.update(start_char=exact_start, end_char=exact_start + len(quote))
                    method = "offsets"
                else:
                    # The already valid paragraph/quote needs no new judgment.
                    # Drop optional invalid metadata rather than invent which
                    # repeated occurrence the model meant to designate.
                    after.pop("start_char")
                    after.pop("end_char")
                    method = "offsets_removed_ambiguous"
            result["citations"].append(after)
            event = {"citation_index": position, "kind": "repair" if method else "exact", "before": dict(citation),
                     "after": after, "start": exact_start, "end": exact_start + len(quote)}
            if method:
                event["method"] = method
            result["events"].append(event)
            continue

        normalized = _locations(quote, contexts, normalized=True)
        # A format repair at the stated index is legal only when the same safely
        # normalized quote has exactly one location across *all* passages.
        local_normalized = [match for match in normalized if match["index"] == index]
        repaired: dict[str, Any] | None = None
        repair_kind = "safe_format"
        if len(normalized) == 1 and local_normalized:
            repaired = normalized[0]
        proposals = [] if repaired or not in_bounds else _fuzzy_candidates(quote, contexts[index], index, fuzzy_threshold, window_tokens)
        exact = [] if repaired else _locations(quote, contexts, normalized=False)
        if not repaired and len(exact) == 1:
            # A normalized alternative elsewhere is still an ambiguity: do not
            # silently choose one occurrence just because its typography matches.
            if len(normalized) == 1:
                repaired, repair_kind = exact[0], "wrong_index_exact"
        if repaired:
            after = {"index": repaired["index"], "quote": repaired["quote"]}
            if "start_char" in citation:
                after.update(start_char=repaired["start"], end_char=repaired["end"])
            result["citations"].append(after)
            result["events"].append({"citation_index": position, "kind": "repair", "method": repair_kind,
                                     "normalization_version": NORMALIZATION_VERSION, "before": dict(citation),
                                     "after": after, "start": repaired["start"], "end": repaired["end"]})
            continue
        choices = normalized + exact + proposals
        seen: set[tuple[int, int, int]] = set()
        for candidate in choices:
            key = (candidate["index"], candidate["start"], candidate["end"])
            if key in seen:
                continue
            seen.add(key)
            result["candidates"].append({"citation_index": position, **candidate})
            if len(seen) == MAX_CANDIDATES:
                break
        ambiguous = len(normalized) > 1 or len(exact) > 1
        code = "ambiguous_quote" if ambiguous else "quote_requires_rejudgment"
        error(position, code, "Quote has multiple possible locations." if ambiguous else
              "No unique formatting-only or exact wrong-index repair; rejudge this claim against original evidence.")
        result["events"].append({"citation_index": position, "kind": "requery_required", "before": dict(citation),
                                 "reason": code, "candidate_count": len(seen)})
    return result


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _SENTENCE.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _numeric_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sentence_start, sentence_end in _sentence_spans(text):
        sentence = text[sentence_start:sentence_end]
        for match in _NUMBER.finditer(sentence):
            # Do not parse only one component of an unfamiliar numeric notation
            # (grouped thousands, Unicode digit runs, or numeric exponents).
            before_char = sentence[match.start() - 1:match.start()]
            after_char = sentence[match.end():match.end() + 1]
            before_nonspace = sentence[:match.start()].rstrip()[-1:]
            after_nonspace = sentence[match.end():].lstrip()[:1]
            if (after_char and (after_char.isnumeric() or after_char in "^")) or (
                before_char == "," and match.start() > 1 and sentence[match.start() - 2].isnumeric()
            ) or (
                after_char == "," and match.end() + 1 < len(sentence) and sentence[match.end() + 1].isnumeric()
            ) or (
                before_char.isspace() and before_nonspace.isnumeric()
            ) or (
                after_char.isspace() and after_nonspace.isnumeric()
            ):
                continue
            try:
                value = Decimal(match.group())
            except InvalidOperation:
                continue
            tail = sentence[match.end():]
            unit_match = _UNIT.match(tail)
            unit = unit_match.group("unit") if unit_match else ""
            # The entire containing sentence must match except this one numeric
            # span. This deliberately misses paraphrases instead of guessing an
            # entity, quantity, condition, or alignment from lexical proximity.
            before = _normalize(sentence[:match.start()])[0].lstrip()
            after = _normalize(tail)[0].rstrip()
            records.append({"key": (before, after, unit), "value": value, "literal": match.group(),
                            "unit": unit, "anchor": before + "{number}" + after,
                            "start": sentence_start + match.start(), "end": sentence_start + match.end(),
                            "sentence_start": sentence_start, "sentence_end": sentence_end})
    return records


def numeric_conflict_signals(claim_text: Any, citations: Any, contexts: list[str]) -> list[dict[str, Any]]:
    """Signal differing values only at unique, identical sentence/unit anchors.

    Values use Decimal solely for exact equality (``3 == 3.0``). No unit
    conversion, arithmetic, formula evaluation, fuzzy entity matching, or verdict
    occurs here. A signal is an input to the model's contradiction review.
    """
    if (not isinstance(claim_text, str) or not isinstance(citations, list)
            or not isinstance(contexts, list) or any(not isinstance(text, str) for text in contexts)):
        return []
    claims = _numeric_records(claim_text)
    claim_counts = Counter(record["key"] for record in claims)
    evidence: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[int, int, int]] = set()
    for citation in citations[:32]:
        if not isinstance(citation, dict):
            continue
        index, quote = citation.get("index"), citation.get("quote")
        if (isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(contexts)
                or not isinstance(quote, str) or not quote.strip()):
            continue
        positions = _occurrences(contexts[index], quote, limit=2)
        if len(positions) != 1:
            continue
        quote_start = positions[0][0]
        for record in _numeric_records(quote):
            key = (index, quote_start + record["start"], quote_start + record["end"])
            if key in seen:
                continue
            seen.add(key)
            evidence[record["key"]].append({**record, "index": index, "quote": quote,
                                             "quote_start": quote_start, "quote_end": quote_start + len(quote)})
    signals: list[dict[str, Any]] = []
    for record in claims:
        matches = evidence.get(record["key"], [])
        if claim_counts[record["key"]] != 1 or len(matches) != 1 or record["value"] == matches[0]["value"]:
            continue
        found = matches[0]
        signals.append({"kind": "numeric_conflict_signal", "claim_span": claim_text[record["sentence_start"]:record["sentence_end"]],
                        "claim_start": record["sentence_start"], "claim_end": record["sentence_end"],
                        "evidence": [{"index": found["index"], "quote": found["quote"]}],
                        "evidence_start": found["quote_start"], "evidence_end": found["quote_end"],
                        "values": {"claim": record["literal"], "evidence": found["literal"]},
                        "unit": record["unit"], "anchor": record["anchor"]})
    return signals


__all__ = ["repair_citations", "numeric_conflict_signals", "NORMALIZATION_VERSION"]
