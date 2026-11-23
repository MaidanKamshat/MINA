"""MINA v2.9 offline regression tests. No network, OAuth, or calendar writes."""
import unittest
from datetime import date

from mina_calendar_v27 import (
    parse_voice_calendar, calendar_create_intent,
)
from mina_google_calendar import google_event_body

TODAY = date(2026, 11, 21)


class SpokenCalendarRegression(unittest.TestCase):
    def parse(self, text):
        return parse_voice_calendar(text, today=TODAY)

    def test_original_voice_transcription(self):
        p = self.parse('Mina, schedule a test appointment on Monday, November 30th at 10 a.m. for 15 minutes. Remind me one day and two hours before.')
        self.assertIsNotNone(p)
        e = p['event']
        self.assertEqual((e['title'], e['date'], e['time'], e['end_time']),
                         ('Test appointment', '2026-11-30', '10:00 AM', '10:15 AM'))

    def test_reminders_are_sent_in_google_payload(self):
        p = self.parse('Mina, schedule a test appointment on Monday, November 30th at 10 a.m. for 15 minutes.')
        body = google_event_body(p['event'])
        self.assertEqual(body['start']['dateTime'], '2026-11-30T10:00:00-05:00')
        self.assertEqual(body['end']['dateTime'], '2026-11-30T10:15:00-05:00')
        self.assertEqual([r['minutes'] for r in body['reminders']['overrides']], [1440, 120])

    def test_time_punctuation_variants(self):
        for written in ('10 AM', '10am', '10 a.m.', '10 A.M.', '10:00 a.m.'):
            with self.subTest(written=written):
                p = self.parse(f'Mina, schedule an appointment on November 30th at {written} for 15 minutes.')
                self.assertIsNotNone(p)
                self.assertEqual(p['event']['time'], '10:00 AM')
                self.assertEqual(p['event']['end_time'], '10:15 AM')

    def test_time_spelled_out(self):
        p = self.parse('Mina, schedule an appointment on November 30 at ten in the morning for fifteen minutes.')
        self.assertEqual(p['event']['time'], '10:00 AM')
        self.assertEqual(p['event']['end_time'], '10:15 AM')

    def test_duration_half_hour(self):
        p = self.parse('Mina, schedule an appointment on November 30 at 4 p.m. for half an hour.')
        self.assertEqual(p['event']['end_time'], '4:30 PM')

    def test_tomorrow_title_not_polluted(self):
        p = self.parse('Mina, schedule a test appointment tomorrow at 10 AM for 15 minutes.')
        self.assertEqual(p['event']['title'], 'Test appointment')
        self.assertEqual(p['event']['date'], '2026-11-22')

    def test_wrong_weekday_no_silent_date_guess(self):
        self.assertIsNone(self.parse('Mina, schedule an appointment Tuesday, November 30 at 10 a.m.'))

    def test_midnight_overflow_no_silent_adjustment(self):
        self.assertIsNone(self.parse('Mina, schedule an appointment on November 30 at 11 p.m. for two hours.'))

    def test_compound_email_write_remains_blocked(self):
        t = 'Mina, schedule an appointment on November 30 at 10 a.m. and send an email.'
        self.assertIsNone(self.parse(t))
        self.assertFalse(calendar_create_intent(t))

    def test_shopping_list_remains_separate(self):
        t = 'Mina, add whole milk to my Target shopping list.'
        self.assertIsNone(self.parse(t))
        self.assertFalse(calendar_create_intent(t))

    def test_incomplete_calendar_uses_clarification_route(self):
        t = 'Mina, schedule an appointment next month.'
        self.assertIsNone(self.parse(t))
        self.assertTrue(calendar_create_intent(t))


if __name__ == '__main__':
    unittest.main()
