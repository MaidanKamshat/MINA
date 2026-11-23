"""Offline coordinator tests; no API key, network access or embeddings needed."""
import json
import unittest

from mina_coordinator import extract_request, parse_structured_response


class FakeResponse:
    def __init__(self, data):
        self.output_text = json.dumps(data)


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.responses = self

    def create(self, **kwargs):
        assert kwargs["text"]["format"]["type"] == "json_schema"
        assert kwargs["model"] == "gpt-4.1-mini"
        return FakeResponse(self.data)


def payload(intent, tasks=(), constraints=(), write=False):
    return {
        "intent": intent, "tasks": list(tasks), "constraints": list(constraints),
        "preferences": [], "missing_information": [], "write_action_requested": write,
    }


def task(task_id, evidence):
    return {"task_id": task_id, "description": evidence, "evidence": evidence}


def constraint(kind, task_id, value, evidence):
    return {"kind": kind, "task_id": task_id, "value": value, "evidence": evidence}


class CoordinatorTests(unittest.TestCase):
    def test_simple_list_change_is_not_executed(self):
        q = "Add milk to my grocery list."
        s = extract_request(q, FakeClient(payload("list_update", [task("shopping_list_update", "Add milk")], write=True)))
        self.assertEqual(s.route, "simple")
        self.assertTrue(s.write_action_requested)
        self.assertEqual(s.status, "parsed_not_executed")

    def test_complex_three_tasks_deadline(self):
        q = "Return library books, buy groceries, and pick up my daughter before 2:30 PM."
        data = payload("planning", [task("library", "Return library books"), task("groceries", "buy groceries"),
                                    task("school_pickup", "pick up my daughter")],
                       [constraint("deadline", "school_pickup", "14:30", "before 2:30 PM")])
        s = extract_request(q, FakeClient(data))
        self.assertEqual(s.route, "complex")
        self.assertEqual(s.constraints[0].value, "14:30")

    def test_two_tasks_explicit_planning(self):
        q = "Help plan library returns and groceries."
        data = payload("planning", [task("library", "library returns"), task("groceries", "groceries")])
        self.assertEqual(extract_request(q, FakeClient(data)).route, "complex")

    def test_two_tasks_without_planning_is_simple(self):
        q = "I need to return library books and buy groceries."
        data = payload("information", [task("library", "return library books"), task("groceries", "buy groceries")])
        self.assertEqual(extract_request(q, FakeClient(data)).route, "simple")

    def test_reject_unrequested_task(self):
        q = "I need to return library books."
        data = payload("planning", [task("library", "return library books"), task("groceries", "Costco")])
        with self.assertRaisesRegex(ValueError, "Unanchored task"):
            parse_structured_response(q, json.dumps(data))

    def test_reject_invented_deadline_evidence(self):
        q = "Return library books and buy groceries."
        data = payload("planning", [task("library", "Return library books"), task("groceries", "buy groceries")],
                       [constraint("deadline", "groceries", "14:30", "before 2:30 PM")])
        with self.assertRaisesRegex(ValueError, "Unanchored constraint"):
            parse_structured_response(q, json.dumps(data))

    def test_reject_invalid_time_format(self):
        q = "Pick up my daughter before 2:30 PM and buy groceries."
        data = payload("planning", [task("school_pickup", "Pick up my daughter"), task("groceries", "buy groceries")],
                       [constraint("deadline", "school_pickup", "2:30 PM", "before 2:30 PM")])
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            parse_structured_response(q, json.dumps(data))

    def test_school_preparation_not_mistaken_for_meal(self):
        q = "What should I prepare for school tomorrow?"
        data = payload("information", [task("meal", "prepare for school")])
        state = extract_request(q, FakeClient(data))
        self.assertEqual([t.task_id for t in state.tasks], ["school_preparation"])
        self.assertEqual(state.route, "simple")

    def test_school_lunch_stays_meal(self):
        q = "What food should I prepare for school lunch?"
        data = payload("information", [task("meal", "prepare for school lunch")])
        state = extract_request(q, FakeClient(data))
        self.assertEqual([t.task_id for t in state.tasks], ["meal"])

    def test_simple_weather_request(self):
        q = "What's the weather tomorrow?"
        data = payload("information", [task("weather_lookup", "weather tomorrow")])
        self.assertEqual(extract_request(q, FakeClient(data)).route, "simple")


if __name__ == "__main__":
    unittest.main(verbosity=2)
