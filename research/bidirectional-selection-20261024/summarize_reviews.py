"""Aggregate recorded AI semantic reviews; no model calls or semantic heuristics."""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parents[1] / 'results/bidirectional-selection-20261024-recovered'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    packets = HERE / 'review-packets'
    key = read(packets / 'private-key.json')
    cases = read(HERE / 'cases.json')
    seeds = {s['seed_id']: s for s in cases['controlled_seeds']}
    paths = [HERE / 'review-natural-part1.json', HERE / 'review-natural-part2.json',
             packets / 'review-controlled.json']
    reviews = [v for p in paths for v in read(p)['reviews']]
    rows = [r for name in ('blind-natural.json', 'blind-controlled.json')
            for r in read(packets / name)['records']]
    by_review = {r['review_id']: r for r in reviews}
    assert len(reviews) == len(by_review) == 152
    assert set(by_review) == set(key['mapping']) == {r['review_id'] for r in rows}
    # Two outputs retain 'imaginary tray' but do not explicitly repeat exercise/
    # assumption scope; predeclared scoped-assumption sensitivity has two readings.
    scope_ambiguous = {'r-c87271dadf30a43135a8e6de', 'r-fd0a48d8cf3b7025b1c4ea7c'}
    joined = []
    for row in rows:
        review = by_review[row['review_id']]
        mappings = review['target_mappings']
        assert {m['fact_id'] for m in mappings} == {f['id'] for f in row['expected_facts']}
        assert len(mappings) == len(row['expected_facts'])
        valid = row['status'] == 'valid'
        if valid:
            assert all(type(m['retained']) is bool for m in mappings)
            assert review['semantic_complete'] == (all(m['retained'] for m in mappings) and not review['spurious_claims'])
            count = len(row['validated_output']['claims'])
            assert all(0 <= i < count for m in mappings for i in m['claim_indices'])
            assert all(0 <= s['claim_index'] < count for s in review['spurious_claims'])
        else:
            assert review['semantic_complete'] is None
            assert all(m['retained'] is None for m in mappings)
            assert not review['spurious_claims']
        joined.append({**key['mapping'][row['review_id']], 'review_id': row['review_id'],
                       'valid': valid, 'pure_nf': row['expected_pure_nf'],
                       'target_count': len(mappings),
                       'retained_targets': [m['fact_id'] for m in mappings if m['retained'] is True],
                       'semantic_omissions': [m['fact_id'] for m in mappings if m['retained'] is False],
                       'technical_unknown_targets': [m['fact_id'] for m in mappings if m['retained'] is None],
                       'spurious_claims': review['spurious_claims'],
                       'semantic_complete': review['semantic_complete'],
                       'scoped_assumption_only': review['scoped_assumption_only'],
                       'ambiguous_scoped_assumption': row['review_id'] in scope_ambiguous})

    def summary(selected):
        nf = [r for r in selected if r['pure_nf']]
        targets = sum(r['target_count'] for r in selected)
        retained = sum(len(r['retained_targets']) for r in selected)
        complete = sum(r['semantic_complete'] is True for r in selected)
        scoped = sum(r['valid'] and r['scoped_assumption_only'] for r in selected)
        ambiguous = sum(r['valid'] and r['ambiguous_scoped_assumption'] for r in selected)
        return {'attempts': len(selected), 'valid': sum(r['valid'] for r in selected),
                'technical_errors': sum(not r['valid'] for r in selected),
                'factual_opportunities': targets, 'retained_factual_targets': retained,
                'all_cause_unserved_targets': targets-retained,
                'semantic_omissions_on_valid_outputs': sum(len(r['semantic_omissions']) for r in selected),
                'technical_unknown_targets': sum(len(r['technical_unknown_targets']) for r in selected),
                'pure_nf_opportunities': len(nf), 'pure_nf_valid': sum(r['valid'] for r in nf),
                'pure_nf_correct_and_valid': sum(r['semantic_complete'] is True for r in nf),
                'pure_nf_wrong_upgrade_cases': sum(r['valid'] and bool(r['spurious_claims']) for r in nf),
                'pure_nf_technical_errors': sum(not r['valid'] for r in nf),
                'spurious_claims_in_factual_answers': sum(len(r['spurious_claims']) for r in selected if not r['pure_nf']),
                'spurious_claims_in_nf_answers': sum(len(r['spurious_claims']) for r in nf),
                'complete_semantic_cases': complete,
                'permissive_scoped_complete_interval': [complete+scoped, complete+scoped+ambiguous],
                'permissive_scoped_nf_correct_interval': [sum(r['semantic_complete'] is True for r in nf)+scoped,
                                                        sum(r['semantic_complete'] is True for r in nf)+scoped+ambiguous]}

    natural = {arm: summary([r for r in joined if r['probe']=='natural' and r['arm']==arm])
               for arm in ('base', 'fresh', 'generic', 'bidirectional')}
    controlled = {arm: {kind: summary([r for r in joined if r['probe']=='controlled' and r['arm']==arm and
                                     seeds[r['case_id']]['kind']==kind]) for kind in ('omission','spurious','clean')}
                  for arm in ('generic', 'bidirectional')}
    identities = {(r['probe'],r['case_id'],r['arm'],r['repetition']):r for r in joined}
    pairs = []
    for r in joined:
        if r['probe']!='natural' or r['arm']!='generic': continue
        b = identities[('natural',r['case_id'],'bidirectional',r['repetition'])]
        gains = sorted(set(b['retained_targets'])-set(r['retained_targets']))
        losses = sorted(set(r['retained_targets'])-set(b['retained_targets']))
        pairs.append({'case_id': r['case_id'], 'repetition': r['repetition'],
                      'generic_valid':r['valid'], 'bidirectional_valid':b['valid'],
                      'generic_complete':r['semantic_complete'], 'bidirectional_complete':b['semantic_complete'],
                      'gained_served_targets':gains, 'lost_served_targets':losses,
                      'nf_error_delta': (int(bool(b['spurious_claims']))-int(bool(r['spurious_claims'])))
                        if r['pure_nf'] and r['valid'] and b['valid'] else None,
                      'generic_review_id':r['review_id'], 'bidirectional_review_id':b['review_id']})
    mechanical = read(RUN / 'analysis.json')
    raw = [json.loads(line) for line in (RUN/'responses.jsonl').read_text(encoding='utf-8').splitlines()]
    callmap = {(r['probe'],r['case_id'],r['arm'],r['repetition']):r for r in raw}
    chain = {}
    for arm in ('generic','bidirectional'):
        base = mechanical['natural']['base']['runtime']
        rev = mechanical['natural'][arm]['runtime']
        latencies = sorted(callmap[('natural',r['case_id'],'base',r['repetition'])]['latency_seconds']+
                           callmap[('natural',r['case_id'],arm,r['repetition'])]['latency_seconds']
                           for r in joined if r['probe']=='natural' and r['arm']==arm)
        chain[arm] = {'reference_known_cached_usd':base['reference_cost']['known_usage_subtotal']+rev['reference_cost']['known_usage_subtotal'],
                      'reference_all_miss_usd':base['reference_cost']['cache_standardized_all_miss_known_subtotal']+rev['reference_cost']['cache_standardized_all_miss_known_subtotal'],
                      'sum_per_call_latency_mean_seconds':sum(latencies)/len(latencies),
                      'sum_per_call_latency_p95_seconds':latencies[30],
                      'note':'Analytical base+revision chain; excludes queueing, disruption and possibly untracked original attempt. Shared base must not be added twice to physical spending.'}
    result = {'qualification':'AI semantic review of synthetic M1 selection, not author adjudication or full M1/end-to-end contract quality.',
              'responses_sha256':sha(RUN/'responses.jsonl'), 'freeze_sha256':sha(RUN/'freeze.json'),
              'review_files_sha256':{str(p.relative_to(HERE)):sha(p) for p in paths},
              'natural':natural, 'controlled':controlled,
              'natural_per_repeat':{arm:{str(rep):summary([r for r in joined if r['probe']=='natural' and r['arm']==arm and r['repetition']==rep])
                                          for rep in (0,1)} for arm in natural},
              'paired_natural':sorted(pairs,key=lambda p:(p['case_id'],p['repetition'])),
              'natural_without_hypothetical_boundary_case':{arm:summary([r for r in joined if r['probe']=='natural' and r['arm']==arm and r['case_id']!='sel-04']) for arm in natural},
              'chain_accounting':chain,
              'all_miss_chain_cost_ratio':chain['bidirectional']['reference_all_miss_usd']/chain['generic']['reference_all_miss_usd'],
              'physical_attempt_accounting':{'recorded':152,'possible_untracked_extra':1,'known_cost_is_subtotal':True},
              'scored_records':joined}
    with (HERE/'semantic-analysis.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'natural':natural, 'controlled':controlled, 'changed_pairs':[p for p in pairs if p['gained_served_targets'] or p['lost_served_targets'] or p['nf_error_delta']], 'chain':chain},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
