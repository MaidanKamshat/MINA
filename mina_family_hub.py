"""Local-only, user-controlled family shopping lists and place-pairing suggestions.

The three shopping lists and scheduled visits live in a gitignored local JSON.
External calendar/list/email providers are *not* connected. A route is checked
with HeiGIT only when the user opted in and explicitly supplied both addresses.
No guessed distances, addresses, business hours, or appointment availabilities.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Any

from mina_saved_places import display_clock, parse_clock
from mina_live_tools import LocationRequired, ToolUnavailable

STORES = {'costco': 'Costco', 'target': 'Target', 'trader_joes': "Trader Joe’s"}
PLACES = {**STORES, 'library': 'Library', 'dentist': 'Dentist', 'pediatrician': 'Pediatrician'}
PAIRS = (('library', 'costco'), ('dentist', 'target'), ('pediatrician', 'trader_joes'))
MAX_FILE_BYTES = 80_000
LOCAL_DATA = Path(__file__).resolve().parent / 'local_data' / 'mina_family_hub.json'


class FamilyHubError(ValueError):
    pass


def blank_hub() -> dict:
    return {
        'schema_version': '1.0', 'source': 'user_provided_local',
        'stores': {key: [] for key in STORES},
        'places': {key: {'name': name, 'address': '', 'notes': ''} for key, name in PLACES.items()},
        'visits': [],
        'preferences': {'pickup_time': '', 'school_address': '', 'home_address': '', 'shopping_minutes': 45, 'lunch_minutes': 45, 'buffer_minutes': 15,
                        'library_minutes': 15, 'pickup_minutes': 10, 'library_open_time': ''},
        'pairings': [{'visit': visit, 'store': store} for visit, store in PAIRS],
    }


def _safe_text(value: Any, *, max_len: int, may_be_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise FamilyHubError('Text field must be a string.')
    value = value.strip()
    if (len(value) > max_len or (not may_be_empty and not value) or
            any(ord(ch) < 32 for ch in value) or any(ch in value for ch in '<>')):
        raise FamilyHubError(f'Enter a valid text value up to {max_len} characters.')
    return value


def validate_hub(hub: dict) -> dict:
    if not isinstance(hub, dict) or hub.get('schema_version') != '1.0':
        raise FamilyHubError('Unrecognized Family Hub schema version.')
    if hub.get('source') != 'user_provided_local':
        raise FamilyHubError('Family Hub must be marked as local user-provided information.')
    if not isinstance(hub.get('places'), dict) or set(hub['places']) != set(PLACES):
        raise FamilyHubError('Family Hub must have the six supported Saved Places.')
    for place_id, p in hub['places'].items():
        if not isinstance(p, dict) or set(p) != {'name', 'address', 'notes'}:
            raise FamilyHubError(f'Invalid Saved Place: {place_id}.')
        _safe_text(p['name'], max_len=70)
        _safe_text(p['address'], max_len=180, may_be_empty=True)
        _safe_text(p['notes'], max_len=240, may_be_empty=True)
    stores = hub.get('stores')
    if not isinstance(stores, dict) or set(stores) != set(STORES):
        raise FamilyHubError('Family Hub supports three separate store lists.')
    all_ids = set()
    for store_id, items in stores.items():
        if not isinstance(items, list) or len(items) > 100:
            raise FamilyHubError(f'{store_id} list must contain no more than 100 items.')
        names = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {'id', 'name', 'done'}:
                raise FamilyHubError('Invalid shopping item.')
            item_id = _safe_text(item['id'], max_len=50)
            if not re.fullmatch('[a-zA-Z0-9_-]+', item_id) or item_id in all_ids:
                raise FamilyHubError('Invalid or duplicate shopping item identifier.')
            all_ids.add(item_id)
            name = _safe_text(item['name'], max_len=80).casefold()
            if name in names or type(item['done']) is not bool:
                raise FamilyHubError('Duplicate shopping item or invalid completion flag.')
            names.add(name)
    prefs = hub.get('preferences')
    if prefs is not None:
        required = {'pickup_time', 'school_address', 'home_address', 'shopping_minutes', 'lunch_minutes', 'buffer_minutes'}
        optional = {'library_minutes', 'pickup_minutes', 'library_open_time'}
        if not isinstance(prefs, dict) or not required <= set(prefs) or set(prefs) - required - optional:
            raise FamilyHubError('Invalid Family Hub scheduling preferences.')
        if prefs['pickup_time']:
            try:
                parse_clock(prefs['pickup_time'])
            except ValueError:
                raise FamilyHubError('School pickup must use 12-hour AM/PM time.') from None
        if prefs.get('library_open_time'):
            try:
                parse_clock(prefs['library_open_time'])
            except ValueError:
                raise FamilyHubError('Library opening needs AM/PM time.') from None
        for key in ('school_address', 'home_address'):
            _safe_text(prefs[key], max_len=180, may_be_empty=True)
        for key in ('shopping_minutes', 'lunch_minutes', 'buffer_minutes', 'library_minutes', 'pickup_minutes'):
            if key in prefs and (type(prefs[key]) is not int or not 0 <= prefs[key] <= 180):
                raise FamilyHubError('Shopping/lunch/buffer preferences must be 0–180 minutes.')
    visits = hub.get('visits')
    if not isinstance(visits, list) or len(visits) > 40:
        raise FamilyHubError('Family Hub supports up to 40 saved visits.')
    visit_ids = set()
    for visit in visits:
        if not isinstance(visit, dict) or not {'id', 'place', 'date', 'time', 'title'} <= set(visit) or set(visit) - {'id', 'place', 'date', 'time', 'title', 'end_time'}:
            raise FamilyHubError('Invalid scheduled visit.')
        visit_id = _safe_text(visit['id'], max_len=50)
        if not re.fullmatch('[a-zA-Z0-9_-]+', visit_id) or visit_id in visit_ids:
            raise FamilyHubError('Invalid or duplicate visit identifier.')
        visit_ids.add(visit_id)
        if visit['place'] not in {'library', 'dentist', 'pediatrician'}:
            raise FamilyHubError('Only library/dentist/pediatrician visits can be paired in this MVP.')
        _safe_text(visit['title'], max_len=90)
        try:
            date.fromisoformat(visit['date'])
            start = parse_clock(visit['time'])
            if visit.get('end_time'):
                end = parse_clock(visit['end_time'])
                if end <= start:
                    raise ValueError('Visit end must be later than start')
        except (ValueError, TypeError):
            raise FamilyHubError('Visits need a valid ISO date and 12-hour AM/PM time.') from None
    pairs = hub.get('pairings')
    if (not isinstance(pairs, list) or len(pairs) != len(PAIRS)
            or {(p.get('visit'), p.get('store')) for p in pairs if isinstance(p, dict)} != set(PAIRS)):
        raise FamilyHubError('Only the three approved visit/store pairings are supported in this MVP.')
    return hub


def load_hub(path: Path = LOCAL_DATA) -> dict:
    path = Path(path)
    if not path.exists():
        return blank_hub()
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise FamilyHubError('Family Hub local data file is too large.')
        hub = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FamilyHubError('Family Hub local JSON is missing, corrupt, or unreadable.') from exc
    return validate_hub(hub)


def save_hub(hub: dict, path: Path = LOCAL_DATA) -> Path:
    validate_hub(hub)
    path = Path(path)
    raw = json.dumps(hub, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise FamilyHubError('Family Hub data limit exceeded.')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents partial local writes if the app crashes mid-save.
    fd, temp_name = tempfile.mkstemp(prefix='.mina_hub_', dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as fp:
            fp.write(raw)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path


def update_place(hub: dict, place_id: str, *, name: str, address: str, notes: str = '') -> dict:
    if place_id not in PLACES:
        raise FamilyHubError('Unsupported saved place.')
    new = copy.deepcopy(hub)
    new['places'][place_id] = {
        'name': _safe_text(name, max_len=70),
        'address': _safe_text(address, max_len=180, may_be_empty=True),
        'notes': _safe_text(notes, max_len=240, may_be_empty=True),
    }
    return validate_hub(new)


def add_item(hub: dict, store_id: str, item_name: str) -> dict:
    if store_id not in STORES:
        raise FamilyHubError('Choose Costco, Target, or Trader Joe’s.')
    name = _safe_text(item_name, max_len=80)
    new = copy.deepcopy(hub)
    items = new['stores'][store_id]
    if name.casefold() in {item['name'].casefold() for item in items}:
        raise FamilyHubError('That item is already on this store list.')
    if len(items) >= 100:
        raise FamilyHubError('Maximum 100 items per store.')
    all_ids = {x['id'] for each in new['stores'].values() for x in each}
    count = 1
    while f'item_{count}' in all_ids:
        count += 1
    items.append({'id': f'item_{count}', 'name': name, 'done': False})
    return validate_hub(new)


def set_item_done(hub: dict, store_id: str, item_id: str, done: bool) -> dict:
    if store_id not in STORES or type(done) is not bool:
        raise FamilyHubError('Invalid store or completion value.')
    new = copy.deepcopy(hub)
    found = False
    for item in new['stores'][store_id]:
        if item['id'] == item_id:
            item['done'] = done
            found = True
    if not found:
        raise FamilyHubError('Shopping item not found in selected store.')
    return validate_hub(new)


def add_visit(hub: dict, *, place_id: str, day: str, time: str, title: str, end_time: str = '') -> dict:
    if place_id not in {'library', 'dentist', 'pediatrician'}:
        raise FamilyHubError('Choose Library, Dentist or Pediatrician.')
    try:
        date.fromisoformat(day)
        start_internal = parse_clock(time)
        valid_time = display_clock(start_internal)
        valid_end = display_clock(parse_clock(end_time)) if end_time else ''
        if valid_end and parse_clock(valid_end) <= start_internal:
            raise ValueError('End is not later than start')
    except (TypeError, ValueError):
        raise FamilyHubError('Visit requires a real date and AM/PM time such as 3:15 PM.') from None
    new = copy.deepcopy(hub)
    ids = {v['id'] for v in new['visits']}
    n = 1
    while f'visit_{n}' in ids:
        n += 1
    record = {'id': f'visit_{n}', 'place': place_id, 'date': day,
              'time': valid_time, 'title': _safe_text(title, max_len=90)}
    if valid_end:
        record['end_time'] = valid_end
    new['visits'].append(record)
    return validate_hub(new)


def set_preferences(hub: dict, *, pickup_time: str, school_address: str,
                    home_address: str, shopping_minutes: int,
                    lunch_minutes: int, buffer_minutes: int,
                    library_minutes: int = 15, pickup_minutes: int = 10,
                    library_open_time: str = '') -> dict:
    """Persist user-supplied constraints locally; never imply they're verified calendar facts."""
    new = copy.deepcopy(hub)
    new['preferences'] = {
        'pickup_time': display_clock(parse_clock(pickup_time)) if pickup_time else '',
        'school_address': _safe_text(school_address, max_len=180, may_be_empty=True),
        'home_address': _safe_text(home_address, max_len=180, may_be_empty=True),
        'shopping_minutes': shopping_minutes, 'lunch_minutes': lunch_minutes,
        'buffer_minutes': buffer_minutes,
        'library_minutes': library_minutes, 'pickup_minutes': pickup_minutes,
        'library_open_time': display_clock(parse_clock(library_open_time)) if library_open_time else '',
    }
    return validate_hub(new)


