"""Protocol invariants only; invented fixtures are not benchmark exemplars."""
import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy
from grounding.contracts import VerificationError

spec = importlib.util.spec_from_file_location('coverage_protocol',Path(__file__).with_name('protocol.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

def fixture(answer='A has −3.5 V. Please wait. B is blue.'):
    units=p.source_units(answer)
    return answer, {'claims':[{'claim_id':'c1','claim_text':'A has −3.5 V.'},
                              {'claim_id':'c2','claim_text':'B is blue.'}],
                    'coverage':[{'unit_id':u['unit_id'],
                                 'claim_ids':[] if i==1 else ['c1' if i==0 else 'c2'],
                                 'nf_reason':'Instruction.' if i==1 else None} for i,u in enumerate(units)]}

class ProtocolTests(unittest.TestCase):
    def test_units_are_lossless_occurrence_addresses(self):
        for answer in ['同句。\n同句。', '−3.5 / 35; 5\u0301 🚦。\r\n"No." Next.', 'One long unit without terminal marks']:
            units=p.source_units(answer)
            self.assertEqual(''.join(u['text'] for u in units),answer)
            self.assertEqual(len({u['unit_id'] for u in units}),len(units))
            for u in units:self.assertEqual(answer[u['source_start']:u['source_end']],u['text'])
        self.assertNotEqual(p.source_units('Same. Same.')[0]['unit_id'],p.source_units('Same. Same.')[1]['unit_id'])

    def test_payload_and_semantics_shared(self):
        answer,_=fixture()
        self.assertEqual(p.payload('ledger_id',answer),p.payload('ledger_text',answer))
        self.assertTrue(p.prompts()['ledger_id'].startswith(p.SEMANTICS+p.LEDGER_COMMON))
        self.assertTrue(p.prompts()['ledger_text'].startswith(p.SEMANTICS+p.LEDGER_COMMON))
        self.assertIn('claim_text may add only a shared antecedent',p.SEMANTICS)
        self.assertIn('Preserve entities, quantifiers, conditions, uncertainty',p.SEMANTICS)
        self.assertIn(p.SEMANTICS.split('Keep original order.')[1].split('claim_text may add')[0],p.DECOMPOSE_PROMPT)

    def test_text_echo_strict_without_digit_sign_folding(self):
        answer,raw=fixture()
        for row,u in zip(raw['coverage'],p.source_units(answer)):row['source_text']=u['text']
        self.assertEqual(len(p.validate('ledger_text',raw,answer)['claims']),2)
        for changed in ['A has 3.5 V. ','A has −35 V. ','A has -3.5 V. ']:
            bad=deepcopy(raw);bad['coverage'][0]['source_text']=changed
            with self.assertRaises(VerificationError):p.validate('ledger_text',bad,answer)

    def test_no_missing_duplicate_reordered_or_foreign_unit(self):
        answer,raw=fixture()
        variants=[]
        missing=deepcopy(raw);missing['coverage'].pop();variants.append(missing)
        duplicate=deepcopy(raw);duplicate['coverage'][1]['unit_id']='u0001';variants.append(duplicate)
        reverse=deepcopy(raw);reverse['coverage'].reverse();variants.append(reverse)
        foreign=deepcopy(raw);foreign['coverage'][0]['unit_id']='other';variants.append(foreign)
        for bad in variants:
            with self.assertRaises(VerificationError):p.validate('ledger_id',bad,answer)

    def test_mixed_not_silently_full_unit_excluded(self):
        answer='A is red, so please wait.'
        raw={'claims':[{'claim_id':'c1','claim_text':'A is red.'}],
             'coverage':[{'unit_id':'u0001','claim_ids':['c1'],'nf_reason':'Please wait is an instruction.'}]}
        result=p.validate('ledger_id',raw,answer)
        self.assertEqual(result['non_factual_spans'],[])
        self.assertEqual(len(result['protocol_diagnostics']['mixed_units']),1)

    def test_ledger_does_not_prove_semantic_completeness(self):
        answer='A is red and B is blue.'
        raw={'claims':[{'claim_id':'c1','claim_text':'A is red.'}],
             'coverage':[{'unit_id':'u0001','claim_ids':['c1'],'nf_reason':None}]}
        result=p.validate('ledger_id',raw,answer)
        self.assertFalse(result['protocol_diagnostics']['semantic_coverage_proven'])
        self.assertEqual(len(result['claims']),1)  # The missing fact must fail semantic review, not be invented by code.

    def test_noncontiguous_provenance_does_not_fill_intervening_unit(self):
        answer,raw=fixture()
        raw['claims']=raw['claims'][:1]
        raw['coverage'][2]['claim_ids']=['c1']
        result=p.validate('ledger_id',raw,answer)
        self.assertEqual([u['unit_id'] for u in result['claims'][0]['source_units']],['u0001','u0003'])
        self.assertNotIn('source_span',result['claims'][0])
        self.assertEqual(result['non_factual_spans'][0]['text'],'Please wait. ')

    def test_invalid_refs_or_kind_not_repaired(self):
        answer,raw=fixture()
        for field,value in [('claim_ids',['missing']),('claim_ids',[]),('nf_reason',''),('kind','unknown')]:
            bad=deepcopy(raw);bad['coverage'][0][field]=value
            with self.assertRaises(VerificationError):p.validate('ledger_id',bad,answer)
        extra=deepcopy(raw);extra['claims'].append({'claim_id':'c3','claim_text':'Unsupported extra.'})
        with self.assertRaises(VerificationError):p.validate('ledger_id',extra,answer)

    def test_stable_source_order_only_no_claim_merging(self):
        answer,raw=fixture()
        raw['claims'].reverse()
        result=p.validate('ledger_id',raw,answer)
        self.assertEqual([c['claim_id'] for c in result['claims']],['c1','c2'])
        self.assertEqual([c['claim_text'] for c in result['claims']],['A has −3.5 V.','B is blue.'])

if __name__=='__main__':unittest.main()
