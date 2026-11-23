"""v2.12.6: readable proposed route timeline without bogus live timing."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from mina_route_schedule_v2125 import apply_pickup_window_guard, replace_legacy_route_map_caption

RAW = ("PROVISIONAL LIVE-ROUTE PLAN — NOT A VERIFIED REAL-WORLD SCHEDULE\n"
       "Start: 12:30 PM.\n"
       "1. Buy groceries — estimated arrival 12:56 PM.\n"
       "2. Return library books — estimated arrival 1:44 PM.\n"
       "3. Pick up child from school — estimated arrival 2:23 PM. Route total: ~15.28 km.\n")
WINDOW=('3:15 PM','3:30 PM')
DURATIONS={'groceries':30,'library':20,'school_pickup':15}

def run_guard(raw=RAW, status='provisional_live_route_plan', **kw):
    result=SimpleNamespace(status=status,answer=raw,trace=[{'step':'coordinator'}],
                           map_report=object())
    return apply_pickup_window_guard(result,window=WINDOW,duration_minutes=15,
                                    departure_time='12:30 PM',stop_durations=DURATIONS,
                                    shopping_label='Costco',plan_date='2026-11-23',**kw)

class RouteTimelineV2126Tests(unittest.TestCase):
    def test_timeline_uses_only_known_raw_etas_and_durations(self):
        r=run_guard()
        for expected in ('12:30 PM','12:56 PM–1:26 PM','1:44 PM–2:04 PM',
                         '2:04 PM–2:56 PM','52 extra minutes','3:15 PM','3:30 PM',
                         'Costco','Library','original geographic route'):
            self.assertIn(expected,r.answer)
        self.assertLess(r.answer.index('Proposed afternoon schedule'),
                        r.answer.index('Original backend route ETAs'))
        self.assertIn('estimated arrival 2:23 PM',r.answer)
        self.assertEqual(r.trace[-1]['adjusted_timeline_shown'],True)
        self.assertEqual(r.trace[-1]['decision'],'retime_required')
        self.assertEqual(r.trace[-1]['version'],'2.12.6')
        self.assertIsNotNone(r.map_report)
    def test_no_stop_details_no_invented_timeline(self):
        r=run_guard(raw='3. Pick up child from school — estimated arrival 2:23 PM.')
        self.assertNotIn('### Proposed afternoon schedule',r.answer)
        self.assertIn('52 extra minutes',r.answer)
        self.assertEqual(r.trace[-1]['adjusted_timeline_shown'],False)
    def test_conflicting_etaseries_no_invented_timeline(self):
        r=run_guard(raw=RAW.replace('1:44 PM','1:00 PM'))
        self.assertNotIn('### Proposed afternoon schedule',r.answer)
        self.assertEqual(r.trace[-1]['adjusted_timeline_shown'],False)
    def test_late_arrival_is_not_approved_or_retimed(self):
        r=run_guard(raw=RAW.replace('2:23 PM','3:45 PM'))
        self.assertEqual(r.status,'no_feasible_plan')
        self.assertNotIn('### Proposed afternoon schedule',r.answer)
    def test_no_private_geolocation_or_write_side_effects(self):
        r=run_guard()
        self.assertNotIn('35.715',r.answer)
        self.assertNotIn('address',str(r.trace).lower())
    def test_legend_fixed_only_in_true_provenance_branch(self):
        html='<div>Public demo locations reconnected.</div>'
        self.assertIn('Route locations from Family Hub',replace_legacy_route_map_caption(html))
        html2='<div>PUBLIC&nbsp;demo&nbsp;locations&nbsp;reconnected</div>'
        self.assertNotIn('demo',replace_legacy_route_map_caption(html2).lower())
        self.assertIn('my map polyline',replace_legacy_route_map_caption('my map polyline'))
        src=Path(__file__).with_name('streamlit_app.py').read_text()
        ast.parse(src)
        self.assertIn("e.get('geocoding') == 'matched_all_requested_stops'",src)
        self.assertIn('map_html = replace_legacy_route_map_caption(map_html)',src)
        self.assertIn('stop_durations=bridge.durations',src)

if __name__=='__main__':unittest.main()
