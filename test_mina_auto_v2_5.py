"""Strict offline safety and auto-routing checks for MINA v2.5."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from mina_auto_mode import (
    apply_local_action, auto_route, is_explicit_local_confirmation,
    local_schedule_answer, parse_bulk_list_add, parse_directions, parse_voice_visit,
    time_window_advice,
)
from mina_family_hub import (
    FamilyHubError, blank_hub, add_visit, add_item, pending_items, save_hub,
    load_hub, set_preferences,
)
from mina_ui_adapter import status_caption

TODAY = date(2026,11,21)

class AutoRoutingTests(unittest.TestCase):
    def test_weather_time_simple(self):
        for prompt in ('What is the weather in Apex?', 'What time is it in North Carolina?'):
            self.assertEqual(auto_route(prompt, today=TODAY).kind, 'assistant')

    def test_complex_family_plan(self):
        self.assertEqual(auto_route('Plan library, groceries, and school pickup route', today=TODAY).kind, 'family_plan')

    def test_directions(self):
        result = auto_route('Show directions from Target, Cary NC to Library, Apex NC', today=TODAY)
        self.assertEqual(result.kind, 'directions')
        self.assertEqual(result.data, ('Target, Cary NC', 'Library, Apex NC'))

    def test_no_guessed_directions(self):
        self.assertIsNone(parse_directions('Where should I go?'))

    def test_local_list_read(self):
        self.assertEqual(auto_route('What is on my Target shopping list?', today=TODAY).kind, 'hub_read')

    def test_pairing_read(self):
        self.assertEqual(auto_route('What shopping can I combine with my dentist appointment?', today=TODAY).kind, 'hub_read')

    def test_schedule_read(self):
        self.assertEqual(auto_route('What do I have tomorrow?', today=TODAY).kind, 'schedule_read')

    def test_external_write_not_locally_approved(self):
        for prompt in ('Add a dentist appointment to my calendar', 'Send an email to my doctor',
                       'Mina, add bread to my Target list and email the doctor'):
            self.assertNotIn(auto_route(prompt, today=TODAY).kind,
                             {'local_list_proposal','local_visit_proposal'})

    def test_voice_list_multi(self):
        intent = auto_route('Mina, could you please add milk, eggs and bread to my Target shopping list?', today=TODAY)
        self.assertEqual(intent.kind, 'local_list_proposal')
        self.assertEqual(intent.data, {'store':'target', 'items':['milk','eggs','bread']})

    def test_voice_list_single(self):
        self.assertEqual(parse_bulk_list_add('Hey Mina, add milk to my Costco list') ,
                         {'store':'costco','items':['milk']})

    def test_trader_joes(self):
        self.assertEqual(parse_bulk_list_add("Add apples and bananas to my Trader Joe's list")['store'], 'trader_joes')

    def test_no_compound_external_operation(self):
        self.assertIsNone(parse_bulk_list_add('Add milk to my Target list and send an email'))

    def test_no_overlong_or_markup(self):
        self.assertIsNone(parse_bulk_list_add('Add <script> to my Target list'))
        self.assertIsNone(parse_bulk_list_add('Add ' + 'x'*400 + ' to my Target list'))

    def test_too_many_items_refused(self):
        self.assertIsNone(parse_bulk_list_add('Add ' + ', '.join('item' + str(n) for n in range(11)) + ' to my Target list'))

    def test_ambiguous_confirmation_not_accepted(self):
        self.assertFalse(is_explicit_local_confirmation('yes'))
        self.assertFalse(is_explicit_local_confirmation('confirm calendar event'))
        self.assertTrue(is_explicit_local_confirmation('Mina, confirm my local update'))

    def test_local_label_correct(self):
        self.assertIn('Local change proposed', status_caption('local_confirmation_required'))

class VisitAndPreferencesTests(unittest.TestCase):
    def test_tomorrow_time_range(self):
        v = parse_voice_visit('Mina, I have a dentist appointment tomorrow from 11 AM to 1 PM', today=TODAY)
        self.assertEqual((v['date'],v['time'],v['end_time']),('2026-11-22','11:00 AM','1:00 PM'))

    def test_named_date(self):
        v = parse_voice_visit('I have a pediatrician appointment on November 25 from 9:30 AM to 10:15 AM', today=TODAY)
        self.assertEqual(v['date'], '2026-11-25')

    def test_24h_visit_input_not_silently_assumed(self):
        self.assertIsNone(parse_voice_visit('I have a dentist appointment tomorrow from 11:00 to 13:00', today=TODAY))

    def test_no_guessed_date(self):
        self.assertIsNone(parse_voice_visit('I have a dentist appointment at 11 AM', today=TODAY))

    def test_no_book_through_local(self):
        self.assertIsNone(parse_voice_visit('Book a dentist appointment tomorrow from 11 AM to 1 PM', today=TODAY))
        self.assertIsNone(parse_voice_visit('Add dentist appointment tomorrow at 11 AM to my calendar', today=TODAY))

    def test_bad_end_time(self):
        self.assertIsNone(parse_voice_visit('I have a dentist appointment tomorrow from 1 PM to 11 AM', today=TODAY))
        with self.assertRaises(FamilyHubError):
            add_visit(blank_hub(), place_id='dentist', day='2026-11-22', time='1:00 PM', end_time='11:00 AM', title='Dentist')

    def test_optional_end_time_backward_compatible(self):
        v = add_visit(blank_hub(), place_id='dentist', day='2026-11-22', time='11:00 AM', title='Old record')
        self.assertNotIn('end_time', v['visits'][0])

    def test_list_bulk_atomic(self):
        hub = blank_hub()
        action = {'kind':'list', 'store':'target', 'items':['Milk','Eggs','Bread']}
        result = apply_local_action(hub, action)
        self.assertEqual(pending_items(result,'target'),['Milk','Eggs','Bread'])
        self.assertEqual(pending_items(result,'costco'), [])
        self.assertEqual(pending_items(hub, 'target'), [])

    def test_duplicate_bulk_all_or_nothing(self):
        hub = add_item(blank_hub(),'target','Milk')
        with self.assertRaises(FamilyHubError):
            apply_local_action(hub, {'kind':'list','store':'target','items':['Eggs','Milk']})
        self.assertEqual(pending_items(hub,'target'), ['Milk'])

    def test_visit_saved_with_confirmed_action(self):
        info = parse_voice_visit('I have a dentist appointment tomorrow from 11 AM to 1 PM', today=TODAY)
        updated = apply_local_action(blank_hub(), {'kind':'visit','visit':info})
        self.assertEqual(updated['visits'][0]['end_time'],'1:00 PM')

    def test_save_load_old_hub_no_prefs(self):
        old = blank_hub()
        old.pop('preferences')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'test.json'
            save_hub(old,p)
            self.assertNotIn('preferences',load_hub(p))

    def test_new_prefs_persist(self):
        hub = set_preferences(blank_hub(),pickup_time='3:15 PM',school_address='School, Apex NC',home_address='',
                              shopping_minutes=45,lunch_minutes=45,buffer_minutes=20)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'test.json'
            save_hub(hub,p)
            self.assertEqual(load_hub(p)['preferences']['pickup_time'], '3:15 PM')

    def test_prefs_reject_24h(self):
        with self.assertRaises(ValueError):
            set_preferences(blank_hub(),pickup_time='15:15',school_address='',home_address='',
                            shopping_minutes=45,lunch_minutes=45,buffer_minutes=15)

    def test_local_day_summary_with_target(self):
        hub = add_item(blank_hub(), 'target','Bread')
        hub = add_visit(hub,place_id='dentist',day='2026-11-21',time='11:00 AM',end_time='1:00 PM',title='Dentist')
        answer = local_schedule_answer(hub,day=TODAY)
        self.assertIn('1:00 PM',answer)
        self.assertIn('Bread',answer)
        self.assertIn('not calendar-verified',answer)

    def test_schedule_empty_not_calendar_claim(self):
        self.assertIn('not a Google Calendar check',local_schedule_answer(blank_hub(),day=TODAY))

class TimeWindowTests(unittest.TestCase):
    def setUp(self):
        self.visit = {'time':'11:00 AM','end_time':'1:00 PM'}

    def test_missing_end_no_time_guess(self):
        self.assertIn('end time', time_window_advice({'time':'11:00 AM'},pickup_time='3:15 PM',first_leg_minutes=5))

    def test_missing_school_no_full_feasibility(self):
        answer = time_window_advice(self.visit,pickup_time='3:15 PM',first_leg_minutes=7)
        self.assertIn('NOT checked store-to-school',answer)
        self.assertIn('135 minutes',answer)

    def test_infeasible_skip_shopping(self):
        answer = time_window_advice(self.visit,pickup_time='1:25 PM',first_leg_minutes=15,
                                    school_leg_minutes=15,shopping_minutes=45,buffer_minutes=15)
        self.assertIn('skip shopping',answer)

    def test_lunch_not_fitting(self):
        answer = time_window_advice(self.visit,pickup_time='2:45 PM',first_leg_minutes=10,
                                    school_leg_minutes=15,shopping_minutes=45,lunch_minutes=45,buffer_minutes=20)
        self.assertIn('Lunch is not safely budgeted', answer)

    def test_tight_slack_warn(self):
        answer = time_window_advice(self.visit,pickup_time='3:15 PM',first_leg_minutes=7,
                                    school_leg_minutes=15,shopping_minutes=45,lunch_minutes=45,buffer_minutes=15)
        self.assertIn('very tight', answer)

    def test_sufficient_slack_still_provisional(self):
        answer = time_window_advice(self.visit,pickup_time='4:45 PM',first_leg_minutes=7,
                                    school_leg_minutes=15,shopping_minutes=30,lunch_minutes=30,buffer_minutes=15)
        self.assertIn('provisional', answer)
        self.assertIn('restaurant venue has been verified',answer)

if __name__ == '__main__':
    unittest.main()
