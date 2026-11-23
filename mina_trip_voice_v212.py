"""Strict, deterministic extraction of user-supplied constraints for MINA route requests.

This is an input adapter only. Route computation and feasibility remain the job of the
existing Coordinator/Planner/Critic/Controller. All sources remain unverified user notes.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import calendar
import re

class TripParseError(ValueError):
    pass

_AMPM = r'(?:a\.?\s*m\.?|p\.?\s*m\.?)'
_CLOCK = rf'(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*{_AMPM}'
_CLOCK_OPT = rf'(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*(?:{_AMPM})?'
_DEPARTURE = re.compile(
    rf'\b(?:leave|leaving|depart(?:ing)?(?:\s+from)?|start(?:ing)?\s+from)\s+'
    rf'(?:my\s+|the\s+)?home\s+at\s+(?P<clock>{_CLOCK})', re.I)
_WINDOW = re.compile(
    rf'\b(?:school\s+(?:pickup|pick\s*up|for\s+pickup)|pickup|pick\s*up)\b'
    rf'.{{0,65}}?\bbetween\s+(?P<first>{_CLOCK_OPT})\s+and\s+(?P<last>{_CLOCK})', re.I)
_DATE = re.compile(
    r'\b(?:(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s+)?'
    r'(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+'
    r'(?P<day>[0-3]?\d)(?:st|nd|rd|th)?(?:\s*,?\s*(?P<year>20\d\d))?\b', re.I)
_SCHOOL_PICKUP = re.compile(
    r'\b(?:school\s+(?:pickup|pick\s*up|for\s+pick\s*up)|'
    r'pick(?:ing)?\s+up\s+(?:my\s+|the\s+|a\s+)?(?:child|kids?)\s+(?:at|from)\s+school|'
    r'pick\s+up\s+my\s+child\s+from\s+school)\b', re.I)

_STORES = {
    'costco': re.compile(r'\bcostco\b', re.I),
    'target': re.compile(r'\btarget\b', re.I),
    'trader_joes': re.compile(r"\btrader\s+joe[’']?s\b", re.I),
}

@dataclass(frozen=True)
class TripVoiceConstraints:
    prompt_for_planner: str
    requested_tasks: frozenset[str]
    departure_time: str | None
    plan_date: str | None
    duration_overrides: dict[str, int]
    store: str | None
    pickup_window: tuple[str, str] | None


def normalize_clock(value: str, implied_meridiem: str | None = None) -> str:
    """Return 12-hour clock for supported speech forms. No guesses without AM/PM."""
    s = re.sub(r'[.\s]', '', value.strip()).lower()
    match = re.fullmatch(r'(\d{1,2})(?::([0-5]\d))?(am|pm)?', s)
    if not match:
        raise TripParseError('Could not read the requested time. Say it with AM or PM.')
    h = int(match.group(1)); mins = int(match.group(2) or '00')
    ap = (match.group(3) or implied_meridiem or '').upper()
    if not (1 <= h <= 12 and ap in {'AM', 'PM'}):
        raise TripParseError('Please specify AM or PM for the route time.')
    return f'{h}:{mins:02d} {ap}'


def clock_minutes(value: str) -> int:
    h, rest = value.split(':'); minutes, period = rest.split()
    return (int(h) % 12 + (12 if period == 'PM' else 0)) * 60 + int(minutes)


def _one_duration(pattern: str, prompt: str, task: str) -> int | None:
    vals = [int(x) for x in re.findall(pattern, prompt, re.I)]
    if not vals:
        return None
    if len(set(vals)) != 1 or any(not 1 <= value <= 360 for value in vals):
        raise TripParseError(f'Please clarify the minutes for {task}. Nothing was planned.')
    return vals[0]


def _parse_date(prompt: str, today: date) -> str | None:
    found = list(_DATE.finditer(prompt))
    relatives = re.findall(r'\b(?:today|tomorrow)\b', prompt, re.I)
    if found and relatives:
        raise TripParseError('Please specify only one trip date.')
    if not found:
        if len(relatives) != 1:
            if len(relatives) > 1:
                raise TripParseError('Please specify only one trip date.')
            return None
        from datetime import timedelta
        return (today + timedelta(days=1 if relatives[0].lower() == 'tomorrow' else 0)).isoformat()
    if len(found) != 1:
        raise TripParseError('Please specify only one trip date.')
    m = found[0]
    month = list(calendar.month_name).index(m.group('month').capitalize())
    year = int(m.group('year')) if m.group('year') else today.year
    try:
        day = date(year, month, int(m.group('day')))
        if not m.group('year') and day < today:
            day = date(year + 1, month, int(m.group('day')))
    except ValueError:
        raise TripParseError('The date in the route request is invalid.') from None
    if m.group('weekday') and day.strftime('%A').lower() != m.group('weekday').lower():
        raise TripParseError('The weekday and calendar date do not match. Please clarify the date.')
    return day.isoformat()


def parse_trip_voice(prompt: str, *, today: date) -> TripVoiceConstraints:
    if not isinstance(prompt, str):
        raise TripParseError('Trip request must be text.')
    tasks: set[str] = set()
    if re.search(r'\blibrar(?:y|ies)\b', prompt, re.I):
        tasks.add('library')
    store_matches = [store for store, pattern in _STORES.items() if pattern.search(prompt)]
    if len(store_matches) > 1:
        raise TripParseError('This route planner supports one shopping stop per plan. Which store should I use?')
    store = store_matches[0] if store_matches else None
    if store or re.search(r'\bgrocer(?:y|ies)\b', prompt, re.I):
        tasks.add('groceries')
    if _SCHOOL_PICKUP.search(prompt):
        tasks.add('school_pickup')

    departure_matches = list(_DEPARTURE.finditer(prompt))
    if len(departure_matches) > 1:
        raise TripParseError('Please specify one home departure time.')
    departure = None
    normalized = prompt
    if departure_matches:
        m = departure_matches[0]
        if re.search(r'\b(?:not|don\W*t)\s*$', prompt[max(0, m.start()-15):m.start()], re.I):
            raise TripParseError('Please clarify whether you want to leave home at that time.')
        departure = normalize_clock(m.group('clock'))
        # The backend scope checker only accepts fixed_time constraints assigned
        # to an errand. Departure is a route-level setting, not another errand.
        normalized = prompt[:m.start()] + 'start from home' + prompt[m.end():]

    durations = {}
    patterns = {
        'library': r'\blibrar(?:y|ies)\b\s+for\s+(\d{1,3})\s*(?:minutes?|mins?)\b',
        'groceries': r'\b(?:costco|target|trader\s+joe[’\']?s|grocer(?:y|ies))\b\s+for\s+(\d{1,3})\s*(?:minutes?|mins?)\b',
        'school_pickup': r'\b(?:school\s+pickup|pickup)\b\s+for\s+(\d{1,3})\s*(?:minutes?|mins?)\b',
    }
    for task in tasks:
        value = _one_duration(patterns[task], prompt, task)
        if value is not None:
            durations[task] = value

    pickup_window = None
    windows = list(_WINDOW.finditer(prompt))
    if len(windows) > 1:
        raise TripParseError('Please specify one school pickup window.')
    if windows:
        m = windows[0]
        end = normalize_clock(m.group('last'))
        start = normalize_clock(m.group('first'), implied_meridiem=end.split()[-1])
        if clock_minutes(start) >= clock_minutes(end):
            raise TripParseError('Pickup window end must be after its start.')
        pickup_window = (start, end)

    return TripVoiceConstraints(normalized, frozenset(tasks), departure,
                               _parse_date(prompt, today), durations, store, pickup_window)


# v2.12.1 - classify explicit multi-stop planning requests independently of
# the generic Auto router. Generic routing may mistakenly classify explicit
# negative safety instructions ("don't create events") as write requests.
_PLAN_WORDS = re.compile(
    r"\b(?:plan(?:ning)?|itinerary|route|routing|best\s+order|feasib(?:le|ility)|"
    r"organize\s+(?:my|the)\s+(?:day|afternoon|errands))\b", re.I)
_NEGATED_WRITES = re.compile(
    r"\b(?:don[’']?t|do\s+not|never|without)\s+"
    r"(?:also\s+)?(?:create|add|send|change|modify|delete|remove|save|schedule|book)"
    r"[^.!?;]*", re.I)
_STORE_ITEM_CHANGES = re.compile(
    r"\b(?:add|put|remove|delete)\b[^.!?;]*\b(?:to|from)\s+"
    r"(?:my\s+)?(?:costco|target|trader\s+joe[’']?s)\b", re.I)
_POSITIVE_WRITES = re.compile(
    r"\b(?:create|add|send|change|modify|delete|remove|save|schedule|book)\b"
    r"[^.!?;]*\b(?:calendar|event|appointment|email|message|shopping\s+list|"
    r"grocer(?:y|ies)\s+list|costco\s+list|target\s+list)\b", re.I)


def classify_multi_stop_route(prompt: str) -> str:
    """'route', 'mixed', or 'none'. Never performs any write or geocoding.

    'mixed' means route planning plus an affirmative request to change user
    data; the caller should ask to separate the actions rather than bypass
    either write guard. Explicit negated writes are retained as safety intent.
    """
    if not isinstance(prompt, str) or not _PLAN_WORDS.search(prompt):
        return 'none'
    if re.search(r"\b(?:don[’']?t|do\s+not|never)\s+(?:want\s+to\s+)?plan\b", prompt, re.I):
        return 'none'
    # A route requires at least two distinct stops, not just the word 'plan'.
    tasks = set()
    if re.search(r'\blibrar(?:y|ies)\b', prompt, re.I): tasks.add('library')
    if any(p.search(prompt) for p in _STORES.values()) or re.search(r'\bgrocer(?:y|ies)\b', prompt, re.I):
        tasks.add('groceries')
    if _SCHOOL_PICKUP.search(prompt):
        tasks.add('school_pickup')
    if len(tasks) < 2:
        return 'none'
    affirmative_text = _NEGATED_WRITES.sub('', prompt)
    if _POSITIVE_WRITES.search(affirmative_text) or _STORE_ITEM_CHANGES.search(affirmative_text):
        return 'mixed'
    return 'route'
