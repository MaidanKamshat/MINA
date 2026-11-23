"""MINA 2.12.5: scheduling guard and provenance tests."""
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from mina_route_schedule_v2125 import check_pickup_window, apply_pickup_window_guard

WINDOW=('3:15 PM','3:30 PM')
RAW=("PROVISIONAL LIVE-ROUTE PLAN — NOT A VERIFIED REAL-WORLD SCHEDULE\n"
     "1. Buy groceries — estimated arrival 12:56 PM.\n"
     "2. Return library books — estimated arrival 1:44 PM.\n"
     "3. Pick up child from school — estimated arrival 2:23 PM. Route total: ~15.28 km.\n")

def result(answer=RAW,status='provisional_live_route_plan'):
    return SimpleNamespace(answer=answer,status=status,trace=[{'step':'coordinator'}],
                           candidates=[],map_report=object())

class PickupWindowTests(unittest.TestCase):
    def test_early_arrival_has_52_minute_slack_and_proposed_315_to_330(self):
        check=check_pickup_window(RAW,WINDOW,15)
        self.assertEqual(check.decision,'retime_required')
        self.assertEqual(check.hold_minutes,52)
        self.assertEqual(check.scheduled_arrival,'3:15 PM')
        self.assertEqual(check.service_end,'3:30 PM')
        guarded=apply_pickup_window_guard(result(),window=WINDOW,duration_minutes=15,
                                         plan_date='2026-11-23')
        self.assertEqual(guarded.status,'provisional_live_route_plan')
        self.assertIn('52 extra minutes',guarded.answer)
        self.assertIn('unadjusted',guarded.answer)
        self.assertEqual(guarded.trace[-1]['step'],'pickup_window_guard')
    def test_inside_window(self):
        text=RAW.replace('2:23 PM','3:15 PM')
        guarded=apply_pickup_window_guard(result(text),window=WINDOW,duration_minutes=15)
        self.assertEqual(guarded.trace[-1]['decision'],'inside_window')
        self.assertIn('3:30 PM',guarded.answer)
    def test_late_arrival_is_not_feasible(self):
        for eta in ('3:16 PM','3:45 PM'):
            with self.subTest(eta=eta):
                guarded=apply_pickup_window_guard(result(RAW.replace('2:23 PM',eta)),
                                                  window=WINDOW,duration_minutes=15)
                self.assertEqual(guarded.status,'no_feasible_plan')
                self.assertIn('timing rejected',guarded.answer)
    def test_service_longer_than_window_rejected(self):
        guarded=apply_pickup_window_guard(result(),window=WINDOW,duration_minutes=20)
        self.assertEqual(guarded.status,'no_feasible_plan')
    def test_missing_school_eta_fails_closed(self):
        guarded=apply_pickup_window_guard(result('Route feasible. School next.'),
                                         window=WINDOW,duration_minutes=15)
        self.assertEqual(guarded.status,'needs_clarification')
        self.assertIn('could not be verified',guarded.answer)
    def test_failed_route_not_upgraded(self):
        original=result(status='needs_clarification')
        self.assertIs(apply_pickup_window_guard(original,window=WINDOW,duration_minutes=15),original)
    def test_no_pickup_window_does_not_change_route(self):
        original=result()
        self.assertIs(apply_pickup_window_guard(original,window=None,duration_minutes=15),original)
    def test_source_has_schedule_guard_and_map_provenance(self):
        src=Path(__file__).with_name('streamlit_app.py').read_text()
        ast.parse(src)
        self.assertIn('from mina_route_schedule_v2125 import apply_pickup_window_guard',src)
        self.assertIn('result = apply_pickup_window_guard(',src)
        self.assertIn('pickup_window_guard',Path(__file__).with_name('mina_route_schedule_v2125.py').read_text())
        self.assertIn("map_html.replace('Public demo locations reconnected'",src)
        self.assertIn("e.get('geocoding') == 'matched_all_requested_stops'",src)
    def test_no_private_address_in_guard_trace(self):
        guarded=apply_pickup_window_guard(result(),window=WINDOW,duration_minutes=15)
        self.assertNotIn('address',str(guarded.trace).lower())

if __name__=='__main__':unittest.main()
