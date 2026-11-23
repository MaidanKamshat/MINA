"""v2.14 conversational slot-fill acceptance checks — offline, synthetic only."""
from __future__ import annotations

import ast
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock
import unittest

from mina_conversation_state_v214 import (
    VERSION, PENDING_TTL_MINUTES, create_pending_route, decide_followup,
    pending_route_caption,
)
from mina_route_bridge_v212 import build_route_inputs
from mina_trip_voice_v212 import classify_multi_stop_route
from mina_time_window_planner_v213 import plan_family_route, pickup_window_from_target

TODAY = date(2026,11,22)
NOW = datetime(2026,11,22,13,0,tzinfo=timezone.utc)
ORIGINAL = ("Mina, I need to visit Costco and the library before picking up my child from school "
            "tomorrow. Help me plan the best route. I haven't decided what time I'll leave home.")
HUB = {
    'preferences': {
        'home_address':'SYNTHETIC START', 'school_address':'SYNTHETIC SCHOOL',
        'pickup_time':'3:15 PM','pickup_minutes':15,
        'shopping_minutes':45, 'library_minutes':15, 'buffer_minutes':15,
        'library_open_time':'9:00 AM',
    },
    'places': {'costco':{'name':'Costco','address':'SYNTHETIC COSTCO'},
               'library':{'name':'Library','address':'SYNTHETIC LIBRARY'}},
}
# Synthetic map coords and offline ORS fixtures from v2.13 acceptance tests.
P={'origin':'-78.100,35.100','groceries':'-78.200,35.200',
   'library':'-78.300,35.300','school_pickup':'-78.400,35.400'}
M={'durations':[[0,660,840,1800], [900,0,180,1800],
                [900,180,0,240], [1800,1800,1800,0]],
   'distances':[[0,3200,4800,9200], [3700,0,4200,7000],
                 [5300,1200,0,1500], [8200,7200,3500,0]]}
GEO={'type':'FeatureCollection','features':[{'type':'Feature',
    'geometry':{'type':'LineString','coordinates':[[-78.1,35.1],[-78.2,35.2],[-78.3,35.3],[-78.4,35.4]]},
    'properties':{'summary':{'distance':16000,'duration':1090}}}]}


def setup_pending(*, request=ORIGINAL):
    initial = build_route_inputs(request,today=TODAY,hub=HUB)
    assert initial.requested == {'groceries','library','school_pickup'}
    assert initial.start_time is None and initial.missing == ()
    return create_pending_route(request,date_anchor=TODAY,plan_date=initial.plan_date,
                                requested=initial.requested,now=NOW)


