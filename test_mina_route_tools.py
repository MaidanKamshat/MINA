"""No-network regression tests for v1.6 real-route integration."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

from mina_live_tools import LocationRequired, ToolUnavailable
from mina_route_tools import (
    DIRECTIONS_URL, GEOCODE_URL, RouteReport, describe_route, geocode_route_stop,
    get_route_report, write_route_map,
)
from mina_route_routing import is_route_only_query
from mina_runtime import run_request, run_state
from mina_state import RequestState

P1 = '-78.85030,35.73260'
P2 = '-78.78080,35.79150'
P3 = '-78.80320,35.77210'


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode('utf-8')
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size=-1):
        return self.payload[:size]


def route_response(legs=1):
    segments = ([{'distance': 12000, 'duration': 900}] if legs == 1 else [
        {'distance': 5000, 'duration': 460}, {'distance': 7000, 'duration': 440}])
    coords = [[-78.85030, 35.73260], [-78.80320, 35.77210], [-78.78080, 35.79150]]
    return {'features': [{'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coords},
                          'properties': {'summary': {'distance': 12000, 'duration': 900},
                                         'segments': segments}}]}


def fake_opener(request, *, timeout):
    assert timeout <= 10
    if request.full_url.startswith(DIRECTIONS_URL):
        assert request.get_method() == 'POST'
        assert request.get_header('Authorization') == 'fake-test-key'
        return FakeHTTPResponse(route_response(len(json.loads(request.data)['coordinates']) - 1))
    if request.full_url.startswith(GEOCODE_URL):
        assert request.get_method() == 'GET'
        return FakeHTTPResponse({'features': [
            {'geometry': {'coordinates': [-78.8503, 35.7326]},
             'properties': {'label': 'Apex Town Hall, Apex, North Carolina', 'confidence': 0.96}},
            {'geometry': {'coordinates': [-79.5, 36.5]},
             'properties': {'label': 'Other place', 'confidence': 0.73}},
        ]})
    raise AssertionError('Unexpected URL')


class RouteToolTests(unittest.TestCase):
    def test_endpoints_current_heigit(self):
        self.assertTrue(GEOCODE_URL.startswith('https://api.heigit.org/pelias/v1'))
        self.assertTrue(DIRECTIONS_URL.startswith('https://api.heigit.org/openrouteservice'))

    def test_one_leg_real_route_mock(self):
        r = get_route_report([P1, P2], api_key='fake-test-key', opener=fake_opener)
        self.assertEqual((r.distance_km, r.duration_minutes), (12, 15))
        self.assertEqual(len(r.legs), 1)
        self.assertEqual(r.legs[0].origin, '-78.85030, 35.73260')
        self.assertIn('no verified live traffic', describe_route(r))
        self.assertEqual(r.geojson['geometry']['type'], 'LineString')

    def test_multiple_stops_and_legs(self):
        r = get_route_report([P1, P3, P2], api_key='fake-test-key', opener=fake_opener)
        self.assertEqual([s.duration_minutes for s in r.legs], [7.7, 7.3])
        self.assertEqual(len(r.stops), 3)

    def test_full_public_name_geocodes_with_confidence(self):
        point = geocode_route_stop('Apex Town Hall, Apex, North Carolina',
                                   api_key='fake-test-key', opener=fake_opener)
        self.assertIn('Apex Town Hall', point.label)
        self.assertEqual(point.longitude, -78.8503)

    def test_ambiguous_geocoding_rejected(self):
        def ambiguous(req, *, timeout):
            return FakeHTTPResponse({'features': [
                {'geometry': {'coordinates': [-78.8, 35.7]},
                 'properties': {'label': 'Same name, A', 'confidence': 0.9}},
                {'geometry': {'coordinates': [-79.3, 35.7]},
                 'properties': {'label': 'Same name, B', 'confidence': 0.88}},
            ]})
        with self.assertRaises(LocationRequired):
            geocode_route_stop('Library', api_key='fake-test-key', opener=ambiguous)

    def test_uncertain_geocoding_rejected(self):
        def uncertain(req, *, timeout):
            return FakeHTTPResponse({'features': [
                {'geometry': {'coordinates': [-78.8, 35.7]},
                 'properties': {'label': 'Wrong Place', 'confidence': 0.37}},
            ]})
        with self.assertRaises(LocationRequired):
            geocode_route_stop('Vague address', api_key='fake-test-key', opener=uncertain)

    def test_missing_key_rejected_without_network(self):
        with self.assertRaises(LocationRequired):
            get_route_report([P1, P2], api_key='')

    def test_invalid_coordinates_rejected(self):
        for coords in ('1000,35', '-78,200', '0,Infinity'):
            with self.subTest(coords=coords), self.assertRaises(LocationRequired):
                geocode_route_stop(coords, api_key='fake-test-key',
                                   opener=lambda *_a, **_kw: FakeHTTPResponse({'features': []}))

    def test_network_unavailable_not_hallucinated(self):
        def broken(*_a, **_kw):
            raise URLError('provider down: fake-test-key')
        with self.assertRaises(ToolUnavailable) as context:
            get_route_report([P1, P2], api_key='fake-test-key', opener=broken)
        self.assertNotIn('fake-test-key', str(context.exception))

    def test_incomplete_route_fails_closed(self):
        def incomplete(req, *, timeout):
            return FakeHTTPResponse({'features': [{'properties': {}}]})
        with self.assertRaises(ToolUnavailable):
            get_route_report([P1, P2], api_key='fake-test-key', opener=incomplete)

    def test_unsupported_large_routes_rejected(self):
        with self.assertRaises(LocationRequired):
            get_route_report([P1]*6, api_key='fake-test-key', opener=fake_opener)

    def test_map_html_saved_without_key(self):
        r = get_route_report([P1, P2], api_key='fake-test-key', opener=fake_opener)
        with tempfile.TemporaryDirectory() as temp:
            path = write_route_map(r, Path(temp)/'map.html')
            html = path.read_text(encoding='utf-8')
            self.assertIn('leaflet', html)
            self.assertIn('OpenStreetMap', html)
            self.assertIn('-78.8503', html)
            self.assertNotIn('fake-test-key', html)
            self.assertNotIn('Authorization', html)

    def test_route_only_classifier(self):
        self.assertTrue(is_route_only_query('Show driving route between the two public locations'))
        self.assertTrue(is_route_only_query('What is the distance between these two places?'))
        self.assertFalse(is_route_only_query('Plan a trip to buy groceries before 2 PM'))
        self.assertFalse(is_route_only_query('Add a driving route to my calendar'))

    def test_fastpath_no_openai_and_route_answer(self):
        r = get_route_report([P1, P2], api_key='fake-test-key', opener=fake_opener)
        with patch('mina_route_tools.get_route_report', return_value=r) as mock:
            result = run_request('Show driving route between my two public stops',
                                 use_rag=False, live_tools=True, route_stops=(P1,P2))
        self.assertEqual(result.status, 'simple_response')
        self.assertIn('15 minutes', result.answer)
        self.assertIs(result.map_report, r)
        mock.assert_called_once_with((P1,P2))
        self.assertTrue(any(t['step']=='live_route' for t in result.trace))

    def test_missing_stops_no_fake_route(self):
        result = run_request('Show driving route between two stops', use_rag=False, live_tools=True)
        self.assertEqual(result.status, 'needs_clarification')
        self.assertIn('--origin', result.answer)

    def test_write_guard_always_precedes_route_fetch(self):
        q = 'Add a driving route to my calendar'
        with patch('mina_route_tools.get_route_report', side_effect=AssertionError('should not fetch')):
            result = run_state(RequestState(q,'information',route='simple'),
                               live_tools=True, route_stops=(P1,P2))
        self.assertEqual(result.status, 'approval_required')

    def test_default_synthetic_mode_no_network(self):
        state = RequestState('Show driving route between two public places', 'information',route='simple')
        with patch('mina_route_tools.get_route_report', side_effect=AssertionError('should not fetch')):
            result = run_state(state, live_tools=False, route_stops=(P1,P2))
        self.assertEqual(result.status,'simple_response')
        self.assertIsNone(result.map_report)

    def test_unavailable_provider_routed_as_tool_unavailable(self):
        with patch('mina_route_tools.get_route_report', side_effect=ToolUnavailable('no network')):
            result = run_request('Show a driving route between the stops',
                                 live_tools=True, route_stops=(P1,P2))
        self.assertEqual(result.status, 'tool_unavailable')
        self.assertIn('No synthetic travel estimate', result.answer)


if __name__=='__main__': unittest.main()
