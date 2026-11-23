"""One-shot, user-initiated read-only OSM opening_hours discovery via Overpass.

These raw community-edited tags are never treated as verified schedules and
never auto-write to Saved Places or enter the Critic. No unattended polling.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mina_live_tools import ToolUnavailable, LocationRequired

OVERPASS = 'https://overpass-api.de/api/interpreter'

@dataclass(frozen=True)
class OSMHoursFinding:
    name: str
    opening_hours_raw: str
    osm_url: str
    source: str = 'OpenStreetMap/Overpass (community data, UNVERIFIED)'


def lookup_osm_hours(name: str, longitude: float, latitude: float, *, opener=None) -> OSMHoursFinding | None:
    """Exact-name + nearby search; ambiguous matches fail closed, no auto-use."""
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120 or re.search(r'[\r\n<>]', name):
        raise LocationRequired('Specify a public venue name (2–120 characters).')
    if (not isinstance(longitude, (int,float)) or not isinstance(latitude, (int,float))
            or not math.isfinite(longitude) or not math.isfinite(latitude)
            or not -180 <= longitude <= 180 or not -90 <= latitude <= 90):
        raise LocationRequired('Specify valid public longitude/latitude coordinates.')
    # Query only features that have name and opening_hours tags. Filter exact
    # case-insensitive name client-side rather than guessing nearest business.
    q = f'[out:json][timeout:8];nwr(around:75,{latitude:.6f},{longitude:.6f})["name"]["opening_hours"];out center 20;'
    req = Request(OVERPASS, data=urlencode({'data': q}).encode('ascii'), method='POST',
                  headers={'User-Agent':'MINA-capstone-demo/1.8 (manual opening-hours query)',
                           'Content-Type':'application/x-www-form-urlencoded',
                           'Accept':'application/json'})
    try:
        with (opener or urlopen)(req, timeout=10) as response:
            body = response.read(200_001)
        if len(body) > 200_000:
            raise ValueError('Response too large')
        data = json.loads(body)
    except (OSError, ValueError, TimeoutError, UnicodeError):
        raise ToolUnavailable('OpenStreetMap hours lookup unavailable or malformed; no times were assumed.') from None
    if not isinstance(data, dict) or not isinstance(data.get('elements'), list):
        raise ToolUnavailable('OpenStreetMap hours lookup returned an invalid format.')
    matches = []
    for element in data['elements'][:30]:
        if not isinstance(element, dict):
            continue
        tags = element.get('tags')
        typ, eid = element.get('type'), element.get('id')
        if typ not in {'node', 'way', 'relation'} or type(eid) is not int or not isinstance(tags, dict):
            continue
        raw, actual = tags.get('opening_hours'), tags.get('name')
        if (isinstance(actual, str) and actual.casefold().strip() == name.casefold().strip()
                and isinstance(raw, str) and 0 < len(raw) <= 400):
            matches.append(OSMHoursFinding(actual, raw, f'https://www.openstreetmap.org/{typ}/{eid}'))
    if not matches:
        return None
    # Duplicate geometries or same-named neighboring businesses require review.
    if len(matches) != 1:
        raise LocationRequired('Multiple matching OSM venues; inspect manually before using opening hours.')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description='One-off OSM hours discovery; does NOT write schedules or change MINA plans.')
    parser.add_argument('--name', required=True, help='Exact public venue name on OpenStreetMap')
    parser.add_argument('--longitude', required=True, type=float)
    parser.add_argument('--latitude', required=True, type=float)
    args = parser.parse_args()
    try:
        finding = lookup_osm_hours(args.name, args.longitude, args.latitude)
    except (LocationRequired, ToolUnavailable) as exc:
        print('UNVERIFIED HOURS LOOKUP:', str(exc))
        raise SystemExit(1)
    if finding is None:
        print('NOT FOUND: OSM does not provide matching hours for this named venue here.')
    else:
        print('UNVERIFIED OPENSTREETMAP OPENING HOURS:', finding.opening_hours_raw)
        print('OSM PLACE:', finding.osm_url)
        print('Review against the venue website, holiday exceptions and actual location.')
        print('This query does NOT change Saved Places or feed these hours to the Planner.')

if __name__ == '__main__':
    main()
