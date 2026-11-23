import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from mina_ui_adapter import (UISettings, UIInputError, execute_ui_request,
                             validate_ui_settings, status_caption, save_preview_map)


class TestUIAdapter(unittest.TestCase):
    def setUp(self):
        self.recorded = []
        def runner(text, **kwargs):
            self.recorded.append((text, kwargs))
            return type('Result', (), {'status': 'simple_response', 'answer': 'ok'})()
        self.runner = runner

    def test_assistant_runs_live_tools_without_route(self):
        execute_ui_request('  What time is it?  ', UISettings(), runner=self.runner)
        self.assertEqual(self.recorded[0][0], 'What time is it?')
        self.assertTrue(self.recorded[0][1]['live_tools'])
        self.assertNotIn('live_plan', self.recorded[0][1])

    def test_directions_stops(self):
        s = UISettings(mode='directions', origin='1,2', destination='3,4', via=('5,6',))
        execute_ui_request('Show driving directions.', s, runner=self.runner)
        self.assertEqual(self.recorded[0][1]['route_stops'], ('1,2', '5,6', '3,4'))

    def test_directions_rejects_missing_stops(self):
        with self.assertRaises(UIInputError):
            validate_ui_settings(UISettings(mode='directions', origin='x'))

    def test_directions_rejects_many_stops(self):
        with self.assertRaises(UIInputError):
            validate_ui_settings(UISettings(mode='directions', origin='x', destination='y', via=('a', 'b', 'c', 'd')))

    def test_family_plan_passes_saved_places_explicitly(self):
        s = UISettings(mode='family_plan', origin='1,2', task_locations={'library': '3,4', 'groceries': '5,6'},
                       durations={'library': 15, 'groceries': 60}, saved_places_file='example.json',
                       plan_date='2026-11-20', start_time='3:15 PM')
        execute_ui_request('Plan library and groceries before 5 PM.', s, runner=self.runner)
        plan = self.recorded[0][1]['live_plan']
        self.assertEqual(plan.start_time, '3:15 PM')
        self.assertEqual(plan.saved_places_file, 'example.json')
        self.assertEqual(plan.task_locations['groceries'], '5,6')

    def test_family_plan_rejects_24_hour_input(self):
        s = UISettings(mode='family_plan', origin='1,2', task_locations={'library': '3,4', 'groceries': '5,6'},
                       durations={'library': 15, 'groceries': 60}, start_time='15:15')
        with self.assertRaisesRegex(UIInputError, '12-hour'):
            validate_ui_settings(s)

    def test_family_plan_rejects_missing_duration(self):
        s = UISettings(mode='family_plan', origin='1,2', task_locations={'library': '3,4', 'groceries': '5,6'},
                       durations={'library': 15})
        with self.assertRaisesRegex(UIInputError, 'duration'):
            validate_ui_settings(s)

    def test_family_plan_rejects_incomplete_hours_inputs(self):
        s = UISettings(mode='family_plan', origin='1,2', task_locations={'library': '3,4', 'groceries': '5,6'},
                       durations={'library': 15, 'groceries': 60}, saved_places_file='example.json')
        with self.assertRaisesRegex(UIInputError, 'Saved Places'):
            validate_ui_settings(s)

    def test_request_must_be_nonempty(self):
        with self.assertRaises(UIInputError):
            execute_ui_request('   ', UISettings(), runner=self.runner)

    def test_request_length_cap(self):
        with self.assertRaises(UIInputError):
            execute_ui_request('x'*3001, UISettings(), runner=self.runner)

    def test_unrecognized_status_caption(self):
        self.assertEqual(status_caption('unknown'), 'MINA response')
        self.assertIn('nothing changed', status_caption('approval_required'))

    def test_save_map_injected_writer(self):
        with TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'map.html'
            def writer(report, output_path):
                self.assertEqual(report, 'test-report')
                self.assertEqual(output_path, expected)
                expected.write_text('demo')
                return expected
            self.assertEqual(save_preview_map('test-report', writer=writer, output_path=expected), expected)


class TestUIWriteSafetyIntegration(unittest.TestCase):
    def test_calendar_mutation_is_blocked_without_network(self):
        from mina_ui_adapter import execute_ui_request, UISettings
        result = execute_ui_request('Add a school event to my calendar.', UISettings())
        self.assertEqual(result.status, 'approval_required')
        self.assertTrue(any(x.get('step') == 'safety' for x in result.trace))

    def test_list_mutation_is_blocked_without_network(self):
        from mina_ui_adapter import execute_ui_request, UISettings
        result = execute_ui_request('Add milk to the shopping list.', UISettings())
        self.assertEqual(result.status, 'approval_required')
