"""Offline v2.13 regression suite: mocked ORS; no network and no user addresses."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from mina_time_window_planner_v213 import (
    LiveRouteError, _validated_matrix, _validated_geometry, _point,
    plan_family_route, planner_candidates, critic_candidate,
    controller_select, pickup_window_from_target, _js_json,
)

# Geographic data below are synthetic, nowhere near the user's private home.
P={'origin':'-78.100,35.100', 'groceries':'-78.200,35.200',
   'library':'-78.300,35.300', 'school_pickup':'-78.400,35.400'}
TASKS=('library','groceries','school_pickup')
D={'groceries':30,'library':20,'school_pickup':15}
WIN=('3:15 PM','3:30 PM')

# Node order origin, groceries, library, school; two complete candidate orders.
MATRIX={'durations':[[0,660,840,1800],
                     [900,0,180,1800],
                     [900,180,0,240],
                     [1800,1800,1800,0]],
        'distances':[[0,3200,4800,9200],
                     [3700,0,4200,7000],
                     [5300,1200,0,1500],
                     [8200,7200,3500,0]]}

GEO={'type':'FeatureCollection','features':[{'type':'Feature',
    'geometry':{'type':'LineString','coordinates':[[-78.100,35.100],[-78.200,35.200],[-78.300,35.300],[-78.400,35.400]]},
    'properties':{'summary':{'distance':16000,'duration':1090}}}]}


def run(**overrides):
    kw=dict(origin=P['origin'],locations={k:P[k] for k in TASKS},tasks=TASKS,
            depart_time='12:30 PM',plan_date='2026-11-23',durations=D,
            pickup_window=WIN,library_open='9:00 AM',buffer_minutes=15,
            store_label='Costco',matrix_fetcher=lambda coords:MATRIX,
            geometry_fetcher=lambda coords:GEO)
    kw.update(overrides)
    return plan_family_route(**kw)

class TimeWindowPlannerV213Tests(unittest.TestCase):
    def test_school_always_last_and_both_orders_have_all_tasks(self):
        all_orders=planner_candidates(TASKS)
        self.assertEqual(len(all_orders),2)
        self.assertTrue(all(x[-1]=='school_pickup' for x in all_orders))
        self.assertTrue(all(set(x)==set(TASKS) for x in all_orders))
    def test_main_prompt_selected_inside_critic_not_posthoc(self):
        r=run()
        self.assertEqual(r.status,'provisional_live_route_plan')
        c=next(t for t in r.trace if t['step']=='controller')
        self.assertEqual(c['selected'],['groceries','library','school_pickup'])
        self.assertEqual(c['decision'],'selected_feasible_only')
        self.assertIn('12:56 PM–1:26 PM',r.answer)
        self.assertIn('1:44 PM–2:04 PM',r.answer)
        self.assertIn('2:04 PM–2:56 PM',r.answer)
        self.assertIn('3:15 PM–3:30 PM',r.answer)
        self.assertIn('Planner → Critic → Controller',r.answer)
        self.assertNotIn('Original backend route ETAs',r.answer)
        self.assertTrue(r.route_map_html)
        self.assertNotIn('Public demo locations',r.route_map_html)
        self.assertEqual(r.trace[-1]['selected_order'],c['selected'])
        self.assertFalse(any(t['step']=='pickup_window_guard' for t in r.trace))
    def test_controller_selects_alternate_when_first_route_misses_pickup(self):
        alternate={k:[row[:] for row in values] for k,values in MATRIX.items()}
        alternate['durations'][2][3] = 60*60  # library -> school too slow
        alternate['durations'][1][3] = 10*60  # groceries -> school fine
        seen=[]
        def geometry(coords):
            seen.extend(coords)
            return GEO
        r=run(matrix_fetcher=lambda _:alternate, geometry_fetcher=geometry)
        self.assertEqual(r.status,'provisional_live_route_plan')
        self.assertEqual(next(t for t in r.trace if t['step']=='controller')['selected'],
                         ['library','groceries','school_pickup'])
        self.assertEqual(sum(c['feasible'] for c in r.candidates),1)
        self.assertEqual(seen, [[-78.100,35.100],[-78.300,35.300],
                                [-78.200,35.200],[-78.400,35.400]])
        self.assertEqual(r.trace[-1]['same_order_as_controller'],True)

    def test_library_opening_can_make_all_routes_infeasible(self):
        r=run(library_open='3:00 PM')
        self.assertEqual(r.status,'no_feasible_plan')
        self.assertFalse(r.route_map_html)

    def test_reject_window_that_cannot_fit_service_without_provider_call(self):
        r=run(pickup_window=('3:15 PM','3:30 PM'),
              durations={'groceries':30,'library':20,'school_pickup':20},
              matrix_fetcher=lambda _: self.fail('must not call provider'))
        self.assertEqual(r.status,'no_feasible_plan')
        self.assertFalse(r.route_map_html)
    def test_reject_late_candidates_and_do_not_produce_map(self):
        r=run(depart_time='3:00 PM',geometry_fetcher=lambda _:self.fail('no route map'))
        self.assertEqual(r.status,'no_feasible_plan')
        self.assertTrue(all(not x['feasible'] for x in r.candidates))
        self.assertEqual(r.trace[-1]['selected'],None)
    def test_missing_matrix_leg_is_not_feasibility_claim(self):
        matrix={'durations':[row[:] for row in MATRIX['durations']]}
        matrix['durations'][0][1]=None
        matrix['durations'][0][2]=None
        r=run(matrix_fetcher=lambda _:matrix)
        self.assertEqual(r.status,'needs_clarification')
        self.assertFalse(r.route_map_html)
        self.assertTrue(all(c['reason']=='travel_estimate_missing' for c in r.candidates))
    def test_hours_opening_delays_library_service_and_checks_school(self):
        r=run(library_open='2:00 PM')
        self.assertEqual(r.status,'provisional_live_route_plan')
        self.assertIn('Wait for the user-entered opening window',r.answer)
        self.assertIn('School pickup',r.answer)
    def test_missing_pickup_window_never_guessed(self):
        with self.assertRaises(LiveRouteError) as cm:
            run(pickup_window=None)
        self.assertEqual(cm.exception.code,'missing_pickup_window')
    def test_saved_pickup_target_window(self):
        self.assertEqual(pickup_window_from_target('3:15 PM',15),WIN)
        self.assertIsNone(pickup_window_from_target(None,15))
    def test_invalid_matrix_and_coords_fail_closed(self):
        with self.assertRaises(LiveRouteError):
            run(matrix_fetcher=lambda _: {'durations':[[0]]})
        with self.assertRaises(LiveRouteError):
            _point('nan,35.2')
        with self.assertRaises(LiveRouteError):
            _validated_matrix({'durations':[[float('nan')]]},1)
    def test_map_label_encoding_cannot_close_script(self):
        self.assertNotIn('</script>',_js_json([{'label':'</script><script>alert(1)</script>'}]))
        self.assertIn(r'\u003c',_js_json('<'))

    def test_provider_outage_yields_redacted_message(self):
        def bad(_):
            raise RuntimeError('PRIVATE_ADDRESS ORSKEY')
        with self.assertRaises(LiveRouteError) as cm:
            run(matrix_fetcher=bad)
        self.assertEqual(cm.exception.code,'provider_unavailable')
        self.assertNotIn('PRIVATE_ADDRESS',str(cm.exception))
        self.assertNotIn('ORSKEY',str(cm.exception))
    def test_geometry_failure_keeps_valid_schedule_but_no_fake_map(self):
        r=run(geometry_fetcher=lambda coords: {'features': []})
        self.assertEqual(r.status,'provisional_live_route_plan')
        self.assertIsNone(r.route_map_html)
        self.assertEqual(r.trace[-1]['status'],'not_displayed')
    def test_hub_planning_path_does_not_use_old_posthoc_guard(self):
        app=Path(__file__).with_name('streamlit_app.py').read_text(encoding='utf8')
        ast.parse(app)
        self.assertIn('result = plan_family_route(',app)
        self.assertIn('pickup_window=schedule_window',app)
        segment=app[app.index('result = plan_family_route('):app.index('result.trace.insert(0,',app.index('result = plan_family_route('))]
        self.assertNotIn('apply_pickup_window_guard',segment)
        self.assertIn("'route_map_html': getattr(result, 'route_map_html', None)",app)
    def test_no_real_address_or_coords_in_trace_or_answer(self):
        r=run()
        self.assertNotIn('-78.100',r.answer+str(r.trace))
        self.assertNotIn('API',str(r.trace))
    def test_candidate_critic_rejects_scope_violation(self):
        secs,_=_validated_matrix(MATRIX,4)
        c=critic_candidate(('library','school_pickup'),tasks=TASKS,start_minutes=750,
                          durations=D,matrix_seconds=secs,indices={'origin':0,'groceries':1,'library':2,'school_pickup':3},
                          buffer_minutes=15,windows={'school_pickup':(915,930)})
        self.assertFalse(c.feasible)
        self.assertEqual(c.reason,'missing_or_duplicate_tasks')
    def test_controller_never_selects_invalid_candidate(self):
        secs,_=_validated_matrix(MATRIX,4)
        c=critic_candidate(('library','school_pickup'),tasks=TASKS,start_minutes=750,
                          durations=D,matrix_seconds=secs,indices={'origin':0,'groceries':1,'library':2,'school_pickup':3},
                          buffer_minutes=15,windows={'school_pickup':(915,930)})
        self.assertIsNone(controller_select([c]))

if __name__=='__main__':unittest.main()
