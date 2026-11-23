"""Offline Experiment 8 tests: no API requests or charges."""
from tot_llm_generator import assess_llm_candidates, generate_llm_candidates

class FakeResponse:
    output_text = '{"candidates":[["library","groceries","school_pickup"],["groceries","library","school_pickup"],["school_pickup","library","groceries"]]}'

class FakeResponses:
    def create(self, **kwargs):
        assert kwargs['text']['format']['type'] == 'json_schema'
        return FakeResponse()

class FakeClient:
    responses = FakeResponses()

candidates = generate_llm_candidates('test request', FakeClient())
assert len(candidates) == 3
checked, best = assess_llm_candidates(candidates)
assert len(checked) == 3 and best is not None
assert all(result['feasible'] for _, result in checked)
print('PASS: mocked LLM response -> 3 candidates -> Critic -> Controller')

checked, best = assess_llm_candidates([
    ('library', 'groceries'),
    ('library', 'library_holds', 'groceries', 'school_pickup'),
    ('school_pickup', 'library', 'groceries'),
])
assert not checked[0][1]['feasible'] and not checked[1][1]['feasible']
assert best is not None and best[0] == ('school_pickup', 'library', 'groceries')
print('PASS: invalid generated candidates rejected, feasible candidate selected')

checked, best = assess_llm_candidates([
    ('library',), ('groceries',), ('school_pickup',)
])
assert best is None
print('PASS: all-invalid candidate set -> no feasible plan')
print('3/3 offline checks passed; live LLM behavior NOT tested.')
