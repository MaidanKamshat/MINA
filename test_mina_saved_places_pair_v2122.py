"""Regression for v2.12.2. Pure offline checks: no Streamlit or provider access."""
import ast
from pathlib import Path
from datetime import date
import unittest
from mina_route_bridge_v212 import build_route_inputs, paired_backend_plan_date

SRC = Path(__file__).with_name('streamlit_app.py').read_text()

class DatePairRegression(unittest.TestCase):
    def test_parser_keeps_requested_date_in_bridge(self):
        hub = {'preferences':{'home_address':'HOME PLACE', 'school_address':'SCHOOL',
                  'pickup_time':'3:15 PM','pickup_minutes':15,'library_open_time':'9:00 AM'},
               'places':{'library':{'address':'LIBRARY'}, 'costco':{'address':'COSTCO'}}}
        r = build_route_inputs(
            'Plan Monday, November 23, 2026: leave home at 12:30 PM, '
            'library for 20 minutes, Costco for 30 minutes and school pickup '
            'between 3:15 and 3:30 PM',today=date(2026,11,21),hub=hub)
        self.assertEqual(r.missing, ())
        self.assertEqual(r.plan_date, '2026-11-23')
        self.assertEqual(r.origin,'HOME PLACE')
        self.assertEqual(r.locations['groceries'], 'COSTCO')
        self.assertEqual(r.durations['library'],20)
        self.assertEqual(r.start_time,'12:30 PM')
        self.assertEqual(paired_backend_plan_date('',r.plan_date),'')

    def test_date_only_is_blocked_for_backend(self):
        for d in ('2026-11-23','',None):
            with self.subTest(date=d):
                self.assertEqual(paired_backend_plan_date('',d),'')
                self.assertEqual(paired_backend_plan_date(None,d),'')

    def test_paired_demo_json_keeps_its_date(self):
        self.assertEqual(paired_backend_plan_date('examples/demo.json','2026-11-23'),'2026-11-23')

    def test_app_route_paths_use_guard(self):
        ast.parse(SRC)
        self.assertIn('from mina_route_bridge_v212 import build_route_inputs, paired_backend_plan_date', SRC)
        self.assertIn('plan_date=bridge.plan_date,',SRC)
        self.assertIn('pickup_window=schedule_window',SRC)
        self.assertIn('result = plan_family_route(',SRC)
        self.assertIn('plan_date=paired_backend_plan_date(saved_places_file, plan_date)',SRC)
        self.assertIn('plan_date=paired_backend_plan_date(\n                                        settings.saved_places_file,',SRC)
        self.assertNotIn("plan_date=bridge.plan_date or ''",SRC)

    def test_route_flow_remains_read_only(self):
        branch = SRC.split("elif trip_route_kind == 'route'",1)[1].split('elif calendar_confirm:',1)[0]
        for action in ('_store_local_hub(', '_store_calendar(', 'google_insert_event('):
            self.assertNotIn(action,branch)
        self.assertIn("'version':'2.12.1'",branch)

if __name__=='__main__':unittest.main()
