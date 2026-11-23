"""Conservative read-only route query detector; no intent classification by LLM."""
import re

ROUTE = re.compile(
    r'\b(route|directions|driving route|drive from|travel time|time to drive|'
    r'distance between|distance from|driving distance|маршрут|доехать|проехать)\b', re.I)
SCHEDULING = re.compile(
    r'\b(schedule|pick up|pickup|arrive by|before \d|calendar|add|delete|'
    r'update|send|book an appointment|drop off|buy groceries|return books)\b', re.I)


def is_route_only_query(request: str) -> bool:
    """Route-only requests may bypass the LLM; planning/mutations must not."""
    return bool(ROUTE.search(request)) and not bool(SCHEDULING.search(request))
