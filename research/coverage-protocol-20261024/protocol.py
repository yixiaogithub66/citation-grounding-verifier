"""Experimental occurrence-addressed coverage; no semantic decisions in code.

Unit ledgers are a different, coarser coverage contract than the legacy character
span union. Neither unit assignment nor exact text copying proves fact recall.
Only the model selects claims; this adapter never merges claims or labels gaps.
"""
from __future__ import annotations

import re
from grounding.contracts import VerificationError
from grounding.prompts_v4 import DECOMPOSE_PROMPT
from grounding.verifiers_v4 import extract_claims

ARMS = ('legacy', 'ledger_text', 'ledger_id')
MAX_UNITS = 256
_END = re.compile(r'(?:[。！？!?；;]|\.(?=\s|$)|\r?\n)[\s\"\'”’）)\]]*')

# Preserve the current task's semantic instructions verbatim. Only serialization
# and coverage/addressing instructions are replaced for the experimental arms.
SEMANTICS = (
    DECOMPOSE_PROMPT.split("Return only this exact JSON schema:", 1)[0]
    + DECOMPOSE_PROMPT[DECOMPOSE_PROMPT.index("Keep original order."):
                       DECOMPOSE_PROMPT.index("source_span and non_factual_spans.text must")]
    + DECOMPOSE_PROMPT[DECOMPOSE_PROMPT.index("claim_text may add only a shared antecedent"):]
)

LEDGER_COMMON = """
The source_units are the complete original answer in order, partitioned without
changing any characters. Read the entire ordered answer before extracting.
Unit boundaries are addresses, not factual or sentence boundaries. A unit may
contain multiple independent facts or both factual and non-factual wording; a
single fact may need multiple units. Preserve cross-unit subjects and scope.
Equal text at different positions belongs to different unit_ids.
Return exactly claims and coverage. claims contains objects with claim_id and
claim_text; use distinct nonempty claim_ids. Do not create one claim per unit by
default. coverage has one entry per input unit in exact input order, with
unit_id, claim_ids and nf_reason. claim_ids lists ALL claims supported by that
unit, including when it supplies a shared subject or qualifier. nf_reason is
null if there is no non-factual wording; otherwise briefly identify and explain
that wording. Pure non-factual units have empty claim_ids and a reason. Mixed
units have both claims and a reason; explaining non-factual wording must not
exclude their factual premises. Never leave both claim_ids and nf_reason empty.
Every claim needs a source reference; multiple claims may share a unit and one
claim may use multiple units. Include every assertion within each unit, not
merely a representative one. Do not invent/omit a unit, attach it only to pass
bookkeeping, or label an unprocessed unit non-factual.
Return only the JSON object, without commentary.
"""

TEXT_PROTOCOL = """
For this protocol every coverage entry also has source_text, which must copy
the ENTIRE text of that unit verbatim, including all punctuation and whitespace.
Return this schema (arrays can have zero or more claims as appropriate):
{"claims":[{"claim_id":"c1","claim_text":"standalone assertion"}],
"coverage":[{"unit_id":"u0001","source_text":"verbatim full unit text",
"claim_ids":["c1"],"nf_reason":null}]}
"""

ID_PROTOCOL = """
For this protocol every coverage entry refers to its source only by unit_id;
do not return a source_text field. The code retrieves the exact original text.
Return this schema (arrays can have zero or more claims as appropriate):
{"claims":[{"claim_id":"c1","claim_text":"standalone assertion"}],
"coverage":[{"unit_id":"u0001","claim_ids":["c1"],"nf_reason":null}]}
"""


def invalid(message):
    raise VerificationError('invalid_model_output', message)


def text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def source_units(answer):
    """Lossless punctuation addressing only; not semantic segmentation."""
    if not text(answer):
        raise ValueError('Expected a nonempty Unicode answer')
    spans = []
    start = 0
    for match in _END.finditer(answer):
        if match.end() > start:
            spans.append((start, match.end()))
            start = match.end()
    if start < len(answer):
        spans.append((start, len(answer)))
    if len(spans) > MAX_UNITS:
        raise ValueError('Answer exceeds the fixed source-unit resource limit')
    units = [{'unit_id': f'u{i+1:04d}', 'text': answer[a:b],
              'source_start': a, 'source_end': b} for i, (a,b) in enumerate(spans)]
    assert ''.join(u['text'] for u in units) == answer
    return units


