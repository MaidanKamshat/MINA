"""Deterministic write-safety regression tests; no OpenAI calls or private data."""
import json
import unittest
from mina_coordinator import extract_request, parse_structured_response
from mina_runtime import run_state
from mina_state import RequestState, RequestedTask
from mina_write_guard import detect_explicit_write
from eval_mina import read_dataset, run_case
from pathlib import Path


class BombClient:
    """Fails if an obvious write request unnecessarily asks an LLM."""
    responses = None
    def __init__(self):
        self.responses = self
    def create(self, **_kwargs):
        raise AssertionError("Write safety should not require an LLM call")


def false_llm_payload(request):
    return json.dumps({
        'intent': 'information',
        'tasks': [{'task_id':'school_preparation', 'description':'School event', 'evidence':'school event'}],
        'constraints': [], 'preferences': [], 'missing_information': [],
        'write_action_requested': False,
    })


class WriteGuardTests(unittest.TestCase):
    def test_w03_direct_write_bypasses_wrong_llm_label(self):
        q = 'Add a school event to my calendar.'
        state = extract_request(q, client=BombClient())
        self.assertEqual((state.intent, [t.task_id for t in state.tasks],
                          state.write_action_requested, state.route),
                         ('calendar_update', ['calendar_update'], True, 'simple'))
        result = run_state(state, use_rag=False)
        self.assertEqual(result.status, 'approval_required')
        self.assertEqual([e['step'] for e in result.trace], ['coordinator','safety'])
        self.assertIn('not changed', result.answer)

    def test_model_parse_is_normalized_for_write(self):
        q = 'Add a school event to my calendar.'
        state = parse_structured_response(q, false_llm_payload(q))
        self.assertEqual(state.intent, 'calendar_update')
        self.assertEqual([t.task_id for t in state.tasks], ['calendar_update'])
        self.assertTrue(state.write_action_requested)

    def test_runtime_defense_in_depth_even_without_flag(self):
        q = 'Add a school event to my calendar.'
        state = RequestState(q, 'information', [RequestedTask('other',q,q)],
                             write_action_requested=False,route='simple')
        self.assertEqual(run_state(state,use_rag=False).status,'approval_required')

    def test_4_labeled_write_commands(self):
        cases = [
            ('Add milk to my grocery list.', 'list_update', 'shopping_list_update'),
            ('Delete eggs from my grocery list.', 'list_update', 'shopping_list_update'),
            ('Add a school event to my calendar.', 'calendar_update', 'calendar_update'),
            ('Send an email to the teacher.', 'message_draft', 'email_draft'),
        ]
        for q, intent, task_id in cases:
            with self.subTest(q=q):
                action = detect_explicit_write(q)
                self.assertEqual((action.intent, action.task_id), (intent, task_id))
                state = extract_request(q, client=BombClient())
                self.assertEqual(run_state(state,use_rag=False).status,'approval_required')

    def test_w03_full_evaluation_invariant(self):
        cases, _ = read_dataset(Path(__file__).parent / 'evaluation' / 'scenarios.json')
        case = next(c for c in cases if c['id'] == 'W03')
        row = run_case(case,'live','llm',False,client=BombClient())
        self.assertTrue(row['pass'], row['errors'])
        self.assertEqual(row['actual_status'],'approval_required')
        self.assertEqual(row['llm_calls'],0)

    def test_questions_negations_and_drafts_are_not_writes(self):
        queries = [
            'What is on my calendar?',
            'How do I add a school event to my calendar?',
            'Do not add a school event to my calendar.',
            "Don't add milk to my grocery list.",
            'Remind me to add an event to my calendar.',
            'Draft an email to the teacher.',
            'What should I prepare for school tomorrow?',
            'Can you explain how to add a calendar event?',
            'I already added a school event to my calendar.',
        ]
        for q in queries:
            with self.subTest(q=q):
                self.assertIsNone(detect_explicit_write(q))

    def test_polite_imperatives(self):
        for q in ('Please add a school event to my calendar.',
                  'Can you add a school event to my calendar?',
                  'Could you send an email to the teacher?'):
            with self.subTest(q=q):
                self.assertIsNotNone(detect_explicit_write(q))

    def test_explicit_multiple_domains_fail_closed(self):
        q = 'Add milk to my grocery list and a school event to my calendar.'
        action = detect_explicit_write(q)
        self.assertEqual((action.intent, action.task_id), ('other', 'other'))
        state = extract_request(q,client=BombClient())
        self.assertTrue(state.write_action_requested)
        self.assertEqual(run_state(state,use_rag=False).status,'approval_required')


if __name__ == '__main__':
    unittest.main()
