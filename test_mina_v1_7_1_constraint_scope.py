"""Narrow, fail-closed repair for unassigned live-route constraint labels."""
import unittest
from unittest.mock import patch

from mina_state import Constraint
from mina_live_planning import _resolve_unassigned_constraint, _validate_inputs, plan_with_live_routes
from mina_planning import NeedsClarification
from test_mina_live_planning import state, params, mock_report
from mina_route_tools import RouteStop


DEMO = (
    "For the demo, plan returning library books, buying groceries, and picking up "
    "a child before 4:30 PM. The library opens at noon, and grocery shopping "
    "takes at least 60 minutes."
)


class ConstraintScopeTests(unittest.TestCase):
    def test_three_exact_local_clauses_bind_only_to_requested_tasks(self):
        cases = [
            (Constraint('deadline', None, '16:30', 'before 4:30 PM'), 'school_pickup'),
            (Constraint('opening_time', None, '12:00', 'at noon'), 'library'),
            (Constraint('minimum_duration', None, '60', 'at least 60 minutes'), 'groceries'),
        ]
        for c, expected in cases:
            with self.subTest(kind=c.kind):
                self.assertEqual(_resolve_unassigned_constraint(DEMO, c, {
                    'library', 'groceries', 'school_pickup'}), expected)

    def test_unassigned_demo_constraints_build_context_without_network(self):
        s = state()
        s.user_request = DEMO
        s.constraints = [
            Constraint('deadline', None, '16:30', 'before 4:30 PM'),
            Constraint('opening_time', 'other', '12:00', 'at noon'),
            Constraint('minimum_duration', None, '60', 'at least 60 minutes'),
        ]
        ctx = _validate_inputs(s, params(durations={
            'library': 15, 'groceries': 30, 'school_pickup': 10,
        }))
        self.assertEqual(ctx.deadlines, {'school_pickup': '16:30'})
        self.assertEqual(ctx.library_open, '12:00')
        self.assertEqual(ctx.durations['groceries'], 60)
        self.assertEqual(s.constraints[0].task_id, None)  # do not alter Coordinator evidence

    def test_demo_full_plan_selects_using_mock_provider(self):
        s = state()
        s.user_request = DEMO
        s.constraints = [
            Constraint('deadline', None, '16:30', 'before 4:30 PM'),
            Constraint('opening_time', None, '12:00', 'at noon'),
            Constraint('minimum_duration', None, '60', 'at least 60 minutes'),
        ]
        with patch('mina_live_planning._require_key', return_value='fake'), \
             patch('mina_live_planning.geocode_route_stop', side_effect=lambda v, **k:
                   RouteStop(v, *[float(x) for x in v.split(',')])), \
             patch('mina_live_planning.get_route_report', side_effect=mock_report):
            result = plan_with_live_routes(s, params(durations={
                'library': 15, 'groceries': 60, 'school_pickup': 10,
            }), planner_mode='deterministic')
        self.assertEqual(result.status, 'provisional_live_route_plan')
        self.assertIsNotNone(result.map_report)

    def test_ambiguous_multi_task_deadline_is_rejected(self):
        request = 'Finish library and groceries before 4:30 PM.'
        c = Constraint('deadline', None, '16:30', 'before 4:30 PM')
        self.assertIsNone(_resolve_unassigned_constraint(request, c, {
            'library', 'groceries', 'school_pickup'}))

    def test_wrong_extracted_time_or_duration_is_not_repaired(self):
        self.assertIsNone(_resolve_unassigned_constraint(
            DEMO, Constraint('deadline', None, '14:30', 'before 4:30 PM'),
            {'school_pickup'}))
        self.assertIsNone(_resolve_unassigned_constraint(
            DEMO, Constraint('opening_time', None, '13:00', 'at noon'),
            {'library'}))
        self.assertIsNone(_resolve_unassigned_constraint(
            DEMO, Constraint('minimum_duration', None, '90', 'at least 60 minutes'),
            {'groceries'}))

    def test_unquoted_constraint_is_not_repaired(self):
        c = Constraint('deadline', None, '16:30', 'before 4:30 PM')
        self.assertIsNone(_resolve_unassigned_constraint('Pick up a child by 4 PM', c, {'school_pickup'}))

    def test_conflicting_or_global_constraint_fails_closed(self):
        s = state()
        s.user_request = DEMO
        s.constraints = [Constraint('deadline', None, '16:30', 'before 4:30 PM'),
                         Constraint('other', None, 'unknown', 'For the demo')]
        with self.assertRaisesRegex(NeedsClarification, 'Unassigned other'):
            _validate_inputs(s, params())

    def test_known_constraints_and_other_preexisting_tests_unchanged(self):
        ctx = _validate_inputs(state(), params())
        self.assertEqual(ctx.deadlines, {'school_pickup': '14:30'})
        self.assertEqual(ctx.library_open, '12:00')


if __name__ == '__main__':
    unittest.main()
