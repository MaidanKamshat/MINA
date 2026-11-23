"""Pure offline tests for voice-to-route scope fix. No network or user-data writes."""
from __future__ import annotations
import ast
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from mina_trip_voice_v212 import parse_trip_voice, TripParseError, normalize_clock
from mina_route_bridge_v212 import build_route_inputs

TODAY=date(2026,11,21)
PROMPT=("Mina, help me plan a hypothetical afternoon on Monday, November 23. "
    "I want to leave home at 12:30 p.m., stop at the library for 20 minutes "
    "and Costco for 30 minutes, and arrive at school for pickup between 3:15 "
    "and 3:30 PM. Find the best order using live driving times and tell me if "
    "the plan is feasible. Don't create any calendar events or change my shopping lists.")
HUB = {
 'preferences':{'home_address':'PRIVATE HOME', 'school_address':'SCHOOL ADDRESS',
                'pickup_time':'3:15 PM', 'pickup_minutes':10,'library_open_time':'9:00 AM',
                'library_minutes':15,'shopping_minutes':45,'buffer_minutes':15},
 'places':{'library':{'address':'LIBRARY ADDRESS'},'target':{'address':'TARGET ADDRESS'},
           'costco':{'address':'COSTCO ADDRESS'},'trader_joes':{'address':'TJ ADDRESS'}}
}

class TripVoiceParserTests(unittest.TestCase):
 def test_exact_voice_phrase(self):
    p=parse_trip_voice(PROMPT,today=TODAY)
    self.assertEqual(p.departure_time,'12:30 PM')
    self.assertEqual(p.plan_date,'2026-11-23')
    self.assertEqual(p.duration_overrides,{'library':20,'groceries':30})
    self.assertEqual(p.pickup_window,('3:15 PM','3:30 PM'))
    self.assertEqual(p.store,'costco')
    self.assertEqual(p.requested_tasks,{'library','groceries','school_pickup'})
    self.assertIn('start from home',p.prompt_for_planner)
    self.assertNotIn('leave home at 12:30',p.prompt_for_planner)
    self.assertIn('school for pickup between 3:15 and 3:30 PM',p.prompt_for_planner)
    self.assertIn("Don't create any calendar events or change my shopping lists.",p.prompt_for_planner)
 def test_clock_variants(self):
    for phrase in ['12:30 p.m.','12:30 PM','12:30 p.m','12:30 pm','12:30 P.M.']:
        with self.subTest(phrase=phrase):
            self.assertEqual(normalize_clock(phrase),'12:30 PM')
 def test_clock_am(self):
    self.assertEqual(normalize_clock('10 a.m.'),'10:00 AM')
 def test_ambiguous_time_no_guess(self):
    with self.assertRaises(TripParseError): normalize_clock('3:15')
 def test_day_mismatch_rejected(self):
    with self.assertRaisesRegex(TripParseError,'weekday'):
        parse_trip_voice(PROMPT.replace('Monday','Tuesday'),today=TODAY)
 def test_yearless_date_future(self):
    p=parse_trip_voice('on November 23, visit the library and Costco',today=TODAY)
    self.assertEqual(p.plan_date,'2026-11-23')
 def test_same_date_next_year_when_past(self):
    p=parse_trip_voice('on November 23, visit the library and Costco',today=date(2026,12,1))
    self.assertEqual(p.plan_date,'2027-11-23')
 def test_explicit_different_date_year(self):
    p=parse_trip_voice('Monday, November 23, 2026 library and Costco',today=TODAY)
    self.assertEqual(p.plan_date,'2026-11-23')
 def test_invalid_date_rejected(self):
    with self.assertRaises(TripParseError):
        parse_trip_voice('February 30 library Costco',today=TODAY)
 def test_paired_stores_rejected(self):
    with self.assertRaisesRegex(TripParseError,'one shopping stop'):
        parse_trip_voice('Library, Costco and Target, school pickup',today=TODAY)
 def test_double_departure_rejected(self):
    with self.assertRaisesRegex(TripParseError,'one home departure time'):
        parse_trip_voice('Leave home at 12 PM and depart home at 1 PM, library and Costco',today=TODAY)
 def test_negative_departure_rejected(self):
    with self.assertRaises(TripParseError):
        parse_trip_voice('Do not leave home at 12:30 PM; library and Costco',today=TODAY)
 def test_unsupported_duration_rejected(self):
    with self.assertRaises(TripParseError):
        parse_trip_voice('library for 999 minutes, Costco for 30 minutes',today=TODAY)
 def test_same_duration_conflict_rejected(self):
    with self.assertRaises(TripParseError):
        parse_trip_voice('library for 15 minutes and library for 20 minutes',today=TODAY)
 def test_no_calendar_write_action(self):
    p=parse_trip_voice(PROMPT,today=TODAY)
    self.assertIn("Don't create any calendar events",p.prompt_for_planner)
 def test_conversational_departure_variants(self):
    for form in ('leave home at 12:30 PM','depart from home at 12:30 PM',
                 'start from home at 12:30 PM','leaving home at 12:30 PM'):
        with self.subTest(form=form):
            self.assertEqual(parse_trip_voice(form+' and stop at library and Costco',today=TODAY).departure_time,'12:30 PM')
 def test_pickup_window_explicit_meridiem(self):
    p=parse_trip_voice('school pickup between 3:15 PM and 3:30 PM',today=TODAY)
    self.assertEqual(p.pickup_window,('3:15 PM','3:30 PM'))
 def test_bad_pickup_window(self):
    with self.assertRaisesRegex(TripParseError,'window end'):
        parse_trip_voice('school pickup between 3:30 PM and 3:15 PM',today=TODAY)