class SlotFillTests(unittest.TestCase):
    def test_missing_departure_has_minimal_private_session_state(self):
        p=setup_pending()
        self.assertEqual(p['version'],VERSION)
        self.assertEqual(p['plan_date'],'2026-11-23')
        self.assertEqual(p['kind'],'route_departure')
        self.assertIn('departure time',pending_route_caption(p))
        self.assertNotIn('SYNTHETIC START',str(p))
        self.assertNotIn('SYNTHETIC SCHOOL',str(p))

    def test_short_answer_fills_departure_and_preserves_date(self):
        p=setup_pending()
        d=decide_followup(p,'12:30 PM',now=NOW + timedelta(minutes=1))
        self.assertEqual(d.kind,'resume')
        self.assertEqual(d.original_date_anchor,TODAY)
        self.assertEqual(d.departure_time,'12:30 PM')
        self.assertIn('I will leave home at 12:30 PM.',d.effective_request)
        self.assertEqual(classify_multi_stop_route(d.effective_request),'route')
        bridge=build_route_inputs(d.effective_request,today=d.original_date_anchor,hub=HUB)
        self.assertEqual(bridge.start_time,'12:30 PM')
        self.assertEqual(bridge.plan_date,'2026-11-23')
        self.assertEqual(bridge.requested,{'groceries','library','school_pickup'})
        self.assertEqual(bridge.source_store,'costco')
        self.assertEqual(bridge.missing,())

    def test_natural_language_short_answers(self):
        p=setup_pending()
        for t in ('I am leaving home at 12:30 PM', 'Mina, at 12:30 p.m.',
                  'Actually, 12:30 PM.', 'I will leave home at 12:30 PM',
                  'We will leave home at 12:30 PM', '15:30'):
            with self.subTest(t=t):
                d=decide_followup(p,t,now=NOW)
                self.assertEqual(d.kind,'resume')
                self.assertIn('leave home at ',d.effective_request)

    def test_cannot_guess_time_or_apply_unrelated_instructions(self):
        p=setup_pending()
        for t in ('12:30','yes','okay'):
            with self.subTest(t=t):
                self.assertEqual(decide_followup(p,t,now=NOW).kind,'reprompt')
        for t in ('What is the weather?', 'Add eggs to Target list',
                  '12:30 PM and delete my shopping list',
                  '12:30 PM and send an email',
                  'Tomorrow I want a different route'):
            with self.subTest(t=t):
                self.assertEqual(decide_followup(p,t,now=NOW).kind,'new_request')
        self.assertEqual(decide_followup(None,'12:30 PM',now=NOW).kind,'none')

    def test_cancel_expire_and_state_validation(self):
        p=setup_pending()
        for c in ('Cancel route','Never mind','Cancel','Stop planning'):
            with self.subTest(c=c):
                self.assertEqual(decide_followup(p,c,now=NOW).kind,'cancel')
        expired=decide_followup(p,'12:30 PM',now=NOW+timedelta(minutes=PENDING_TTL_MINUTES+1))
        self.assertEqual(expired.kind,'expired')
        self.assertEqual(decide_followup({'kind':'junk'},'12:30 PM',now=NOW).kind,'new_request')

    def test_reject_wrong_calendar_or_unvalidated_route_as_pending(self):
        with self.assertRaises(ValueError):
            create_pending_route('Calendar note',date_anchor=TODAY,
                                  plan_date=None,requested={'calendar'},now=NOW)
        with self.assertRaises(ValueError):
            create_pending_route('',date_anchor=TODAY,
                                  plan_date=None,requested={'library','groceries'},now=NOW)
        with self.assertRaises(ValueError):
            create_pending_route('any',date_anchor=TODAY,
                                  plan_date=None,requested={'library'},now=NOW)

    def test_date_anchor_prevents_tomorrow_shift_on_next_day(self):
        p=setup_pending()
        d=decide_followup(p,'I am leaving home at 12:30 PM',now=NOW+timedelta(minutes=2))
        next_day=date(2026,11,23)
        self.assertEqual(build_route_inputs(d.effective_request,today=d.original_date_anchor,hub=HUB).plan_date,
                         '2026-11-23')
        self.assertEqual(build_route_inputs(d.effective_request,today=next_day,hub=HUB).plan_date,
                         '2026-11-24')

    def test_end_to_end_resumed_bridges_into_real_planner_with_offline_mock(self):
        p=setup_pending()
        d=decide_followup(p,'12:30 PM',now=NOW)
        b=build_route_inputs(d.effective_request,today=d.original_date_anchor,hub=HUB)
        window=pickup_window_from_target(HUB['preferences']['pickup_time'],b.durations['school_pickup'])
        result=plan_family_route(origin=P['origin'],locations={t:P[t] for t in b.requested},
                                 tasks=tuple(sorted(b.requested)),depart_time=b.start_time,
                                 plan_date=b.plan_date,durations=b.durations,
                                 pickup_window=window,library_open=b.library_open,
                                 buffer_minutes=b.buffer_minutes,store_label='Costco',
                                 matrix_fetcher=lambda _:M,geometry_fetcher=lambda _:GEO)
        self.assertEqual(result.status,'provisional_live_route_plan')
        self.assertEqual(next(t for t in result.trace if t['step']=='planner')['generated'],2)
        self.assertEqual(next(t for t in result.trace if t['step']=='critic')['passed'],2)
        self.assertEqual(next(t for t in result.trace if t['step']=='controller')['selected'],
                         ['groceries','library','school_pickup'])
        self.assertIn('3:15 PM',result.answer)

    def test_late_departure_is_rejected_even_after_short_answer(self):
        p=setup_pending()
        d=decide_followup(p,'3:00 PM',now=NOW)
        b=build_route_inputs(d.effective_request,today=d.original_date_anchor,hub=HUB)
        r=plan_family_route(origin=P['origin'],locations={t:P[t] for t in b.requested},
                            tasks=tuple(sorted(b.requested)),depart_time=b.start_time,
                            plan_date=b.plan_date,durations=b.durations,
                            pickup_window=pickup_window_from_target('3:15 PM',15),
                            library_open=b.library_open,buffer_minutes=b.buffer_minutes,
                            matrix_fetcher=lambda _:M,
                            geometry_fetcher=lambda _:self.fail('should not create fake map'))
        self.assertEqual(r.status,'no_feasible_plan')
        self.assertEqual(next(t for t in r.trace if t['step']=='controller')['selected'],None)

    def test_streamlit_integration_hooks_are_connected_to_main_route(self):
        app=Path(__file__).with_name('streamlit_app.py').read_text(encoding='utf8')
        ast.parse(app)
        self.assertIn("st.session_state['mina_pending_route'] = create_pending_route(",app)
        self.assertIn('conversation = decide_followup(',app)
        self.assertIn('prompt = conversation.effective_request',app)
        self.assertIn('today=route_today',app)
        self.assertIn("'status':'slot_filled_and_resumed'",app)
        self.assertIn("{'role': 'user', 'text': spoken_prompt}",app)
        self.assertIn("st.session_state['mina_pending_route'] = None",app)
        self.assertIn('Cancel pending route',app)
        self.assertIn('result = plan_family_route(',app)

if __name__=='__main__':unittest.main()
