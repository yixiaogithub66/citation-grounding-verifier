"""Offline aggregation of frozen-case, blinded AI judgments; no model calls."""
from pathlib import Path
import hashlib
import json
from collections import Counter
import jsonschema

HERE=Path(__file__).resolve().parent
RUN=HERE.parents[1]/'results/coverage-protocol-20261024'
ARMS=('legacy','ledger_text','ledger_id')

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    packet=read(HERE/'review-packets/blind-all.json')
    key=read(HERE/'review-packets/private-key.json')['mapping']
    paths=[HERE/'review-part1.json',HERE/'review-part2.json']
    review_rows=[r for p in paths for r in read(p)['reviews']]
    reviews={r['review_id']:r for r in review_rows}
    assert len(reviews)==len(review_rows)==120 and set(reviews)==set(key)
    for r in review_rows:jsonschema.validate(r,packet['scoring_schema'])
    joined=[]
    for r in packet['records']:
        v=reviews[r['review_id']]
        assert {t['fact_id'] for t in v['targets']}=={t['id'] for t in r['expected_facts']}
        assert len(v['targets'])==len(r['expected_facts'])
        if r['extraction_readable']:
            assert all(0<=i<len(r['claims']) for t in v['targets'] for i in t['claim_indices'])
            assert all(0<=x['claim_index']<len(r['claims']) for x in v['claim_issues'])
        else:
            assert all(t['content_retained'] is None and t['standalone_retained'] is None and t['source_supported'] is None and not t['claim_indices'] for t in v['targets'])
        if r['status']!='valid':
            assert v['selection_pass'] is None and v['strict_fidelity_pass'] is None
            assert all(t['standalone_retained'] is None and t['source_supported'] is None for t in v['targets'])
        else:
            if v['selection_pass'] is True:
                assert all(t['content_retained'] is True for t in v['targets'])
                assert not any(x['kind'] in {'non_factual_as_claim','meaning_changed'} for x in v['claim_issues'])
            if v['strict_fidelity_pass'] is True:
                assert v['selection_pass'] is True and not v['claim_issues']
                assert all(t[k] is True for t in v['targets'] for k in ('standalone_retained','source_supported'))
        joined.append({**key[r['review_id']],**v,'valid':r['status']=='valid',
                       'readable':r['extraction_readable'],'pure_nf':r['expected_pure_nf']})

    def summary(rows):
        valid=[r for r in rows if r['valid']]
        invalid=[r for r in rows if not r['valid']]
        ts=[t for r in rows for t in r['targets']]
        vt=[t for r in valid for t in r['targets']]
        it=[t for r in invalid for t in r['targets']]
        nf=[r for r in rows if r['pure_nf']]
        joint=sum(r['strict_fidelity_pass'] is True for r in valid)
        uncertain=sum(r['strict_fidelity_pass'] is None for r in valid)
        cids=sorted({r['case_id'] for r in rows})
        both_lower=both_upper=0
        repeats_applicable=all(sum(r['case_id']==cid for r in rows)==2 for cid in cids)
        for cid in cids:
            rr=[r for r in rows if r['case_id']==cid]
            if len(rr)!=2:continue
            both_lower+=all(r['valid'] and r['strict_fidelity_pass'] is True for r in rr)
            both_upper+=all(r['valid'] and r['strict_fidelity_pass'] is not False for r in rr)
        return {'attempts':len(rows),'valid':len(valid),'technical_errors':len(invalid),
                'target_opportunities':len(ts),
                'completed_content_targets':sum(t['content_retained'] is True for t in vt),
                'valid_semantic_missing_targets':sum(t['content_retained'] is False for t in vt),
                'valid_content_unknown_targets':sum(t['content_retained'] is None for t in vt),
                'technical_unserved_targets':len(it),
                'completed_standalone_targets':sum(t['standalone_retained'] is True for t in vt),
                'valid_standalone_failed_targets':sum(t['standalone_retained'] is False for t in vt),
                'valid_standalone_unknown_targets':sum(t['standalone_retained'] is None for t in vt),
                'completed_source_supported_targets':sum(t['source_supported'] is True for t in vt),
                'valid_source_failed_targets':sum(t['source_supported'] is False for t in vt),
                'selection_pass':sum(r['selection_pass'] is True for r in valid),
                'strict_joint_pass_interval':[joint,joint+uncertain],
                'both_repeats_strict_case_interval':[both_lower,both_upper] if repeats_applicable else None,
                'independent_cases':len(cids),
                'pure_nf_opportunities':len(nf),
                'pure_nf_correct_valid':sum(r['valid'] and r['selection_pass'] is True for r in nf),
                'pure_nf_wrong_valid':sum(r['valid'] and r['selection_pass'] is False for r in nf),
                'pure_nf_technical_errors':sum(not r['valid'] for r in nf),
                'valid_false_claim_answers':sum(any(x['kind'] in {'non_factual_as_claim','meaning_changed'} for x in r['claim_issues']) for r in valid),
                'valid_claim_issue_counts':dict(Counter(x['kind'] for r in valid for x in r['claim_issues'])),
                'raw_diagnostic_content_targets_retained':sum(t['content_retained'] is True for t in ts),
                'raw_diagnostic_content_targets_missing':sum(t['content_retained'] is False for t in ts),
                'raw_diagnostic_content_targets_unknown':sum(t['content_retained'] is None for t in ts),
                'raw_diagnostic_false_claim_answers':sum(r['readable'] and any(x['kind'] in {'non_factual_as_claim','meaning_changed'} for x in r['claim_issues']) for r in rows),
                'raw_unreadable_answers':sum(not r['readable'] for r in rows),
                'raw_diagnostic_scope':'All readable outputs, including valid and invalid; not invalid-only.',
                'invalid_only_diagnostic':{
                    'answers':len(invalid),'readable_answers':sum(r['readable'] for r in invalid),
                    'unreadable_answers':sum(not r['readable'] for r in invalid),
                    'target_opportunities':len(it),
                    'content_retained':sum(t['content_retained'] is True for t in it),
                    'content_missing':sum(t['content_retained'] is False for t in it),
                    'content_unknown':sum(t['content_retained'] is None for t in it),
                    'false_claim_answers_among_readable':sum(r['readable'] and any(x['kind'] in {'non_factual_as_claim','meaning_changed'} for x in r['claim_issues']) for r in invalid)}}

    summaries={a:summary([r for r in joined if r['arm']==a]) for a in ARMS}
    lookup={(r['case_id'],r['repetition'],r['arm']):r for r in joined}
    comparisons={}
    for other in ('legacy','ledger_text'):
        pairs=[]
        for r in joined:
            if r['arm']!='ledger_id':continue
            b=lookup[(r['case_id'],r['repetition'],other)]
            retained=lambda row:{t['fact_id'] for t in row['targets'] if t['content_retained'] is True}
            missing=lambda row:{t['fact_id'] for t in row['targets'] if t['content_retained'] is False}
            unknown=lambda row:{t['fact_id'] for t in row['targets'] if t['content_retained'] is None}
            served=lambda row:retained(row) if row['valid'] else set()
            pairs.append({'case_id':r['case_id'],'repetition':r['repetition'],
                          'control_valid':b['valid'],'candidate_valid':r['valid'],
                          'control_selection':b['selection_pass'],'candidate_selection':r['selection_pass'],
                          'control_joint':b['strict_fidelity_pass'],'candidate_joint':r['strict_fidelity_pass'],
                          'gained_completed_content_targets':sorted(served(r)-served(b)),
                          'lost_completed_content_targets':sorted(served(b)-served(r)),
                          'new_valid_content_loss_against_control_raw':sorted(retained(b)&missing(r)) if r['valid'] and b['readable'] else [],
                          'candidate_content_unknown_against_retained_control':sorted(retained(b)&unknown(r)) if r['valid'] and b['readable'] else [],
                          'accepted_missing_targets_same_as_rejected_raw':sorted(missing(b)&missing(r)) if r['valid'] and not b['valid'] and b['readable'] else [],
                          'accepted_omission_previously_rejected':bool(r['valid'] and not b['valid'] and b['readable'] and missing(b)&missing(r)),
                          'control_review_id':b['review_id'],'candidate_review_id':r['review_id']})
        comparisons[other]=sorted(pairs,key=lambda x:(x['case_id'],x['repetition']))

    multitarget={'cp001':{'f1','f2'},'cp005':{'f2','f3'},'cp017':{'f2','f3'}}
    subsets={}
    for arm in ARMS:
        rr=[r for r in joined if r['arm']==arm and r['case_id'] in multitarget]
        target_rows=[(r,t) for r in rr for t in r['targets'] if t['fact_id'] in multitarget[r['case_id']]]
        subsets[arm]={'independent_answers':3,'target_opportunities':len(target_rows),
                      'completed_retained':sum(r['valid'] and t['content_retained'] is True for r,t in target_rows),
                      'raw_retained':sum(t['content_retained'] is True for r,t in target_rows),
                      'valid_missing':sum(r['valid'] and t['content_retained'] is False for r,t in target_rows)}
    meta={'r-4a7fee71cdd4324bb54c6d3b','r-9fc42d5a313e8c9f2d311b59','r-c509b5d1c132fb243b64e0c0','r-dd1aee80592713eb349c6775'}
    route={'r-aa17b48d1ad5cbf16203aa97','r-5169b3d9b7b4d3eb95a9e0a2'}
    grammar={'r-60cc988af6222bcedaae7bc9'}
    sensitivity={}
    for arm in ARMS:
        rr=[r for r in joined if r['arm']==arm]
        sensitivity[arm]={'meta_guidance_additional_selection_and_joint':sum(r['review_id'] in meta for r in rr),
                          'same_sentence_source_scope_additional_joint':sum(r['review_id'] in route for r in rr),
                          'duplicated_possessive_strict_uncertainty':sum(r['review_id'] in grammar for r in rr),
                          'duplicated_possessive_literal_entity_change_sensitivity_content_loss':sum(r['review_id'] in grammar for r in rr)}
    mechanics=read(RUN/'analysis.json')
    costs={a:mechanics['arms'][a]['runtime']['reference_cost'] for a in ARMS}
    id_cost=costs['ledger_id']['cache_standardized_all_miss_known_subtotal']
    legacy_cost=costs['legacy']['cache_standardized_all_miss_known_subtotal']
    result={'qualification':'AI-assisted synthetic first-pass M1 study; all-attempt metrics and raw-only diagnostics kept separate; not author adjudication.',
            'freeze_sha256':sha(RUN/'freeze.json'),'responses_sha256':sha(RUN/'responses.jsonl'),
            'reviews_sha256':{p.name:sha(p) for p in paths},'arms':summaries,
            'per_repeat':{a:{str(rep):summary([r for r in joined if r['arm']==a and r['repetition']==rep]) for rep in (0,1)} for a in ARMS},
            'paired_id_vs':comparisons,'multi_target_unit_subset':subsets,'sensitivity':sensitivity,
            'reference_cost':costs,'id_vs_legacy_all_miss_ratio':id_cost/legacy_cost,
            'ledger_text_full_cost_unknown':not costs['ledger_text']['complete'],
            'ledger_id_cost_below_ledger_text_known_subtotal':id_cost<costs['ledger_text']['cache_standardized_all_miss_known_subtotal'],
            'scored_records':joined}
    with (HERE/'semantic-analysis.json').open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'arms':summaries,'multi_target':subsets,'sensitivity':sensitivity,'id_vs_legacy_all_miss_ratio':id_cost/legacy_cost},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
