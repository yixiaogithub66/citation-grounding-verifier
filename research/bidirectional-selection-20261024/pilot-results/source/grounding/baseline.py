"""A conservative lexical baseline, without model calls or symbolic algebra.

Retrieval uses IDF-weighted word/character features. Verdicts need a literal
match, matching equations with covered surrounding words, or a tightly aligned
number/negation/equation contrast; retrieval similarity alone is not evidence.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import math
import re
import time
import unicodedata

from grounding.contracts import VerificationRequest, VerificationResult, validate_report


_CJK = r"\u3400-\u4dbf\u4e00-\u9fff"
_FEATURE = re.compile(rf"[A-Za-z_][A-Za-z_0-9]*|[{_CJK}]+|\d+(?:\.\d+)*")
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)*(?:[eE][-+]?\d+)?"
)
_ASSIGNMENT = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*=")
_NEGATION = re.compile(r"\b(?:not|never|no)\b|不是|没有|并非|不|未|非", re.I)
_ENGLISH_STOP = {
    "a", "an", "the", "is", "are", "be", "to", "of", "in", "this", "that",
    "and", "as", "by", "for", "given", "equals",
}
_CHINESE_STOP = re.compile(r"该|这个|的|为|是|中")
_NONFACT = re.compile(
    r"(?:(?:thanks?|thank\s+you)(?:\s+for\s+(?:your\s+)?"
    r"(?:help|answer|explanation|assistance))?|"
    r"please\s+continue|ok(?:ay)?|"
    r"(?:谢谢|感谢)(?:你|您)?(?:的?(?:帮助|解答|分享|回答|支持))?|"
    r"请继续|好的|好|加油)",
    re.I,
)


def split_claims(text: str) -> list[str]:
    """Split prose, retaining decimal, version and scientific number periods."""
    pieces = re.split(r"(?<=[。！？!?；;])\s*|(?<=\.)(?=\s|$)|[\r\n]+", text)
    result = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        # Only split English conjunctions when both sides have their own verb.
        clauses = re.split(r"\s+and\s+", piece)
        if len(clauses) > 1 and all(
            re.search(r"\b(?:is|are|was|were|has|have)\b", clause, re.I)
            for clause in clauses
        ):
            result.extend(clause.strip() for clause in clauses if clause.strip())
        else:
            result.append(piece)
    return result


def _factual(text: str) -> bool:
    plain = text.strip(" \t\r\n.!?。！？；;")
    if not plain or _NONFACT.fullmatch(plain):
        return False
    if text.rstrip().endswith(("?", "？")):
        return False
    return bool(re.search(rf"[A-Za-z0-9{_CJK}]", plain))


def _surface(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text).strip(".!?,;:。！？、")


def _features(text: str) -> Counter:
    features = Counter()
    for token in _FEATURE.findall(unicodedata.normalize("NFKC", text)):
        if re.fullmatch(rf"[{_CJK}]+", token):
            features.update("c:" + token[i:i + 2] for i in range(len(token) - 1))
            if len(token) == 1:
                features["c:" + token] += 1
        else:
            features["w:" + token.lower()] += 1
    return features


def _words(text: str) -> set[str]:
    """Content anchors, used in addition to equation equality."""
    text = _CHINESE_STOP.sub("", text)
    return {
        token for token in _features(text)
        if not token.startswith("w:") or token[2:] not in _ENGLISH_STOP
    }


def _equations(text: str) -> list[tuple[str, str, tuple[int, int]]]:
    equations = []
    for match in _ASSIGNMENT.finditer(text):
        pos = match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        start = pos
        depth = 0
        while pos < len(text):
            char = text[pos]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            if re.match(rf"[{_CJK}。！？；]", char):
                break
            if char in ",;" and depth == 0:
                break
            if char == "." and (pos + 1 == len(text) or text[pos + 1].isspace()):
                break
            if not (char.isascii() and (char.isalnum() or char in "_+-*/^().,[]{} \t")):
                break
            # Stop a right-hand side before another assignment or English clause.
            if char.isspace() and re.match(
                r"\s+(?:and|but|while|where|with|is|are)\b|\s+[A-Za-z]\w*\s*=",
                text[pos:],
                re.I,
            ):
                break
            pos += 1
        rhs = re.sub(r"\s+", "", text[start:pos]).rstrip(".")
        if rhs:
            equations.append((match.group(1), rhs, (match.start(), pos)))
    return equations


def _without_equations(text: str, equations: list) -> str:
    for _, _, (start, end) in reversed(equations):
        text = text[:start] + text[end:]
    return text


def _numeric_signature(text: str) -> tuple[str, list[str]]:
    numbers = _NUMBER.findall(text)
    return _surface(_NUMBER.sub("<NUM>", text)), numbers


def _number_values(text: str) -> list:
    result = []
    for number in _NUMBER.findall(text):
        try:
            result.append(Decimal(number))
        except InvalidOperation:
            result.append(number)
    return result


def _aligned(short: str, long: str) -> bool:
    return bool(short and (short == long or len(short) >= 8 and short in long))


def _opposing_signs(left: str, right: str) -> bool:
    """Recognize aligned sign flips, without interpreting optional unary plus."""
    if len(left) != len(right):
        return False
    differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
    if not differences or any({left[index], right[index]} != {"+", "-"} for index in differences):
        return False
    for index in differences:
        operand = left[index + 1:]
        # Zero terms and products beginning with zero do not change sign.
        number = re.match(r"\(*([0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)\)*", operand)
        if number and Decimal(number.group(1)) == 0:
            return False
        # Changing a sign in an exponent needs algebra beyond this baseline.
        if index and left[index - 1] in "^eE":
            return False
    return True


def _judge(claim: str, evidence: str) -> tuple[str | None, str]:
    claim_surface, evidence_surface = _surface(claim), _surface(evidence)
    if _aligned(claim_surface, evidence_surface):
        return "SUPPORTED", "The claim matches a literal span of the cited passage."

    c_eq, e_eq = _equations(claim), _equations(evidence)
    if c_eq:
        c_words = _words(_without_equations(claim, c_eq))
        e_words = _words(_without_equations(evidence, e_eq))
        anchors_covered = c_words <= e_words
        e_pairs = {(lhs, rhs) for lhs, rhs, _ in e_eq}
        if anchors_covered and all((lhs, rhs) in e_pairs for lhs, rhs, _ in c_eq):
            return "SUPPORTED", "The equations and surrounding content anchors match the cited text."
        if len(c_eq) == 1:
            lhs, rhs, _ = c_eq[0]
            alternatives = [other_rhs for other_lhs, other_rhs, _ in e_eq if other_lhs == lhs]
            # Only a small edit in an otherwise near-identical expression is
            # treated as a contradiction; algebraic equivalence is not resolved.
            if anchors_covered and any(
                other != rhs and SequenceMatcher(None, rhs, other).ratio() >= 0.8
                and _number_values(rhs) != _number_values(other)
                for other in alternatives
            ):
                return "CONTRADICTED", "The same stated formula contains a different numerical value."
            if anchors_covered and any(
                _opposing_signs(other, rhs)
                for other in alternatives
            ):
                return "CONTRADICTED", "The same stated formula has an opposing sign in the cited text."

    c_signature, c_numbers = _numeric_signature(claim)
    e_signature, e_numbers = _numeric_signature(evidence)
    if c_numbers and len(c_numbers) == len(e_numbers):
        if _aligned(c_signature, e_signature) and _number_values(claim) != _number_values(evidence):
            return "CONTRADICTED", "The otherwise matching statement gives different numerical values."

    c_neg, e_neg = _NEGATION.findall(claim), _NEGATION.findall(evidence)
    if bool(c_neg) != bool(e_neg) and max(len(c_neg), len(e_neg)) == 1:
        c_positive = _surface(_NEGATION.sub("", claim))
        e_positive = _surface(_NEGATION.sub("", evidence))
        if _aligned(c_positive, e_positive):
            return "CONTRADICTED", "The otherwise matching statement differs by an explicit negation."
    return None, ""


class BaselineVerifier:
    """A deliberately limited retrieval-and-rule baseline."""

    def __init__(self, settings=None):
        self.settings = settings

    def verify(self, request: VerificationRequest) -> VerificationResult:
        started = time.perf_counter()
        candidates = [
            (index, sentence)
            for index, passage in enumerate(request.context_passages)
            for sentence in split_claims(passage)
            if sentence
        ]
        candidate_features = [_features(text) for _, text in candidates]
        frequencies = Counter(key for features in candidate_features for key in features)
        total = len(candidates)
        idf = {key: math.log((total + 1) / (count + 1)) + 1
               for key, count in frequencies.items()}

        def similarity(features, other):
            common = features.keys() & other.keys()
            dot = sum(features[key] * other[key] * idf.get(key, 1) ** 2 for key in common)
            left = sum((value * idf.get(key, 1)) ** 2 for key, value in features.items())
            right = sum((value * idf.get(key, 1)) ** 2 for key, value in other.items())
            return dot / math.sqrt(left * right) if left and right else 0.0

        claims = []
        for claim in split_claims(request.generated_answer):
            if not _factual(claim):
                continue
            features = _features(claim)
            ranking = sorted(
                range(total),
                key=lambda idx: similarity(features, candidate_features[idx]),
                reverse=True,
            )
            decisions = []
            for idx in ranking[:5]:
                index, evidence = candidates[idx]
                verdict, reasoning = _judge(claim, evidence)
                if verdict:
                    decisions.append((verdict, reasoning, index, evidence))
            verdicts = {item[0] for item in decisions}
            if len(verdicts) == 1:
                verdict, reasoning, index, evidence = decisions[0]
                citations = [{"index": index, "quote": evidence}]
            else:
                verdict = "UNSUPPORTED"
                reasoning = (
                    "The passages contain conflicting matched statements."
                    if len(verdicts) > 1 else
                    "The lexical baseline cannot establish this claim from the supplied passages."
                )
                citations = []
            claims.append({
                "claim_text": claim,
                "verdict": verdict,
                "reasoning": reasoning,
                "citations": citations,
            })
        report = {"claims": claims}
        validate_report(report, request.context_passages)
        return VerificationResult(
            report=report,
            telemetry={
                "backend": "baseline",
                "calls": [],
                "latency_seconds": time.perf_counter() - started,
            },
        )