def pending_items(hub: dict, store_id: str) -> list[str]:
    validate_hub(hub)
    if store_id not in STORES:
        raise FamilyHubError('Unknown store.')
    return [x['name'] for x in hub['stores'][store_id] if not x['done']]


def matched_visit(hub: dict, day: str | None = None) -> list[dict]:
    validate_hub(hub)
    if day:
        try:
            date.fromisoformat(day)
        except ValueError:
            raise FamilyHubError('Use a date such as 2026-11-23.') from None
    visits = [x for x in hub['visits'] if day is None or x['date'] == day]
    return sorted(visits, key=lambda x: (x['date'], parse_clock(x['time'])))


@dataclass(frozen=True)
class PairingHint:
    visit: dict
    store_id: str
    store_name: str
    items: tuple[str, ...]
    distance_km: float
    driving_minutes: float
    route_report: Any


def find_nearby_pairings(hub: dict, *, day: str | None = None,
                         allow_address_lookup: bool = False,
                         router: Callable[[list[str]], Any] | None = None,
                         maximum_minutes: float = 15) -> tuple[list[PairingHint], list[str]]:
    """Check preferred visit/store pairs with ACTUAL HeiGIT driving estimates.

    A 'nearby' recommendation requires an existing saved visit, pending store
    items, two user-entered addresses, opt-in to sharing addresses with HeiGIT,
    and a validated route estimate not exceeding the time threshold. There is
    no fallback to straight-line or synthetic travel time.
    """
    validate_hub(hub)
    if not 0 < maximum_minutes <= 120:
        raise FamilyHubError('Travel threshold must be between 1 and 120 minutes.')
    if router is None:
        from mina_route_tools import get_route_report
        router = get_route_report
    pairs = {(p['visit'], p['store']) for p in hub['pairings']}
    hints, notes = [], []
    route_cache: dict[tuple[str, str], Any] = {}
    future_cutoff = date.today() + timedelta(days=30)
    for visit in matched_visit(hub, day):
        if day is None:
            visit_day = date.fromisoformat(visit['date'])
            if not (date.today() <= visit_day <= future_cutoff):
                continue
        matching = [s for place_id, s in PAIRS if place_id == visit['place']
                    and (place_id, s) in pairs]
        for store_id in matching:
            items = pending_items(hub, store_id)
            if not items:
                continue
            clinic = hub['places'][visit['place']]
            store = hub['places'][store_id]
            if not clinic['address'] or not store['address']:
                notes.append(f"{clinic['name']} + {store['name']}: enter both saved addresses first.")
                continue
            if not allow_address_lookup:
                notes.append(f"{clinic['name']} + {store['name']}: route lookup requires your consent.")
                continue
            try:
                cache_key = (clinic['address'], store['address'])
                if cache_key not in route_cache:
                    route_cache[cache_key] = router([clinic['address'], store['address']])
                report = route_cache[cache_key]
                if (not report.legs or len(report.legs) != 1 or
                        report.duration_minutes <= 0 or report.distance_km <= 0):
                    raise ToolUnavailable('Invalid route estimate')
                if report.duration_minutes <= maximum_minutes:
                    hints.append(PairingHint(visit, store_id, store['name'], tuple(items),
                                             float(report.distance_km), float(report.duration_minutes), report))
                else:
                    notes.append(f"{clinic['name']} + {store['name']}: ~{report.duration_minutes:g} min driving; exceeds the {maximum_minutes:g}-minute threshold.")
            except (LocationRequired, ToolUnavailable, OSError, ValueError):
                notes.append(f"{clinic['name']} + {store['name']}: real route unavailable; proximity not verified.")
    return hints, notes


