"""No-network tests of the evaluation runner and its metric definitions."""
import unittest
import json
from types import SimpleNamespace

from eval_mina import read_dataset, run_case, aggregate, canonical_constraints, DEFAULT_DATASET


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases,cls.digest=read_dataset(DEFAULT_DATASET)

    def test_scenario_count_and_uniqueness(self):
        self.assertEqual(len(self.cases),20)
        self.assertEqual(len({x['id'] for x in self.cases}),20)

    def test_all_20_offline_end_to_end_states(self):
        rows=[run_case(case,'offline','deterministic',False) for case in self.cases]
        failed=[(r['case_id'],r['errors']) for r in rows if not r['pass']]
        self.assertEqual(failed, [])

    def test_metric_denominators(self):
        rows=[run_case(case,'offline','deterministic',False) for case in self.cases]
        s=aggregate(rows,self.digest,mode='offline',planner='deterministic',rag=False)
        self.assertEqual(s['cases'],20)
        self.assertEqual(s['total_llm_calls'],0)
        self.assertEqual(s['write_cases'],4)
        self.assertEqual(s['write_blocked'],4)
        self.assertEqual(s['manual_review_required'],4)

    def test_mocked_live_pipeline_smoke_no_api(self):
        # Tests plumbing only. Fake LLM answers are supplied from ground truth;
        # this must never be reported as actual LLM accuracy.
        chosen = next(c for c in self.cases if c['id'] == 'P01')
        class FakeClient:
            def __init__(self):
                self.responses=self
                self.calls=[]
            def create(self,**kwargs):
                self.calls.append(kwargs)
                name=kwargs['text']['format']['name']
                if name=='mina_request_state':
                    return SimpleNamespace(output_text=json.dumps(chosen['ground_truth']),usage=None)
                if name=='mina_planning_candidates':
                    return SimpleNamespace(output_text=json.dumps({'candidates':[
                        ['library','groceries','school_pickup'],
                        ['groceries','library','school_pickup'],
                    ]}),usage=None)
                raise AssertionError(name)
        fake=FakeClient()
        row=run_case(chosen,'live','llm',False,fake)
        self.assertTrue(row['pass'],row['errors'])
        self.assertEqual(row['llm_calls'],2)
        self.assertEqual(row['actual_status'],'synthetic_plan')

    def test_failed_case_is_not_marked_success(self):
        case=dict(self.cases[0])
        case['expected']=dict(case['expected'])
        case['expected']['status']='no_feasible_plan'
        result=run_case(case,'offline','deterministic',False)
        self.assertFalse(result['pass'])
        self.assertTrue(result['errors'])


if __name__=='__main__':
    unittest.main()
