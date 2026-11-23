"""MINA v2.14.0 — session-only continuation of a *single* pending route.

Safety and scope:
- Only an explicitly recognized, standalone departure-time answer fills the slot.
- A pending route contains the original user's request (which may itself mention
  private details) and its local date anchor, only in the browser session.
  Saved-place objects, API keys, and resolved coordinates are not copied into it.
- New unrelated intents discard the pending route. No writes or network calls here.
- Expired states fail closed. Do not persist across browser/server restarts.
- This module does not continue confirmations for lists, email or calendar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re

VERSION = '2.14.1'
PENDING_TTL_MINUTES = 30
_TIME = r'(?:\d{1,2}(?::[0-5]\d)?\s*(?:a\.?\s*m\.?|p\.?\s*m\.?)|(?:1[3-9]|2[0-3]|00):[0-5]\d)'
# The whole user turn, not a free-form substring. This avoids silently
# dropping extra changes such as 'and delete my list'.
_FOLLOWUP = re.compile(
    rf'^\s*(?:mina[,.:! ]+)?(?:(?:actually|okay|ok|yes|no)[,;:! ]+)?'
    rf'(?:(?:(?:i\s+am|i\s*\x27m|i\s+will|i\s*\x27ll|we\s+will|we\s*\x27ll)\s+)?'
    rf'(?:be\s+)?(?:leav(?:e|ing)|depart(?:ing)?)\s+(?:from\s+)?(?:my\s+|the\s+)?home\s+at\s+|'
    rf'(?:i\s+will\s+|i\s*\x27ll\s+)?(?:leav(?:e|ing)|depart(?:ing)?)\s+at\s+|'
    rf'at\s+)?(?P<time>{_TIME})\s*[.!?]?\s*$', re.I)
# Cancellation is resolved ONLY while a verified pending route exists. Accept
# natural phrases that users say after MINA asks for a departure time.
# The phrase must be a standalone cancellation; an unrelated event cancellation
# or a composite instruction must not silently clear the route.
_CANCEL = re.compile(
    r'^\s*(?:mina[,.:! ]+)?(?:please\s+)?(?:'
    r'cancel(?:\s+(?:the|my|this|that|pending))?\s+(?:pending\s+)?'
    r'(?:route(?:\s+plan)?|trip(?:\s+plan)?|plan)|'
    r'cancel|'
    r'(?:never\s*mind|nevermind)(?:[, ]+cancel(?:\s+(?:the|my|this|that|pending))?'
    r'\s+(?:route(?:\s+plan)?|trip(?:\s+plan)?|plan))?|'
    r'forget\s+(?:that|the|this|my)\s+(?:plan|route|trip)|'
    r'stop\s+planning(?:\s+(?:(?:this|that|the|my)\s+)?(?:route|trip))?|'
    r'no\s+thanks'
    r')\s*[.!?]?\s*$', re.I
)
_AMBIGUOUS_TIME = re.compile(r'^\s*(?:mina[,.:! ]+)?(?:at\s+)?(?:[0-2]?\d)(?::[0-5]\d)?\s*[.!?]?\s*$',re.I)
_SHORT_ACK = re.compile(r'^\s*(?:mina[,.:! ]+)?(?:yes|no|ok|okay|sure|thanks|thank\s+you)\s*[.!?]?\s*$', re.I)


@dataclass(frozen=True)
class FollowupDecision:
    kind: str  # none | resume | cancel | reprompt | expired | new_request
    effective_request: str | None = None
    original_date_anchor: date | None = None
    departure_time: str | None = None
    message: str | None = None


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('An aware UTC timestamp is required.')
    return now.astimezone(timezone.utc)


def _clock(value: str) -> str | None:
    """Conservative 12h AM/PM or unambiguous 24-hour time normalization."""
    simple = re.sub(r'[.\s]', '', value).lower()
    m = re.fullmatch(r'(\d{1,2})(?::([0-5]\d))?(am|pm)', simple)
    if m:
        hh = int(m.group(1))
        if not 1 <= hh <= 12:
            return None
        return f'{hh}:{int(m.group(2) or 0):02d} {m.group(3).upper()}'
    m = re.fullmatch(r'((?:1[3-9]|2[0-3]|00)):([0-5]\d)', simple)
    if m:
        h = int(m.group(1))
        return f'{(h % 12) or 12}:{int(m.group(2)):02d} {"PM" if h >= 12 else "AM"}'
    return None


def create_pending_route(original_request: str, *, date_anchor: date,
                         plan_date: str | None, requested: set[str] | frozenset[str],
                         now: datetime | None = None) -> dict:
    """Hold a validated pending request in Streamlit session state, never disk."""
    if not isinstance(original_request, str) or not original_request.strip():
        raise ValueError('The route request must be text.')
    if len(original_request) > 1500:
        raise ValueError('The pending request is too long.')
    if not isinstance(date_anchor, date):
        raise ValueError('Invalid date anchor.')
    tasks = set(requested)
    if len(tasks) < 2 or not tasks <= {'groceries','library','school_pickup'}:
        raise ValueError('Only a validated multi-stop route may await departure time.')
    if plan_date is not None and not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', plan_date):
        raise ValueError('Invalid route plan date.')
    return {
        'version': VERSION,
        'kind': 'route_departure',
        'original_request': original_request.strip(),
        'date_anchor': date_anchor.isoformat(),
        'plan_date': plan_date,
        'tasks': sorted(tasks),
        'expires_at': (_now(now) + timedelta(minutes=PENDING_TTL_MINUTES)).isoformat(),
    }


def decide_followup(pending: dict | None, user_reply: str, *,
                    now: datetime | None = None) -> FollowupDecision:
    """Resolve at most one waiting slot. No guessing, LLM or external IO."""
    if not pending:
        return FollowupDecision('none')
    if not isinstance(pending, dict) or pending.get('version') != VERSION or pending.get('kind') != 'route_departure':
        return FollowupDecision('new_request')
    if not isinstance(user_reply, str) or not user_reply.strip():
        return FollowupDecision('reprompt', message='Please provide your departure time, such as 12:30 PM, or say Cancel route.')
    if _CANCEL.fullmatch(user_reply):
        return FollowupDecision('cancel', message='Cancelled the pending route. No route was calculated and no data was changed.')
    match = _FOLLOWUP.fullmatch(user_reply.replace('’', "'"))
    if not match:
        if _SHORT_ACK.fullmatch(user_reply):
            return FollowupDecision('reprompt', message='I still need a departure time, such as 12:30 PM, or say Cancel route.')
        # An unrelated user intent takes priority; never apply the old route.
        if _AMBIGUOUS_TIME.fullmatch(user_reply):
            return FollowupDecision('reprompt', message='Please specify AM or PM, for example 12:30 PM. I have not assumed a time.')
        return FollowupDecision('new_request')
    clock = _clock(match.group('time'))
    if clock is None:
        return FollowupDecision('reprompt', message='Please specify AM or PM, for example 12:30 PM. I have not assumed a time.')
    try:
        expires_at = datetime.fromisoformat(pending['expires_at'])
        anchor = date.fromisoformat(pending['date_anchor'])
        request = pending['original_request']
        if expires_at.tzinfo is None or not isinstance(request,str) or not 0 < len(request) <= 1500:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        return FollowupDecision('expired', message='That route clarification is no longer available. Please repeat your route request.')
    if _now(now) >= expires_at:
        return FollowupDecision('expired', message='That route clarification expired. Please repeat your route request.')
    # Add *only* a typed, standalone departure time. The original request's
    # relative date is evaluated against the original user's date anchor.
    effective = request.rstrip().rstrip('.!?') + f'. I will leave home at {clock}.'
    return FollowupDecision('resume', effective_request=effective,
                            original_date_anchor=anchor, departure_time=clock)


def pending_route_caption(pending: dict | None) -> str | None:
    """Non-sensitive display hint; avoid addresses and user-text reproduction."""
    if not isinstance(pending, dict) or pending.get('kind') != 'route_departure':
        return None
    day = pending.get('plan_date')
    suffix = f' for {day}' if isinstance(day,str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}',day) else ''
    return f'Route planning paused{suffix}: please reply with a departure time (e.g. 12:30 PM), or say Cancel route.'
