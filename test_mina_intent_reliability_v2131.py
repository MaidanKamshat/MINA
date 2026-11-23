"""Offline regression tests for MINA v2.13.1. Never access network or user data."""
from __future__ import annotations
import ast
import importlib.util
import re
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from mina_intent_reliability_v2131 import unsaved_named_stop, missing_departure_reply
from mina_trip_voice_v212 import classify_multi_stop_route, parse_trip_voice
from mina_route_bridge_v212 import build_route_inputs

ROOT=Path(__file__).resolve().parent
TODAY=date(2026,11,22)
HUB={
    'preferences': {'home_address': 'PRIVATE SAVED HOME', 'school_address': 'SAVED SCHOOL',
                    'pickup_time':'3:15 PM','pickup_minutes':15,'library_open_time':'9:00 AM',
                    'shopping_minutes':45,'library_minutes':15,'buffer_minutes':15},
    'places': {'library':{'name':'Library','address':'SAVED LIBRARY'},
               'costco':{'name':'Costco','address':'SAVED COSTCO'},
               'target':{'name':'Target','address':'SAVED TARGET'},
               'dentist':{'name':'Dentist','address':'SAVED DENTIST'}}
}
REG05 = ("Mina, I need to visit Costco and the library before picking up my child from "
         "school tomorrow. Help me plan the best route. I haven't decided what time I'll leave home.")
REG03 = ("Mina, plan a hypothetical route from home to a place called MINA QA Unspecified Stop, "
         "and then to my child's school. I haven't provided the address for that stop. "
         "Can you plan the route without guessing its location?")
REG04 = ("Mina, I need to stop at MINA QA Unspecified Stop before picking up my child "
         "from school. Find the best driving route from home.")


def _calendar_read_router():
    """Load real shipped router but stub unavailable *other* modules during offline test.

    Production uses its actual installed modules. A stub is used here solely
    because the capstone's incremental patch ZIPs do not bundle the full app.
    """
    saved = types.ModuleType('mina_saved_places')
    saved.parse_clock = lambda s: '10:00'
    saved.display_clock = lambda s: '10:00 AM'
    auto = types.ModuleType('mina_auto_mode')
    def local_date(text, today):
        if 'november 24, 2026' in text.lower():return date(2026,11,24)
        return today
    auto._date_from_text = local_date
    auto._local_list_command_text = lambda s:s
    spec = importlib.util.spec_from_file_location('mina_calendar_v27_readonly_test',ROOT/'mina_calendar_v27.py')
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'mina_saved_places':saved,'mina_auto_mode':auto}):
        assert spec.loader is not None
        spec.loader.exec_module(mod)
    return mod.calendar_read_intent


class DateAndNegationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.calendar_read=staticmethod(_calendar_read_router())

    def test_read_date_with_dont_change_anything(self):
        q=("Mina, show me only my calendar events for November 24, 2026. "
           "Include both my local MINA calendar and Google Calendar. Don't change anything.")
        self.assertEqual(self.calendar_read(q,today=TODAY),('agenda',date(2026,11,24)))

    def test_read_date_without_negation_still_works(self):
        self.assertEqual(self.calendar_read(
            'Mina, show me calendar events for November 24, 2026',today=TODAY),
            ('agenda',date(2026,11,24)))

    def test_do_not_create_or_change_anything_is_readonly(self):
        q='Show my calendar events on November 24, 2026; do not create or change anything.'
        self.assertEqual(self.calendar_read(q,today=TODAY),('agenda',date(2026,11,24)))

    def test_not_let_affirmative_writes_pass(self):
        for q in (
            'Show my calendar events and delete a meeting',
            'Show my calendar and create an event on November 24, 2026',
            "Show my calendar, don't change anything, then delete my event",
            "Don't create anything and show my calendar, but add a meeting",
        ):
            with self.subTest(q=q):self.assertIsNone(self.calendar_read(q,today=TODAY))

    def test_unrelated_query_not_calendar_read(self):
        self.assertIsNone(self.calendar_read('Write a friendly email to a teacher on Monday',today=TODAY))


