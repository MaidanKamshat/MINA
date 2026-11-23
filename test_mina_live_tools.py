"""Offline unit/integration tests for the opt-in live-tools extension.

No network, real OpenAI, or account access. HTTP responses and clocks are mocked.
"""
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from mina_live_tools import (
    LocationRequired, ToolUnavailable, current_local_time,
    describe_weather, get_weather_report, resolve_city, WeatherReport,
)
from mina_live_routing import simple_live_topics, requested_weather_day
from mina_runtime import run_state, run_request
from mina_state import RequestState, RequestedTask
from mina_coordinator import choose_route

DATE_NOW = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)


class FakeHTTPResponse:
    def __init__(self, data):
        self.body = io.BytesIO(json.dumps(data).encode("utf-8"))
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return self.body.read()


def fake_http(url, *, timeout):
    assert 0 < timeout <= 10
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "geocoding-api" in parsed.netloc:
        assert params["name"] == ["Apex"]
        return FakeHTTPResponse({"results": [
            {"name": "Apex", "admin1": "North Carolina", "country": "United States",
             "country_code": "US", "latitude": 35.7326, "longitude": -78.8503,
             "timezone": "America/New_York"},
            {"name": "Apex", "admin1": "Colorado", "country": "United States",
             "country_code": "US", "latitude": 39.0, "longitude": -105.0,
             "timezone": "America/Denver"},
        ]})
    if "api.open-meteo.com" in parsed.netloc:
        assert params["timezone"] == ["America/New_York"]
        assert params["temperature_unit"] == ["fahrenheit"]
        assert "precipitation_probability_max" in params["daily"][0]
        return FakeHTTPResponse({"daily": {
            "time": ["2026-11-20", "2026-11-21", "2026-11-22"],
            "temperature_2m_min": [45, 36, 31],
            "temperature_2m_max": [62, 49, 41],
            "precipitation_probability_max": [20, 70, 35],
            "weather_code": [2, 61, 3],
        }})
    raise AssertionError("Network called at unrecognized endpoint")


