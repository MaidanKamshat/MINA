"""v2.2 dashboard tests; no Streamlit server or live HTTP calls."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from mina_dashboard import (
    DashboardInputError, demo_tasks, normalize_task, add_session_task,
    set_done, dashboard_weather_html, safe_task_labels,
)

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / 'examples' / 'demo_today_tasks_v2_2.json'


class TestDashboardV22(unittest.TestCase):
    def test_demo_explicit_and_readable(self):
        tasks = demo_tasks(DEMO)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]['time'], '8:30 AM')
        self.assertEqual(tasks[1]['title'], 'Groceries')

    def test_demo_rejects_missing_demo_label(self):
        path = ROOT / 'test_missing_demo_v22_tmp.json'
        try:
            path.write_text('{"tasks": []}')
            with self.assertRaises(DashboardInputError):
                demo_tasks(path)
        finally:
            path.unlink(missing_ok=True)

    def test_demo_file_has_no_private_coordinates_or_calendar_claim(self):
        data = json.loads(DEMO.read_text())
        self.assertTrue(data['demo'])
        self.assertNotIn('calendar_event_id', str(data))
        self.assertNotIn('latitude', str(data))

    def test_am_pm_format_normalizes(self):
        task = normalize_task('Library books', '03:15 PM', identifier='test_1')
        self.assertEqual(task['time'], '3:15 PM')

    def test_24_hour_rejected(self):
        with self.assertRaises(DashboardInputError):
            normalize_task('School pickup', '15:15', identifier='task_1')

    def test_title_html_rejected(self):
        with self.assertRaises(DashboardInputError):
            normalize_task('<script>alert(1)</script>', identifier='task_1')

    def test_control_character_rejected(self):
        with self.assertRaises(DashboardInputError):
            normalize_task('call\nMom', identifier='task_1')

    def test_too_many_tasks_rejected(self):
        tasks = [normalize_task('Task', identifier=f't_{i}') for i in range(12)]
        with self.assertRaises(DashboardInputError):
            add_session_task(tasks, 'Extra task', '', 13)

    def test_add_task_is_pure(self):
        base = [normalize_task('Groceries', identifier='t_0')]
        result = add_session_task(base, 'School pickup', '3:15 PM', 1)
        self.assertEqual(len(base), 1)
        self.assertEqual(result[-1]['time'], '3:15 PM')

    def test_toggle_is_pure_and_reversible(self):
        tasks = [normalize_task('Groceries', identifier='t_0')]
        yes = set_done(tasks, 't_0', True)
        self.assertTrue(yes[0]['done'])
        self.assertFalse(tasks[0]['done'])
        self.assertFalse(set_done(yes,'t_0',False)[0]['done'])

    def test_toggle_unknown_task_fails(self):
        with self.assertRaises(DashboardInputError):
            set_done([], 'wrong', True)

    def test_bad_weather_shows_unavailable_not_invented(self):
        html = dashboard_weather_html(None, city='Apex, NC')
        self.assertIn('Forecast unavailable', html)
        self.assertNotIn('72°F', html)

    def test_provider_text_html_escaped(self):
        r = SimpleNamespace(low_f=50, high_f=72, condition='<fake> & drizzle',
                            rain_probability_pct=35, city='<img onerror=x>')
        html = dashboard_weather_html(r, city='Apex, NC')
        self.assertIn('High 72°F', html)
        self.assertIn('&lt;fake&gt;', html)
        self.assertNotIn('<img onerror=x>', html)

    def test_task_labels_readable(self):
        labels = safe_task_labels([normalize_task('Pickup', '3:15 PM', identifier='pickup')])
        self.assertEqual(labels[0], ('pickup','Pickup  ·  3:15 PM'))

    def test_standalone_css_and_app_parse(self):
        source = (ROOT/'streamlit_app.py').read_text()
        ast.parse(source)
        css = (ROOT/'mina_theme_v2_2.css').read_text()
        self.assertIn("ROOT / 'mina_theme_v2_2.css'",source)
        self.assertIn('#078B81',css)
        self.assertIn('#FFC21B',css)
        self.assertIn('Welcome, I’m <span class="mina-name">Mina</span>',source)

    def test_voice_and_proven_backend_stay(self):
        source = (ROOT/'streamlit_app.py').read_text()
        for span in ('accept_audio=True','transcribe_wav(', 'generate_spoken_reply(',
                     'execute_ui_request(prompt, settings)', 'save_preview_map(',
                     "with st.chat_message('assistant'"):
            self.assertIn(span,source)

    def test_live_forecast_cached_and_no_fabricated_fallback(self):
        source = (ROOT/'streamlit_app.py').read_text()
        self.assertIn('get_weather_report(place, day=\'today\')',source)
        self.assertIn('ttl=900',source)
        self.assertIn('dashboard_weather_html(None, city=city',source)

    def test_task_changes_are_session_only(self):
        source = (ROOT/'streamlit_app.py').read_text()
        self.assertIn("st.session_state['mina_dashboard_tasks']",source)
        self.assertIn('Not synced with a calendar',source)
        self.assertNotIn('calendar.events().insert(',source)


if __name__=='__main__':
    unittest.main()
