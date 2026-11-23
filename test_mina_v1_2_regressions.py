"""Offline independent regressions for live evaluation mismatch S02/P02/P03.

These tests use mocked JSON from the LLM and require no network calls.
"""
import json
import unittest

from mina_coordinator import parse_structured_response


def payload(intent, task_id, task_evidence, constraint=None):
    return json.dumps({
        'intent': intent,
        'tasks': [{'task_id': task_id, 'description': task_evidence, 'evidence': task_evidence}],
        'constraints': [constraint] if constraint else [],
        'preferences': [], 'missing_information': [], 'write_action_requested': False,
    })


def deadline(kind, value, evidence):
    return {'kind': kind, 'task_id': 'school_pickup', 'value': value, 'evidence': evidence}


class CoordinatorEvaluationRegressionTests(unittest.TestCase):
    def test_food_extracted_as_school_prep_normalizes_to_meal(self):
        q = 'What should I prepare for school lunch?'
        s = parse_structured_response(q, payload('information', 'school_preparation', 'prepare for school lunch'))
        self.assertEqual([t.task_id for t in s.tasks], ['meal'])
        self.assertEqual(s.route, 'simple')

    def test_school_readiness_stays_school_preparation(self):
        q = 'What should I prepare for school tomorrow?'
        s = parse_structured_response(q, payload('information', 'school_preparation', 'prepare for school'))
        self.assertEqual([t.task_id for t in s.tasks], ['school_preparation'])

    def test_before_11am_becomes_deadline(self):
        q = 'Pick up my daughter from school before 11:00 AM.'
        s = parse_structured_response(q, payload('planning', 'school_pickup', 'Pick up my daughter from school',
                                                deadline('fixed_time', '11:00', 'before 11:00 AM')))
        self.assertEqual(s.constraints[0].kind, 'deadline')

    def test_before_1230pm_becomes_deadline(self):
        q = 'Pick up my daughter from school before 12:30 PM.'
        s = parse_structured_response(q, payload('planning', 'school_pickup', 'Pick up my daughter from school',
                                                deadline('fixed_time', '12:30', 'before 12:30 PM')))
        self.assertEqual(s.constraints[0].kind, 'deadline')

    def test_at_11am_remains_fixed_time(self):
        q = 'Pick up my daughter from school at 11:00 AM.'
        s = parse_structured_response(q, payload('planning', 'school_pickup', 'Pick up my daughter from school',
                                                deadline('fixed_time', '11:00', 'at 11:00 AM')))
        self.assertEqual(s.constraints[0].kind, 'fixed_time')

    def test_lunch_and_backpack_not_converted_into_meal_only(self):
        q = 'Prepare school lunch and backpack.'
        s = parse_structured_response(q, payload('information', 'school_preparation', 'school lunch and backpack'))
        self.assertEqual([t.task_id for t in s.tasks], ['school_preparation'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