class OfflineLiveToolTests(unittest.TestCase):
    def test_time_zoned_and_date(self):
        answer = current_local_time("America/New_York", now=DATE_NOW)
        self.assertIn("Friday, November 20, 2026, 11:00 AM", answer)
        self.assertIn("local system clock", answer)

    def test_invalid_time_zone_is_not_guessed(self):
        with self.assertRaises(LocationRequired):
            current_local_time("Unreal/Timezone", now=DATE_NOW)

    def test_geocoding_matches_explicit_state(self):
        got = resolve_city("Apex, NC", opener=fake_http)
        self.assertEqual(got["label"], "Apex, North Carolina")
        self.assertEqual(got["timezone"], "America/New_York")

    def test_ambiguous_city_fails_closed(self):
        with self.assertRaises(LocationRequired):
            resolve_city("Apex", opener=fake_http)

    def test_missing_or_pathlike_city_rejected(self):
        for city in ("", "Apex\nX", "../secret"):
            with self.subTest(city=city), self.assertRaises(LocationRequired):
                resolve_city(city, opener=fake_http)

    def test_tomorrow_weather_is_grounded_in_day_and_timezone(self):
        reading = get_weather_report("Apex, NC", day="tomorrow", now=DATE_NOW,
                                     opener=fake_http)
        self.assertEqual(reading.date, "2026-11-21")
        self.assertEqual((reading.low_f, reading.high_f, reading.rain_probability_pct), (36, 49, 70))
        answer = describe_weather(reading)
        self.assertIn("November", current_local_time("America/New_York", now=DATE_NOW))
        self.assertIn("2026-11-21", answer)
        self.assertIn("jacket", answer)
        self.assertIn("rain jacket or umbrella", answer)
        self.assertIn("open-meteo.com", answer)

    def test_today_weather_separate_from_tomorrow(self):
        reading = get_weather_report("Apex, NC", day="today", now=DATE_NOW, opener=fake_http)
        self.assertEqual((reading.date, reading.condition), ("2026-11-20", "partly cloudy"))

    def test_provider_network_error_fails_closed(self):
        def broken(*_args, **_kwargs):
            raise URLError("network down")
        with self.assertRaises(ToolUnavailable):
            get_weather_report("Apex, NC", opener=broken)

    def test_provider_incomplete_forecast_not_improvised(self):
        def incomplete(url, *, timeout):
            if "geocoding" in url:
                return fake_http(url, timeout=timeout)
            return FakeHTTPResponse({"daily": {"time": []}})
        with self.assertRaises(ToolUnavailable):
            get_weather_report("Apex, NC", day="tomorrow", opener=incomplete, now=DATE_NOW)

    def test_no_external_calls_when_city_missing(self):
        state = RequestState("What's the weather tomorrow?", "information", route="simple")
        with patch("mina_live_tools.get_weather_report", side_effect=AssertionError("no call")):
            result = run_state(state, live_tools=True, use_rag=False)
        self.assertEqual(result.status, "needs_clarification")
        self.assertIn("--city", result.answer)

    def test_live_weather_responds_with_mocked_provider(self):
        sample = WeatherReport("Apex, North Carolina", "tomorrow", "2026-11-21", "America/New_York",
                               36, 49, 70, "light rain", "2026-11-20T11:00:00-05:00")
        with patch("mina_live_tools.get_weather_report", return_value=sample) as fetch:
            result = run_request("What's the weather forecast tomorrow?", live_tools=True,
                                 city="Apex, NC", use_rag=False)
        self.assertEqual(result.status, "simple_response")
        self.assertIn("2026-11-21", result.answer)
        self.assertIn("Open-Meteo", result.answer)
        fetch.assert_called_once_with("Apex, NC", day="tomorrow")
        self.assertEqual(result.trace[-1]["step"], "live_weather")

    def test_live_time_fastpath_works_without_llm(self):
        state = run_request("What time and date is it right now?", live_tools=True,
                            timezone_name="America/New_York", use_rag=False)
        self.assertEqual(state.status, "simple_response")
        self.assertIn("America/New_York", state.answer)
        self.assertTrue(any(i["step"] == "live_time" for i in state.trace))

    def test_live_network_failure_not_misreported_as_weather(self):
        with patch("mina_live_tools.get_weather_report", side_effect=ToolUnavailable("provider offline")):
            result = run_request("What's the weather tomorrow?", city="Apex, NC",
                                 live_tools=True, use_rag=False)
        self.assertEqual(result.status, "tool_unavailable")
        self.assertIn("could not be verified", result.answer)
        self.assertNotIn("°F", result.answer)

    def test_live_write_guard_precedes_any_weather_call(self):
        query = "Add a school event to my calendar and tell me the weather tomorrow."
        with patch("mina_live_tools.get_weather_report", side_effect=AssertionError("must not fetch")):
            result = run_request(query, live_tools=True, city="Apex, NC", use_rag=False)
        self.assertEqual(result.status, "approval_required")
        self.assertEqual([i["step"] for i in result.trace], ["coordinator", "safety"])

    def test_planning_not_hijacked_by_weather_fastpath(self):
        self.assertEqual(simple_live_topics("Plan groceries and check the weather tomorrow."), (False, False))
        state = choose_route(RequestState("Plan groceries and return library books, and check weather.",
                                          "planning", tasks=[
                                              RequestedTask("groceries", "groceries", "groceries"),
                                              RequestedTask("library", "return books", "return library books"),
                                          ]))
        self.assertEqual(state.route, "complex")
        with patch("mina_live_tools.get_weather_report", side_effect=AssertionError("must not fetch")):
            output = run_state(state, live_tools=True, planner_mode="deterministic", use_rag=False)
        self.assertNotIn("live_weather", [i["step"] for i in output.trace])

    def test_baseline_mode_ignores_live_tool_even_for_weather(self):
        state = RequestState("What's the weather tomorrow?", "information", route="simple")
        with patch("mina_live_tools.get_weather_report", side_effect=AssertionError("should not call")):
            result = run_state(state, use_rag=False, live_tools=False)
        self.assertEqual(result.status, "simple_response")
        self.assertIn("No live tools", result.answer)

    def test_readonly_topics_detection(self):
        self.assertEqual(simple_live_topics("What's the weather tomorrow and what time is it now?"), (True, True))
        self.assertEqual(requested_weather_day("What's the weather next weekend?"), "unsupported")
        self.assertEqual(requested_weather_day("What's the forecast tomorrow?"), "tomorrow")
        self.assertEqual(simple_live_topics("What should my kids wear tomorrow?"), (True, False))


if __name__ == "__main__":
    unittest.main()
