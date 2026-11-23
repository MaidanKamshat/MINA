"""Read-only HeiGIT / openrouteservice route tool (v1.6).

Routes are model-based driving estimates, NOT live traffic or an arrival guarantee.
Only user-supplied stops are geocoded. Keys never appear in logs or map HTML.
The tool never falls back to synthetic distances or straight-line estimates.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mina_live_tools import LocationRequired, ToolUnavailable

GEOCODE_URL = "https://api.heigit.org/pelias/v1/search"
DIRECTIONS_URL = "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"
SOURCE_URL = "https://api.heigit.org/"
TIMEOUT_SECONDS = 9
MAX_STOPS = 5


@dataclass(frozen=True)
class RouteStop:
    label: str
    longitude: float
    latitude: float


@dataclass(frozen=True)
class RouteLeg:
    origin: str
    destination: str
    distance_km: float
    duration_minutes: float


@dataclass(frozen=True)
class RouteReport:
    stops: tuple[RouteStop, ...]
    legs: tuple[RouteLeg, ...]
    distance_km: float
    duration_minutes: float
    retrieved_at_utc: str
    geojson: dict
    source: str = SOURCE_URL


def _require_key(key: str | None = None) -> str:
    if key is None:
        # If installed, dotenv allows local .env without exposing it to a terminal command.
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent / '.env', override=False)
        except ImportError:
            pass
        key = os.environ.get('HEIGIT_API_KEY', '')
    if not isinstance(key, str) or not key.strip() or len(key) > 4096 or '\n' in key or '\r' in key:
        raise LocationRequired('Routing API key is missing. Add HEIGIT_API_KEY to your local .env file.')
    return key.strip()


def _load_json(req: Request, *, opener=None) -> dict:
    opener = opener or urlopen
    try:
        with opener(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Response too large')
        data = json.loads(raw.decode('utf-8'))
    except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
        # Do not disclose URLs/headers/keys embedded in upstream HTTP exceptions.
        raise ToolUnavailable('HeiGIT routing/geocoding could not be reached or returned invalid data.') from None
    if not isinstance(data, dict) or data.get('error'):
        raise ToolUnavailable('Routing provider returned an error or incomplete information.')
    return data


def _valid_coord(lon: float, lat: float) -> bool:
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


def _explicit_lon_lat(location: str) -> RouteStop | None:
    """Optional precise coordinates in 'longitude,latitude' order; no geocoding call."""
    match = re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*', location)
    if not match:
        return None
    lon, lat = float(match.group(1)), float(match.group(2))
    if not _valid_coord(lon, lat):
        raise LocationRequired('Coordinates must be longitude,latitude in the valid geographic range.')
    return RouteStop(f'{lon:.5f}, {lat:.5f}', lon, lat)


def geocode_route_stop(location: str, *, api_key: str, opener=None) -> RouteStop:
    """Resolve a stop without guessing among materially different plausible matches."""
    if not isinstance(location, str) or not location.strip() or len(location) > 180 or any(c in location for c in '\r\n<>'):
        raise LocationRequired('Provide a full public place name and city, or longitude,latitude.')
    explicit = _explicit_lon_lat(location)
    if explicit:
        return explicit
    req = Request(f'{GEOCODE_URL}?{urlencode({"text": location.strip(), "size": 5})}',
                  headers={'Authorization': api_key, 'Accept': 'application/json'}, method='GET')
    data = _load_json(req, opener=opener)
    features = data.get('features')
    if not isinstance(features, list) or not features:
        raise LocationRequired('Stop not found. Use a more precise public address or longitude,latitude.')
    candidates = []
    for feature in features[:5]:
        if not isinstance(feature, dict):
            continue
        props = feature.get('properties') or {}
        geometry = feature.get('geometry') or {}
        coords = geometry.get('coordinates') if isinstance(geometry, dict) else None
        if not isinstance(props, dict) or not isinstance(coords, list) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
            confidence = props.get('confidence')
            confidence = float(confidence) if confidence is not None else None
        except (ValueError, TypeError):
            continue
        if not _valid_coord(lon, lat) or (confidence is not None and (not math.isfinite(confidence) or confidence < 0 or confidence > 1)):
            continue
        label = props.get('label') or props.get('name')
        if not isinstance(label, str) or not label.strip():
            continue
        candidates.append((RouteStop(label[:180], lon, lat), confidence))
    if not candidates:
        raise ToolUnavailable('The geocoder did not return a valid location.')
    # When no confidence is provided, require a unique result. Competing almost-
    # equal confident locations must be clarified instead of silently choosing one.
    first, score = candidates[0]
    if score is None and len(candidates) > 1:
        raise LocationRequired('Multiple possible stops found; provide the full street address or longitude,latitude.')
    if score is not None and score < 0.65:
        raise LocationRequired('Place could not be confidently located. Provide a more precise address.')
    for other, alt_score in candidates[1:]:
        if (abs(first.longitude - other.longitude) > 0.002 or
                abs(first.latitude - other.latitude) > 0.002):
            if alt_score is None or score is None or score - alt_score < 0.10:
                raise LocationRequired('Multiple plausible locations found. Specify the full public address.')
    return first


def get_route_report(locations: list[str] | tuple[str, ...], *, api_key: str | None = None,
                     opener=None, now: datetime | None = None) -> RouteReport:
    """Read-only one-to-four-leg driving route preserving user's stop order."""
    if not isinstance(locations, (list, tuple)) or not 2 <= len(locations) <= MAX_STOPS:
        raise LocationRequired('Provide 2–5 stops in the order you want to visit them.')
    key = _require_key(api_key)
    stops = tuple(geocode_route_stop(p, api_key=key, opener=opener) for p in locations)
    coordinates = [[s.longitude, s.latitude] for s in stops]
    req = Request(DIRECTIONS_URL, data=json.dumps({'coordinates': coordinates}).encode('utf-8'),
                  headers={'Authorization': key, 'Content-Type': 'application/json',
                           'Accept': 'application/geo+json'}, method='POST')
    data = _load_json(req, opener=opener)
    try:
        features = data['features']
        if not isinstance(features, list) or len(features) != 1:
            raise ValueError('Unexpected route count')
        feature = features[0]
        props = feature['properties']
        summary = props['summary']
        segments = props['segments']
        geometry = feature['geometry']
        route_coords = geometry['coordinates']
        if geometry.get('type') != 'LineString' or not isinstance(route_coords, list) or len(route_coords) < 2:
            raise ValueError('No route line')
        if len(route_coords) > 100_000:
            raise ValueError('Overlong geometry')
        if not isinstance(segments, list) or len(segments) != len(stops) - 1:
            raise ValueError('Missing route legs')
        for p in route_coords:
            if not isinstance(p, list) or len(p) < 2 or not _valid_coord(float(p[0]), float(p[1])):
                raise ValueError('Invalid route geometry')
        distance_m, duration_s = float(summary['distance']), float(summary['duration'])
        if not (0 < distance_m < 5_000_000 and 0 < duration_s < 604_800):
            raise ValueError('Implausible total route')
        legs = []
        for i, seg in enumerate(segments):
            d, t = float(seg['distance']), float(seg['duration'])
            if not (math.isfinite(d) and math.isfinite(t) and 0 < d < 5_000_000 and 0 < t < 604_800):
                raise ValueError('Invalid route segment')
            legs.append(RouteLeg(stops[i].label, stops[i + 1].label, round(d / 1000, 2), round(t / 60, 1)))
        if abs(sum(seg['distance'] for seg in segments) - distance_m) > max(100, distance_m * .10):
            raise ValueError('Distance summary does not match segments')
        if abs(sum(seg['duration'] for seg in segments) - duration_s) > max(60, duration_s * .10):
            raise ValueError('Duration summary does not match segments')
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise ToolUnavailable('The route provider did not return a complete, valid itinerary.') from None
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec='seconds')
    # Only pass through verified geometry; not provider-generated HTML or hidden fields.
    return RouteReport(stops, tuple(legs), round(distance_m / 1000, 2),
                       round(duration_s / 60, 1), ts,
                       {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': route_coords},
                        'properties': {} })