class RouteContextTests(unittest.TestCase):
    def test_reg05_is_family_route_even_when_school_comes_after_picking_up(self):
        self.assertEqual(classify_multi_stop_route(REG05),'route')
        trip=parse_trip_voice(REG05,today=TODAY)
        self.assertEqual(trip.requested_tasks, {'library','groceries','school_pickup'})
        self.assertEqual(trip.plan_date,'2026-11-23')
        self.assertIsNone(trip.departure_time)

    def test_reg05_saved_profile_is_complete(self):
        bridge=build_route_inputs(REG05,today=TODAY,hub=HUB)
        self.assertFalse(bridge.missing)
        self.assertEqual(bridge.plan_date,'2026-11-23')
        self.assertIsNone(bridge.start_time)
        self.assertEqual(bridge.locations['school_pickup'],'SAVED SCHOOL')

    def test_departure_prompt_only_mentions_saved_target_without_address(self):
        msg=missing_departure_reply(day='2026-11-23',pickup='3:15 PM')
        self.assertIn('3:15 PM',msg)
        self.assertIn('departure time',msg)
        self.assertNotIn('PRIVATE SAVED HOME',msg)
        self.assertIn('No route was calculated',msg)

    def test_relative_date_parse_same_date_deterministic(self):
        self.assertEqual(parse_trip_voice('Plan library, Costco and school pickup tomorrow',today=TODAY).plan_date,'2026-11-23')
        self.assertEqual(parse_trip_voice('Plan library, Costco and school pickup today',today=TODAY).plan_date,'2026-11-22')

    def test_conflicting_relative_explicit_date_fails_closed(self):
        from mina_trip_voice_v212 import TripParseError
        with self.assertRaisesRegex(TripParseError,'only one trip date'):
            parse_trip_voice('Plan library and Costco tomorrow November 23, 2026',today=TODAY)

    def test_reg03_unknown_stop_without_coordinate_guess(self):
        self.assertEqual(unsaved_named_stop(REG03,HUB),'MINA QA Unspecified Stop')

    def test_reg04_unknown_stop_without_hints(self):
        self.assertEqual(unsaved_named_stop(REG04,HUB),'MINA QA Unspecified Stop')

    def test_known_saved_place_is_not_unknown(self):
        for q in ('Plan a route: stop at Costco before picking up my child from school',
                  'Find a route to a place called Library, and then to school'):
            with self.subTest(q=q):self.assertIsNone(unsaved_named_stop(q,HUB))

    def test_general_unrelated_questions_are_not_route(self):
        self.assertIsNone(unsaved_named_stop('Please email the teacher about school',HUB))

    def test_retain_confirmed_route_behavior(self):
        p=('Mina, plan Monday, November 23, 2026. Leave home at 12:30 PM, '
           'library for 20 minutes and Costco for 30 minutes and school pickup '
           'between 3:15 and 3:30 PM. Do not create calendar events.')
        self.assertEqual(classify_multi_stop_route(p),'route')
        b=build_route_inputs(p,today=TODAY,hub=HUB)
        self.assertEqual(b.missing,())
        self.assertEqual(b.start_time,'12:30 PM')
        self.assertEqual(b.pickup_window,('3:15 PM','3:30 PM'))

    def test_app_wiring_does_not_write_unknown_or_missing_time(self):
        s=(ROOT/'streamlit_app.py').read_text(encoding='utf8')
        ast.parse(s)
        unknown=s.split('if unknown_stop is not None:',1)[1].split("elif trip_route_kind == 'mixed':",1)[0]
        missing=s.split('if has_profile and not bridge.start_time:',1)[1].split('elif has_profile:',1)[0]
        for branch in (unknown,missing):
            self.assertNotIn('execute_ui_request(',branch)
            self.assertNotIn('plan_family_route(',branch)
            self.assertNotIn('google_insert_event(',branch)
            self.assertNotIn('_store_calendar(',branch)
            self.assertNotIn('_store_local_hub(',branch)
        self.assertIn("'status':'missing_departure_time'",s)
        self.assertIn("'status':'unknown_named_stop'",s)


if __name__=='__main__':unittest.main()
