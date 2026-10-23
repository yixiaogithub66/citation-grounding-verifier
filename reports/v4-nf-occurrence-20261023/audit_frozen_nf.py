import ast, collections, hashlib, json, unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
FROZEN=ROOT/'results/v4-m1-faithful-20261023'

def readjl(p):
 return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
class VerificationError(Exception):
 def __init__(self,code,message,*args):
  self.code=code;self.message=message;super().__init__(message)
# Execute only four read-only pure functions from the immutable source snapshot.
source=FROZEN/'dev/source/grounding/verifiers_v4.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
names={'_invalid','_text','_meaningful','extract_claims'}
module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
namespace={'Any':object,'VerificationError':VerificationError,'unicodedata':unicodedata}
exec(compile(module,str(source),'exec'),namespace)
extract=namespace['extract_claims']; meaningful=namespace['_meaningful']
# Proposed policy supplied by root: one occurrence per row, same-text cursor plus
# globally nondecreasing NF starts. This is isolated offline code.
new_source=source.read_text(encoding='utf-8')
new_source=new_source.replace('    exclusions: list[dict] = []\n    for row in excluded:', '    exclusions: list[dict] = []\n    nf_prior_start = 0\n    nf_last_start: dict[str, int] = {}\n    for row in excluded:',1)
old_block="""        start = answer.find(row["text"])
        if start < 0:
            _invalid("A non-factual span is not an exact answer substring.")
        while start >= 0:
            end = start + len(row["text"])
            covered.update(range(start, end))
            exclusions.append({**row, "source_start": start, "source_end": end})
            start = answer.find(row["text"], start + 1)"""
new_block="""        start = answer.find(row["text"], max(nf_prior_start, nf_last_start.get(row["text"], -1) + 1))
        if start < 0:
            _invalid("Each non-factual row needs a separate exact answer occurrence in answer order.")
        end = start + len(row["text"])
        covered.update(range(start, end))
        exclusions.append({**row, "source_start": start, "source_end": end})
        nf_prior_start = nf_last_start[row["text"]] = start"""
