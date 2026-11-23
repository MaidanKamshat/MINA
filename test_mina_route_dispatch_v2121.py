"""Regression for v2.12 bypass: first route must enter adapter, not old Coordinator directly."""
from pathlib import Path
from datetime import date
import ast
import unittest

from mina_trip_voice_v212 import classify_multi_stop_route, parse_trip_voice

PROMPT = (
    "Mina, help me plan a hypothetical afternoon on Monday, November 23. "
    "I want to leave home at 12:30 p.m., stop at the library for 20 minutes "
    "and Costco for 30 minutes, and arrive at school for pickup between 3:15 "
    "and 3:30 PM. Find the best order using road travel estimates and tell me "
    "if the plan is feasible. Don't create any calendar events or change my shopping lists."
)

class DispatchTests(unittest.TestCase):
    def test_original_voice_utterance_gets_route_priority(self):
        self.assertEqual(classify_multi_stop_route(PROMPT), 'route')

    def test_original_text_is_cleaned_before_coordinator(self):
        parsed = parse_trip_voice(PROMPT,today=date(2026,11,21))
        self.assertEqual(parsed.departure_time,'12:30 PM')
        self.assertNotIn('leave home at 12:30',parsed.prompt_for_planner)
        self.assertIn('school for pickup between 3:15 and 3:30 PM',parsed.prompt_for_planner)

    def test_accepted_planning_phrasings(self):
        for p in (
            'Mina plan a route from home to library and Costco',
            'Could you find the best order of Costco and the library?',
            'Can you make an itinerary for library, Costco and school pickup?',
            'Is it feasible to stop at library and Costco on my route?',
        ):
            with self.subTest(p=p): self.assertEqual(classify_multi_stop_route(p),'route')

    def test_negated_write_does_not_trigger_mixed(self):
        for p in (
            "Plan library and Costco, but don't create calendar events.",
            'Plan library and Costco. Do not change my shopping list.',
            'Plan library and Costco without sending emails.',
        ):
            with self.subTest(p=p):self.assertEqual(classify_multi_stop_route(p),'route')

    def test_mixed_positive_write_blocks_route(self):
        for p in (
            'Plan the library and Costco route and create an event in my calendar.',
            'Plan Costco and library and add eggs to my shopping list.',
            'Plan library and Costco and send an email to the teacher.',
            'Plan library and Costco and add eggs to Costco.',
        ):
            with self.subTest(p=p):self.assertEqual(classify_multi_stop_route(p),'mixed')

    def test_nonplanning_lists_and_calendar_not_hijacked(self):
        for p in (
            'Mina, add eggs to Costco shopping list.',
            'Remove toothpaste from Target shopping list.',
            'Schedule dentist for tomorrow at 10 a.m.',
            "What's in my calendar tomorrow?",
            "What's the best way to buy Costco items?",
            'Do not plan library and Costco.',
            "I don't want to plan library and Costco.",
        ):
            with self.subTest(p=p):self.assertEqual(classify_multi_stop_route(p),'none')

    def test_ambiguous_one_stop_not_hijacked(self):
        self.assertEqual(classify_multi_stop_route('Plan Costco shopping tomorrow'), 'none')

    def test_ast_compiles(self):
        ast.parse(Path(__file__).with_name('streamlit_app.py').read_text())

    def test_route_branch_precedes_calendar_and_generic_auto(self):
        s=Path(__file__).with_name('streamlit_app.py').read_text()
        self.assertLess(s.index("elif trip_route_kind == 'route'"),s.index("elif calendar_confirm:"))
        self.assertLess(s.index("elif trip_route_kind == 'route'"),s.index("elif auto_intent.kind == 'external_write':"))
        self.assertIn('trip_route_kind = classify_multi_stop_route(prompt)',s)
        self.assertIn("if mode == 'family_plan' and trip_route_kind == 'none'",s)

    def test_route_flow_has_diagnostic_trace_and_typed_start(self):
        s=Path(__file__).with_name('streamlit_app.py').read_text()
        branch=s.split("elif trip_route_kind == 'route'",1)[1].split('elif calendar_confirm:',1)[0]
        self.assertIn('build_route_inputs(prompt',branch)
        self.assertIn('depart_time=start_value',branch)
        self.assertIn('result = plan_family_route(',branch)
        self.assertIn('pickup_window=schedule_window',branch)
        self.assertIn("result.trace.insert(0, {'step':'route_voice_adapter'",branch)
        self.assertIn("'version':'2.12.1'",branch)
        for write in ('google_insert_event(', '_store_local_hub(', '_store_calendar('):
            self.assertNotIn(write,branch)

    def test_mixed_action_has_no_write(self):
        s=Path(__file__).with_name('streamlit_app.py').read_text()
        branch=s.split("if trip_route_kind == 'mixed':",1)[1].split("elif trip_route_kind == 'route'",1)[0]
        self.assertIn('mixed_read_write_blocked',branch)
        self.assertNotIn('execute_ui_request(',branch)
        self.assertNotIn('_store_local_hub(',branch)

if __name__=='__main__':unittest.main()
