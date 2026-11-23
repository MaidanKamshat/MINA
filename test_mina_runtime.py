"""Offline integration/regression checks for MINA v1; NO external API calls."""
import unittest
import json

from mina_state import RequestedTask, Constraint, RequestState
from mina_coordinator import choose_route
from mina_planning import (
    NeedsClarification, build_context, allowed_sequences, validate_candidate,
    assess_plans, format_plan,
)
from mina_runtime import run_state, run_request


def make_state(deadline='14:30', opening='12:00', grocery_duration=90):
    q = 'Return library books, buy groceries and pick up my daughter by 2:30 PM.'
    state = RequestState(
        user_request=q,
        intent='planning',
        tasks=[
            RequestedTask('library', 'Return library books', 'Return library books'),
            RequestedTask('groceries', 'buy groceries', 'buy groceries'),
            RequestedTask('school_pickup', 'pick up my daughter', 'pick up my daughter'),
        ],
        constraints=[
            Constraint('opening_time', 'library', opening, 'library opens at noon'),
            Constraint('minimum_duration', 'groceries', str(grocery_duration), 'at least 90 minutes'),
            Constraint('deadline', 'school_pickup', deadline, 'by 2:30 PM'),
        ],
    )
    return choose_route(state)


class IntegrationTests(unittest.TestCase):
    def test_complex_route(self):
        self.assertEqual(make_state().route, 'complex')

    def test_real_constraint_overrides_baseline_fixture(self):
        ctx = build_context(make_state())
        self.assertEqual(ctx.library_open, '12:00')
        self.assertEqual(ctx.durations['groceries'], 90)
        self.assertEqual(ctx.deadlines['school_pickup'], '14:30')
        self.assertIn('SYNTHETIC', ctx.provenance)

    def test_late_library_first_rejected(self):
        state = make_state()
        result = validate_candidate(('library', 'groceries', 'school_pickup'), state, build_context(state))
        self.assertFalse(result['feasible'])
        self.assertIn('Deadline', result['reason'])

    def test_groceries_first_feasible(self):
        state = make_state()
        result = validate_candidate(('groceries', 'library', 'school_pickup'), state, build_context(state))
        self.assertTrue(result['feasible'])
        self.assertEqual(result['timeline'][-1], ('school_pickup', '14:00'))

    def test_missing_or_unrequested_task_rejected(self):
        state = make_state()
        ctx = build_context(state)
        self.assertFalse(validate_candidate(('library', 'school_pickup'), state, ctx)['feasible'])
        self.assertFalse(validate_candidate(('groceries', 'library', 'school_pickup', 'library_holds'), state, ctx)['feasible'])

    def test_incomplete_travel_data_fails_closed(self):
        state = make_state()
        ctx = build_context(state)
        ctx.travel_minutes.pop(('groceries', 'library'))
        result = validate_candidate(('groceries', 'library', 'school_pickup'), state, ctx)
        self.assertFalse(result['feasible'])
        self.assertIn('Travel estimate unavailable', result['reason'])

    def test_impossible_deadline_rejected(self):
        state = make_state(deadline='11:00')
        ctx = build_context(state)
        checks, best = assess_plans(state, ctx, allowed_sequences(state))
        self.assertIsNone(best)
        self.assertTrue(all(not x['feasible'] for x in checks))

    def test_controller_picks_feasible_plan(self):
        state = make_state()
        ctx = build_context(state)
        checks, best = assess_plans(state, ctx, [('library', 'groceries', 'school_pickup')])
        self.assertEqual(best['sequence'], ['groceries', 'library', 'school_pickup'])
        self.assertEqual(len(checks), 2)
        self.assertEqual(checks[1]['generator'], 'bounded search')

    def test_output_only_authorized_tasks(self):
        state = make_state()
        ctx = build_context(state)
        _, best = assess_plans(state, ctx, allowed_sequences(state))
        text = format_plan(best, ctx)
        self.assertNotIn('library holds', text.lower())
        self.assertNotIn('Costco', text)
        self.assertIn('SYNTHETIC', text)

    def test_runtime_trace_full_pipeline(self):
        result = run_state(make_state(), planner_mode='deterministic', use_rag=False)
        self.assertEqual(result.status, 'synthetic_plan')
        self.assertEqual([x['step'] for x in result.trace],
                         ['coordinator', 'retrieval', 'context', 'planner', 'critic', 'controller'])
        self.assertTrue(any(not x['feasible'] for x in result.candidates))

    def test_runtime_no_feasible(self):
        result = run_state(make_state(deadline='11:00'), planner_mode='deterministic', use_rag=False)
        self.assertEqual(result.status, 'no_feasible_plan')
        self.assertNotIn('simulated arrival', result.answer)

    def test_write_requires_approval_no_external_action(self):
        state = RequestState('Add milk to my grocery list', 'list_update',
                             [RequestedTask('shopping_list_update', 'Add milk', 'Add milk')],
                             write_action_requested=True, route='simple')
        result = run_state(state, use_rag=False)
        self.assertEqual(result.status, 'approval_required')
        self.assertIn('have not changed', result.answer)

    def test_simple_bypasses_planner_and_critic(self):
        state = RequestState("What should I pack for school?", 'information', route='simple')
        result = run_state(state, planner_mode='deterministic', use_rag=False)
        self.assertEqual(result.status, 'simple_response')
        self.assertNotIn('planner', [x['step'] for x in result.trace])
        self.assertNotIn('critic', [x['step'] for x in result.trace])

    def test_unsupported_task_does_not_invent_schedule(self):
        state = RequestState('Plan groceries and my dentist appointment', 'planning',
                             [RequestedTask('groceries', 'buy groceries', 'groceries'),
                              RequestedTask('appointment', 'dentist', 'dentist appointment')],
                             route='complex')
        result = run_state(state, use_rag=False, planner_mode='deterministic')
        self.assertEqual(result.status, 'needs_clarification')

    def test_unknown_constraint_fails_closed(self):
        state = make_state()
        state.constraints.append(Constraint('other', 'groceries', 'special need', 'special need'))
        with self.assertRaises(NeedsClarification):
            build_context(state)

    def test_two_llm_calls_end_to_end_with_mock(self):
        query = ("Tomorrow I need to return library books, buy groceries, and pick up "
                 "my daughter before 2:30 PM. The library opens at noon, "
                 "and groceries take at least 90 minutes.")

        class FakeOutput:
            def __init__(self, data):
                self.output_text = json.dumps(data)

        class FakeClient:
            def __init__(self):
                self.responses = self
                self.calls = []

            def create(self, **kwargs):
                name = kwargs['text']['format']['name']
                self.calls.append(name)
                if name == 'mina_request_state':
                    return FakeOutput({
                        'intent': 'planning',
                        'tasks': [
                            {'task_id': 'library', 'description': 'return books', 'evidence': 'return library books'},
                            {'task_id': 'groceries', 'description': 'buy groceries', 'evidence': 'buy groceries'},
                            {'task_id': 'school_pickup', 'description': 'pickup daughter', 'evidence': 'pick up my daughter'},
                        ],
                        'constraints': [
                            {'kind': 'deadline', 'task_id': 'school_pickup', 'value': '14:30', 'evidence': 'before 2:30 PM'},
                            {'kind': 'opening_time', 'task_id': 'library', 'value': '12:00', 'evidence': 'library opens at noon'},
                            {'kind': 'minimum_duration', 'task_id': 'groceries', 'value': '90', 'evidence': 'at least 90 minutes'},
                        ],
                        'preferences': [], 'missing_information': [], 'write_action_requested': False,
                    })
                if name == 'mina_planning_candidates':
                    return FakeOutput({'candidates': [
                        ['library', 'groceries', 'school_pickup'],
                        ['groceries', 'library', 'school_pickup'],
                    ]})
                raise AssertionError(name)

        fake = FakeClient()
        result = run_request(query, client=fake, planner_mode='llm', use_rag=False)
        self.assertEqual(fake.calls, ['mina_request_state', 'mina_planning_candidates'])
        self.assertEqual(result.status, 'synthetic_plan')
        self.assertTrue(any(not item['feasible'] for item in result.candidates))
        self.assertIn('Buy groceries', result.answer)
        self.assertNotIn('Costco', result.answer)

    def test_two_task_planning_works(self):
        state = RequestState('Please plan my library return and groceries', 'planning', [
            RequestedTask('library', 'return', 'library return'),
            RequestedTask('groceries', 'buy', 'groceries'),
        ], route='complex')
        result = run_state(state, use_rag=False, planner_mode='deterministic')
        self.assertEqual(result.status, 'synthetic_plan')
        self.assertEqual(len(result.candidates), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