def describe_route(report: RouteReport) -> str:
    legs = '\n'.join(f'  {i}. {leg.origin} → {leg.destination}: ~{leg.distance_km:g} km, '
                     f'~{leg.duration_minutes:g} min' for i, leg in enumerate(report.legs, start=1))
    return (f'HeiGIT/openrouteservice driving route, {len(report.stops)} stops:\n{legs}\n'
            f'Total estimate: ~{report.distance_km:g} km, ~{report.duration_minutes:g} minutes.\n'
            f'Source: {report.source} | Checked UTC: {report.retrieved_at_utc}.\n'
            'Estimated driving durations only: no verified live traffic, parking, stops, '
            'pickup buffers, opening hours or deadline guarantee. No calendar writes.')


def write_route_map(report: RouteReport, output_path: str | Path) -> Path:
    """Local Leaflet HTML preview. No API keys. Online tiles need internet.

    A map can contain user-provided location coordinates; keep it local.
    """
    path = Path(output_path)
    if path.suffix.lower() != '.html':
        raise ValueError('Route map output must end in .html')
    if len(str(path)) > 500:
        raise ValueError('Map output path is too long')
    path.parent.mkdir(parents=True, exist_ok=True)
    route_js = json.dumps(report.geojson, ensure_ascii=True).replace('<', '\\u003c')
    stop_js = json.dumps([{'lat': s.latitude, 'lon': s.longitude, 'label': s.label}
                          for s in report.stops], ensure_ascii=True).replace('<', '\\u003c')
    title = html.escape('MINA route preview — estimates only')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{font-family:system-ui;margin:0}}header{{padding:14px 18px}}#map{{height:72vh}}
small{{color:#555}}.leaflet-popup-content{{overflow-wrap:anywhere}}</style></head>
<body><header><strong>{title}</strong><div>Approx. {report.distance_km:g} km / {report.duration_minutes:g} min ·
 no live traffic or arrival guarantee. Public demo locations recommended.</div>
<small>Route: HeiGIT / openrouteservice · Map © OpenStreetMap contributors · Map display: Leaflet</small></header>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const route={route_js};
const stops={stop_js};
const map=L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,
 attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}}).addTo(map);
const line=L.geoJSON(route,{{style:{{color:'#2563eb',weight:5}}}}).addTo(map);
stops.forEach((p,i)=>L.marker([p.lat,p.lon]).addTo(map).bindPopup(
  (i+1)+'. '+p.label.replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))));
map.fitBounds(line.getBounds().pad(0.15));
</script></body></html>'''
    path.write_text(page, encoding='utf-8')
    return path
