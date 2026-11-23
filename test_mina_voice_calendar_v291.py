"""MINA v2.9.1: regression tests for spoken appointment end times.

No network or Google account access; only proposes events and checks fields.
Existing v2.9 test suite should also be executed.
"""
import unittest
from datetime import date
from mina_calendar_v27 import parse_voice_calendar

TODAY = date(2026, 11, 21)

class CalendarDurationRegression291(unittest.TestCase):
    def event(self, message):
        result = parse_voice_calendar(message, today=TODAY)
        self.assertIsNotNone(result, 'Parser incorrectly returned None')
        self.assertEqual(result['kind'], 'event')
        return result['event']

    def test_10_am_15_minutes(self):
        e = self.event('Mina, schedule a test appointment on Monday, November 30th at 10 a.m. for 15 minutes. Remind me one day and two hours before.')
        self.assertEqual((e['date'],e['time'],e['end_time']), ('2026-11-30','10:00 AM','10:15 AM'))

    def test_4_pm_15_minutes(self):
        e = self.event('Mina, schedule a test appointment on November 30th at 4 p.m. for 15 minutes.')
        self.assertEqual((e['time'],e['end_time']), ('4:00 PM','4:15 PM'))

    def test_near_noon_crosses_meridian(self):
        e = self.event('Mina, schedule an appointment on November 30 at 11:50 a.m. for 20 minutes.')
        self.assertEqual((e['time'],e['end_time']), ('11:50 AM','12:10 PM'))

    def test_near_midnight_is_rejected(self):
        result = parse_voice_calendar('Mina, schedule an appointment on November 30 at 11:50 p.m. for 20 minutes.',today=TODAY)
        self.assertIsNone(result)

    def test_10_am_without_duration(self):
        e = self.event('Mina, schedule a test appointment on November 30 at 10 a.m.')
        self.assertEqual(e['time'],'10:00 AM')
        self.assertEqual(e['end_time'],'')

if __name__ == '__main__': unittest.main()