# Only narrow, explicitly read-only family-hub prompts are handled by this module.
# Calendar writes and ordinary planning remain delegated to the existing safety gate/runtime.
_LIST_QUESTION = re.compile(
    r"\b(?:what(?:'s| is)?|show|read|remind me|tell me)\b.{0,80}\b(?:on|in|from|for|my)\b.{0,15}\b(costco|target|trader\s*joe(?:'s|s)?)\b.{0,30}\blist\b|"
    r"\b(?:show|read)\b.{0,60}\b(costco|target|trader\s*joe(?:'s|s)?)\b.{0,20}\blist\b",
    re.I,
)
_PAIR_QUESTION = re.compile(r'\b(?:pair|combine|nearby|near|on my way|on the way|same trip|errands? around|stop by)\b', re.I)
_ADD_COMMAND = re.compile(
    r"^\s*(?:please\s+)?(?:add|put)\s+(.{1,80}?)\s+(?:to|on)\s+(?:my\s+|the\s+)?"
    r"(costco|target|trader\s*joe(?:'s|s)?)\s+(?:shopping\s+|grocery\s+)?list(?:,?\s+please)?\s*[.!?]?\s*$", re.I,
)
# Voice transcriptions often include the assistant's wake name and polite
# phrasing. Remove ONLY a tightly anchored greeting/request prefix. This is
# not a general LLM intent classifier or permission to change external data.
_WAKE = re.compile(r"^(?:(?:hey|hi|hello)\s+)?mina\b[\s,:.!-]*", re.I)
_POLITE = re.compile(
    r"^(?:please[,\s]+|(?:can|could|would|will)\s+you[,\s]+(?:please[,\s]+)?|"
    r"i\s+(?:want|need)\s+to\s+|i(?:'d|\s+would)\s+like\s+to\s+)",
    re.I,
)


