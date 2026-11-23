"""Offline safety/regression tests: no Google account or API calls required."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import Mock

from mina_calendar_v27 import (
    CalendarError, blank_calendar, validate, make_event, add_event, add_note,
    agenda, reminder_dates, due_calendar_reminders, acknowledge_reminder,
    load_demo_birthdays, load_calendar, save_calendar,
    parse_voice_calendar, calendar_read_intent, format_agenda,
)
from mina_google_calendar import (
    GoogleCalendarError, google_event_body, insert_event, list_events,
    connected_token_present,
)

TODAY = date(2026, 11, 21)
TZ = ZoneInfo('America/New_York')

class LocalCalendarTests(unittest.TestCase):
    def setUp(self):
        self.e = make_event('Dentist appointment','2027-03-06','11:30 AM',kind='appointment')
    def test_01_empty(self): self.assertEqual(validate(blank_calendar())['events'],[])
    def test_02_add(self): self.assertEqual(len(add_event(blank_calendar(),self.e)['events']),1)
    def test_03_duplicate_rejected(self):
        with self.assertRaises(CalendarError): add_event(add_event(blank_calendar(),self.e),self.e)
    def test_04_bad_end(self):
        with self.assertRaises((CalendarError,ValueError)): make_event('Visit','2027-03-06','11:30 AM','10:00 AM')
    def test_05_bad_date(self):
        with self.assertRaises(ValueError): make_event('Visit','2027-02-30','11:30 AM')
    def test_06_notes(self):
        x=add_note(blank_calendar(),'Bring insurance card',now=datetime(2026,11,21,tzinfo=TZ))
        self.assertEqual(x['notes'][0]['content'],'Bring insurance card')
    def test_07_note_text_sanitized(self):
        with self.assertRaises(CalendarError): add_note(blank_calendar(),'<script>alert(1)</script>')
    def test_08_roundtrip_local_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mina_calendar.json';data=add_event(blank_calendar(),self.e)
            save_calendar(data,p)
            self.assertEqual(load_calendar(p),data)
    def test_09_file_mode_private(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mina_calendar.json';save_calendar(blank_calendar(),p)
            self.assertEqual(p.stat().st_mode&0o077,0)
    def test_10_corrupt_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mina_calendar.json';p.write_text('{bad')
            with self.assertRaises(CalendarError): load_calendar(p)
            self.assertEqual(p.read_text(),'{bad')
    def test_11_demo_seven(self): self.assertEqual(len(load_demo_birthdays(blank_calendar())['events']),7)
    def test_12_demo_stays_marked(self):
        d=load_demo_birthdays(blank_calendar())
        self.assertTrue(all(x['source']=='demo' for x in d['events']))
    def test_13_demo_idempotent(self):
        d=load_demo_birthdays(blank_calendar())
        self.assertEqual(len(load_demo_birthdays(d)['events']),7)
    def test_14_demo_preserves_user(self):
        d=add_event(blank_calendar(),self.e)
        self.assertEqual(len(load_demo_birthdays(d)['events']),8)
    def test_15_yearly_birthdays_future(self):
        d=load_demo_birthdays(blank_calendar())
        a=agenda(d,date(2026,11,21),400)
        self.assertEqual(len(a),7)
        self.assertTrue(all(x['date']>='2026-11-21' for x in a))
    def test_16_reminder_march_day_before(self):
        t=reminder_dates(self.e)
        self.assertEqual(t['24h'].strftime('%Y-%m-%d %I:%M %p'),'2027-03-05 11:30 AM')
    def test_17_reminder_march_two_hours(self):
        self.assertEqual(reminder_dates(self.e)['2h'].strftime('%Y-%m-%d %I:%M %p'),'2027-03-06 09:30 AM')
    def test_18_24h_due(self):
        d=add_event(blank_calendar(),self.e)
        out=due_calendar_reminders(d,datetime(2027,3,5,12,0,tzinfo=TZ))
        self.assertEqual(len(out),1);self.assertEqual(out[0]['stage'],'1440')
    def test_19_2h_due(self):
        d=add_event(blank_calendar(),self.e)
        out=due_calendar_reminders(d,datetime(2027,3,6,10,0,tzinfo=TZ))
        self.assertEqual(out[0]['stage'],'120')
    def test_20_acknowledged(self):
        d=add_event(blank_calendar(),self.e)
        now=datetime(2027,3,6,10,0,tzinfo=TZ)
        key=due_calendar_reminders(d,now)[0]['key']
        self.assertEqual(due_calendar_reminders(acknowledge_reminder(d,key),now),[])
    def test_21_not_due_after_event(self):
        d=add_event(blank_calendar(),self.e)
        self.assertEqual(due_calendar_reminders(d,datetime(2027,3,6,12,0,tzinfo=TZ)),[])
    def test_22_local_agenda(self):
        d=add_event(blank_calendar(),self.e)
        self.assertIn('Dentist appointment',format_agenda(d,now=TODAY))
    def test_23_bad_schema_rejected(self):
        with self.assertRaises(CalendarError): validate({'events':[]})
    def test_24_reminder_naive_now_rejected(self):
        with self.assertRaises(CalendarError): due_calendar_reminders(blank_calendar(),datetime(2026,11,21))

class VoiceTests(unittest.TestCase):
    def parse(self,text): return parse_voice_calendar(text,today=TODAY)
    def test_25_dentist_date(self):
        p=self.parse('Mina, I have a dentist appointment on March 6 at 11:30 AM.')
        self.assertEqual(p['event']['date'],'2027-03-06')
    def test_26_pediatrician(self):
        p=self.parse('Mina, schedule a pediatrician appointment on March 6 at 11:30 AM to 1:00 PM.')
        self.assertEqual(p['event']['end_time'],'1:00 PM')
    def test_27_notes(self):
        self.assertEqual(self.parse('Mina, make a note: bring insurance card.')['content'],'bring insurance card')
    def test_28_birthday(self):
        p=self.parse('Mina, add Emma birthday on June 17.')
        self.assertEqual(p['event']['title'],'Emma birthday')
        self.assertEqual(p['event']['repeat'],'yearly')
    def test_29_possessive_birthday(self):
        p=self.parse("Mina, add Alicia's birthday on July 3.")
        self.assertEqual(p['event']['title'],'Alicia birthday')
    def test_30_compound_email_blocked(self):
        self.assertIsNone(self.parse('Mina, add dentist appointment March 6 at 11:30 AM and send my teacher an email.'))
    def test_31_shopping_not_calendar(self):
        self.assertIsNone(self.parse('Mina, add milk to my Target shopping list.'))
    def test_32_no_time_no_booking(self):
        self.assertIsNone(self.parse('Mina, please book a dentist appointment for March 6.'))
    def test_33_unambiguous_read(self):
        self.assertEqual(calendar_read_intent('Mina, what is on my calendar tomorrow?',today=TODAY)[1],date(2026,11,22))
    def test_34_notes_read(self):
        self.assertEqual(calendar_read_intent('Mina, show my notes.',today=TODAY)[0],'notes')
    def test_35_no_implict_write_on_read(self):
        self.assertIsNone(parse_voice_calendar('Mina, when is my next appointment?',today=TODAY))
    def test_36_calendar_read_doesnt_accept_writes(self):
        self.assertIsNone(calendar_read_intent('Mina, delete my calendar event',today=TODAY))

class GooglePayloadTests(unittest.TestCase):
    def setUp(self): self.e=make_event('Dentist appointment','2027-03-06','11:30 AM',kind='appointment')
    def test_37_reminders_1440_120(self):
        p=google_event_body(self.e)
        self.assertEqual([x['minutes'] for x in p['reminders']['overrides']],[1440,120])
    def test_38_start_timezone(self):
        p=google_event_body(self.e)
        self.assertEqual(p['start']['dateTime'],'2027-03-06T11:30:00-05:00')
    def test_39_default_one_hour_explicit_note(self):
        p=google_event_body(self.e)
        self.assertEqual(p['end']['dateTime'],'2027-03-06T12:30:00-05:00')
        self.assertIn('assumed',p['description'])
    def test_40_actual_end_respected(self):
        e=make_event('Doctor','2027-03-06','11:30 AM','1:00 PM',kind='appointment')
        self.assertEqual(google_event_body(e)['end']['dateTime'],'2027-03-06T13:00:00-05:00')
    def test_41_yearly_recurrence(self):
        e=make_event('Birthday','2027-03-06','9:00 AM',kind='birthday',repeat='yearly')
        self.assertEqual(google_event_body(e)['recurrence'],['RRULE:FREQ=YEARLY'])
    def test_42_demo_cannot_export(self):
        e=load_demo_birthdays(blank_calendar())['events'][0]
        with self.assertRaises(CalendarError):google_event_body(e)
    def test_43_fake_google_create(self):
        fake=Mock();fake.events.return_value.insert.return_value.execute.return_value={'id':'server-id','htmlLink':'https://calendar.google.com/x'}
        result=insert_event(self.e,service=fake)
        self.assertEqual(result['id'],'server-id')
        self.assertEqual(fake.events.return_value.insert.call_args.kwargs['sendUpdates'],'none')
    def test_44_existing_google_id_blocks_duplicate(self):
        self.e['google_event_id']='already-in-google'
        with self.assertRaises(GoogleCalendarError):insert_event(self.e,service=Mock())
    def test_45_fake_google_read(self):
        fake=Mock();fake.events.return_value.list.return_value.execute.return_value={'items':[{'summary':'Dentist','start':{'dateTime':'2027-03-06T11:30:00-05:00'},'id':'a'}]}
        out=list_events(service=fake,now=datetime(2027,3,5,tzinfo=TZ))
        self.assertEqual(out[0]['title'],'Dentist')
    def test_46_token_status_not_auth(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'not-here';self.assertFalse(connected_token_present(p))
    def test_47_demo_no_private_names(self):
        source=json.loads((Path(__file__).parent/'examples'/'mina_demo_birthdays_v27.json').read_text())
        self.assertEqual(len(source),7)
        self.assertTrue(all('Friend' in e['title'] or 'Family Member' in e['title'] or 'Relative' in e['title'] for e in source))

if __name__=='__main__':unittest.main()
