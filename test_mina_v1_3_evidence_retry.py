"""Offline tests for bounded evidence retry: no API usage."""
import json
import unittest
from mina_coordinator import extract_request, UnanchoredEvidenceError

QUERY = ('Tomorrow I need to return library books, buy groceries, and pick up '
         'my daughter from school before 2:30 PM. The library opens at noon, '
         'and grocery shopping takes at least 120 minutes.')


def response(evidence):
    return json.dumps({
        'intent':'planning',
        'tasks':[
            {'task_id':'library','description':'return library books','evidence':evidence},
            {'task_id':'groceries','description':'buy groceries','evidence':'buy groceries'},
            {'task_id':'school_pickup','description':'pick up daughter','evidence':'pick up my daughter from school'},
        ],
        'constraints':[
            {'kind':'deadline','task_id':'school_pickup','value':'14:30','evidence':'before 2:30 PM'},
            {'kind':'opening_time','task_id':'library','value':'12:00','evidence':'library opens at noon'},
            {'kind':'minimum_duration','task_id':'groceries','value':'120','evidence':'at least 120 minutes'},
        ],
        'preferences':[], 'missing_information':[], 'write_action_requested':False,
    })


class FakeClient:
    def __init__(self, outputs):
        self.outputs=list(outputs)
        self.calls=[]
        self.responses=self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        class R: pass
        r=R()
        r.output_text=self.outputs[len(self.calls)-1]
        return r


class EvidenceRetryTests(unittest.TestCase):
    def test_valid_evidence_no_retry(self):
        client=FakeClient([response('return library books')])
        state=extract_request(QUERY,client=client)
        self.assertEqual(state.route,'complex')
        self.assertEqual(len(client.calls),1)

    def test_unanchored_quote_gets_exactly_one_retry(self):
        client=FakeClient([response('return borrowed library books'), response('return library books')])
        state=extract_request(QUERY,client=client)
        self.assertEqual(len(state.tasks),3)
        self.assertEqual(len(client.calls),2)
        self.assertIn('RETRY AFTER EVIDENCE VALIDATION FAILURE',client.calls[1]['instructions'])

    def test_second_invalid_evidence_fails_closed(self):
        client=FakeClient([response('return borrowed library books'),response('return borrowed library books')])
        with self.assertRaises(UnanchoredEvidenceError):
            extract_request(QUERY,client=client)
        self.assertEqual(len(client.calls),2)

    def test_does_not_retry_unrelated_bad_json(self):
        client=FakeClient(['not JSON','not used'])
        with self.assertRaises(json.JSONDecodeError):
            extract_request(QUERY,client=client)
        self.assertEqual(len(client.calls),1)


if __name__=='__main__':
    unittest.main()