def _local_list_command_text(request: str) -> str:
    text = request.strip()
    # Allow: 'Hey Mina, could you please add ...?' but never strip material
    # after the initial greeting/request phrase (e.g. 'and email it').
    for _ in range(3):
        updated = _WAKE.sub('', text, count=1)
        updated = _POLITE.sub('', updated, count=1)
        if updated == text:
            break
        text = updated.strip()
    return text


def _store_id(name: str) -> str:
    compact = re.sub(r"[\s’']", '', name.casefold())
    return 'trader_joes' if compact in {'traderjoes', 'traderjoe'} else compact


def parse_pending_list_add(request: str) -> tuple[str, str] | None:
    if not isinstance(request, str) or len(request) > 200:
        return None
    m = _ADD_COMMAND.fullmatch(_local_list_command_text(request))
    if not m:
        return None
    name = m.group(1).strip()
    if re.search(r'\b(?:calendar|appointment|email|send|delete|remove|cancel|and\s+then|also\s+add)\b', name, re.I):
        return None
    try:
        name = _safe_text(name, max_len=80)
    except FamilyHubError:
        return None
    store_id = _store_id(m.group(2))
    return (store_id, name) if store_id in STORES else None


def read_hub_intent(request: str) -> tuple[str, str | None] | None:
    """Classify only narrow read requests; never bypass original write guard."""
    if not isinstance(request, str) or len(request) > 300:
        return None
    from mina_write_guard import detect_explicit_write
    if detect_explicit_write(request) or parse_pending_list_add(request):
        return None
    if re.search(r'\b(?:add|delete|remove|update|send|schedule|reschedule|book|cancel)\b', request, re.I):
        return None
    m = _LIST_QUESTION.search(request)
    if m:
        store = _store_id(next(group for group in m.groups() if group))
        if store in STORES:
            return ('list', store)
    if _PAIR_QUESTION.search(request) and re.search(r'\b(?:library|dentist|dental|pediatrician|appointment|costco|target|trader)\b', request, re.I):
        return ('pair', None)
    return None


