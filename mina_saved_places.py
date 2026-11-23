"""Validated read-only Saved Places hours and time windows for optional live planning.

User-facing JSON is strictly 12-hour AM/PM. The route Critic uses internal HH:MM.
Do not silently infer opening hours, school times or real-world calendar validity.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mina_planning import NeedsClarification

TASKS = frozenset({'library', 'groceries', 'school_pickup'})
DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
CLOCK_12H = re.compile(r'^(1[0-2]|0?[1-9]):([0-5]\d)\s*(AM|PM)$', re.I)
CLOCK_LEGACY = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')


def parse_clock(value: str, *, legacy: bool = False) -> str:
    """Normalize a saved AM/PM time to internal HH:MM; optionally accept old CLI 24h."""
    if not isinstance(value, str):
        raise NeedsClarification('Time must be a string with AM or PM, e.g. 3:15 PM.')
    m = CLOCK_12H.fullmatch(value.strip())
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == 'PM' else 0)
        return f'{hour:02d}:{int(m.group(2)):02d}'
    if legacy and CLOCK_LEGACY.fullmatch(value.strip()):
        return value.strip()
    raise NeedsClarification(f'Use 12-hour AM/PM time, e.g. 3:15 PM (got {value!r}).')


def display_clock(hhmm: str) -> str:
    hour, minute = (int(x) for x in hhmm.split(':'))
    return f'{hour % 12 or 12}:{minute:02d} {"PM" if hour >= 12 else "AM"}'


def parse_window(window: dict) -> tuple[str, str]:
    if not isinstance(window, dict) or set(window) != {'start', 'end'}:
        raise NeedsClarification('Every time window requires only start and end in AM/PM.')
    start = parse_clock(window['start'])
    end = parse_clock(window['end'])
    if start >= end:
        raise NeedsClarification('Overnight/zero-length opening or pickup windows are not supported.')
    return (start, end)


@dataclass(frozen=True)
class SavedHours:
    windows: dict[str, tuple[str, str]]
    timezone: str
    sources: dict[str, str]
    demo: bool
    day: str


def load_saved_hours(path: str, day: str, requested: set[str]) -> SavedHours:
    """Read a small local JSON of verified-by-user time ranges, never a live-calendar guarantee."""
    try:
        raw = Path(path).expanduser().read_bytes()
        if len(raw) > 80_000:
            raise ValueError('Saved Places file too large')
        data = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        raise NeedsClarification('Cannot read valid Saved Places JSON file.') from None
    if not isinstance(data, dict) or data.get('schema_version') != '1.0':
        raise NeedsClarification('Saved Places must have schema_version 1.0.')
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        raise NeedsClarification('Specify --plan-date YYYY-MM-DD for Saved Places hours.') from None
    tz = data.get('timezone')
    try:
        if not isinstance(tz, str) or not tz or ZoneInfo(tz).key != tz:
            raise ValueError()
    except (ZoneInfoNotFoundError, ValueError):
        raise NeedsClarification('Saved Places timezone must be a valid IANA zone.') from None
    places = data.get('places')
    if not isinstance(places, dict) or set(places) - TASKS:
        raise NeedsClarification('Saved Places must contain only supported task IDs.')
    if not requested <= set(places):
        raise NeedsClarification('Saved Places missing required task configuration: ' + ', '.join(sorted(requested - set(places))))
    windows: dict[str, tuple[str, str]] = {}
    sources: dict[str, str] = {}
    is_demo = False
    day_name = DAY_NAMES[d.weekday()]
    for task in requested:
        entry = places[task]
        if not isinstance(entry, dict):
            raise NeedsClarification(f'Invalid Saved Places entry: {task}')
        source = entry.get('source')
        if source not in {'user_provided', 'user_provided_demo'}:
            raise NeedsClarification(f'{task} needs explicit source user_provided or user_provided_demo.')
        is_demo |= source == 'user_provided_demo'
        sources[task] = source
        if task == 'school_pickup':
            days = entry.get('school_days')
            overrides = entry.get('date_overrides', {})
            if (not isinstance(days, list) or not days or len(set(days)) != len(days)
                    or any(x not in DAY_NAMES for x in days) or not isinstance(overrides, dict)):
                raise NeedsClarification('School pickup needs valid school_days and optional date_overrides.')
            if day in overrides:
                selected = overrides[day]
            elif day_name in days:
                selected = entry.get('time_window')
            else:
                selected = None
            if selected is None:
                raise NeedsClarification(f'School pickup is not confirmed for {day}. No pickup schedule assumed.')
            windows[task] = parse_window(selected)
        else:
            # Exact date exception has precedence over the weekly hours.
            exceptions = entry.get('date_overrides', {})
            weekly = entry.get('weekly_hours')
            if not isinstance(exceptions, dict) or not isinstance(weekly, dict):
                raise NeedsClarification(f'{task} needs weekly_hours (and optional date_overrides).')
            selected = exceptions.get(day, weekly.get(day_name))
            if selected is None:
                raise NeedsClarification(f'{task} has no confirmed hours for {day} ({day_name}).')
            windows[task] = parse_window(selected)
    return SavedHours(windows, tz, sources, is_demo, day)
