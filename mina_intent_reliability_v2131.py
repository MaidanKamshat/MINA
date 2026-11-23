"""MINA v2.13.1: narrow, read-only checks for grounded family-route inputs.

No external services, no private-file access, no mutation. Distinguishes a user-named
unsaved stop from the supported Family Hub stop set; never assigns coordinates.
"""
from __future__ import annotations
import re

# Only match a named stop when the request explicitly establishes travel context.
_ROUTE_CONTEXT = re.compile(r'\b(?:route|driving|plan|planning|trip|pick(?:ing)?\s+up|pickup)\b', re.I)
_UNKNOWN_PATTERNS = (
    re.compile(r'\bplace\s+called\s+(?P<name>[a-z][a-z0-9\s\x27\u2019-]{1,75}?)\s*,?\s*(?=and\s+then\b|then\b|before\b|\.|\?|$)', re.I),
    re.compile(r'\bstop\s+at\s+(?P<name>[a-z][a-z0-9\s\x27\u2019-]{1,75}?)\s+(?=before\s+(?:pick(?:ing)?\s+up|school|going\s+to)|and\s+then\b)', re.I),
)
_KNOWN = {'home','school','my school', 'my child\'s school','library', 'the library',
          'costco', 'target', "trader joe's", 'trader joes', 'the dentist',
          'dentist', 'pediatrician', 'groceries', 'grocery store'}


def unsaved_named_stop(prompt: str, hub: dict | None = None) -> str | None:
    """Return safe display label for a genuinely unknown *named* route stop.

    Do not use this for general geocoding or for unspecified free-form stops.
    A valid address given by the user is not enough to validate a map point.
    """
    if not isinstance(prompt, str) or len(prompt) > 650 or not _ROUTE_CONTEXT.search(prompt):
        return None
    names = set(_KNOWN)
    if isinstance(hub, dict):
        for place in (hub.get('places') or {}).values():
            if isinstance(place, dict):
                name = place.get('name')
                if isinstance(name, str): names.add(name.strip().casefold())
    for pattern in _UNKNOWN_PATTERNS:
        match = pattern.search(prompt)
        if not match: continue
        label = re.sub(r'\s+', ' ', match.group('name')).strip(' ,.-')
        # Never treat a street address or an input artifact as a confirmed match.
        if not 2 <= len(label) <= 76:
            continue
        if label.casefold() in names:
            continue
        return label
    return None


def missing_departure_reply(*, day: str | None, pickup: str) -> str:
    """Ask for the actual missing constraint, rather than inventing departure time."""
    dated = f' for **{day}**' if day else ''
    return (f'I found your saved school pickup target **{pickup}** (your note, not school-verified){dated}. '
            'I also found the saved stops, but you did not specify a home departure time '
            'or departure window. **What time would you like to leave?** '
            'No route was calculated; I did not assume a departure time or change any data.')