def list_answer(hub: dict, store_id: str) -> str:
    names = pending_items(hub, store_id)
    if not names:
        return f'{STORES[store_id]} shopping list has no pending items.'
    return f"{STORES[store_id]} shopping list ({len(names)} pending):\n" + '\n'.join(f'- {item}' for item in names)


def pairing_setup_guidance(hub: dict, request: str, *, today: date | None = None) -> str:
    """Explain missing LOCAL prerequisites; never invent a visit, item or address.

    Called when no usable pairing was found. A matching visit is within the
    same 30-day window as find_nearby_pairings. This makes the UI actionable
    without silently changing lists or contacting HeiGIT.
    """
    validate_hub(hub)
    today = today or date.today()
    end = today + timedelta(days=30)
    requested = []
    requested_lower = request.casefold() if isinstance(request, str) else ''
    for place_id, store_id in PAIRS:
        keywords = {'library': ('library', 'books'),
                    'dentist': ('dentist', 'dental'),
                    'pediatrician': ('pediatrician', 'pediatric')}[place_id]
        if any(word in requested_lower for word in keywords):
            requested.append((place_id, store_id))
    # With no explicit visit name, provide prerequisites for each supported pair.
    selected = requested or list(PAIRS)
    lines = ['No eligible nearby stop is confirmed yet. Here is what MINA has saved locally:']
    for place_id, store_id in selected:
        matching_visits = [v for v in hub['visits']
                           if v['place'] == place_id
                           and today <= date.fromisoformat(v['date']) <= end]
        items = pending_items(hub, store_id)
        place_name = hub['places'][place_id]['name']
        store_name = hub['places'][store_id]['name']
        lines.append(
            f'- **{place_name} + {store_name}**: '
            f'{len(matching_visits)} visit(s) in the next 30 days; '
            f'{len(items)} pending shopping item(s).'
        )
        missing = []
        if not matching_visits:
            missing.append(f'save an upcoming {place_name} visit in Family Hub')
        if not items:
            missing.append(f'add an unchecked item to the {store_name} list')
        if missing:
            lines.append('  Next: ' + '; '.join(missing) + '.')
    lines.append('For an actual proximity check, also enter both public business addresses '
                 'in Saved Places and enable HeiGIT address lookup. No visit, purchase, '
                 'or calendar event was created.')
    return '\n'.join(lines)


