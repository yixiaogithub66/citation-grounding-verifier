import copy
import json
from pathlib import Path
import tempfile
import unittest

from grounding.config import Settings
from grounding.contracts import VerificationError
from scripts.draft_v4_adjudication import run, validate_reviews

class DraftTests(unittest.TestCase):
    def test_ai_draft_does_not_approve_author_or_expose_prior_labels(self):
        item = {"review_id":"r1", "reported_claim":{"claim_text":"A is 3.","verdict":"UNSUPPORTED"},
                "backend":"minimal", "author_review":{"status":"pending_author","approved_at":None}, "ai_review":{"status":"pending_ai"}}
        case = {"id":"one","task_type":"Summary","input":{"context_passages":["A is 3."],"generated_answer":"A is 3."},
                "native_gold":{"labels":[]},"reported_claims_for_review":[item]}
        package={"schema_version":"ragtruth-v1-adjudication-v4.0","cases":[case]}
        captured=[]
        class Fake:
            def __init__(self,settings): pass
            def complete(self,messages,stage,telemetry):
                captured.append(json.loads(messages[1]["content"]))
                return {"reviews":[{"review_id":"r1","claim_text":"A is 3.","proposed_verdict":"SUPPORTED",
                     "reasoning":"Stated directly.","citations":[{"index":0,"quote":"A is 3."}],
                     "inference":"The source states the same value.","confidence":"high"}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pending=root/'pending.json'
            pending.write_text(json.dumps(package))
            result=run(pending,root/'draft',Settings(api_key='test'),client_factory=Fake,workers=1)
            reviewed=result['cases'][0]['reported_claims_for_review'][0]
            self.assertEqual(reviewed['author_review'],item['author_review'])
            self.assertEqual(reviewed['ai_review']['proposed_verdict'],'SUPPORTED')
            self.assertEqual(result['ai_draft_provenance']['author_approved'],0)
            self.assertEqual(set(captured[0]),{'context_passages','claims'})
            self.assertEqual(set(captured[0]['claims'][0]),{'review_id','claim_text'})
            self.assertEqual(json.loads(pending.read_text()),package)

    def test_bad_quote_and_missing_review_are_errors(self):
        items=[{'review_id':'r1','claim_text':'A'}]
        row={'review_id':'r1','claim_text':'A','proposed_verdict':'SUPPORTED','reasoning':'x',
             'inference':'x','confidence':'high','citations':[{'index':0,'quote':'invented'}]}
        for payload in ({'reviews':[row]},{'reviews':[]}):
            with self.assertRaises(VerificationError):
                validate_reviews(payload,items,['A'])

if __name__=='__main__': unittest.main()
