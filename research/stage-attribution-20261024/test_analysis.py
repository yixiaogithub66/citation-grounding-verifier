import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stage_analysis', Path(__file__).with_name('analyze.py'))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class AttributionScoringTests(unittest.TestCase):
    def test_common_contract_and_review_failure_are_not_hidden(self):
        original = analysis.HERE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); run = base/'run'; (run/'stage-results').mkdir(parents=True)
                (run/'call-results').mkdir(); analysis.HERE = base
                def save(path, value): path.write_text(json.dumps(value), encoding='utf-8')
                claim = {'id':'t1', 'claim_text':'The lamp is blue.'}
                row = {**claim, 'verdict':'SUPPORTED', 'reasoning':'Direct.', 'citations':[{'index':0,'quote':'The lamp is blue.'}]}
                case = {'id':'s', 'generated_answer':claim['claim_text'], 'context_passages':['The lamp is blue.'], 'claims':[claim]}
                save(base/'cases.json', [case]); save(base/'annotations.json', [{'id':'s','targets':[{**claim,'verdict':'SUPPORTED'}]}])
                initials = [{'key':a,'stage':'m3','case_id':'s','arm':a,'repetition':0} for a in ('simple','current')]
                review = {'key':'r','stage':'review','case_id':'s','arm':'current','repetition':0,'claim_id':'t1','initial_key':'current'}
                save(run/'planned-requests.json', {'initial':initials,'reviews':[review]})
                for t in initials:
                    # Current public contract passes even though its richer schema is missing.
                    value = {'label_rows':{'t1':row},'public_valid':{'t1':True},'rows':{'t1':row} if t['arm']=='simple' else {}, 'order_valid':True}
                    save(run/'stage-results'/(t['key']+'.json'), {**t,'validated_output':value})
                # A reviewed correct row becoming unavailable loses one usable decision.
                save(run/'stage-results/r.json', {**review,'before':row,'after':None,'triggered':True,'telemetry':{}})
                with contextlib.redirect_stdout(io.StringIO()): analysis.summarize(run)
                result = json.loads((base/'analysis.json').read_text())
                self.assertEqual(result['m3']['current']['public_valid_correct'], 1)
                self.assertEqual(result['m3']['current']['arm_schema_valid_correct'], 0)
                self.assertEqual(result['review']['transitions']['correct->incomplete'], 1)
                self.assertEqual(result['review']['net_usable_label_gain'], -1)
        finally:
            analysis.HERE = original

    def test_evidence_identity_does_not_depend_on_arm_or_token_cost(self):
        claim = {'id':'t1','claim_text':'An assertion'}
        left = {'verdict':'CONTRADICTED','citations':[{'index':0,'quote':'opposite'}], 'derivation':'step one'}
        right = {**left,'derivation':'step two','arm':'current'}
        self.assertEqual(analysis.evidence_identity(['source'],claim,left), analysis.evidence_identity(['source'],claim,right))


if __name__ == '__main__': unittest.main()
