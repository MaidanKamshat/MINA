"""Conservative, deterministic fast route for obvious read-only live queries.

If a request includes planning or mutation terms, let the existing Coordinator
handle it instead of silently dropping tasks in the read-only fast path.
"""
from __future__ import annotations
import re

WEATHER = re.compile(r"\b(weather|forecast|temperature|rainfall|rainy|snowfall)\b", re.I)
WEATHER_CLOTHES = re.compile(
    r"\b(?:what should (?:the |my )?(?:kids|children|daughter|son|child) wear|"
    r"how should i dress (?:the |my )?(?:kids|children|daughter|son|child))\b", re.I,
)
CURRENT_TIME = re.compile(
    r"\b(what(?:'s| is) the (?:current |local )?(?:time|date)|what (?:time and date|date and time) is it|what time is it|what day is it|"
    r"current (?:time|date)|time (?:right )?now|today'?s date|date today)\b", re.I,
)
PLANNING_OR_ACTION = re.compile(
    r"\b(plan|schedule|organize|buy|purchase|pick up|pickup|drop off|return|appointment|"
    r"add|delete|remove|update|send|book|reschedule|calendar|grocery list|email)\b", re.I,
)


def simple_live_topics(request: str) -> tuple[bool, bool]:
    """Return (weather, current_time) for isolated, clearly read-only questions."""
    if PLANNING_OR_ACTION.search(request):
        return False, False
    return bool(WEATHER.search(request) or WEATHER_CLOTHES.search(request)), bool(CURRENT_TIME.search(request))


def requested_weather_day(request: str) -> str:
    if re.search(r"\btomorrow\b", request, re.I):
        return "tomorrow"
    if re.search(r"\b(next week|weekend|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", request, re.I):
        return "unsupported"
    return "today"
