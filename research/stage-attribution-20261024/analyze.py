"""Offline, fixed-denominator scoring and procedurally blinded review export."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from grounding.verifiers_v4 import conflict_error


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(run):
    plan = read(run / 'planned-requests.json')
    records = {p.stem: read(p) for p in (run / 'stage-results').glob('*.json')}
    cases = {c['id']: c for c in read(HERE / 'cases.json')}
    annotations = {c['id']: c for c in read(HERE / 'annotations.json')}
    return plan, records, cases, annotations


def evidence_identity(contexts, claim, row):
    return {'context_passages': contexts, 'claim_text': claim['claim_text'],
            'verdict': row.get('verdict'), 'citations': row.get('citations')}


def prepare(run):
    plan, records, cases, annotations = load(run)
    m1, evidence, mapping = [], {}, {}
    for task in plan['initial']:
        rec = records.get(task['key'], {})
        case, annotation = cases[task['case_id']], annotations[task['case_id']]
        if task['stage'] == 'm1':
            rid = 'm-' + digest({'salt': 'stage-blind-v1', 'key': task['key']})[:20]
            raw = rec.get('raw_output')
            readable = isinstance(raw, dict) and isinstance(raw.get('claims'), list)
            m1.append({'review_id': rid, 'generated_answer': case['generated_answer'],
                       'expected_targets': [{k: t[k] for k in ('id', 'claim_text', 'source_span', 'essential_elements')}
                                            for t in annotation['targets']],
                       'expected_non_factual': annotation['non_factual'],
                       'readable': readable, 'raw_output': raw})
            mapping[rid] = {k: task[k] for k in ('key', 'case_id', 'arm', 'repetition')}
        else:
            for claim in case['claims']:
                row = (rec.get('validated_output') or {}).get('label_rows', {}).get(claim['id'])
                add_evidence(evidence, case, annotation, claim, row)
    for task in plan['reviews']:
        rec = records.get(task['key'], {})
        case, annotation = cases[task['case_id']], annotations[task['case_id']]
        claim = next(c for c in case['claims'] if c['id'] == task['claim_id'])
        add_evidence(evidence, case, annotation, claim, rec.get('after'))
    random.Random('stage-blind-v1').shuffle(m1)
    es = list(evidence.values())
    random.Random('stage-evidence-v1').shuffle(es)
    out = HERE / 'review-packets'
    save(out / 'm1-all.json', m1)
    save(out / 'm1-part1.json', m1[:len(m1)//2])
    save(out / 'm1-part2.json', m1[len(m1)//2:])
    save(out / 'evidence-all.json', es)
    save(out / 'private-key.json', mapping)
    print(json.dumps({'m1_outputs': len(m1), 'unique_evidence_items': len(es)}))


def add_evidence(evidence, case, annotation, claim, row):
    if not isinstance(row, dict) or row.get('verdict') not in ('SUPPORTED', 'CONTRADICTED'):
        return
    identity = evidence_identity(case['context_passages'], claim, row)
    eid = 'e-' + digest(identity)[:20]
    reference = next(t for t in annotation['targets'] if t['id'] == claim['id'])
    evidence[eid] = {'review_id': eid, **identity, 'reference_verdict': reference['verdict'],
                     'reference_rationale': reference['rationale']}


def costs(run, records):
    groups = defaultdict(list)
    for path in (run / 'call-results').glob('*.json'):
        call = read(path)
        stage = records[call['stage_key']]
        group = stage['stage'] + (':' + stage['arm'] if stage['stage'] != 'review' else '')
        groups[group].append(call)
    output = {}
    for group, calls in groups.items():
        p = o = cache = missing = cache_missing = 0
        models, fingerprints = Counter(), Counter()
        for call in calls:
            assert len(call['calls']) == 1
            trace = call['calls'][0]
            models[str(trace.get('model'))] += 1
            fingerprints[str(trace.get('system_fingerprint'))] += 1
            u = trace.get('usage') or {}
            if type(u.get('prompt_tokens')) is not int or type(u.get('completion_tokens')) is not int:
                missing += 1
                continue
            p += u['prompt_tokens']; o += u['completion_tokens']
            hit = u.get('prompt_cache_hit_tokens')
            if hit is None:
                hit = (u.get('prompt_tokens_details') or {}).get('cached_tokens')
            if type(hit) is not int:
                cache_missing += 1
            else:
                assert 0 <= hit <= u['prompt_tokens']
                cache += hit
        lat = sorted(c['latency_seconds'] for c in calls)
        output[group] = {'calls': len(calls), 'prompt_tokens_known': p, 'output_tokens_known': o,
                         'cache_hit_tokens_known': cache, 'usage_missing_calls': missing,
                         'cache_missing_calls': cache_missing,
                         'all_miss_known_subtotal': (p*.30 + o*1.20)/1e6,
                         'observed_cache_estimate': None if missing or cache_missing else ((p-cache)*.30+cache*.006+o*1.20)/1e6,
                         'cost_complete': missing == 0, 'models': dict(models), 'fingerprints': dict(fingerprints),
                         'call_latency_mean_seconds': statistics.mean(lat),
                         'call_latency_p95_seconds': lat[max(0, (95*len(lat)+99)//100-1)]}
    return output


def summarize(run):
    plan, records, cases, annotations = load(run)
    summary = {'qualification': 'AI-authored diagnostic component study; not author gold or end-to-end benchmark',
               'm1': {}, 'm3': {}, 'review': {}, 'costs': costs(run, records)}
    evidence_path = HERE / 'evidence-review.json'
    ev = {x['review_id']: x for x in read(evidence_path)['reviews']} if evidence_path.exists() else {}
    def semantically_usable(case, claim, row):
        if row is None:
            return False
        if row['verdict'] == 'UNSUPPORTED':
            return True
        eid = 'e-' + digest(evidence_identity(case['context_passages'], claim, row))[:20]
        return ev.get(eid, {}).get('evidence_sufficient')
    paired_m3 = {}
    for arm in ('simple', 'current'):
        c = Counter(); details = []
        for task in plan['initial']:
            if task['stage'] != 'm3' or task['arm'] != arm:
                continue
            case = cases[task['case_id']]
            ann = {t['id']: t for t in annotations[task['case_id']]['targets']}
            rec = records.get(task['key'], {})
            v = rec.get('validated_output') or {}
            complete = joint = not v.get('unexpected_rows', 0) and v.get('order_valid', False)
            c['unexpected_rows'] += v.get('unexpected_rows', 0)
            c['order_invalid_batches'] += not v.get('order_valid', False)
            for claim in case['claims']:
                cid, gold = claim['id'], ann[claim['id']]['verdict']
                row = v.get('label_rows', {}).get(cid)
                public = bool(v.get('public_valid', {}).get(cid))
                correct = row is not None and row.get('verdict') == gold
                schema_valid = cid in v.get('rows', {})
                supported = semantically_usable(case, claim, row)
                c.update(opportunities=1, identifiable=row is not None, raw_label_correct=correct,
                         public_valid=public, public_valid_correct=public and correct,
                         arm_schema_valid=schema_valid, arm_schema_valid_correct=schema_valid and correct,
                         evidence_valid_correct_lower=public and correct and supported is True,
                         evidence_valid_correct_upper=public and correct and supported is not False)
                complete &= public; joint &= public and correct
                detail = {'case_id': task['case_id'], 'repetition': task['repetition'], 'claim_id': cid,
                          'reference': gold, 'verdict': row.get('verdict') if row else None,
                          'public_valid': public, 'label_correct': correct, 'evidence_sufficient': supported}
                details.append(detail)
                paired_m3[(task['case_id'], task['repetition'], cid, arm)] = detail
            c.update(case_attempts=1, public_complete_cases=complete, public_complete_correct_cases=joint)
        summary['m3'][arm] = {**dict(c), 'details': details}
    diffs = Counter()
    for key, current in paired_m3.items():
        if key[-1] != 'current': continue
        simple = paired_m3[(*key[:-1], 'simple')]
        a, b = simple['public_valid'] and simple['label_correct'], current['public_valid'] and current['label_correct']
        diffs[('correct' if a else 'not_correct') + '->' + ('correct' if b else 'not_correct')] += 1
    summary['m3']['paired_common_contract'] = dict(diffs)
    rc, transitions, details = Counter(), Counter(), []
    for task in plan['reviews']:
        case = cases[task['case_id']]
        claim = next(c for c in case['claims'] if c['id'] == task['claim_id'])
        gold = next(t['verdict'] for t in annotations[task['case_id']]['targets'] if t['id'] == task['claim_id'])
        rec = records.get(task['key'], {})
        before, after = rec.get('before'), rec.get('after')
        def state(row):
            return 'incomplete' if row is None else ('correct' if row.get('verdict') == gold else 'wrong')
        bs, fs = state(before), state(after)
        transitions[bs+'->'+fs] += 1
        bv = before is not None and (before['verdict'] != 'CONTRADICTED' or conflict_error(before, case['context_passages']) is None)
        av = after is not None and (after['verdict'] != 'CONTRADICTED' or conflict_error(after, case['context_passages']) is None)
        be, ae = semantically_usable(case, claim, before), semantically_usable(case, claim, after)
        triggered = rec.get('triggered', False)
        rc.update(opportunities=1, eligible=before is not None, triggered=triggered,
                  before_correct=bs=='correct', after_correct=fs=='correct',
                  before_contract_correct=bv and bs=='correct', after_contract_correct=av and fs=='correct',
                  before_evidence_correct_lower=bv and bs=='correct' and be is True,
                  after_evidence_correct_lower=av and fs=='correct' and ae is True,
                  before_evidence_correct_upper=bv and bs=='correct' and be is not False,
                  after_evidence_correct_upper=av and fs=='correct' and ae is not False,
                  wrong_initial_triggered=bs=='wrong' and triggered,
                  wrong_initial_not_triggered=bs=='wrong' and not triggered)
        tel = rec.get('telemetry') or {}
        rc['c_reviews'] += len(tel.get('contradiction_reviews', []))
        rc['u_reviews'] += len(tel.get('unsupported_reviews', []))
        details.append({'case_id': task['case_id'], 'repetition': task['repetition'], 'claim_id': task['claim_id'],
                        'reference': gold, 'before': before.get('verdict') if before else None,
                        'after': after.get('verdict') if after else None, 'transition': bs+'->'+fs,
                        'triggered': triggered, 'before_evidence': be, 'after_evidence': ae,
                        'physical_calls': rec.get('physical_calls', 0)})
    summary['review'] = {**dict(rc), 'transitions': dict(transitions), 'details': details,
                         'net_label_corrections': transitions['wrong->correct']-transitions['correct->wrong'],
                         'net_usable_label_gain': rc['after_contract_correct']-rc['before_contract_correct']}
    review_files = [HERE/'m1-review-part1.json', HERE/'m1-review-part2.json']
    if all(p.exists() for p in review_files):
        reviews = {r['review_id']: r for p in review_files for r in read(p)['reviews']}
        packets = read(HERE/'review-packets/m1-all.json')
        mapping = read(HERE/'review-packets/private-key.json')
        assert len(reviews) == 80 and set(reviews) == set(mapping)
        for arm in ('concise', 'current'):
            c, cases_pass, scored = Counter(), defaultdict(list), []
            for packet in packets:
                ident = mapping[packet['review_id']]
                if ident['arm'] != arm: continue
                r = reviews[packet['review_id']]
                expected = {t['id'] for t in packet['expected_targets']}
                assert {t['id'] for t in r['targets']} == expected and len(r['targets']) == len(expected)
                valid = records.get(ident['key'], {}).get('status') == 'valid'
                fields = ('content_retained', 'standalone', 'faithful', 'source_sufficient', 'atomic')
                flags = [t[f] for t in r['targets'] for f in fields] + [r['no_false_claims'], r['no_fact_in_nf'], r['all_claims_well_formed']]
                assert all(x is None or type(x) is bool for x in flags)
                lower = valid and all(x is True for x in flags)
                upper = valid and all(x is not False for x in flags)
                c.update(attempts=1, structurally_valid=valid, raw_readable=packet['readable'],
                         targets=len(expected), strict_joint_lower=lower, strict_joint_upper=upper,
                         false_claim_outputs=r['no_false_claims'] is False,
                         pure_nf_attempts=not expected,
                         pure_nf_correct_valid=not expected and valid and r['no_false_claims'] is True)
                for target in r['targets']:
                    for f in fields:
                        c['raw_'+f] += target[f] is True
                        c['raw_'+f+'_unknown'] += target[f] is None
                        c['completed_'+f] += valid and target[f] is True
                cases_pass[ident['case_id']].append((lower, upper))
                scored.append({**ident, **r, 'valid': valid, 'strict_lower': lower, 'strict_upper': upper})
            c['both_repeats_lower'] = sum(all(x[0] for x in xs) for xs in cases_pass.values())
            c['both_repeats_upper'] = sum(all(x[1] for x in xs) for xs in cases_pass.values())
            summary['m1'][arm] = {**dict(c), 'details': scored}
    expected_evidence = {x['review_id'] for x in read(HERE/'review-packets/evidence-all.json')} if (HERE/'review-packets/evidence-all.json').exists() else set()
    if ev:
        assert set(ev) == expected_evidence, 'Evidence review must cover every unique S/C output'
        assert all(x.get('evidence_sufficient') is None or type(x.get('evidence_sufficient')) is bool for x in ev.values())
    summary['semantic_audit_complete'] = bool(summary['m1']) and set(ev) == expected_evidence and evidence_path.exists()
    save(HERE/'analysis.json', summary)
    print(json.dumps({k: ({a: {x:y for x,y in b.items() if x != 'details'} for a,b in v.items()}
                          if k in ('m1','m3') else {x:y for x,y in v.items() if x != 'details'} if k=='review' else v)
                      for k,v in summary.items()}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'summarize'))
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else summarize)(args.run)
