"""Explicit, privacy-gated geocoding preflight for MINA Family Hub routes.

No route, list, calendar or hub writes. Called only after a separate UI consent
for public geocoders and HeiGIT route services. Never persist addresses/coordinates.
Conservative matching (house number, street and ZIP) prevents a nearby but wrong
POI result from being used for a school pickup or a private home.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_CENSUS = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
_PHOTON = 'https://photon.komoot.io/api/'
_ADDRESS_RE = re.compile(r'^(?P<line>.+?),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?(?:,?\s+(?:USA|US))?$', re.I)
_COORD_RE = re.compile(r'^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,2}(?:\.\d+)?)\s*$')
_UNIT_RE = re.compile(r'(?:,\s*|\s+)(?:STE|SUITE|UNIT|APT|APARTMENT|#)\s*[-#\w]+.*$', re.I)
_STREET_WORDS = {'DRIVE':'DR', 'ROAD':'RD', 'STREET':'ST', 'AVENUE':'AVE',
                 'BOULEVARD':'BLVD', 'LANE':'LN', 'PARKWAY':'PKWY', 'COURT':'CT',
                 'PLACE':'PL', 'CIRCLE':'CIR', 'HIGHWAY':'HWY', 'TRAIL':'TRL'}
_LABEL = {'origin':'home', 'library':'library', 'groceries':'shopping stop', 'school_pickup':'school pickup'}

class SavedRouteLocationError(ValueError):
    """Public diagnostics ONLY; never include raw address or exception text."""
    def __init__(self, key: str, reason: str):
        self.key=key
        self.label=_LABEL.get(key,'saved stop')
        self.reason=reason
        super().__init__(f'{self.label}: {reason}')

@dataclass(frozen=True)
class ResolvedRoute:
    origin: str
    locations: dict[str,str]
    provider_by_stop: dict[str,str]


def _tokens(value: str) -> tuple[str,...]:
    line=_UNIT_RE.sub('', value.upper())
    t=re.findall(r'[A-Z0-9]+',line)
    return tuple(_STREET_WORDS.get(x,x) for x in t)


def _spec(address: str):
    m=_ADDRESS_RE.fullmatch(address.strip())
    if not m: return None
    line=m['line'].strip()
    # Unit/suite numbers are not address-house numbers.
    house=re.match(r'^(\d+[A-Z]?)\s+(.+)$',line,re.I)
    if not house:return None
    street=_tokens(house.group(2))
    if not street:return None
    return {'house':house.group(1).upper(),'street':street,'city':m['city'].strip().upper(),
            'state':m['state'].upper(),'zip':m['zip']}


def _as_coord(lon,lat):
    try:
        lo=float(lon);la=float(lat)
        if not (math.isfinite(lo) and math.isfinite(la) and -180<=lo<=180 and -90<=la<=90):return None
        return f'{lo:.6f},{la:.6f}'
    except (ValueError,TypeError,OverflowError):return None


def _fetch_json(url: str):
    # Avoid sending addresses to any arbitrary endpoint; only hardcoded HTTPS providers.
    request=Request(url,headers={'Accept':'application/json', 'User-Agent':'MINA-Capstone-RoutePrototype/2.12.3'})
    with urlopen(request,timeout=8) as response:
        return json.load(response)


def _census_match(data, spec):
    matches=((data or {}).get('result') or {}).get('addressMatches') or []
    accepted=[]
    for item in matches:
        matched=str(item.get('matchedAddress') or '')
        match=re.match(r'^\s*(\d+[A-Z]?)\s+([^,]+),\s*([^,]+),\s*([A-Z]{2}),?\s*(\d{5})',matched,re.I)
        if not match: continue
        num, street, city, state, postal=match.groups()
        if (num.upper()!=spec['house'] or _tokens(street)!=spec['street']
            or city.strip().upper()!=spec['city'] or state.upper()!=spec['state'] or postal!=spec['zip']):
            continue
        coords=item.get('coordinates') or {}
        c=_as_coord(coords.get('x'),coords.get('y'))
        if c:accepted.append(c)
    return accepted[0] if len(set(accepted))==1 else None


def _photon_match(data, spec):
    accepted=[]
    for item in ((data or {}).get('features') or []):
        prop=item.get('properties') or {}
        if (str(prop.get('housenumber') or '').upper()!=spec['house']
            or _tokens(str(prop.get('street') or ''))!=spec['street']
            or str(prop.get('postcode') or '')[:5]!=spec['zip']):
            continue
        if prop.get('countrycode') and str(prop['countrycode']).upper()!='US':continue
        geom=item.get('geometry') or {}
        coords=geom.get('coordinates') or []
        if len(coords)<2:continue
        c=_as_coord(coords[0],coords[1])
        if c:accepted.append(c)
    return accepted[0] if len(set(accepted))==1 else None


def _resolve_one(address: str, key: str, fetcher):
    s=(address or '').strip()
    direct=_COORD_RE.fullmatch(s)
    if direct:
        c=_as_coord(direct.group(1),direct.group(2))
        if c:return c,'already_coordinates'
        raise SavedRouteLocationError(key,'invalid_coordinates')
    spec=_spec(s)
    if spec is None:
        raise SavedRouteLocationError(key,'incomplete_street_address')
    # Unit/apt is intentionally omitted only from the public geocoding query;
    # otherwise a correct street address may fail exact street matching.
    parts=_ADDRESS_RE.fullmatch(s)
    query=f"{_UNIT_RE.sub('',parts['line'])}, {parts['city']}, {parts['state']} {parts['zip']}"
    outages=0
    try:
        url=_CENSUS+'?'+urlencode({'address':query,'benchmark':'Public_AR_Current','format':'json'})
        c=_census_match(fetcher(url),spec)
        if c:return c,'Census'
    except (OSError,ValueError,TypeError,KeyError,TimeoutError):outages+=1
    try:
        url=_PHOTON+'?'+urlencode({'q':query,'limit':5,'lang':'en','countrycode':'US'})
        c=_photon_match(fetcher(url),spec)
        if c:return c,'Photon'
    except (OSError,ValueError,TypeError,KeyError,TimeoutError):outages+=1
    raise SavedRouteLocationError(key, 'geocoding_unavailable' if outages==2 else 'not_confidently_matched')


def resolve_saved_route_points(origin: str, locations: dict[str,str], *, fetcher=None,
                                verified_overrides: dict[str,str] | None = None)->ResolvedRoute:
    """Convert all requested private Family Hub route locations to backend coordinates.

    Caller MUST check the user's geocoding+route consent first. No result is
    published to the routing backend if any stop has a doubtful match.
    """
    if fetcher is None:fetcher=_fetch_json
    verified_overrides = verified_overrides or {}
    # Overrides come only from local route-pin data saved after explicit user
    # verification, not from model output or an arbitrary HTTP provider match.
    allowed = {'origin', 'library', 'groceries', 'school_pickup'}
    if set(verified_overrides) - allowed:
        raise SavedRouteLocationError('origin','invalid_verified_pin_key')
    def pick(key, address):
        if key not in verified_overrides:
            return _resolve_one(address,key,fetcher)
        candidate=verified_overrides[key]
        m=_COORD_RE.fullmatch(candidate or '')
        if not m:
            raise SavedRouteLocationError(key,'invalid_verified_coordinates')
        normalized=_as_coord(*m.groups())
        if not normalized:
            raise SavedRouteLocationError(key,'invalid_verified_coordinates')
        return normalized,'user_verified_local_pin'
    o,source=pick('origin',origin)
    coords={};providers={'origin':source}
    for key,address in locations.items():
        coords[key],providers[key]=pick(key,address)
    return ResolvedRoute(o,coords,providers)