def prompts():
    return {'legacy': DECOMPOSE_PROMPT,
            'ledger_text': SEMANTICS + LEDGER_COMMON + TEXT_PROTOCOL,
            'ledger_id': SEMANTICS + LEDGER_COMMON + ID_PROTOCOL}


def payload(arm, generated_answer):
    if arm not in ARMS:
        raise ValueError('Unknown protocol arm')
    if arm == 'legacy':
        return {'generated_answer': generated_answer, 'max_claims': 64,
                'boundary_context': {'before':'', 'after':''}}
    return {'source_units': [{'unit_id':u['unit_id'], 'text':u['text']}
                             for u in source_units(generated_answer)],
            'max_claims': 64, 'boundary_context': {'before':'', 'after':''}}


def validate(arm, raw_output, generated_answer, max_claims=64):
    if arm == 'legacy':
        claims, excluded = extract_claims(raw_output, generated_answer, max_claims=max_claims)
        return {'claims': claims, 'non_factual_spans': excluded,
                'protocol_diagnostics': {'contract':'legacy-exact-span-character-union'}}
    if arm not in ARMS:
        raise ValueError('Unknown protocol arm')
    if not isinstance(raw_output, dict) or set(raw_output) != {'claims','coverage'}:
        invalid('Ledger extraction must have exactly claims and coverage')
    claims, coverage = raw_output['claims'], raw_output['coverage']
    if not isinstance(claims, list) or not isinstance(coverage, list):
        invalid('Ledger claims and coverage must be arrays')
    if len(claims) > max_claims:
        invalid('Ledger exceeds configured claim limit')
    units = source_units(generated_answer)
    if len(coverage) != len(units):
        invalid('Ledger must explicitly account for every source unit once')
    by_id = {}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'claim_id','claim_text'} or not text(claim['claim_id']) or not text(claim['claim_text']):
            invalid('Each ledger claim needs exactly nonempty claim_id and claim_text')
        cid = claim['claim_id']
        if cid in by_id:
            invalid('Claim ids must be unique')
        by_id[cid] = []
    excluded, mixed, ledger = [], [], []
    fields = {'unit_id','claim_ids','nf_reason'}
    if arm == 'ledger_text':
        fields = fields | {'source_text'}
    for row, unit in zip(coverage, units):
        if not isinstance(row, dict) or set(row) != fields:
            invalid('Coverage entry fields differ from the protocol schema')
        if row['unit_id'] != unit['unit_id']:
            invalid('Coverage must name each input unit exactly once in source order')
        if arm == 'ledger_text' and row['source_text'] != unit['text']:
            invalid('source_text must equal the full original unit without normalization')
        refs = row['claim_ids']
        if not isinstance(refs, list) or any(not text(cid) for cid in refs) or len(refs) != len(set(refs)) or any(cid not in by_id for cid in refs):
            invalid('Coverage claim_ids must be unique existing claim references')
        reason = row['nf_reason']
        if reason is not None and not text(reason):
            invalid('nf_reason must be null or a nonempty explicit explanation')
        if not refs and reason is None:
            invalid('A unit must explicitly reference claims or explain non-factual content')
        # This renders the model's explicit two-field classification, rather than
        # inferring a semantic label from its text or silently filling omissions.
        kind = 'mixed' if refs and reason is not None else ('factual' if refs else 'non_factual')
        if not refs:
            excluded.append({'text': unit['text'], 'reason': reason,
                             'source_start':unit['source_start'], 'source_end':unit['source_end']})
        elif reason is not None:
            mixed.append({'unit_id':unit['unit_id'], 'reason':reason})
        for cid in refs:
            by_id[cid].append(unit)
        ledger.append({'unit_id':unit['unit_id'], 'kind':kind,
                       'claim_ids':list(refs), 'nf_reason':reason})
    if any(not refs for refs in by_id.values()):
        invalid('Every claim must have an explicit source-unit reference')
    normalized = []
    for claim in sorted(claims, key=lambda c: by_id[c['claim_id']][0]['source_start']):
        refs = by_id[claim['claim_id']]
        normalized.append({**claim, 'source_start':refs[0]['source_start'],
                           'provenance_kind':'explicit_unit_references',
                           'source_units':[dict(u) for u in refs]})
    return {'claims':normalized, 'non_factual_spans':excluded,
            'protocol_diagnostics':{'contract':'explicit-source-unit-ledger',
                                    'source_units':units, 'coverage':ledger,
                                    'mixed_units':mixed,
                                    'semantic_coverage_proven':False,
                                    'no_envelope_or_automatic_gap_assignment':True}}
