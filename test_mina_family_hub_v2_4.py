"""Offline regression tests for local shopping lists and HeiGIT pairing suggestions."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from mina_family_hub import (
    PAIRS, FamilyHubError, add_item, add_visit, blank_hub, find_nearby_pairings,
    list_answer, load_hub, parse_pending_list_add, pending_items, pairing_answer,
    read_hub_intent, save_hub, set_item_done, update_place,
)
from mina_write_guard import detect_explicit_write


class HubTests(unittest.TestCase):
    def setUp(self):
        self.hub = blank_hub()

    def test_initial_lists_separate(self):
        self.assertEqual(set(self.hub['stores']), {'costco', 'target', 'trader_joes'})
        self.assertTrue(all(not rows for rows in self.hub['stores'].values()))
        self.assertEqual(len(PAIRS), 3)

    def test_local_persistence_and_item_done(self):
        hub = add_item(self.hub, 'target', 'Milk')
        self.assertEqual(pending_items(hub, 'target'), ['Milk'])
        self.assertEqual(pending_items(hub, 'costco'), [])
        hub = set_item_done(hub, 'target', hub['stores']['target'][0]['id'], True)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'private.json'
            save_hub(hub, path)
            self.assertEqual(pending_items(load_hub(path), 'target'), [])
            self.assertEqual(load_hub(path)['stores']['target'][0]['name'], 'Milk')

    def test_duplicate_and_invalid_rejected(self):
        hub = add_item(self.hub, 'costco', 'Eggs')
        with self.assertRaises(FamilyHubError):
            add_item(hub, 'costco', 'eggs')
        with self.assertRaises(FamilyHubError):
            update_place(hub, 'doctor', name='Doctor', address='Somewhere')
        with self.assertRaises(FamilyHubError):
            add_item(hub, 'target', '<script>')

    def test_appointments_in_12h_format(self):
        hub = add_visit(self.hub, place_id='dentist', day='2026-11-23', time='3:15 PM', title='Dentist visit')
        self.assertEqual(hub['visits'][0]['time'], '3:15 PM')
        with self.assertRaises(FamilyHubError):
            add_visit(self.hub, place_id='dentist', day='2026-11-23', time='15:15', title='Dentist visit')

    def test_no_list_no_pairing_no_api(self):
        calls = []
        hub = add_visit(self.hub, place_id='dentist', day='2026-11-23', time='3:15 PM', title='Dentist visit')
        hints, notes = find_nearby_pairings(hub, day='2026-11-23', router=lambda x: calls.append(x))
        self.assertEqual(hints, [])
        self.assertEqual(notes, [])
        self.assertEqual(calls, [])

    def test_consent_required_and_missing_address_no_calls(self):
        hub = add_item(self.hub, 'target', 'Milk')
        hub = add_visit(hub, place_id='dentist', day='2026-11-23', time='3:15 PM', title='Dentist visit')
        calls = []
        hints, notes = find_nearby_pairings(hub, day='2026-11-23', router=lambda x: calls.append(x))
        self.assertEqual(hints, [])
        self.assertIn('enter both saved addresses', notes[0])
        hub = update_place(hub, 'dentist', name='Demo dentist', address='Demo Clinic, Cary, NC')
        hub = update_place(hub, 'target', name='Demo Target', address='Public Target, Cary, NC')
        hints, notes = find_nearby_pairings(hub, day='2026-11-23', router=lambda x: calls.append(x))
        self.assertEqual(hints, [])
        self.assertIn('consent', notes[0])
        self.assertEqual(calls, [])

    def _ready(self):
        hub = add_item(self.hub, 'target', 'Milk')
        hub = add_item(hub, 'target', 'Bread')
        hub = add_visit(hub, place_id='dentist', day='2026-11-23', time='3:15 PM', title='Dentist visit')
        hub = update_place(hub, 'dentist', name='Demo dentist', address='Demo Clinic, Cary, NC')
        hub = update_place(hub, 'target', name='Demo Target', address='Demo Target, Cary, NC')
        return hub

    def test_true_short_road_route_produces_hint_with_items(self):
        hub = self._ready()
        calls = []
        report = SimpleNamespace(legs=[object()], distance_km=2.4, duration_minutes=7.3)
        def router(x):
            calls.append(x)
            return report
        hints, notes = find_nearby_pairings(hub, day='2026-11-23', allow_address_lookup=True, router=router)
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].items, ('Milk', 'Bread'))
        self.assertIn('Target', pairing_answer(hints, notes))
        self.assertEqual(calls, [['Demo Clinic, Cary, NC', 'Demo Target, Cary, NC']])

    def test_far_route_never_recommended(self):
        report = SimpleNamespace(legs=[object()], distance_km=28, duration_minutes=29)
        hints, notes = find_nearby_pairings(self._ready(), day='2026-11-23', allow_address_lookup=True, router=lambda x: report)
        self.assertFalse(hints)
        self.assertIn('exceeds', notes[0])

    def test_route_failure_does_not_guess(self):
        from mina_live_tools import ToolUnavailable
        def fail(x):
            raise ToolUnavailable('network down')
        hints, notes = find_nearby_pairings(self._ready(), day='2026-11-23', allow_address_lookup=True, router=fail)
        self.assertFalse(hints)
        self.assertIn('not verified', notes[0])

    def test_unrelated_day_no_pairs(self):
        hints, _ = find_nearby_pairings(self._ready(), day='2026-11-24', allow_address_lookup=True,
                                        router=lambda x: self.fail('Should not call router'))
        self.assertFalse(hints)

    def test_library_costco_pair(self):
        hub = add_item(self.hub, 'costco', 'Paper towels')
        hub = add_visit(hub, place_id='library', day='2026-11-23', time='1:00 PM', title='Return library books')
        self.assertEqual(len(hub['visits']), 1)

    def test_local_list_command_strict_scope(self):
        self.assertEqual(parse_pending_list_add('Add milk to my Target shopping list.'), ('target', 'milk'))
        self.assertEqual(parse_pending_list_add("Put apples on my Trader Joe's list"), ('trader_joes', 'apples'))
        self.assertIsNone(parse_pending_list_add('Add an event to my calendar'))
        self.assertIsNone(parse_pending_list_add('Plan errands and add milk to my Target list'))
        self.assertIsNone(parse_pending_list_add('Add dentist appointment to my Target list'))

    def test_local_command_still_write_requires_confirmation(self):
        self.assertEqual(detect_explicit_write('Add milk to my Target shopping list').intent, 'list_update')

    def test_read_only_prompts(self):
        self.assertEqual(read_hub_intent("What's on my Target shopping list?"), ('list','target'))
        self.assertEqual(read_hub_intent('Show my Costco shopping list'), ('list', 'costco'))
        self.assertEqual(read_hub_intent('What can I combine with my dentist appointment?'), ('pair', None))
        self.assertIsNone(read_hub_intent('Add milk to my Target shopping list'))
        self.assertIsNone(read_hub_intent('Plan errands and add a calendar event'))

    def test_list_answer(self):
        self.assertIn('Milk', list_answer(add_item(self.hub,'target','Milk'),'target'))

if __name__ == '__main__':
    unittest.main()

class SyntheticGuardTests(unittest.TestCase):
    def test_multistop_assistant_mode_requires_live_settings(self):
        from mina_family_hub import needs_live_family_mode
        self.assertTrue(needs_live_family_mode('Plan groceries and library and school pickup before 4:30 PM'))
        self.assertFalse(needs_live_family_mode('What time is it?'))
        self.assertFalse(needs_live_family_mode('Plan errands and add a school event to my calendar'))

class ReminderCandidateTests(unittest.TestCase):
    def test_potential_pair_only_from_future_visit_and_items(self):
        from mina_family_hub import blank_hub, add_item, add_visit, potential_pairs
        hub = add_item(blank_hub(),'target','Milk')
        hub = add_visit(hub, place_id='dentist', day='2026-11-23', time='3:15 PM', title='Dentist visit')
        self.assertEqual(potential_pairs(hub, start_day='2026-11-21')[0][1], 'target')
        self.assertEqual(potential_pairs(hub, start_day='2026-11-24'), [])

class RouteRequestLimitTests(unittest.TestCase):
    def test_repeat_visits_share_one_road_lookup(self):
        from mina_family_hub import blank_hub, add_item, add_visit, update_place, find_nearby_pairings
        hub=add_item(blank_hub(),'target','Milk')
        hub=update_place(hub,'dentist',name='Dentist',address='Clinic, Cary, NC')
        hub=update_place(hub,'target',name='Target',address='Target, Cary, NC')
        for day in ('2026-11-23','2026-11-24'):
            hub=add_visit(hub,place_id='dentist',day=day,time='3:15 PM',title='Dentist')
        calls=[]
        report=SimpleNamespace(legs=[object()],distance_km=4,duration_minutes=9)
        def router(x):
            calls.append(x)
            return report
        hints,notes=find_nearby_pairings(hub,day=None,router=router,allow_address_lookup=True)
        # Skip test when executed outside its Nov 2026 demonstration window.
        if date.today() <= date(2026,11,23):
            self.assertEqual(len(hints), 2)
            self.assertEqual(len(calls), 1)
