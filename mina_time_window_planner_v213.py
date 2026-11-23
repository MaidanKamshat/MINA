"""MINA v2.13: route-specific, time-window-aware Planner -> Critic -> Controller.

Replaces *post-hoc schedule correction* for Family Hub trips with an explicit
bounded search scored against user-provided visit durations and pickup windows.
Travel times come from the HeiGIT/openrouteservice directed matrix (not traffic).
Location lookup/consent stays in the existing app. No local data writes here.
The frozen v1.8 backend is not modified; this is the Streamlit live route path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from itertools import permutations
from math import ceil, isfinite
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from urllib.request import Request, urlopen
import json
import os

from mina_trip_voice_v212 import clock_minutes, normalize_clock

MATRIX_ENDPOINT = 'https://api.openrouteservice.org/v2/matrix/driving-car'
DIRECTIONS_ENDPOINT = 'https://api.openrouteservice.org/v2/directions/driving-car/geojson'
TASK_ORDER = ('groceries', 'library', 'school_pickup')
LABELS = {'groceries':'Groceries', 'library':'Library', 'school_pickup':'School pickup'}


class LiveRouteError(ValueError):
    """Public, redacted error; never embeds private addresses, pins or API keys."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse_clock(value: str) -> int:
    try:
        return clock_minutes(normalize_clock(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise LiveRouteError('invalid_time', 'Please specify the planning time using AM or PM.') from None


def _clock(minutes: int) -> str:
    if not 0 <= minutes <= 1439:
        raise LiveRouteError('outside_day','The requested itinerary goes beyond the planning day.')
    hour, minute = divmod(minutes, 60)
    return f'{(hour % 12) or 12}:{minute:02d} {"AM" if hour < 12 else "PM"}'


def _point(value: str) -> list[float]:
    try:
        lon_s, lat_s = value.split(',')
        lon, lat = float(lon_s), float(lat_s)
        if not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError()
        return [lon, lat]
    except (ValueError, TypeError, AttributeError):
        raise LiveRouteError('invalid_point','One of the verified route points is invalid.') from None


def _api_key() -> str:
    # Support existing HeiGIT/ORS .env configurations without exposing key values.
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    except ImportError:
        pass
    for name in ('ORS_API_KEY', 'OPENROUTESERVICE_API_KEY',
                 'HEIGIT_API_KEY', 'OPENROUTESERVICE_KEY', 'ORS_KEY'):
        value = os.environ.get(name, '').strip()
        if value:
            return value
    raise LiveRouteError('missing_ors_key',
                         'No HeiGIT/openrouteservice API key was found for the time-aware route matrix.')


def _post_ors(endpoint: str, payload: dict, *, key: str) -> dict:
    # Endpoint is fixed in code; callers cannot supply URLs or redirect locations.
    if endpoint not in (MATRIX_ENDPOINT,DIRECTIONS_ENDPOINT):
        raise LiveRouteError('invalid_endpoint','Route provider configuration is invalid.')
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    req = Request(endpoint, data=body, method='POST', headers={
        'Accept':'application/json, application/geo+json',
        'Content-Type':'application/json', 'Authorization':key,
        'User-Agent':'MINA-Capstone-ProvisionalRoute/2.13'})
    try:
        with urlopen(req, timeout=18) as res:
            data = res.read(3_000_001)
            if len(data) > 3_000_000:
                raise LiveRouteError('provider_response_too_large','Route provider response was too large.')
        obj = json.loads(data)
        if not isinstance(obj, dict):
            raise ValueError()
        return obj
    except LiveRouteError:
        raise
    except (OSError, ValueError, TypeError, TimeoutError):
        # NEVER return raw exceptions: provider errors may contain key/query.
        raise LiveRouteError('provider_unavailable',
                             'HeiGIT route estimates could not be retrieved; no schedule was guessed.') from None


def _matrix(coords: list[list[float]]) -> dict:
    return _post_ors(MATRIX_ENDPOINT, {'locations':coords, 'metrics':['duration','distance']}, key=_api_key())


def _directions(coords: list[list[float]]) -> dict:
    return _post_ors(DIRECTIONS_ENDPOINT, {'coordinates':coords,'instructions':False}, key=_api_key())


def _validated_matrix(data: dict, size: int) -> tuple[list[list[float | None]], list[list[float | None]]]:
    if not isinstance(data,dict):
        raise LiveRouteError('invalid_matrix','HeiGIT did not return a usable route matrix.')
    def validate(name):
        m = data.get(name)
        if not isinstance(m,list) or len(m) != size:
            raise LiveRouteError('invalid_matrix','HeiGIT did not return a usable route matrix.')
        output=[]
        for row in m:
            if not isinstance(row,list) or len(row)!=size:
                raise LiveRouteError('invalid_matrix','HeiGIT did not return a usable route matrix.')
            record=[]
            for value in row:
                if value is None:
                    record.append(None)
                elif isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value) and value >= 0:
                    record.append(float(value))
                else:
                    raise LiveRouteError('invalid_matrix','HeiGIT returned invalid travel estimates.')
            output.append(record)
        return output
    durations=validate('durations')
    distances=validate('distances') if 'distances' in data else [[None]*size for _ in range(size)]
    return durations,distances


@dataclass(frozen=True)
class ScheduleCandidate:
    sequence: tuple[str, ...]
    feasible: bool
    reason: str
    timeline: tuple[dict, ...]
    travel_minutes: int
    buffer_minutes: int
    waiting_minutes: int
    finish_minutes: int | None
    score: int | None


def planner_candidates(tasks: tuple[str,...]) -> list[tuple[str,...]]:
    """Planner: exhaustive bounded alternative orders, school always last."""
    if not tasks or len(tasks) > 6 or len(tasks) != len(set(tasks)) or set(tasks)-set(TASK_ORDER):
        raise LiveRouteError('unsupported_tasks','This route has an unsupported set of stops.')
    pickup = 'school_pickup' in tasks
    errands = sorted(t for t in tasks if t != 'school_pickup')
    return [p + (('school_pickup',) if pickup else ()) for p in permutations(errands)]


def critic_candidate(sequence: tuple[str,...], *, tasks:tuple[str,...],
                     start_minutes: int, durations:dict[str,int],
                     matrix_seconds:list[list[float|None]],
                     indices:dict[str,int], buffer_minutes:int,
                     windows:dict[str,tuple[int,int|None]]) -> ScheduleCandidate:
    """Critic: service START not earlier than opening; service END <= latest.

    Early school arrival is held *before* the final school leg, not passed off
    as an actual early pickup. Travel buffer applies to each leg including home.
    """
    if len(sequence)!=len(tasks) or set(sequence)!=set(tasks) or len(set(sequence))!=len(sequence):
        return ScheduleCandidate(sequence,False,'missing_or_duplicate_tasks',(),0,0,0,None,None)
    if 'school_pickup' in tasks and sequence[-1]!='school_pickup':
        return ScheduleCandidate(sequence,False,'school_pickup_not_last',(),0,0,0,None,None)
    now=start_minutes; previous='origin'; elapsed_driving=elapsed_buffer=wait_total=0
    steps=[]
    for task in sequence:
        seconds = matrix_seconds[indices[previous]][indices[task]]
        if seconds is None:
            return ScheduleCandidate(sequence,False,'travel_estimate_missing',tuple(steps),
                                     elapsed_driving,elapsed_buffer,wait_total,None,None)
        drive_minutes = ceil(seconds/60)
        travel_plus_buffer = drive_minutes + buffer_minutes
        pre_leg_departure = now
        arriving = now + travel_plus_buffer
        elapsed_driving += drive_minutes
        elapsed_buffer += buffer_minutes
        opening, closing = windows.get(task,(0,None))
        hold_before = 0
        waiting_at_venue = 0
        # Prefer flexible time before school departure, not waiting on school grounds.
        if task == 'school_pickup' and arriving < opening:
            hold_before = opening - arriving
            now += hold_before
            arriving += hold_before
            wait_total += hold_before
        if task != 'school_pickup' and arriving < opening:
            waiting_at_venue = opening-arriving
            wait_total += waiting_at_venue
        service_start = arriving + waiting_at_venue
        service_end = service_start + durations[task]
        if service_end > 1439:
            return ScheduleCandidate(sequence,False,'outside_planning_day',tuple(steps),
                                     elapsed_driving,elapsed_buffer,wait_total,None,None)
        if closing is not None and service_end > closing:
            return ScheduleCandidate(sequence,False,
                                     'pickup_window_missed' if task == 'school_pickup' else 'venue_window_missed',
                                     tuple(steps),elapsed_driving,elapsed_buffer,wait_total,service_end,None)
        steps.append({'task':task, 'from':previous, 'departure':now,
                      'pre_hold_departure':pre_leg_departure,
                      'drive_minutes':drive_minutes,'buffer_minutes':buffer_minutes,
                      'hold_before_leg_minutes':hold_before,
                      'arrival':arriving, 'venue_wait_minutes':waiting_at_venue,
                      'service_start':service_start,'service_end':service_end})
        now=service_end; previous=task
    # Objective: minimize driving (+buffers) then time outside active errands.
    score=-(elapsed_driving*1000 + elapsed_buffer*10 + wait_total)
    return ScheduleCandidate(sequence,True,'all_time_windows_satisfied',tuple(steps),
                             elapsed_driving,elapsed_buffer,wait_total,now,score)


def controller_select(candidates:list[ScheduleCandidate]) -> ScheduleCandidate | None:
    """Controller: only Critic-approved candidates, deterministic tie-break."""
    passed=[c for c in candidates if c.feasible]
    return sorted(passed,key=lambda c:(-c.score,c.sequence))[0] if passed else None


def _validated_geometry(geo:dict) -> list[list[float]] | None:
    try:
        features=geo['features']; shape=features[0]['geometry']
        if shape['type'] != 'LineString':
            return None
        coords=shape['coordinates']
        if not isinstance(coords,list) or len(coords)<2 or len(coords)>50000:
            return None
        return [_point(f'{a[0]},{a[1]}') for a in coords]
    except (KeyError,IndexError,ValueError,TypeError,LiveRouteError):
        return None


def _js_json(value) -> str:
    return json.dumps(value, separators=(',',':')).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026')


def _route_map_html(route_line: list[list[float]], stops: list[tuple[str,list[float]]]) -> str:
    # All interpolated data is numeric, fixed labels, and JSON escaped.
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>html,body,#map{height:100%;margin:0}#title{z-index:900;position:absolute;left:10px;top:10px;background:white;padding:6px 9px;border-radius:6px;font:13px sans-serif;box-shadow:0 1px 4px #999;max-width:85%}</style>
</head><body><div id="map"></div><div id="title">Family Hub route · HeiGIT estimates · not live traffic</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const route='''+_js_json([[lat,lon] for lon,lat in route_line])+''';
const stops='''+_js_json([{'label':label,'point':[coord[1],coord[0]]} for label,coord in stops])+''';
if(window.L){const map=L.map('map');L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);const line=L.polyline(route,{color:'#2F64AF',weight:5}).addTo(map);for(const s of stops){L.marker(s.point).addTo(map).bindPopup(s.label)}map.fitBounds(line.getBounds().pad(0.1))}
</script></body></html>'''


def _format_result(selected: ScheduleCandidate, *, plan_date:str|None,
                   departure_time:str, store_label:str,buffer_minutes:int,
                   count:int, rejected:int, distance_km:float|None) -> str:
    lines=['### Proposed time-window-aware route · provisional','',
           f'**Date:** {plan_date or "not specified"} · **Depart:** {departure_time}',
           '', '**Planner → Critic → Controller:** evaluated '
           f'**{count}** candidate orders; **{rejected}** failed or had missing travel data. '
           'The selected itinerary satisfies the **user-provided** modeled windows.','',
           'Estimated leg driving times come from **HeiGIT/openrouteservice**, '
           '**not live traffic**. Each leg also includes the saved '
           f'**{buffer_minutes}-minute planning buffer**.','',]
    for leg in selected.timeline:
        task=leg['task'];label=store_label if task=='groceries' else LABELS[task]
        if leg['hold_before_leg_minutes']:
            lines.append(f'- **{_clock(leg["pre_hold_departure"])}–{_clock(leg["departure"])}** — '
                         f'Flexible time before going to {label} ({leg["hold_before_leg_minutes"]} min).')
        if leg['venue_wait_minutes']:
            lines.append(f'- **{_clock(leg["arrival"])}–{_clock(leg["service_start"])}** — '
                         f'Wait for the user-entered opening window at {label}.')
        lines.append(f'- **{_clock(leg["service_start"])}–{_clock(leg["service_end"])}** — '
                     f'{label} ({leg["service_end"]-leg["service_start"]} min; '
                     f'arrive about {_clock(leg["arrival"])}).')
    distance_text = (f'**Distance estimate:** {distance_km:.2f} km · ' if distance_km is not None else '')
    lines += ['', distance_text + f'**Driving estimate:** {selected.travel_minutes} min · '
              f'**Buffers:** {selected.buffer_minutes} min · '
              f'**Flexible/wait time:** {selected.waiting_minutes} min.',
              '', '*Provisional only: school/store hours and availability were not verified. '
              'Travel times are not departure-time-specific; confirm commitments independently. '
              'No calendar, shopping-list, or email changes were made.*']
    return '\n'.join(lines)


def pickup_window_from_target(target: str | None, duration_minutes: int) -> tuple[str,str] | None:
    """Convert an explicitly saved pickup TARGET + duration to a bounded window."""
    if not target:
        return None
    if not isinstance(duration_minutes,int) or not (1<=duration_minutes<=360):
        raise LiveRouteError('invalid_duration','Saved pickup duration is invalid.')
    start=_parse_clock(target)
    if start + duration_minutes >= 1440:
        raise LiveRouteError('invalid_pickup_window','Saved pickup would extend beyond the day.')
    return _clock(start),_clock(start+duration_minutes)


def plan_family_route(*, origin:str, locations:dict[str,str],
                      tasks:tuple[str,...], depart_time:str, plan_date:str|None,
                      durations:dict[str,int], pickup_window:tuple[str,str]|None,
                      library_open:str|None, buffer_minutes:int,
                      store_label:str='Groceries',
                      matrix_fetcher:Callable|None=None,
                      geometry_fetcher:Callable|None=None):
    """Execute Planner -> Critic -> Controller with real provider leg estimates.

    `matrix_fetcher`/`geometry_fetcher` allow offline tests; production makes
    at most one ORS matrix + one ORS directions call. No placeholder ETAs.
    """
    if not set(tasks) <= set(locations) or not tasks:
        raise LiveRouteError('missing_stop','A saved route stop is missing.')
    if not isinstance(buffer_minutes,int) or not (0<=buffer_minutes<=180):
        raise LiveRouteError('invalid_buffer','The route buffer must be 0–180 minutes.')
    if plan_date:
        try: date.fromisoformat(plan_date)
        except ValueError: raise LiveRouteError('invalid_date','The plan date is invalid.') from None
    start=_parse_clock(depart_time)
    for task in tasks:
        if task not in durations or not isinstance(durations[task],int) or not (1<=durations[task]<=360):
            raise LiveRouteError('invalid_duration','A visit duration is missing or invalid.')
    windows={}
    if 'school_pickup' in tasks:
        if not pickup_window:
            raise LiveRouteError('missing_pickup_window',
                                 'A school pickup time window is needed before route planning.')
        earliest,latest=map(_parse_clock,pickup_window)
        if not 0<=earliest<latest<=1439:
            raise LiveRouteError('invalid_pickup_window','The pickup window is invalid.')
        if latest-earliest < durations['school_pickup']:
            return SimpleNamespace(status='no_feasible_plan',
                answer='**No feasible schedule:** pickup duration exceeds the requested school window. '
                       'Nothing was changed.',trace=[{'step':'critic','status':'rejected_pickup_duration',
                       'version':'2.13.0'}],candidates=[],map_report=None,route_map_html=None)
        windows['school_pickup']=(earliest,latest)
    if 'library' in tasks and library_open:
        windows['library']=(_parse_clock(library_open),None)
    # Explicit, deterministic order matches matrix indices (no private data in traces).
    names=('origin',)+tuple(t for t in TASK_ORDER if t in tasks)
    indices={key:i for i,key in enumerate(names)}
    points=[_point(origin if name=='origin' else locations[name]) for name in names]
    try:
        raw=(matrix_fetcher or _matrix)(points)
        secs,dist=_validated_matrix(raw,len(points))
    except LiveRouteError:
        raise
    except Exception:
        raise LiveRouteError('provider_unavailable',
                             'HeiGIT travel matrix could not be retrieved; no schedule was guessed.') from None
    sequences=planner_candidates(tasks)
    candidates=[critic_candidate(sequence,tasks=tasks,start_minutes=start,durations=durations,
                                 matrix_seconds=secs,indices=indices,buffer_minutes=buffer_minutes,
                                 windows=windows) for sequence in sequences]
    approved=controller_select(candidates)
    trace=[{'step':'coordinator','intent':'planning','route':'complex',
            'task_ids':list(tasks)},
           {'step':'live_route_matrix','status':'ok','provider':'HeiGIT/openrouteservice',
            'location_count':len(points),'date':plan_date,'time_dependent_traffic':False},
           {'step':'planner','version':'2.13.0','strategy':'bounded_exhaustive_time_window',
            'generated':len(sequences)},
           {'step':'critic','version':'2.13.0', 'evaluated':len(candidates),
            'passed':sum(c.feasible for c in candidates),
            'rejected_reasons':sorted({c.reason for c in candidates if not c.feasible}),
            'user_supplied_pickup_window':list(pickup_window) if pickup_window else None,
            'user_supplied_library_open':library_open or None,
            'service_durations':dict(durations),'travel_buffer_per_leg':buffer_minutes}]
    cand_output=[{'sequence':list(c.sequence),'feasible':c.feasible,'reason':c.reason,
                  'score':c.score, 'travel_minutes':c.travel_minutes,
                  'waiting_minutes':c.waiting_minutes,
                  'timeline':[{k:(_clock(v) if k in ('arrival','service_start','service_end') else v)
                              for k,v in leg.items()} for leg in c.timeline]} for c in candidates]
    if approved is None:
        incompletes=any(c.reason=='travel_estimate_missing' for c in candidates)
        trace.append({'step':'controller','version':'2.13.0','selected':None,
                      'reason':'missing_travel_data' if incompletes else 'no_feasible_candidate'})
        return SimpleNamespace(status='needs_clarification' if incompletes else 'no_feasible_plan',
            answer=('Some HeiGIT route legs have no travel estimate; timing cannot be evaluated safely.'
                    if incompletes else 'No candidate itinerary fits the user-provided pickup window and visit durations.')
                    +' **No calendar/list/email changes were made.**',
            trace=trace,candidates=cand_output,map_report=None,route_map_html=None)
    ordered=('origin',)+approved.sequence
    leg_distances=[dist[indices[a]][indices[b]] for a,b in zip(ordered,ordered[1:])]
    total_distance_km=(round(sum(leg_distances)/1000,2)
                       if all(x is not None for x in leg_distances) else None)
    trace.append({'step':'controller','version':'2.13.0','decision':'selected_feasible_only',
                  'selected':list(approved.sequence),'score':approved.score,
                  'travel_minutes':approved.travel_minutes,'waiting_minutes':approved.waiting_minutes,
                  'distance_km':total_distance_km})
    geometry=None; route_map_html=None
    try:
        geo=(geometry_fetcher or _directions)([points[indices[k]] for k in ordered])
        geometry=_validated_geometry(geo)
        if geometry:
            route_map_html=_route_map_html(geometry,
                [(('Start: Home' if key=='origin' else
                   (store_label if key=='groceries' else LABELS[key])),points[indices[key]])
                 for key in ordered])
    except (LiveRouteError, OSError, ValueError):
        pass
    except Exception:
        pass
    trace.append({'step':'route_map','source':'HeiGIT/openrouteservice' if geometry else 'unavailable',
                  'selected_order':list(approved.sequence),
                  'same_order_as_controller':bool(geometry),
                  'status':'provider_geometry' if geometry else 'not_displayed'})
    return SimpleNamespace(status='provisional_live_route_plan',
        answer=_format_result(approved,plan_date=plan_date,departure_time=depart_time,
                              store_label=store_label,buffer_minutes=buffer_minutes,
                              count=len(candidates),rejected=sum(not c.feasible for c in candidates),
                              distance_km=total_distance_km),
        trace=trace,candidates=cand_output,map_report=None,route_map_html=route_map_html)
