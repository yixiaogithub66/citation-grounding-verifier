#!/usr/bin/env python3
"""Run exposed claim-gold regression or explicitly labelled supplementary drafts.

This tool never grants confirmation/unseen status and never overwrites a run.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.config_v4 import load_v4_config
from grounding.contracts import VerificationError, VerificationRequest, validate_report
from grounding.contracts_v4 import validate_v4_report
from grounding.factory import build_verifier
from grounding.scoring import fraction, usage_summary, cost_summary
from scripts.benchmark_ragtruth import _jsonl, _write_json, _sha, _now, _redact, public_settings
from scripts.ragtruth_v4 import code_hashes
from scripts.score_v4 import score_claim_case

def summarize(records):
    summaries={}
    for backend in sorted({r['backend'] for r in records}):
        rows=[r for r in records if r['backend']==backend]
        counts=Counter(r['score']['execution_status'] for r in rows)
        matched=sum(r['score']['alignment_diagnostic']['strict']['matched_claim_count'] for r in rows)
        correct=sum(r['score']['alignment_diagnostic']['strict']['correct_claim_count'] for r in rows)
        gold=sum(r['score']['alignment_diagnostic']['strict']['gold_claim_count'] for r in rows)
        predicted=sum(r['score']['completed_claim_count'] for r in rows)
        usage=usage_summary(rows)
        summaries[backend]={'count':len(rows),'status_counts':dict(counts),
                           'completed_aligned_verdict_accuracy':fraction(correct,matched),
                           'gold_alignment_coverage':fraction(matched,gold),
                           'completed_claim_count':predicted,'gold_claim_count':gold,
                           'strict_all_gold_f1_diagnostic':fraction(2*correct,gold+predicted),
                           'mean_latency_seconds':sum(r['latency_seconds'] for r in rows)/len(rows),
                           'usage':usage}
    return summaries

def run(dataset, output_dir, settings, config, *, backends=('optimized-v4.0',), split=None, workers=4, limit=None):
    cases=_jsonl(dataset)
    if split:
        cases=[c for c in cases if c.get('split')==split]
    if limit:
        cases=cases[:limit]
    if not cases or len({c['id'] for c in cases})!=len(cases):
        raise ValueError('Cases must have unique IDs and a nonempty selection')
    for case in cases:
        VerificationRequest.from_dict(case['input'])
        validate_report({'claims':[{k:v for k,v in c.items() if k in {'claim_text','verdict','reasoning','citations'}} for c in case['expected']['claims']]},case['input']['context_passages'])
    output_dir.mkdir(parents=True,exist_ok=False)
    hashes=code_hashes()
    for name,digest in hashes.items():
        target=output_dir/'source'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
        if _sha(target)!=digest:
            raise ValueError('Code changed during snapshot, no inference started')
    metadata={'kind':'exposed-claim-regression-not-unseen','created_at':_now(),'dataset':str(dataset.resolve()),
              'dataset_sha256':_sha(dataset),'selected_ids':[c['id'] for c in cases],
              'settings':public_settings(settings),'v4_config':config.public_dict(),'code_files_sha256':hashes,
              'backends':list(backends),'workers':workers,'supplementary_author_approval':
              'not asserted; see source dataset status'}
    _write_json(output_dir/'config.json',metadata,exclusive=True)
    def work(case,backend):
        started=time.monotonic()
        prediction,telemetry,error=None,{'calls':[]},None
        try:
            verifier=build_verifier(backend,settings,v4_config=config)
            result=verifier.verify(VerificationRequest.from_dict(case['input']))
            prediction,telemetry=result.report,result.telemetry
            validate_v4_report(prediction,case['input']['context_passages'])
        except VerificationError as exc:
            prediction=None
            telemetry=exc.telemetry
            error={'code':exc.code,'message':exc.message}
        except Exception as exc:
            prediction=None
            error={'code':'unexpected_error','message':type(exc).__name__}
        return _redact({'id':case['id'],'backend':backend,'prediction':prediction,'telemetry':telemetry,'error':error,
                        'latency_seconds':time.monotonic()-started,'score':score_claim_case(case,prediction,error)},settings.api_key)
    records=[]
    with (output_dir/'responses.jsonl').open('x',encoding='utf-8',newline='\n') as stream:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(work,case,b) for case in cases for b in backends]):
                record=future.result()
                records.append(record)
                # Preserve even malformed Unicode in untrusted model telemetry.
                stream.write(json.dumps(record,ensure_ascii=True)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
                _write_json(output_dir/'progress.json',{'completed':len(records),'expected':len(cases)*len(backends)})
                print(f"[{len(records)}/{len(cases)*len(backends)}] {record['id']} {record['score']['execution_status']}",flush=True)
    summary=summarize(records)
    report={'kind':metadata['kind'],'backends':summary,'config_sha256':_sha(output_dir/'config.json'),
            'responses_sha256':_sha(output_dir/'responses.jsonl'),
            'note':'Conditional label accuracy only uses completed text-aligned claims. Read with gold alignment coverage and unmatched predictions; not semantic accuracy of every paraphrase.'}
    _write_json(output_dir/'report.json',report,exclusive=True)
    lines=['# v4 claim regression','',report['note'],'',
           '| Backend | Complete / partial / error | Aligned label accuracy | Gold alignment coverage | All-gold strict F1 diagnostic | Mean seconds |',
           '| --- | --- | --- | --- | --- | --- |']
    def pct(f): return 'n/a' if f['value'] is None else f"{f['value']:.2%}"
    for name,s in summary.items():
        c=s['status_counts']
        lines.append(f"| {name} | {c.get('complete',0)} / {c.get('partial',0)} / {c.get('error',0)} | {pct(s['completed_aligned_verdict_accuracy'])} | {pct(s['gold_alignment_coverage'])} | {pct(s['strict_all_gold_f1_diagnostic'])} | {s['mean_latency_seconds']:.2f} |")
    (output_dir/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--v4-config',type=Path)
    p.add_argument('--backends',nargs='+',choices=('baseline','minimal','optimized-v2','optimized-v3','optimized-v4.0','optimized-v4-combined','optimized-v4-m1-faithful'),default=['optimized-v4.0'])
    p.add_argument('--split')
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    if not 1<=args.workers<=16 or args.limit is not None and args.limit<1: p.error('Invalid workers/limit')
    settings=load_settings(thinking='enabled')
    if any(b!='baseline' for b in args.backends) and not settings.api_key: p.error('LLM_API_KEY is required')
    run(args.dataset,args.output_dir,settings,load_v4_config(args.v4_config),backends=tuple(args.backends),split=args.split,workers=args.workers,limit=args.limit)

if __name__=='__main__': main()
