"""Conservative, deterministic guard for explicit requests to modify external data.

This is a small high-precision safety backstop, NOT a general-purpose intent parser.
It detects clear imperative calendar/list/email actions so a single LLM label error
cannot send a write request through the informational-response branch.

The MVP intentionally has NO external write tools: recognizing a write request
means BLOCKING it with approval_required, never performing the action.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class WriteAction:
    intent: str
    task_id: str


_PREFIX = re.compile(
    r"^(?:(?:please\s+)|(?:can|could|would|will)\s+you\s+|"
    r"(?:i\s+(?:need|want)\s+you\s+to\s+))",
    re.IGNORECASE,
)
_COMMAND = re.compile(
    r"^(add|create|put|schedule|book|delete|remove|update|edit|change|"
    r"move|reschedule|cancel|clear|mark|send|email|forward|reply)\b",
    re.IGNORECASE,
)
_LIST = re.compile(
    r"\b(?:grocery|shopping|to[- ]?do|task|packing)\s+list\b|"
    r"\b(?:my|the)\s+list\b",
    re.IGNORECASE,
)
_CALENDAR = re.compile(r"\b(calendar|event|appointment|meeting)\b", re.IGNORECASE)
_EMAIL = re.compile(r"\b(email|e[- ]?mail|message|teacher|doctor|recipient)\b", re.IGNORECASE)


def detect_explicit_write(request: str) -> WriteAction | None:
    """Identify clear commands to change a list/calendar or send an email.

    A question ABOUT an action, a negative command, a reminder, or a draft
    request is not treated as a direct external write. Ambiguous actions are
    left for the Coordinator, while the runtime retains its separate safety gate.
    """
    text = request.strip()
    if not text:
        return None
    # Guard against the most common informational and negated requests.
    if re.match(
        r"^(?:do\s+not|don't|never|how\b|what\b|why\b|when\b|where\b|"
        r"did\b|have\b|should\b|is\b|are\b|tell\s+me\b|"
        r"explain\b|remind\s+me\b|draft\b|write\s+(?:a\s+)?draft\b)",
        text, re.IGNORECASE,
    ):
        return None
    # Strip polite imperatives, without stripping ordinary questions such as
    # 'Can you explain how to add an event?'
    text = _PREFIX.sub('', text, count=1).strip()
    if re.match(r"^(?:do\s+not|don't|never|explain\b|tell\s+me\b|how\b|draft\b)", text, re.I):
        return None
    command_match = _COMMAND.match(text)
    if not command_match:
        # Also guard explicit writes in compound requests, e.g. "Plan my
        # errands and then add the pickup to my calendar." A leading
        # planning verb must not bypass write safety. Recursion only applies
        # to a shorter, clearly introduced clause.
        for match in re.finditer(r"\b(?:and|then|also)\s+(?:then\s+)?(?:please\s+)?"
                                  r"(?=(?:add|create|put|schedule|book|delete|remove|"
                                  r"update|edit|change|move|reschedule|cancel|clear|mark|"
                                  r"send|email|forward|reply)\b)", text, re.I):
            nested = detect_explicit_write(text[match.end():])
            if nested is not None:
                return nested
        return None
    verb = command_match.group(1).lower()
    if verb in {'send', 'email', 'forward', 'reply'}:
        if verb == 'email' or _EMAIL.search(text):
            return WriteAction('message_draft', 'email_draft')
        return None
    if verb in {'add', 'create', 'put', 'schedule', 'book', 'delete', 'remove',
                'update', 'edit', 'change', 'move', 'reschedule', 'cancel', 'clear', 'mark'}:
        calendar = bool(_CALENDAR.search(text))
        listed = bool(_LIST.search(text))
        # If a message clearly asks for multiple kinds of external writes,
        # block the whole operation instead of silently selecting one action.
        # `other` is deliberately NOT a runnable write tool.
        if calendar and listed:
            return WriteAction('other', 'other')
        if calendar:
            return WriteAction('calendar_update', 'calendar_update')
        if listed:
            return WriteAction('list_update', 'shopping_list_update')
    return None
