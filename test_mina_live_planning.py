"""v1.7: no-network mixed-source planning tests and safety/regression coverage."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from mina_state import RequestState, RequestedTask, Constraint
from mina_live_tools import LocationRequired, ToolUnavailable
from mina_live_planning import LivePlanInputs, plan_with_live_routes
from mina_route_tools import RouteReport, RouteStop, RouteLeg
from mina_runtime import run_state, run_request

POINTS = {
    'start': '-78.85030,35.73260',
    'library': '-78.80320,35.77210',
    'groceries': '-78.78080,35.79150',
    'school_pickup': '-78.83010,35.75220',
}


def state():
    return RequestState(
        'Tomorrow plan returning library books, buying groceries and picking up child '
        'before 2:30 PM; library opens at noon; groceries take at least 90 minutes.',
        'planning', tasks=[
            RequestedTask('library', 'library', 'library books'),
            RequestedTask('groceries', 'groceries', 'groceries'),
            RequestedTask('school_pickup', 'school pickup', 'picking up child'),
        ], constraints=[
            Constraint('deadline', 'school_pickup', '14:30', 'before 2:30 PM'),
            Constraint('opening_time', 'library', '12:00', 'library opens at noon'),
            Constraint('minimum_duration', 'groceries', '90', 'at least 90 minutes'),
        ], route='complex',
    )


def params(**kwargs):
    values = dict(origin=POINTS['start'], start_time='10:00',
                  task_locations={k: POINTS[k] for k in ('library', 'groceries', 'school_pickup')},
                  durations={'library': 10, 'groceries': 75, 'school_pickup': 10},
                  library_open='12:00', travel_buffer_minutes=10)
    values.update(kwargs)
    return LivePlanInputs(**values)


def mock_report(locations, *, api_key=None, opener=None):
    # Produce deterministic provider-like legs, with route duration depending on direction.
    coords = [str(x) for x in locations]
    durations = []
    for a, b in zip(coords, coords[1:]):
        if a == b:
            raise ValueError('Duplicate points')
        durations.append(12.2 if len(coords) == 4 else 10.0)
    stops = tuple(RouteStop(s, *[float(x) for x in s.split(',')]) for s in coords)
    legs = tuple(RouteLeg(stops[i].label, stops[i+1].label, 4.0, t)
                 for i, t in enumerate(durations))
    return RouteReport(stops, legs, 4.0*len(legs), sum(durations),
                       datetime(2026,11,20,tzinfo=timezone.utc).isoformat(),
                       {'type':'Feature','geometry':{'type':'LineString','coordinates':[
                           [s.longitude,s.latitude] for s in stops]},'properties':{}})


class FakeLLM:
    def __init__(self, output):
        self.output = output
        self.responses = self
    def create(self, **kwargs):
        return SimpleNamespace(output_text=self.output)


class LivePlanTests(unittest.TestCase):
    def test_live_route_injects_actual_leg_estimates_with_explicit_buffer(self):
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report) as routes:
            result = plan_with_live_routes(state(), params(), planner_mode='deterministic')
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertEqual(routes.call_count, 2)
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all(x['feasible'] for x in result.candidates))
        self.assertIn('HeiGIT', result.answer)
        self.assertIn('NOT verified', result.answer)
        self.assertIn('10 min per leg', result.answer)
        self.assertIn('library', str(result.map_report.stops))
        self.assertTrue(result.map_report.geojson['geometry']['coordinates'])
        self.assertIn('live_context', [t['step'] for t in result.trace])
        self.assertNotIn('fake', result.answer)

    def test_minimum_duration_is_applied(self):
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result = plan_with_live_routes(state(), params(durations={'library':10,'groceries':15,'school_pickup':10}),
                                           planner_mode='deterministic')
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertIn('estimated arrival', result.answer)

    def test_no_feasible_plan_is_safe_and_has_no_map(self):
        s=state()
        s.constraints[0] = Constraint('deadline','school_pickup','10:30','before 10:30 AM')
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result = plan_with_live_routes(s, params(), planner_mode='deterministic')
        self.assertEqual(result.status, 'no_feasible_plan')
        self.assertIsNone(result.map_report)
        self.assertEqual(sum(c['feasible'] for c in result.candidates),0)

    def test_run_request_end_to_end_entrypoint_uses_live_planning_branch(self):
        with patch('mina_runtime.extract_request', return_value=state()), \
             patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result=run_request('Plan library, groceries, and school pickup before 2:30 PM',
                               use_rag=False, live_tools=True, live_plan=params(),
                               planner_mode='deterministic')
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertEqual(result.route, 'complex')
        self.assertEqual(result.trace[0]['step'], 'coordinator')
        self.assertEqual(result.trace[-1]['step'], 'controller')

    def test_missing_duration_aborts_without_network(self):
        with patch('mina_live_planning.get_route_report', side_effect=AssertionError('NO NETWORK')), \
             patch('mina_live_planning.geocode_route_stop', side_effect=AssertionError('NO NETWORK')):
            result=run_state(state(), live_tools=True, live_plan=params(durations={'library':10,'groceries':60}),
                             planner_mode='deterministic')
        self.assertEqual(result.status, 'needs_clarification')
        self.assertIn('duration', result.answer)

    def test_missing_library_open_aborts_without_network(self):
        s=state()
        s.constraints=[c for c in s.constraints if c.kind != 'opening_time']
        with patch('mina_live_planning.get_route_report', side_effect=AssertionError('NO NETWORK')):
            result=run_state(s, live_tools=True, live_plan=params(library_open=None),
                             planner_mode='deterministic')
        self.assertEqual(result.status, 'needs_clarification')
        self.assertIn('Library opening',result.answer)

    def test_missing_pickup_deadline_aborts_without_network(self):
        s=state()
        s.constraints=[c for c in s.constraints if c.kind != 'deadline']
        with patch('mina_live_planning.get_route_report', side_effect=AssertionError('NO NETWORK')):
            result=run_state(s, live_tools=True, live_plan=params(), planner_mode='deterministic')
        self.assertEqual(result.status,'needs_clarification')
        self.assertIn('School pickup requires', result.answer)

    def test_routing_provider_failure_fails_closed(self):
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=ToolUnavailable('private-key-leak')):
            result=run_state(state(), live_tools=True, live_plan=params(), planner_mode='deterministic')
        self.assertEqual(result.status,'tool_unavailable')
        self.assertIn('No synthetic travel time was substituted', result.answer)
        self.assertNotIn('private-key-leak', result.answer)

    def test_write_gate_precedes_any_live_route_calls(self):
        s=state()
        s.user_request='Add a school event to my calendar'
        with patch('mina_live_planning._require_key', side_effect=AssertionError('SHOULD NOT ACCESS')):
            result=run_state(s, live_tools=True, live_plan=params(), planner_mode='deterministic')
        self.assertEqual(result.status,'approval_required')
        self.assertEqual(result.trace[1]['step'],'safety')

    def test_live_plan_opt_in_required(self):
        with self.assertRaises(ValueError):
            run_state(state(), live_tools=False, live_plan=params(), planner_mode='deterministic')

    def test_invalid_user_supplied_parameters_and_conflicts(self):
        with patch('mina_live_planning._require_key', side_effect=AssertionError('NO NETWORK')):
            bad = [params(start_time='25:00'), params(travel_buffer_minutes=-1),
                   params(durations={'library':0,'groceries':90,'school_pickup':10}),
                   params(task_locations={'library': POINTS['library']}),
                   params(library_open='13:00')]
            for p in bad:
                with self.subTest(param=p):
                    result=run_state(state(), live_tools=True, live_plan=p, planner_mode='deterministic')
                    self.assertEqual(result.status,'needs_clarification')

    def test_llm_generated_order_still_passes_deterministic_critic(self):
        fake = FakeLLM(json.dumps({'candidates': [
            ['school_pickup','groceries','library'],
            ['library','groceries','school_pickup']
        ]}))
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result=plan_with_live_routes(state(), params(), client=fake, planner_mode='llm')
        self.assertEqual(result.status,'provisional_live_route_plan')
        self.assertEqual(sum(c['feasible'] for c in result.candidates),2)
        self.assertTrue(result.candidates[0]['reason'].startswith('School pickup must'))

    def test_llm_outage_bounded_fallback(self):
        fake = FakeLLM(None)
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result=plan_with_live_routes(state(), params(), client=fake, planner_mode='llm')
        self.assertEqual(result.status,'provisional_live_route_plan')
        self.assertTrue(any(t.get('method')=='bounded fallback' for t in result.trace))

    def test_audit_does_not_contain_route_coordinates_or_secrets(self):
        from mina_audit import audit_record
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k: \
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result=run_state(state(), live_tools=True, live_plan=params(), planner_mode='deterministic')
        log = json.dumps(audit_record(result, mode='deterministic', rag_enabled=False, elapsed_ms=200))
        self.assertNotIn('-78.', log)
        self.assertNotIn('fake', log)
        self.assertIn('provisional_live_route_plan',log)

    def test_original_synthetic_path_unchanged_without_live_plan(self):
        with patch('mina_live_planning.get_route_report',side_effect=AssertionError('NO NETWORK')):
            result=run_state(state(), live_tools=False, planner_mode='deterministic')
        self.assertEqual(result.status, 'synthetic_plan')
        self.assertIn('SYNTHETIC',result.answer)


if __name__=='__main__':
    unittest.main()
