"""MINA v2.5: conservative automatic intent routing and voice-local actions.

No LLM-produced text is granted write permission. Only deterministic, narrowly
matched local list/visit commands yield a confirmation proposal. External
calendar/email/list changes remain blocked by the original guard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

from mina_family_hub import (
    STORES, PLACES, PAIRS, FamilyHubError, _local_list_command_text,
    _safe_text, _store_id, pending_items, matched_visit, needs_live_family_mode,
    parse_pending_list_add, read_hub_intent,
)
from mina_saved_places import display_clock, parse_clock
from mina_write_guard import detect_explicit_write

_STORES = r"(costco|target|trader\s*joe(?:'s|s)?)"
_LIST_ADD = re.compile(
    r"^(?:add|put)\s+(.{1,230}?)\s+(?:to|on)\s+(?:my\s+|the\s+)?" +
    _STORES + r"\s+(?:shopping\s+|grocery\s+)?list\s*(?:,?\s+please)?[.!?]?\s*$", re.I,
)
_FORBIDDEN_LIST = re.compile(
    r"\b(?:calendar|appointment|email|send|delete|remove|cancel|schedule|book|"
    r"update|reschedule|then|also|remind|invite|notify|message)\b", re.I,
)
_DATE_MONTHS = {'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12}
_WEEKDAYS = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
             'friday': 4, 'saturday': 5, 'sunday': 6}
_CLOCK = r'(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*[AP]M'


@dataclass(frozen=True)
class AutoIntent:
    kind: str
    data: Any = None


def parse_bulk_list_add(prompt: str) -> dict | None:
    """Read a complete, narrowly scoped multi-item local list command."""
    if not isinstance(prompt, str) or len(prompt) > 360:
        return None
    text = _local_list_command_text(prompt)
    m = _LIST_ADD.fullmatch(text)
    if not m:
        return None
    body = m.group(1).strip()
    if _FORBIDDEN_LIST.search(body) or ';' in body:
        return None
    pieces = re.split(r'\s*,\s*|\s+and\s+', body, flags=re.I)
    if not 1 <= len(pieces) <= 10:
        return None
    try:
        items = [_safe_text(x.strip(), max_len=80) for x in pieces]
    except FamilyHubError:
        return None
    if any(not re.search(r'[A-Za-zÀ-žА-Яа-я]', x) for x in items):
        return None
    if len(set(x.casefold() for x in items)) != len(items):
        return None
    store = _store_id(m.group(2))
    return {'store': store, 'items': items} if store in STORES else None


def _date_from_text(prompt: str, today: date) -> date | None:
    text = prompt.lower()
    if re.search(r'\bday\s+after\s+tomorrow\b', text):
        return today + timedelta(days=2)
    if re.search(r'\btomorrow\b', text):
        return today + timedelta(days=1)
    if re.search(r'\btoday\b', text):
        return today
    if re.search(r'\byesterday\b', text):
        return today - timedelta(days=1)
    iso = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    us = re.search(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', text)
    if us:
        try:
            return date(int(us.group(3)), int(us.group(1)), int(us.group(2)))
        except ValueError:
            return None
    months = '|'.join(_DATE_MONTHS)
    named = re.search(rf'\b({months})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b', text)
    if named:
        year = int(named.group(3)) if named.group(3) else today.year
        try:
            result = date(year, _DATE_MONTHS[named.group(1)], int(named.group(2)))
            if not named.group(3) and result < today:
                result = date(year + 1, _DATE_MONTHS[named.group(1)], int(named.group(2)))
            return result
        except ValueError:
            return None
    weekday = re.search(r'\b(?:on\s+|next\s+)(' + '|'.join(_WEEKDAYS) + r')\b', text)
    if weekday:
        offset = (_WEEKDAYS[weekday.group(1)] - today.weekday()) % 7
        if text[weekday.start():weekday.end()].startswith('next') and offset == 0:
            offset = 7
        return today + timedelta(days=offset)
    return None


def _parse_voice_clock(clock: str) -> str:
    value = re.sub(r'\s+', ' ', clock.strip().upper())
    value = re.sub(r'(?<=\d)(?=AM|PM)', ' ', value)
    value = re.sub(r'^(\d{1,2})\s+(AM|PM)$', r'\1:00 \2', value)
    return display_clock(parse_clock(value))


def parse_voice_visit(prompt: str, *, today: date | None = None) -> dict | None:
    """Record existing/supplied appointments as LOCAL notes after user confirmation.

    Deliberately refuses booking and calendar/email mutation commands.
    Requires a clear date AND starting time; never guesses a visit duration.
    """
    if not isinstance(prompt, str) or len(prompt) > 320:
        return None
    text = _local_list_command_text(prompt)
    if re.search(r'\b(?:calendar|email|book|reschedule|cancel|invite|send|delete|move)\b', text, re.I):
        return None
    if not re.match(r'^(?:i\s+(?:have|had|will\s+have)\b|remember\s+(?:that\s+)?i\s+have\b|'
                    r'note\s+(?:that\s+)?i\s+have\b|(?:save|record|add|note)\b)', text, re.I):
        return None
    places = [p for p, pattern in {
        'dentist': r'\b(?:dentist|dental)\b',
        'pediatrician': r'\b(?:pediatrician|pediatric|pediatrician\'s)\b',
        'library': r'\blibrary\b',
    }.items() if re.search(pattern, text, re.I)]
    if len(places) != 1:
        return None
    day = _date_from_text(text, today or date.today())
    if not day:
        return None
    # Avoid extracting unrelated pickup times as the appointment time.
    time_phrase = re.search(rf'\b(?:from|at|starts?\s+at)\s+({_CLOCK})'
                            rf'(?:\s*(?:to|until|through|[-–])\s*({_CLOCK}))?', text, re.I)
    if not time_phrase:
        return None
    try:
        start = _parse_voice_clock(time_phrase.group(1))
        end = _parse_voice_clock(time_phrase.group(2)) if time_phrase.group(2) else ''
        if end and parse_clock(end) <= parse_clock(start):
            return None
    except ValueError:
        return None
    title = {'dentist': 'Dentist appointment', 'pediatrician': 'Pediatrician appointment',
             'library': 'Library visit'}[places[0]]
    return {'place': places[0], 'date': day.isoformat(),
            'time': start, 'end_time': end, 'title': title}


def parse_directions(prompt: str) -> tuple[str, str] | None:
    """Parse explicit X-to-Y-only directions without guessing addresses."""
    if not isinstance(prompt, str) or len(prompt) > 350:
        return None
    if not re.search(r'\b(?:directions?|route|drive|map|navigate)\b', prompt, re.I):
        return None
    match = re.search(r'\bfrom\s+(.{4,120}?)\s+to\s+(.{4,120}?)(?:[.!?]|$)', prompt, re.I)
    if not match:
        return None
    start, end = (x.strip() for x in match.groups())
    if re.search(r'\b(?:and\s+add|and\s+send|calendar|shopping\s+list)\b', prompt, re.I):
        return None
    return (start, end)


def auto_route(prompt: str, *, today: date | None = None) -> AutoIntent:
    """Deterministic safety-first tool selection. No manual Mode selection."""
    bulk = parse_bulk_list_add(prompt)
    if bulk:
        return AutoIntent('local_list_proposal', bulk)
    visit = parse_voice_visit(prompt, today=today)
    if visit:
        return AutoIntent('local_visit_proposal', visit)
    # A composite or real external mutation must be handled by the write guard.
    if detect_explicit_write(prompt) or detect_explicit_write(_local_list_command_text(prompt)):
        return AutoIntent('external_write')
    hub_read = read_hub_intent(prompt)
    if hub_read:
        return AutoIntent('hub_read', hub_read)
    if re.search(r'\b(?:what(?:\'s| is)?\s+on\s+my\s+schedule|my\s+(?:appointments?|plans?)\s+(?:today|tomorrow)|'
                 r'what\s+do\s+i\s+have\s+(?:today|tomorrow)|remind\s+me\s+(?:about|of)\s+my\s+'
                 r'(?:dentist|pediatrician)\s+appointment)\b', prompt, re.I):
        return AutoIntent('schedule_read', {'tomorrow': bool(re.search(r'\btomorrow\b', prompt, re.I))})
    directions = parse_directions(prompt)
    if directions:
        return AutoIntent('directions', directions)
    if needs_live_family_mode(prompt):
        return AutoIntent('family_plan')
    return AutoIntent('assistant')


def local_schedule_answer(hub: dict, *, day: date) -> str:
    """Read locally saved visits; no implication of a real-calendar sync."""
    visits = matched_visit(hub, day.isoformat())
    if not visits:
        return (f'No locally saved visits for {day.isoformat()}. '
                'This is not a Google Calendar check; you can record an appointment by voice.')
    rows = [f'**Locally saved visits — {day.isoformat()} (not calendar-verified):**']
    for visit in visits:
        end = f"–{visit['end_time']}" if visit.get('end_time') else ' (end time not saved)'
        rows.append(f"- {visit['time']}{end} · {visit['title']}")
        for place, store in PAIRS:
            if visit['place'] == place:
                items = pending_items(hub, store)
                if items:
                    rows.append(f"  - Your {STORES[store]} list: {', '.join(items)}. "
                                'Potential paired stop; proximity and schedule not yet checked.')
    prefs = hub.get('preferences') or {}
    if prefs.get('pickup_time'):
        rows.append(f"Saved school pickup target: {prefs['pickup_time']} (user-provided, not calendar-verified).")
    return '\n'.join(rows)


def time_window_advice(visit: dict, *, pickup_time: str, first_leg_minutes: float,
                       school_leg_minutes: float | None = None, shopping_minutes: int = 45,
                       lunch_minutes: int = 45, buffer_minutes: int = 15) -> str:
    """Conservative schedule slack: no feasibility claim without school leg."""
    if not visit.get('end_time'):
        return ('The appointment end time is not saved, so I cannot calculate the available '
                'shopping/lunch window. Add an end time to the local visit.')
    if not pickup_time:
        return ('School pickup time is not saved. Add it in Family Hub preferences '
                'before MINA estimates the time window.')
    start = parse_clock(visit['end_time'])
    finish = parse_clock(pickup_time)
    minutes = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])
    window = minutes(finish) - minutes(start)
    if window <= 0:
        return 'School pickup is at or before the appointment ends. Do not add shopping.'
    if school_leg_minutes is None:
        return (f'From appointment end ({visit["end_time"]}) to saved pickup '
                f'({pickup_time}): **{window} minutes**. '
                f'The clinic-to-store drive is estimated at {first_leg_minutes:g} minutes, '
                'but I have NOT checked store-to-school driving. I cannot guarantee '
                'the shopping or lunch stop fits; add the school address and allow route lookup.')
    base = first_leg_minutes + school_leg_minutes + shopping_minutes + buffer_minutes
    slack = window - base
    if slack < 0:
        return (f'Available window: {window} min; drive + shopping + safety buffer '
                f'~{base:g} min. **Risk: skip shopping to protect school pickup.** '
                'Times are HeiGIT estimates, not live traffic.')
    if lunch_minutes and slack < lunch_minutes:
        return (f'Available window: {window} min. Estimated drive + shopping + buffer '
                f'~{base:g} min, leaving ~{slack:g} min. **Lunch is not safely budgeted.** '
                'Traffic and appointment overruns remain uncertain.')
    combined = base + lunch_minutes
    if window - combined < 15:
        return (f'Available window: {window} min; shopping, lunch, estimated driving '
                f'and safety buffer use ~{combined:g} min. Only ~{window-combined:g} min remains: '
                '**very tight; prefer skipping lunch or an errand.** '
                'Traffic, parking and delays are not live-verified.')
    return (f'Available window: {window} min. Estimated driving, shopping, lunch '
            f'and safety buffer: ~{combined:g} min, leaving ~{window-combined:g} min. '
            'This is provisional: no live traffic, parking, restaurant opening hours '
            'or appointment overrun checks. No restaurant venue has been verified.')


def apply_local_action(hub: dict, action: dict) -> dict:
    """Execute a confirmed local action as one atomic JSON replacement by caller.

    This function is never invoked without a button or explicit voice
    confirmation. External services are not modified.
    """
    from mina_family_hub import add_item, add_visit
    from mina_followups import clear_store_after_purchase
    if action.get('kind') == 'list':
        items = action.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            raise FamilyHubError('Invalid proposed shopping items.')
        updated = hub
        for item in items:
            updated = add_item(updated, action['store'], item)
        return updated
    if action.get('kind') == 'clear_list':
        return clear_store_after_purchase(
            hub, action['store'], expected_item_ids=action.get('expected_item_ids', []))
    if action.get('kind') == 'visit':
        visit = action['visit']
        return add_visit(hub, place_id=visit['place'], day=visit['date'],
                         time=visit['time'], end_time=visit.get('end_time', ''),
                         title=visit['title'])
    raise FamilyHubError('Unrecognized local confirmation action.')


def is_explicit_local_confirmation(prompt: str) -> bool:
    return bool(re.fullmatch(
        r'\s*(?:(?:hey|hi|hello)\s+)?(?:mina[,.:! ]+)?'
        r'(?:confirm (?:my |the |this )?local (?:change|update)|'
        r'yes[, ]+confirm (?:the |this )?local (?:change|update)|'
        r'save (?:this |the )?local (?:change|update))\s*[.!?]?\s*', prompt, re.I,
    ))
