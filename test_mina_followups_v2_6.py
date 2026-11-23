"""Offline checks for v2.6; not live browser or background push tests."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mina_family_hub import FamilyHubError, blank_hub, add_item, add_visit, pending_items
from mina_auto_mode import apply_local_action
from mina_followups import (
    blank_followups, validate_followups, acknowledge, record_visit, record_shopping,
    due_reminders, due_checkins, save_followups, load_followups,
    parse_purchased_all, clear_store_after_purchase,
)

TZ = ZoneInfo('America/New_York')


def sample(now, store='target'):
    hub = add_item(blank_hub(), store, 'Bread')
    hub = add_item(hub, store, 'Milk')
    hub = add_visit(hub, place_id='dentist', day=now.date().isoformat(),
                    time='11:00 AM', end_time='1:00 PM', title='Dentist appointment')
    return hub


class LocalPersistence(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(validate_followups(blank_followups())['schema_version'], '1.0')

    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'local' / 'notes.json'
            self.assertEqual(load_followups(path), blank_followups())
            data = acknowledge(blank_followups(), 'visit_1', '24h')
            save_followups(data, path)
            self.assertEqual(load_followups(path), data)

    def test_invalid_key_rejected(self):
        data = blank_followups()
        data['reminders_ack']['something_bad'] = True
        with self.assertRaises(FamilyHubError):
            validate_followups(data)

    def test_invalid_ack_stage(self):
        with self.assertRaises(FamilyHubError):
            acknowledge(blank_followups(), 'visit_1', '3h')

    def test_visit_status(self):
        self.assertEqual(record_visit(blank_followups(), 'visit_1', 'attended')['visit_outcomes']['visit_1'], 'attended')

    def test_visit_status_invalid(self):
        with self.assertRaises(FamilyHubError):
            record_visit(blank_followups(), 'visit_1', 'booked')

    def test_shopping_status(self):
        self.assertEqual(record_shopping(blank_followups(), 'visit_1', 'partial')['shopping_outcomes']['visit_1'], 'partial')


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 23, 11, 0, tzinfo=TZ)
        self.hub = sample(self.start)
        self.data = blank_followups()

    def test_more_than_24h_not_due(self):
        self.assertEqual(due_reminders(self.hub, self.data, now=self.start-timedelta(hours=25)), [])

    def test_24h_at_exact_trigger(self):
        info = due_reminders(self.hub, self.data, now=self.start-timedelta(hours=24))
        self.assertEqual(info[0]['stage'], '24h')
        self.assertEqual(info[0]['pending_items'], ['Bread', 'Milk'])

    def test_24h_until_two_hour_stage(self):
        info = due_reminders(self.hub, self.data, now=self.start-timedelta(hours=3))
        self.assertEqual(info[0]['stage'], '24h')

    def test_acknowledged_not_shown(self):
        records = acknowledge(self.data, 'visit_1', '24h')
        self.assertEqual(due_reminders(self.hub, records, now=self.start-timedelta(hours=12)), [])

    def test_2h_stage(self):
        info = due_reminders(self.hub, self.data, now=self.start-timedelta(hours=2))
        self.assertEqual(info[0]['stage'], '2h')

    def test_2h_new_even_if_24h_ack(self):
        records = acknowledge(self.data, 'visit_1', '24h')
        info = due_reminders(self.hub, records, now=self.start-timedelta(minutes=110))
        self.assertEqual(info[0]['stage'], '2h')

    def test_no_reminder_after_appointment(self):
        self.assertEqual(due_reminders(self.hub, self.data, now=self.start), [])
        self.assertEqual(due_reminders(self.hub, self.data, now=self.start+timedelta(minutes=1)), [])

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            due_reminders(self.hub, self.data, now=datetime(2026,11,22,11))

    def test_checkin_only_yesterday(self):
        self.assertEqual(due_checkins(self.hub, self.data, today=date(2026,11,23)), [])
        checks = due_checkins(self.hub, self.data, today=date(2026,11,24))
        self.assertEqual(len(checks), 1)
        self.assertIsNone(checks[0]['visit_outcome'])

    def test_after_attended_asks_store(self):
        records = record_visit(self.data, 'visit_1', 'attended')
        checks = due_checkins(self.hub, records, today=date(2026,11,24))
        self.assertEqual(checks[0]['paired_store'], 'target')
        self.assertEqual(checks[0]['pending_items'], ['Bread', 'Milk'])

    def test_after_missed_no_store_question(self):
        records = record_visit(self.data, 'visit_1', 'missed')
        self.assertEqual(due_checkins(self.hub, records, today=date(2026,11,24)), [])

    def test_not_yet_stops_repeat(self):
        records = record_visit(self.data, 'visit_1', 'attended')
        records = record_shopping(records, 'visit_1', 'not_yet')
        self.assertEqual(due_checkins(self.hub, records, today=date(2026,11,24)), [])

    def test_done_empty_stops_repeat(self):
        records = record_visit(self.data, 'visit_1', 'attended')
        ids = [item['id'] for item in self.hub['stores']['target']]
        clean = clear_store_after_purchase(self.hub, 'target', expected_item_ids=ids)
        self.assertEqual(due_checkins(clean, records, today=date(2026,11,24)), [])


class PurchaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.hub = add_item(add_item(blank_hub(), 'target', 'Milk'), 'target', 'Bread')

    def test_voice_completed_explicit(self):
        for p in ('Mina, I bought everything at Target',
                  'I purchased all items at Costco',
                  "I got everything from Trader Joe's"):
            self.assertIsNotNone(parse_purchased_all(p))

    def test_no_bare_yes_or_future_or_partial(self):
        for p in ('Yes', 'I will buy everything at Target', 'I bought milk at Target',
                  'Clear Target', 'I bought everything at Target and send an email',
                  'I bought everything at Target and Costco'):
            self.assertIsNone(parse_purchased_all(p), p)

    def test_safe_clear_only_confirmed_path(self):
        ids = [x['id'] for x in self.hub['stores']['target']]
        action = {'kind':'clear_list','store':'target','expected_item_ids':ids}
        new = apply_local_action(self.hub, action)
        self.assertEqual(new['stores']['target'], [])
        self.assertEqual(len(self.hub['stores']['target']), 2)

    def test_stale_confirmation_rejected(self):
        ids = [x['id'] for x in self.hub['stores']['target']]
        changed = add_item(self.hub, 'target', 'Eggs')
        with self.assertRaises(FamilyHubError):
            apply_local_action(changed, {'kind':'clear_list','store':'target','expected_item_ids':ids})

    def test_cannot_clear_wrong_store(self):
        with self.assertRaises(FamilyHubError):
            clear_store_after_purchase(self.hub, 'costco', expected_item_ids=[])

    def test_one_store_only(self):
        h = add_item(self.hub, 'costco', 'Coffee')
        ids = [it['id'] for it in h['stores']['target']]
        new = apply_local_action(h, {'kind':'clear_list','store':'target','expected_item_ids':ids})
        self.assertEqual(pending_items(new, 'costco'), ['Coffee'])

    def test_invalid_clear_no_write(self):
        with self.assertRaises(FamilyHubError):
            apply_local_action(self.hub, {'kind':'clear_list','store':'target','expected_item_ids':['bad']})
        self.assertEqual(pending_items(self.hub,'target'), ['Milk', 'Bread'])

if __name__ == '__main__':
    unittest.main()

class SpokenFollowupTests(unittest.TestCase):
    def setUp(self):
        from mina_followups import parse_yesterday_visit_status, parse_yesterday_shopping_status
        self.visit_parser = parse_yesterday_visit_status
        self.shop_parser = parse_yesterday_shopping_status
        self.today = date(2026, 11, 24)
        self.hub = sample(datetime(2026, 11, 23, 11, tzinfo=TZ))
        self.records = blank_followups()

    def test_yes_attended(self):
        data = self.visit_parser('Mina, yes, I went to the dentist yesterday', self.hub, self.records, today=self.today)
        self.assertEqual(data, {'visit_id':'visit_1', 'place':'dentist', 'outcome':'attended'})

    def test_missed(self):
        data = self.visit_parser('I missed my dentist appointment yesterday', self.hub, self.records, today=self.today)
        self.assertEqual(data['outcome'], 'missed')

    def test_no_bare_yes(self):
        self.assertIsNone(self.visit_parser('yes',self.hub,self.records,today=self.today))

    def test_reject_compound(self):
        self.assertIsNone(self.visit_parser('I went to the dentist yesterday and book my calendar',self.hub,self.records,today=self.today))

    def test_avoid_duplicate_status(self):
        self.records = record_visit(self.records, 'visit_1', 'attended')
        self.assertIsNone(self.visit_parser('I went to the dentist yesterday',self.hub,self.records,today=self.today))

    def test_not_yet_target(self):
        self.records = record_visit(self.records, 'visit_1', 'attended')
        data = self.shop_parser("I didn't go to Target yesterday",self.hub,self.records,today=self.today)
        self.assertEqual(data, {'visit_id':'visit_1','store':'target','outcome':'not_yet'})

    def test_partial_target(self):
        self.records = record_visit(self.records, 'visit_1', 'attended')
        data = self.shop_parser('I bought only some items at Target',self.hub,self.records,today=self.today)
        self.assertEqual(data['outcome'], 'partial')

    def test_no_cross_store(self):
        self.records = record_visit(self.records, 'visit_1', 'attended')
        self.assertIsNone(self.shop_parser("I didn't go to Costco yesterday",self.hub,self.records,today=self.today))

class YesterdayVoiceEntryTests(unittest.TestCase):
    def test_save_yesterday_visit_proposal_date(self):
        from mina_auto_mode import parse_voice_visit
        parsed = parse_voice_visit('Mina, I had a dentist appointment yesterday from 11 AM to 1 PM', today=date(2026, 11, 24))
        self.assertEqual(parsed['date'], '2026-11-23')
        self.assertEqual(parsed['end_time'], '1:00 PM')
