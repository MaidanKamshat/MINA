"""Prepare a conservative, provenance-aware family-plan call from voice + saved local profile.

Does not route, geocode, call an API, mutate hub data, or certify an itinerary.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from mina_trip_voice_v212 import parse_trip_voice, TripParseError

STORE_LABELS = {'target': 'Target', 'costco': 'Costco', 'trader_joes': "Trader Joe's"}

@dataclass(frozen=True)
class RouteBridgeInputs:
    missing: tuple[str, ...]
    requested: frozenset[str]
    origin: str
    locations: dict[str, str]
    durations: dict[str, int]
    start_time: str | None
    plan_date: str | None
    library_open: str
    buffer_minutes: int
    prompt_for_planner: str
    source_store: str | None
    pickup_window: tuple[str, str] | None


def build_route_inputs(prompt: str, *, today: date, hub: dict | None) -> RouteBridgeInputs:
    trip = parse_trip_voice(prompt, today=today)
    hub = hub if isinstance(hub, dict) else {}
    prefs = hub.get('preferences') or {}
    places = hub.get('places') or {}
    missing: list[str] = []
    origin = str(prefs.get('home_address') or '').strip()
    if not origin: missing.append('home departure address')
    locations: dict[str,str] = {}
    if 'library' in trip.requested_tasks:
        locations['library'] = str((places.get('library') or {}).get('address') or '').strip()
        if not locations['library']: missing.append('library address')
        if not prefs.get('library_open_time'): missing.append('user-provided library opening time')
    if 'groceries' in trip.requested_tasks:
        # An explicit store ALWAYS determines the map location. Never substitute Target for Costco.
        store = trip.store or 'target'
        locations['groceries'] = str((places.get(store) or {}).get('address') or '').strip()
        if not locations['groceries']: missing.append(f'{STORE_LABELS[store]} address')
    if 'school_pickup' in trip.requested_tasks:
        locations['school_pickup'] = str(prefs.get('school_address') or '').strip()
        if not locations['school_pickup']: missing.append('school pickup address')
        if not (prefs.get('pickup_time') or trip.pickup_window):
            missing.append('school pickup time/window')
    durations = {
        'library': int(prefs.get('library_minutes') or 15),
        'groceries': int(prefs.get('shopping_minutes') or 45),
        'school_pickup': int(prefs.get('pickup_minutes') or 10),
    }
    for k,v in trip.duration_overrides.items():
        durations[k] = v
    durations = {k:v for k,v in durations.items() if k in trip.requested_tasks}
    if any(x < 1 or x > 360 for x in durations.values()):
        raise TripParseError('Saved visit duration must be between 1 and 360 minutes.')
    buf = int(prefs.get('buffer_minutes', 15))
    if not 0 <= buf <= 180:
        raise TripParseError('Saved route buffer is invalid; review Settings.')
    normalized = trip.prompt_for_planner
    # The core scheduling engine must see the pickup scope and source clearly.
    # If the user's prompt states a school window, do not inject a conflicting saved target.
    if 'school_pickup' in trip.requested_tasks and not trip.pickup_window and prefs.get('pickup_time'):
        normalized += (' School pickup is at ' + str(prefs['pickup_time'])
                       + ' according to my saved local notes (not school-verified).')
    return RouteBridgeInputs(tuple(missing), trip.requested_tasks, origin,
          locations, durations, trip.departure_time, trip.plan_date,
          str(prefs.get('library_open_time') or '') if 'library' in trip.requested_tasks else '',
          buf, normalized, trip.store, trip.pickup_window)


def paired_backend_plan_date(saved_places_file: str | None, requested_date: str | None) -> str:
    """Respect the v1.8 `--saved-places`/`--plan-date` pairing contract.

    Family Hub route inputs are passed as explicit origin/task_locations and
    durations, not through a v1.8 Saved Places JSON file. Passing a date
    without that file throws UIInputError before routing. The user-supplied
    date still remains present in the original prompt and in the trace, but
    this helper does not claim calendar-accurate hours or timed availability.
    """
    file_arg = (saved_places_file or '').strip()
    date_arg = (requested_date or '').strip()
    if not file_arg:
        return ''
    # Never create a file on the user's Mac; this is only the paired parameter.
    # Caller is responsible for requiring a valid date if a file is supplied.
    return date_arg
