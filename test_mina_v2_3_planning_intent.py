"""Regression tests for plan-versus-write distinction in MINA v2.3.

Offline-only; no live APIs, credentials, user addresses, or LLM calls.
"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mina_coordinator import extract_request, parse_structured_response
from mina_runtime import run_state, run_request
from mina_live_planning import LivePlanInputs
from mina_write_guard import detect_explicit_write

PROMPT = (
    "Mina, I need to return library books, buy groceries, and pick up my child "
    "from school before 4:30 PM. The library opens at noon, and grocery "
    "shopping takes at least 60 minutes. Please find the best order for these errands."
)


def payload(request=PROMPT, *, hallucinated_write=True, task_labels=None):
    tasks = [
        ("library", "return library books"),
        ("shopping_list_update" if hallucinated_write else "groceries", "buy groceries"),
        ("calendar_update" if hallucinated_write else "school_pickup", "pick up my child from school"),
    ] if task_labels is None else task_labels
    return json.dumps({
        "intent": "calendar_update" if hallucinated_write else "planning",
        "tasks": [{"task_id": ident, "description": evidence, "evidence": evidence}
                  for ident, evidence in tasks],
        "constraints": [
            {"kind": "deadline", "task_id": "school_pickup", "value": "16:30",
             "evidence": "before 4:30 PM"},
            {"kind": "opening_time", "task_id": "library", "value": "12:00",
             "evidence": "library opens at noon"},
            {"kind": "minimum_duration", "task_id": "groceries", "value": "60",
             "evidence": "grocery shopping takes at least 60 minutes"},
        ],
        "preferences": [], "missing_information": [],
        "write_action_requested": hallucinated_write,
    })


class FakeMessage:
    def __init__(self, output_text):
        self.output_text = output_text


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.responses = self
    def create(self, **kwargs):
        return FakeMessage(self.response)


class PlanningVersusWriteTests(unittest.TestCase):
    def test_main_prompt_not_deterministically_a_write(self):
        self.assertIsNone(detect_explicit_write(PROMPT))

    def test_spurious_model_write_flags_repaired_from_user_words(self):
        state = parse_structured_response(PROMPT, payload())
        self.assertEqual(state.intent, 'planning')
        self.assertFalse(state.write_action_requested)
        self.assertEqual(state.route, 'complex')
        self.assertEqual({t.task_id for t in state.tasks}, {'library', 'groceries', 'school_pickup'})
        self.assertTrue(all(t.evidence.lower() in PROMPT.lower() for t in state.tasks))
        self.assertEqual(len(state.constraints), 3)

    def test_spurious_label_repaired_via_full_coordinator(self):
        state = extract_request(PROMPT, client=FakeClient(payload()))
        self.assertEqual(state.route, 'complex')
        self.assertFalse(state.write_action_requested)

    def test_result_does_not_take_safety_write_path(self):
        state = parse_structured_response(PROMPT, payload())
        result = run_state(state, planner_mode='deterministic', use_rag=False)
        self.assertNotEqual(result.status, 'approval_required')
        self.assertFalse(any(t.get('step') == 'safety' for t in result.trace))

    def test_main_voice_prompt_reaches_live_plan_instead_of_safety(self):
        settings = LivePlanInputs(
            origin='-78.85030,35.73260',
            task_locations={
                'library': '-78.80320,35.77210',
                'groceries': '-78.78080,35.79150',
                'school_pickup': '-78.83010,35.75220',
            },
            start_time='10:00 AM',
            durations={'library': 15, 'groceries': 60, 'school_pickup': 10},
            travel_buffer_minutes=10,
        )
        fake_outcome = SimpleNamespace(
            status='provisional_live_route_plan', answer='PROVISIONAL DEMO PLAN',
            trace=[{'step': 'controller', 'decision': 'selected'}],
            candidates=[], map_report=None,
        )
        with patch('mina_live_planning.plan_with_live_routes', return_value=fake_outcome) as planning:
            result = run_request(
                PROMPT, client=FakeClient(payload()), use_rag=False,
                planner_mode='deterministic', live_tools=True, live_plan=settings,
            )
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertEqual(result.route, 'complex')
        self.assertEqual(result.trace[-1]['step'], 'controller')
        planning.assert_called_once()

    def test_normal_read_only_plan_unaffected(self):
        state = parse_structured_response(PROMPT, payload(hallucinated_write=False))
        self.assertEqual((state.intent, state.route, state.write_action_requested),
                         ('planning', 'complex', False))

    def test_direct_calendar_write_is_still_blocked(self):
        q = 'Add a school event to my calendar.'
        self.assertIsNotNone(detect_explicit_write(q))
        self.assertEqual(extract_request(q).write_action_requested, True)

    def test_grocery_list_mutation_is_still_blocked(self):
        self.assertIsNotNone(detect_explicit_write('Add milk to my grocery list.'))

    def test_compound_calendar_mutation_is_detected(self):
        q = 'Plan my library and grocery trip and add a school event to my calendar.'
        self.assertEqual(detect_explicit_write(q).intent, 'calendar_update')
        state = parse_structured_response(q, json.dumps({
            "intent": "planning", "tasks": [], "constraints": [],
            "preferences": [], "missing_information": [], "write_action_requested": False,
        }))
        self.assertTrue(state.write_action_requested)
        self.assertEqual(run_state(state, planner_mode='deterministic', use_rag=False).status,
                         'approval_required')

    def test_compound_email_send_detected(self):
        q = 'Plan errands and then send an email to the teacher.'
        self.assertEqual(detect_explicit_write(q).intent, 'message_draft')

    def test_compound_grocery_list_write_detected(self):
        q = 'Plan my library visit and add eggs to my grocery list.'
        self.assertEqual(detect_explicit_write(q).intent, 'list_update')

    def test_not_a_false_read_only_exception_if_calendar_is_mentioned(self):
        q = 'Plan my groceries and return library books, then add a reminder to the calendar.'
        self.assertIsNotNone(detect_explicit_write(q))

    def test_no_override_without_explicit_planning_cue(self):
        q = 'Buy groceries and return library books.'
        state = parse_structured_response(q, json.dumps({
            "intent": "list_update",
            "tasks": [{"task_id": "shopping_list_update", "description": "groceries", "evidence": "groceries"}],
            "constraints": [], "preferences": [], "missing_information": [],
            "write_action_requested": True,
        }))
        self.assertTrue(state.write_action_requested)  # fail closed if ambiguous


if __name__ == '__main__':
    unittest.main()