class RouteBridgeTests(unittest.TestCase):
 def test_exact_user_input_selected_addresses(self):
    r=build_route_inputs(PROMPT,today=TODAY,hub=HUB)
    self.assertEqual(r.missing,())
    self.assertEqual(r.origin,'PRIVATE HOME')
    self.assertEqual(r.locations,{'library':'LIBRARY ADDRESS','groceries':'COSTCO ADDRESS','school_pickup':'SCHOOL ADDRESS'})
    self.assertEqual(r.durations,{'library':20,'groceries':30,'school_pickup':10})
    self.assertEqual(r.start_time,'12:30 PM')
    self.assertEqual(r.plan_date,'2026-11-23')
    self.assertEqual(r.pickup_window,('3:15 PM','3:30 PM'))
 def test_missing_costco_refuses_target_substitution(self):
    hub={'preferences':HUB['preferences'],'places':dict(HUB['places'])}
    hub['places']['costco']={'address':''}
    result=build_route_inputs(PROMPT,today=TODAY,hub=hub)
    self.assertIn('Costco address',result.missing)
    self.assertEqual(result.locations['groceries'],'')
    self.assertNotEqual(result.locations['groceries'],'TARGET ADDRESS')
 def test_preference_minutes_apply_if_unspoken(self):
    r=build_route_inputs('Library, Costco, school pickup',today=TODAY,hub=HUB)
    self.assertEqual(r.durations['library'],15)
    self.assertEqual(r.durations['groceries'],45)
 def test_generically_requested_grocery_uses_saved_default(self):
    r=build_route_inputs('Library, groceries, school pickup',today=TODAY,hub=HUB)
    self.assertEqual(r.locations['groceries'],'TARGET ADDRESS')
 def test_missing_school_window_blocks(self):
    hub={'preferences':dict(HUB['preferences']), 'places':HUB['places']}
    hub['preferences'].pop('pickup_time')
    r=build_route_inputs('Library, Costco and school pickup',today=TODAY,hub=hub)
    self.assertIn('school pickup time/window',r.missing)
 def test_user_pickup_window_suffices_without_stored_time(self):
    hub={'preferences':dict(HUB['preferences']), 'places':HUB['places']}
    hub['preferences'].pop('pickup_time')
    r=build_route_inputs(PROMPT,today=TODAY,hub=hub)
    self.assertNotIn('school pickup time/window',r.missing)
 def test_missing_library_hours_must_disclose(self):
    hub={'preferences':dict(HUB['preferences']), 'places':HUB['places']}
    hub['preferences'].pop('library_open_time')
    r=build_route_inputs(PROMPT,today=TODAY,hub=hub)
    self.assertIn('user-provided library opening time',r.missing)
 def test_no_private_hub_modification(self):
    from copy import deepcopy
    before=deepcopy(HUB)
    build_route_inputs(PROMPT,today=TODAY,hub=HUB)
    self.assertEqual(HUB,before)
 def test_hub_absent_fails_closed(self):
    r=build_route_inputs(PROMPT,today=TODAY,hub=None)
    self.assertTrue(r.missing)
 def test_distinct_store_selection(self):
    p=PROMPT.replace('Costco','Trader Joe’s')
    self.assertEqual(build_route_inputs(p,today=TODAY,hub=HUB).locations['groceries'],'TJ ADDRESS')
 def test_saved_pickup_note_not_doubled(self):
    r=build_route_inputs(PROMPT,today=TODAY,hub=HUB)
    self.assertNotIn('according to my saved local notes',r.prompt_for_planner)
 def test_explicit_user_no_pref_notes_used(self):
    r=build_route_inputs('Library and Costco and school pickup',today=TODAY,hub=HUB)
    self.assertIn('according to my saved local notes',r.prompt_for_planner)

class AppWiringTests(unittest.TestCase):
 def test_python_syntax(self):
    text=Path(__file__).with_name('streamlit_app.py').read_text()
    ast.parse(text)
 def test_route_adapter_runs_before_backend(self):
    text=Path(__file__).with_name('streamlit_app.py').read_text()
    branch=text.split("elif trip_route_kind == 'route'",1)[1].split("elif calendar_confirm:",1)[0]
    self.assertIn('build_route_inputs(prompt',branch)
    self.assertIn('depart_time=start_value',branch)
    self.assertIn('result = plan_family_route(',branch)
    self.assertIn('bridge.locations[t] for t in requested',branch)
    self.assertIn('durations=bridge.durations,',branch)
    self.assertIn("mode':'user_confirmed_public_demo'",branch)
 def test_route_readonly_in_app(self):
    branch=Path(__file__).with_name('streamlit_app.py').read_text().split("elif trip_route_kind == 'route'",1)[1].split("elif calendar_confirm:",1)[0]
    for forbidden in ('google_insert_event(', '_store_local_hub(', '_store_calendar('):
        self.assertNotIn(forbidden,branch)

if __name__=='__main__':
 unittest.main()
