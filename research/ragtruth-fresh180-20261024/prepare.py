"""Freeze first, then reuse the unchanged six-response source sampler."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from grounding.config import load_settings
from grounding.config_v4 import load_v4_config
from scripts.benchmark_ragtruth import public_settings, _data, _selection, reserve_exposure, DATA_FILES
from scripts.ragtruth_v4 import code_hashes, _exposure_snapshot, prepare_dataset, PRE_SCHEMA
from scripts.ragtruth_data import canonical_input_bytes, input_sha256

BACKENDS = ['baseline', 'minimal', 'optimized-v4.0']
SEED = 'ragtruth-fresh180-v2-20261024'
PRICES = {'currency':'USD', 'input_per_million':.30,'cached_input_per_million':.006,'output_per_million':1.20}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def now(): return datetime.now(timezone.utc).isoformat()
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2); f.write('\n')
    path.with_suffix('.sha256').write_text(sha(path)+'\n',encoding='ascii')

def context_sha(contexts): return hashlib.sha256(canonical_input_bytes(contexts)).hexdigest()

def freeze(out, audit_path, raw_dir, env_file):
    if out.exists(): raise FileExistsError('Freeze destination must be new')
    audit = read(audit_path)
    if audit.get('unresolved_exposures'): raise ValueError('Resolve listed exposure mappings before certifying a fresh slice')
    excluded = audit['excluded_source_ids']
    if not excluded or len(excluded)!=len(set(excluded)): raise ValueError('Unique known exclusions required')
    for name, expected in audit.get('evidence_files_sha256',{}).items():
        if sha(name)!=expected: raise ValueError('Exposure evidence changed: '+name)
    old = read(ROOT/'dataset/ragtruth-blind-v1/recovery/preparation.json')
    raw_hashes={name:old['raw_files_sha256'][name] for name in ('source_info.jsonl','response.jsonl','provenance.json')}
    if any(sha(raw_dir/n)!=v for n,v in raw_hashes.items()): raise ValueError('Pinned upstream raw hash mismatch')
    ledgers=[ROOT/'results/ragtruth-ledger']
    prior, ledger_hashes = _exposure_snapshot(ledgers)
    if prior-set(excluded): raise ValueError('Exposure audit misses canonical ledger sources')
    settings=load_settings(env_file,thinking='enabled',max_output_tokens=16384)
    config=load_v4_config(ROOT/'configs/optimized-v4.0.json')
    base=code_hashes(ROOT)
    extra=[p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.md')]
    extra += [ROOT/'configs/optimized-v4.0.json',ROOT/'AGENTS.md']
    hashes={**base,**{p.relative_to(ROOT).as_posix():sha(p) for p in extra}}
    source=out/'source';source.mkdir(parents=True)
    for name,expected in hashes.items():
        raw=(ROOT/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Source changed during freeze')
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    sampling={'seed':SEED,'split':'test','sources_per_task':10,'quality':'good','responses_per_source':6,
              'tasks':['QA','Summary','Data2txt'],'ordering':'sha256(seed|task_type|source_id), then source_id',
              'excluded_source_ids':sorted(excluded),'gold_used_for_selection':False,
              'incomplete_group_policy':'exclude sources without exactly six good responses before ranking',
              'deduplication':'Exposure audit excludes exact context aliases and duplicate canonical request groups before hash ranking.'}
    sampler={'schema_version':PRE_SCHEMA,'created_at':now(),'code_files_sha256':base,'python_version':platform.python_version(),
             'settings':public_settings(settings),'v4_config':config.public_dict(),'backends':BACKENDS,
             'sampling':sampling,'exposure_ledger_files_sha256':ledger_hashes,'exposure_ledger_dirs':[str(p.resolve()) for p in ledgers],
             'upstream_raw_sha256':raw_hashes,'run_options':{'workers':4,'seed':20261024},'price_reference':PRICES}
    write(out/'sampling-preselection.json',sampler)
    pre={**sampler,'schema_version':'ragtruth-fresh180-preselection-v1','code_files_sha256':hashes,
         'source_root':str(source.resolve()),'project_root':str(ROOT.resolve()),'raw_dir':str(raw_dir.resolve()),
         'runner_sha256':sha(HERE/'run.py'),'git_commit_before_freeze':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
         'exposure_audit_path':str(audit_path.resolve()),'exposure_audit_sha256':sha(audit_path),
         'sampling_preselection_path':str((out/'sampling-preselection.json').resolve()),
         'sampling_preselection_sha256':sha(out/'sampling-preselection.json'),
         'qualification':'New source-disjoint native comparison; not completion of author-adjudicated acceptance',
         'selection_has_not_run':True}
    write(out/'preselection.json',pre)
    print(json.dumps({'status':'frozen_before_selection','files':len(hashes),'excluded_sources':len(excluded),'model':settings.model}))

def check(prepath):
    if sha(prepath)!=prepath.with_suffix('.sha256').read_text().strip():raise ValueError('Preselection self hash changed')
    pre=read(prepath); source=Path(pre['source_root'])
    if any(sha(source/n)!=v for n,v in pre['code_files_sha256'].items()):raise ValueError('Frozen snapshot changed')
    if sha(pre['sampling_preselection_path'])!=pre['sampling_preselection_sha256']:raise ValueError('Sampling freeze changed')
    if sha(pre['exposure_audit_path'])!=pre['exposure_audit_sha256']:raise ValueError('Exposure evidence changed')
    return pre

def prepare(prepath, data, run_output):
    pre=check(prepath)
    if ROOT.resolve()!=Path(pre['source_root']).resolve():raise ValueError('Run prepare from the frozen source copy')
    audit=read(pre['exposure_audit_path'])
    prep=prepare_dataset(Path(pre['raw_dir']),data,Path(pre['sampling_preselection_path']),project_root=ROOT)
    inputs,manifest,prep,hashes=_data(data)
    selection=_selection(inputs,manifest)
    ids={c['id'] for c in inputs};requests={input_sha256(c['input']) for c in inputs}
    groups={m['source_id'] for m in manifest}
    contexts={context_sha(c['input']['context_passages']) for c in inputs}
    if len(ids)!=180 or len(requests)!=180 or len(groups)!=30 or len(contexts)!=30:raise ValueError('Selected input/source content is not unique')
    if groups & set(pre['sampling']['excluded_source_ids']):raise ValueError('Exposed source selected')
    if contexts & set(audit.get('exposed_context_sha256',[])):raise ValueError('Previously exposed context alias selected')
    if requests & set(audit.get('used_request_sha256',[])):raise ValueError('Previously used request selected')
    if Counter(m['task_type'] for m in manifest)!={'QA':60,'Summary':60,'Data2txt':60}:raise ValueError('Task matrix changed')
    # Register all selected sources before any backend or manual semantic review.
    ledger_path,ledger=reserve_exposure(selection,run_output,ledger_dir=Path(pre['project_root'])/'results/ragtruth-ledger',
                                       replicate=False,smoke=False,freeze_sha256=sha(prepath),data_files_sha256=hashes)
    binding={'schema_version':'ragtruth-fresh180-binding-v1','created_at':now(),'preselection_sha256':sha(prepath),
             'preselection_freeze':str(prepath.resolve()),'data_files_sha256':hashes,'selection':selection,
             'sampling_preselection_sha256':pre['sampling_preselection_sha256'],'exposure_record':str(ledger_path),
             'exposure_record_initial_sha256':sha(ledger_path),'freshness_checks':{'unique_response_ids':180,'unique_requests':180,
             'unique_source_ids':30,'unique_adapted_contexts':30,'previous_source_overlap':0,'previous_request_overlap':0,'previous_context_overlap':0}}
    write(prepath.parent/'binding.json',binding)
    shutil.copyfile(Path(pre['raw_dir'])/'LICENSE',data/'UPSTREAM_LICENSE')
    (data/'README.md').write_text('# Fresh RAGTruth 180\n\n30 source groups × 6 original answers, QA/Summary/Data2txt 60 each.\nInput and source IDs/content are disjoint from recorded exposure and exact aliases.\nNative labels are unchanged and separate from runtime inputs.\nThis is a frozen native comparison, not author-adjudicated acceptance.\nSee research/ragtruth-fresh180-20261024/PLAN.md and exposure-audit.json.\n',encoding='utf-8')
    print(json.dumps({'status':'selected_and_bound','responses':len(inputs),'source_groups':len(groups),'overlap':0,'native_labels_reported':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('freeze','prepare'))
    p.add_argument('--freeze-dir',type=Path,required=True);p.add_argument('--exposure-audit',type=Path)
    p.add_argument('--raw-dir',type=Path,default=ROOT/'tmp/ragtruth-upstream');p.add_argument('--env-file',type=Path,default=ROOT/'.env')
    p.add_argument('--data-dir',type=Path);p.add_argument('--run-output',type=Path)
    a=p.parse_args()
    if a.action=='freeze':freeze(a.freeze_dir.resolve(),a.exposure_audit.resolve(),a.raw_dir.resolve(),a.env_file.resolve())
    else:prepare(a.freeze_dir.resolve()/'preselection.json',a.data_dir.resolve(),a.run_output.resolve())