assert old_block in new_source
new_tree=ast.parse(new_source.replace(old_block,new_block,1))
new_module=ast.Module(body=[n for n in new_tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
new_ns={'Any':object,'VerificationError':VerificationError,'unicodedata':unicodedata}
exec(compile(new_module,'offline-proposed-nf-policy','exec'),new_ns)
extract_proposed=new_ns['extract_claims']

def positions(text,needle):
 out=[]; start=text.find(needle)
 while start>=0:
  out.append(start);start=text.find(needle,start+1)
 return out

def candidate_details(payload,text):
 nf=payload.get('non_factual_spans',[])
 if not isinstance(nf,list): return []
 counts=collections.Counter(r.get('text') for r in nf if isinstance(r,dict) and isinstance(r.get('text'),str))
 return [{'row_index':i,'text':r['text'],'reason':r.get('reason'), 'occurrences':positions(text,r['text']), 'same_text_row_count':counts[r['text']]} for i,r in enumerate(nf) if isinstance(r,dict) and isinstance(r.get('text'),str) and r['text'] and (len(positions(text,r['text']))>1 or counts[r['text']]>1)]

def simulate_one_per_text(payload,text,claims):
 # Diagnostic policy only, not production behavior: each same-text row consumes
 # its next exact start position. No semantic inference or model retry is simulated.
 used=collections.Counter(); spans=[]; extras=[]
 for i,r in enumerate(payload['non_factual_spans']):
  ps=positions(text,r['text']); index=used[r['text']];used[r['text']]+=1
  if index>=len(ps):extras.append(i);continue
  start=ps[index];spans.append((start,start+len(r['text'])))
 covered={i for r in claims for i in range(r['source_start'],r['source_end'])}
 for start,end in spans: covered.update(range(start,end))
 missing=[i for i,ch in enumerate(text) if meaningful(ch) and i not in covered]
 return {'mapped_nf_spans':[list(x) for x in spans], 'excess_nf_row_indices':extras,'uncovered_meaningful_chars':len(missing),'uncovered_ranges':ranges(missing)}

def ranges(xs):
 out=[]
 for i in xs:
  if not out or i!=out[-1][1]:out.append([i,i+1])
  else:out[-1][1]+=1
 return out

input_files={
 'dev':ROOT/'dataset/ragtruth-blind-v1/recovery/inputs.jsonl',
 'behavior':FROZEN/'behavior/pairs.jsonl',
 'physics':ROOT/'dataset/cphos28/cases.jsonl'}
inputs={}
for suite,path in input_files.items():
 rows=readjl(path)
 inputs[suite]=({(r['id'],side):r[side]['input']['generated_answer'] for r in rows for side in ('base','variant')} if suite=='behavior' else {r['id']:r['input']['generated_answer'] for r in rows})
summary=collections.defaultdict(collections.Counter); candidates=[];accepted_payloads=[];exceptions=[];records=[]
response_files={s:FROZEN/s/('predictions.jsonl' if s=='dev' else 'responses.jsonl') for s in inputs}
for suite,path in response_files.items():
 for row in readjl(path):
  backend=row['backend'];key=suite+'/'+backend;counts=summary[key];counts['records']+=1
  rid=row.get('id') or row.get('pair_id');side=row.get('side');mode=row.get('mode','end_to_end')
  text=inputs[suite][(rid,side) if suite=='behavior' else rid]
  telemetry=row.get('telemetry') or {}; extraction=telemetry.get('extraction') or {}
  chunks={c['chunk_id']:c for c in extraction.get('chunks',[])}
  per_chunk=collections.defaultdict(list)
  all_identical=True; policy_changes=[]
  for ci,call in enumerate(telemetry.get('calls',[])):
   if not call.get('stage','').startswith('decompose'):continue
   counts['decompose_calls']+=1
   chunk_id=call.get('chunk_id');chunk=chunks.get(chunk_id)
   if chunk is None:
    exceptions.append({'suite':suite,'id':rid,'backend':backend,'call_index':ci,'issue':'missing_chunk_metadata'});continue
   chunk_text=text[chunk['source_start']:chunk['source_end']]
   attempt={'suite':suite,'id':rid,'side':side,'mode':mode,'backend':backend,'chunk_id':chunk_id,'call_index':ci,'stage':call['stage'],'chunk_start':chunk['source_start'],'chunk_end':chunk['source_end'],'chunk_fallback':chunk['fallback'],'http_status':call.get('http_status'),'finish_reason':call.get('finish_reason')}
   try: payload=json.loads(call.get('response_text') or '')
   except (ValueError,TypeError):
    counts['unparseable_decompose_calls']+=1;continue
   if not isinstance(payload,dict):counts['non_object_payloads']+=1;continue
   nf=payload.get('non_factual_spans')
   if isinstance(nf,list): counts['nf_payloads_all_attempts']+=bool(nf);counts['nf_rows_all_attempts']+=len(nf)
   details=candidate_details(payload,chunk_text)
   attempt['nf_candidates']=details
   if isinstance(nf,list):
    texts=[r.get('text') for r in nf if isinstance(r,dict) and isinstance(r.get('text'),str)]
    counts['nf_payloads_duplicate_text_rows_all_attempts']+=len(texts)!=len(set(texts))
   try:
    claims,excluded=extract(payload,chunk_text,max_claims=64)
    valid=True
   except VerificationError as e:
    valid=False;attempt['frozen_validation_error']=e.message
   try:
    new_claims,new_excluded=extract_proposed(payload,chunk_text,max_claims=64)
    new_valid=True
    attempt['proposed_claims_identical']=valid and claims==new_claims
    attempt['proposed_exclusions_identical']=valid and excluded==new_excluded
    same=valid and claims==new_claims and excluded==new_excluded
   except VerificationError as e:
    new_valid=False;attempt['proposed_validation_error']=e.message
    same=not valid and attempt['frozen_validation_error']==e.message
   attempt['proposed_payload_valid']=new_valid
   attempt['proposed_identical_validation_result']=same
   if not same:
    all_identical=False
    policy_changes.append({'chunk_id':chunk_id,'call_index':ci,'stage':call['stage'],'old_valid':valid,'new_valid':new_valid,'claims_identical':attempt.get('proposed_claims_identical'),'exclusions_identical':attempt.get('proposed_exclusions_identical'),'old_error':attempt.get('frozen_validation_error'),'new_error':attempt.get('proposed_validation_error')})
   attempt['frozen_payload_valid']=valid
   attempt['transport_usable']=call.get('http_status')==200 and call.get('finish_reason')=='stop'
   if valid:
    attempt['frozen_claim_count']=len(claims);attempt['frozen_expanded_nf_count']=len(excluded)
    attempt['single_occurrence_diagnostic']=simulate_one_per_text(payload,chunk_text,claims)
   attempt['_payload']=payload
   per_chunk[chunk_id].append(attempt)
  record_candidates=0;accepted_trigger=0
  for chunk_id,attempts in per_chunk.items():
   chunk=chunks[chunk_id]
   eligible=[a for a in attempts if a['frozen_payload_valid'] and a['transport_usable']]
   accepted=eligible[-1] if eligible and not chunk['fallback'] else None
   if accepted:
    # The runner terminates at the first successfully validated response.
    # Multiple valid non-transport-failing responses would require manual audit.
    if len(eligible)!=1:exceptions.append({'suite':suite,'id':rid,'backend':backend,'chunk_id':chunk_id,'issue':'multiple_valid_candidates'})
    counts['accepted_payloads']+=1
    counts['accepted_nf_rows_before_expansion']+=len(accepted['_payload']['non_factual_spans'])
    counts['accepted_expanded_nf_rows']+=accepted['frozen_expanded_nf_count']
    if accepted['proposed_payload_valid']:
     counts['retained_accepted_old_nf_rows']+=accepted['frozen_expanded_nf_count']
     counts['retained_accepted_new_nf_rows']+=len(accepted['_payload']['non_factual_spans'])
    texts=[r['text'] for r in accepted['_payload']['non_factual_spans']]
    counts['accepted_payloads_duplicate_nf_text_rows']+=len(texts)!=len(set(texts))
    accepted['hard_split_recovery_present']=bool(extraction.get('hard_split_recoveries'))
    _,old_exclusions=extract(accepted['_payload'],text[chunk['source_start']:chunk['source_end']],max_claims=64)
    def nf_key(r):return (r['text'],r['reason'],r['source_start'],r['source_end'])
    actual=collections.Counter(nf_key(r) for r in extraction.get('non_factual_spans',[]))
    actual.update(nf_key(r) for recovery in extraction.get('hard_split_recoveries',[]) for r in recovery['superseded_non_factual_spans'])
    expected=collections.Counter((r['text'],r['reason'],r['source_start']+chunk['source_start'],r['source_end']+chunk['source_start']) for r in old_exclusions)
    if expected-actual:exceptions.append({'suite':suite,'id':rid,'backend':backend,'chunk_id':chunk_id,'issue':'accepted_nf_not_present_in_final_or_recovery_telemetry'})
    counts['accepted_new_invalid']+=not accepted['proposed_payload_valid']
    counts['accepted_same_claims_different_exclusions']+=accepted['proposed_payload_valid'] and not accepted['proposed_exclusions_identical']
    counts['accepted_identical']+=accepted['proposed_identical_validation_result']
    nf=accepted['_payload']['non_factual_spans'];counts['nf_payloads_accepted']+=bool(nf);counts['nf_rows_accepted']+=len(nf)
    accepted_payloads.append({k:v for k,v in accepted.items() if not k.startswith('_')})
   elif not chunk['fallback']:
    exceptions.append({'suite':suite,'id':rid,'backend':backend,'chunk_id':chunk_id,'issue':'no_accepted_payload_reconstruction'})
   for a in attempts:
    a['accepted_final_payload']=a is accepted
    if a['nf_candidates']:
     record_candidates+=1;counts['repeated_nf_payloads_all_attempts']+=1
     counts['candidate_nf_rows_all_attempts']+=len(a['nf_candidates'])
     if a is accepted:
      accepted_trigger+=1;counts['repeated_nf_payloads_accepted']+=1;counts['candidate_nf_rows_accepted']+=len(a['nf_candidates'])
      sim=a['single_occurrence_diagnostic'];counts['accepted_single_occurrence_missing_coverage']+=bool(sim['uncovered_meaningful_chars']);counts['accepted_single_occurrence_excess_rows']+=bool(sim['excess_nf_row_indices'])
     candidates.append({k:v for k,v in a.items() if not k.startswith('_')})
  counts['records_repeated_nf_any_attempt']+=bool(record_candidates);counts['records_repeated_nf_accepted']+=bool(accepted_trigger)
  counts['records_all_parsed_calls_identical']+=all_identical
  counts['records_changed_validation']+=not all_identical
  counts['fallback_chunks']+=sum(c.get('fallback',False) for c in chunks.values())
  records.append({'suite':suite,'id':rid,'side':side,'mode':mode,'backend':backend,'has_repeated_nf_any_attempt':bool(record_candidates),'has_repeated_nf_accepted':bool(accepted_trigger),'decomposition_chunk_count':len(chunks),'hard_split_recovery_count':len(extraction.get('hard_split_recoveries',[])),'all_parsed_calls_identical':all_identical,'policy_changes':policy_changes})
report={
 'schema':'nf-occurrence-offline-audit-v1','scope':'Frozen exposed M1-faithful experiment only. No model calls, runtime/scorer/gold edits, or unseen data.',
 'method':'Parse every decompose/repair response_text. Revalidate using four pure functions extracted from frozen source. Accepted payload requires non-fallback chunk, successful transport, and valid frozen extraction. Distinguish all attempts and accepted payloads.',
 'simulation_limitation':'Single-occurrence mapping is an offline diagnostic, not new production behavior. Coverage changes do not establish factual status or semantic improvement. Downstream judgments are not replayed after changed extraction.',
 'proposed_policy':'One exact occurrence per row. start=find(text,max(prior_NF_start,last_start_for_this_text+1)); separate from claim cursor; no dependence on coverage; missing occurrence invalid; overlap allowed through start+1.',
 'source_sha256':sha(source), 'inputs_sha256':{str(p.relative_to(ROOT)):sha(p) for p in input_files.values()},'responses_sha256':{str(p.relative_to(ROOT)):sha(p) for p in response_files.values()},
 'summary':dict(summary),'candidate_payloads':candidates,'exceptions':exceptions,'records':records,
 'accepted_payload_diagnostics':accepted_payloads}
(OUT/'nf-occurrence-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'summary':dict(summary),'candidate_count':len(candidates),'exceptions':exceptions},ensure_ascii=True,indent=2))