def pairing_answer(hints: list[PairingHint], notes: list[str]) -> str:
    lines = []
    for hint in hints:
        lines.append(
            f"**{hint.visit['title']} ({hint.visit['date']}, {hint.visit['time']}) + {hint.store_name}** — "
            f"~{hint.driving_minutes:g} min / {hint.distance_km:g} km driving from the visit to the store.\n"
            f"Shopping list: {', '.join(hint.items)}.\n"
            'Suggestion only: store opening hours, visit end time, traffic and parking are not checked.'
        )
    if notes:
        lines.extend(notes)
    if not lines:
        lines.append('No qualifying scheduled visits with pending items in their paired store lists. Add a visit and items in Family Hub first.')
    return '\n\n'.join(lines)


def needs_live_family_mode(request: str) -> bool:
    """Do not silently route a multi-stop, time-constrained request to fixtures."""
    if not isinstance(request, str):
        return False
    from mina_write_guard import detect_explicit_write
    if detect_explicit_write(request):
        return False
    categories = (
        bool(re.search(r"\blibrar(?:y|ies)\b", request, re.I)),
        bool(re.search(r"\bgrocer(?:y|ies)\b", request, re.I)),
        bool(re.search(r"\b(?:school\s+pickup|pick\s+up\s+(?:my|the|a)\s+child)\b", request, re.I)),
    )
    return (sum(categories) >= 2 and bool(re.search(
        r"\b(?:plan|route|best\s+order|what\s+order|errands?|before|by\s+\d|first|last)\b",
        request, re.I,
    )))


def potential_pairs(hub: dict, *, start_day: str | None = None, days_ahead: int = 7) -> list[tuple[dict, str, int]]:
    """Unverified reminder candidates from local notes; NOT proximity claims."""
    validate_hub(hub)
    from_day = date.fromisoformat(start_day) if start_day else date.today()
    last_day = from_day + timedelta(days=days_ahead)
    result = []
    for visit in matched_visit(hub):
        d = date.fromisoformat(visit['date'])
        if not from_day <= d <= last_day:
            continue
        for place_id, store_id in PAIRS:
            if visit['place'] == place_id:
                count = len(pending_items(hub, store_id))
                if count:
                    result.append((visit, store_id, count))
    return result
