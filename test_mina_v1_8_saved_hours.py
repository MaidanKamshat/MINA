"""No-network unit tests for v1.8 AM/PM Saved Places and OSM read-only lookup."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mina_saved_places import parse_clock, display_clock, parse_window, load_saved_hours
from mina_planning import NeedsClarification, validate_candidate, SyntheticContext
from mina_live_planning import LivePlanInputs, _validate_inputs, plan_with_live_routes
from mina_state import RequestState, RequestedTask, Constraint
from mina_osm_hours import lookup_osm_hours
from mina_live_tools import ToolUnavailable, LocationRequired
from test_mina_live_planning import POINTS, mock_report

DEMO = 'examples/demo_saved_places_v1_8.json'

class FakeResponse:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def read(self, n): return json.dumps(self.data).encode()


def as_state():
    return RequestState(
        user_request=('For the demo, plan returning library books, buying groceries, and '
                      'picking up a child before 4:30 PM. The library opens at noon, '
                      'and grocery shopping takes at least 60 minutes.'),
        intent='planning', tasks=[RequestedTask(t,t,t) for t in ('library','groceries','school_pickup')],
        constraints=[Constraint('deadline','school_pickup','16:30','before 4:30 PM'),
                     Constraint('opening_time','library','12:00','library opens at noon'),
                     Constraint('minimum_duration','groceries','60','at least 60 minutes')],
        route='complex',
    )

def as_params(**kwargs):
    x = dict(origin=POINTS['start'], task_locations={t:POINTS[t] for t in ('library','groceries','school_pickup')},
             start_time='10:00 AM', durations={'library':15,'groceries':60,'school_pickup':10},
             saved_places_file=DEMO, plan_date='2026-11-20', travel_buffer_minutes=10)
    x.update(kwargs)
    return LivePlanInputs(**x)

class SavedPlacesTests(unittest.TestCase):
    def test_12hour_conversion_and_midnight(self):
        for source, target in [('3:15 PM','15:15'), ('12:00 AM','00:00'),
                               ('12:00 PM','12:00'), ('9:05 AM','09:05')]:
            self.assertEqual(parse_clock(source),target)
            self.assertEqual(parse_clock(display_clock(target)),target)
    def test_saved_json_requires_ampm_not_24hour(self):
        with self.assertRaises(NeedsClarification): parse_clock('15:15')
        self.assertEqual(parse_clock('15:15',legacy=True),'15:15')
    def test_reject_overnight_window(self):
        with self.assertRaises(NeedsClarification):
            parse_window({'start':'8:00 PM', 'end':'6:00 AM'})
    def test_saved_demo_loads_friday_and_provenance(self):
        data = load_saved_hours(DEMO, '2026-11-20', {'library','groceries','school_pickup'})
        self.assertTrue(data.demo)
        self.assertEqual(data.windows['school_pickup'], ('15:15','15:30'))
        self.assertEqual(data.windows['library'], ('12:00','18:00'))
        self.assertEqual(data.windows['groceries'], ('09:00','21:00'))
    def test_closed_or_missing_day_fails_closed(self):
        with self.assertRaisesRegex(NeedsClarification,'no confirmed hours'):
            load_saved_hours(DEMO, '2026-11-22', {'library'})
    def test_saved_file_bad_date(self):
        with self.assertRaises(NeedsClarification): load_saved_hours(DEMO, 'tomorrow', {'library'})
    def test_pickup_waits_till_315_and_finishes_by_330(self):
        ctx = _validate_inputs(as_state(), as_params())
        self.assertEqual(ctx.start,'10:00')
        self.assertEqual(ctx.time_windows['school_pickup'], ('15:15','15:30'))
        self.assertIn('DEMO',ctx.provenance)
        ctx.travel_minutes = {('start','groceries'):30,('groceries','library'):30,
                              ('library','school_pickup'):30}
        result = validate_candidate(('groceries','library','school_pickup'),as_state(),ctx)
        self.assertTrue(result['feasible'], result)
        self.assertEqual(result['timeline'][-1],('school_pickup','15:15'))
    def test_pickup_too_late_rejected_including_duration(self):
        ctx = _validate_inputs(as_state(), as_params())
        ctx.travel_minutes = {('start','groceries'):60,('groceries','library'):60,
                              ('library','school_pickup'):180}
        result = validate_candidate(('groceries','library','school_pickup'),as_state(),ctx)
        self.assertFalse(result['feasible'])
        self.assertIn('Time window',result['reason'])
    def test_arrival_inside_window_but_cannot_finish(self):
        ctx = _validate_inputs(as_state(), as_params())
        ctx.travel_minutes = {('start','groceries'):30,('groceries','library'):30,
                              ('library','school_pickup'):186}
        result = validate_candidate(('groceries','library','school_pickup'),as_state(),ctx)
        self.assertFalse(result['feasible'])
    def test_invalid_12hour_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=json.loads(Path(DEMO).read_text())
            raw['places']['school_pickup']['time_window']['start']='15:15'
            file=Path(directory)/'test.json'; file.write_text(json.dumps(raw))
            with self.assertRaises(NeedsClarification):
                load_saved_hours(str(file),'2026-11-20',{'school_pickup'})
    def test_school_pickup_rejects_weekend_without_exception(self):
        with self.assertRaisesRegex(NeedsClarification, 'not confirmed'):
            load_saved_hours(DEMO, '2026-11-21', {'school_pickup'})

    def test_school_closed_on_exception_date(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(Path(DEMO).read_text())
            raw['places']['school_pickup']['date_overrides']['2026-11-20'] = None
            file = Path(directory) / 'closed.json'; file.write_text(json.dumps(raw))
            with self.assertRaisesRegex(NeedsClarification, 'not confirmed'):
                load_saved_hours(str(file),'2026-11-20',{'school_pickup'})

    def test_pickup_date_override_can_change_window(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(Path(DEMO).read_text())
            raw['places']['school_pickup']['date_overrides']['2026-11-20'] = {
                'start':'2:45 PM', 'end':'3:00 PM'}
            file = Path(directory) / 'early.json'; file.write_text(json.dumps(raw))
            self.assertEqual(load_saved_hours(str(file),'2026-11-20',{'school_pickup'})
                             .windows['school_pickup'],('14:45','15:00'))

    def test_12_hour_library_open_cli_parses_with_existing_request(self):
        ctx = _validate_inputs(as_state(),as_params(library_open='12:00 PM'))
        self.assertEqual(ctx.library_open,'12:00')

    def test_24_hour_saved_user_window_is_never_allowed_even_if_legacy_cli_is(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(Path(DEMO).read_text())
            raw['places']['groceries']['weekly_hours']['Fri']['end'] = '21:00'
            file = Path(directory) / 'bad.json'; file.write_text(json.dumps(raw))
            with self.assertRaises(NeedsClarification):
                load_saved_hours(str(file),'2026-11-20',{'groceries'})

    def test_conflicting_library_opening_is_not_silently_replaced(self):
        with self.assertRaisesRegex(NeedsClarification,'Conflicting|conflicts'):
            _validate_inputs(as_state(),as_params(library_open='10:00'))
    def test_no_saved_data_preserves_old_behavior(self):
        from test_mina_live_planning import state, params
        self.assertFalse(_validate_inputs(state(),params()).time_windows)
    def test_full_live_uses_saved_pickup_window_mock_network(self):
        with patch('mina_live_planning._require_key',return_value='mock'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda loc,**kw:
                    __import__('mina_route_tools').RouteStop(loc,*[float(x) for x in loc.split(',')])), \
             patch('mina_live_planning.get_route_report',side_effect=mock_report):
            result=plan_with_live_routes(as_state(),as_params(),planner_mode='deterministic')
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertIn('3:15 PM', result.answer)
        self.assertIn('3:30 PM', result.answer)
        self.assertNotIn('15:15',result.answer)

class OSMTests(unittest.TestCase):
    def test_exact_name_discovery_not_auto_write(self):
        response={'elements':[{'type':'node','id':123,'tags':{'name':'Demo Library','opening_hours':'Mo-Fr 09:00-17:00'}}]}
        def opener(req,timeout):
            self.assertEqual(req.full_url,'https://overpass-api.de/api/interpreter')
            self.assertIn(b'around%3A75',req.data)
            return FakeResponse(response)
        finding = lookup_osm_hours('Demo Library',-78.8,35.7,opener=opener)
        self.assertIn('09:00', finding.opening_hours_raw)
        self.assertIn('node/123',finding.osm_url)
    def test_name_mismatch_no_guess(self):
        finding = lookup_osm_hours('Another Shop',-78.8,35.7,opener=lambda req,timeout:
                                   FakeResponse({'elements':[{'type':'node','id':1,'tags':{'name':'Wrong','opening_hours':'24/7'}}]}))
        self.assertIsNone(finding)
    def test_multiple_matches_fail_closed(self):
        x={'type':'node','id':1,'tags':{'name':'Demo Library','opening_hours':'24/7'}}
        with self.assertRaises(LocationRequired):
            lookup_osm_hours('Demo Library',-78.8,35.7,opener=lambda req,timeout: FakeResponse({'elements':[x,x]}))
    def test_api_down_no_hours_guessed(self):
        with self.assertRaises(ToolUnavailable):
            lookup_osm_hours('Demo Library',-78.8,35.7,opener=lambda req,timeout: (_ for _ in ()).throw(OSError('down')))
    def test_coordinates_must_be_valid(self):
        with self.assertRaises(LocationRequired): lookup_osm_hours('Demo Library',200,91)

if __name__=='__main__': unittest.main()
