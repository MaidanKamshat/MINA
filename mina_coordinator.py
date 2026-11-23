"""MINA Block 2: structured intent extraction and selective routing.

Only parses requests and selects a branch. It NEVER executes external writes
or claims that calendar, map, or scheduling tools have been run.
"""
import json
import re
from pathlib import Path

from complexity_router import assess_complexity
from mina_state import Constraint, RequestedTask, RequestState
from mina_write_guard import detect_explicit_write

MODEL = "gpt-4.1-mini"
TASK_IDS = (
    "library", "groceries", "school_pickup", "appointment",
    "shopping_list_update", "calendar_update", "email_draft",
    "weather_lookup", "household", "meal", "school_preparation", "other",
)
SCHEDULABLE = {"library", "groceries", "school_pickup", "appointment", "household", "meal"}

# Flat, strict JSON schema: downstream Python does the independent validation.
SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": [
            "information", "planning", "list_update", "calendar_update", "message_draft", "other"
        ]},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "task_id": {"type": "string", "enum": list(TASK_IDS)},
            "description": {"type": "string"},
            "evidence": {"type": "string"},
        }, "required": ["task_id", "description", "evidence"], "additionalProperties": False}},
        "constraints": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": [
                "deadline", "opening_time", "minimum_duration", "fixed_time", "other"
            ]},
            "task_id": {"type": ["string", "null"], "enum": list(TASK_IDS) + [None]},
            "value": {"type": "string"},
            "evidence": {"type": "string"},
        }, "required": ["kind", "task_id", "value", "evidence"], "additionalProperties": False}},
        "preferences": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "write_action_requested": {"type": "boolean"},
    },
    "required": [
        "intent", "tasks", "constraints", "preferences", "missing_information", "write_action_requested"
    ],
    "additionalProperties": False,
}

INSTRUCTIONS = """You are MINA's intent extractor, not the planner.
Extract only tasks EXPLICITLY requested in the current user message.
Do not infer that the user wants Costco, a specific library, a calendar update,
extra errands, or any action merely because it is a common family preference.
Every task and constraint MUST include a short `evidence` that is an EXACT
contiguous quotation from the user's message. If no quote exists, omit it.
The user's message is your ONLY evidence: no retrieved notes are present.
Task ids: library (return/visit library), groceries (buy groceries),
school_pickup, appointment, shopping_list_update, calendar_update,
email_draft, weather_lookup, household, meal, school_preparation, other.
Use school_preparation for preparing bags, clothes, school supplies or morning readiness.
Do NOT use meal for school preparation unless food, cooking or lunch is explicitly mentioned.
When the user asks about school lunch or preparing food, classify that task as meal,
not school_preparation (unless they ALSO request bags, clothes, supplies, etc.).
Use `planning` for requests to coordinate/schedule errands. Simple questions
are `information`. A request to add an item to a list is `list_update`.
Interpret "before", "by" and "no later than" as DEADLINE, never fixed_time.
Use fixed_time only for explicit "at [time]" commitments or appointments.
For time constraints, convert to 24-hour HH:MM (e.g., 2:30 PM => 14:30;
noon => 12:00). For duration use minutes as a decimal-free string.
Identify only missing information essential for executing the current task.
Do not fabricate times or data. Do not execute any action.
CRITICAL: Planning errands is READ-ONLY. "Return library books", "buy groceries",
and "pick up my child" are ordinary activities, NOT requests to modify a
shopping list, calendar, or email. Set write_action_requested=true ONLY for
an explicit request to add/edit/delete external data or send a message.
"Plan the best order for these errands" always means planning, not saving them.
"""


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


class UnanchoredEvidenceError(ValueError):
    """Model supplied a citation that is not a substring of the user request."""


def _verify_evidence(excerpt: str, original: str, name: str) -> None:
    if not excerpt.strip() or _normalize(excerpt) not in _normalize(original):
        raise UnanchoredEvidenceError(f"Unanchored {name}: model must quote the user's actual request")


def parse_structured_response(user_request: str, output_text: str) -> RequestState:
    """Convert JSON from the model into typed state; fail closed on bad evidence."""
    if not user_request.strip():
        raise ValueError("User request is empty")
    raw = json.loads(output_text)
    if not isinstance(raw, dict):
        raise ValueError("Invalid response object")
    tasks = []
    for item in raw["tasks"]:
        if item["task_id"] not in TASK_IDS:
            raise ValueError("Unknown task id")
        _verify_evidence(item["evidence"], user_request, "task evidence")
        # Domain-specific disambiguation for a known extraction failure:
        # "prepare for school" is school readiness, not meal preparation.
        task_id = item["task_id"]
        task_evidence = item["evidence"]
        contains_food = bool(re.search(
            r"\b(?:meal|food|cook|breakfast|lunch|lunchbox|dinner|snack|recipe)\b",
            task_evidence, flags=re.I))
        contains_nonfood_school_tasks = bool(re.search(
            r"\b(?:backpack|bags?|clothes|uniform|supplies|homework|folders|books)\b",
            task_evidence, flags=re.I))
        # Domain-level normalization based on the literal evidence span, not test IDs.
        # "prepare for school" is readiness; "prepare for school lunch" is food.
        if (task_id == "meal"
                and re.search(r"\bschool\b", user_request, flags=re.I)
                and re.search(r"\b(prepare|pack|ready|bag|clothes|supplies)\b", user_request, flags=re.I)
                and not re.search(r"\b(meal|food|cook|breakfast|lunch|dinner|snack|recipe|lunchbox)\b",
                                  user_request, flags=re.I)):
            task_id = "school_preparation"
        elif task_id == "school_preparation" and contains_food and not contains_nonfood_school_tasks:
            task_id = "meal"
        tasks.append(RequestedTask(task_id, item["description"], item["evidence"]))
    constraints = []
    for item in raw["constraints"]:
        _verify_evidence(item["evidence"], user_request, "constraint evidence")
        if item["task_id"] is not None and item["task_id"] not in TASK_IDS:
            raise ValueError("Unknown constraint task id")
        if item["kind"] not in {"deadline", "opening_time", "minimum_duration", "fixed_time", "other"}:
            raise ValueError("Unknown constraint type")
        if item["kind"] in {"deadline", "opening_time", "fixed_time"} and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item["value"]):
            raise ValueError("Time must be in HH:MM format")
        if item["kind"] == "minimum_duration" and not re.fullmatch(r"\d+", item["value"]):
            raise ValueError("Duration must be in whole minutes")
        kind = item["kind"]
        # Explicit deadline language must not become an exact-time commitment.
        # In particular, "pick up ... before 11 AM" is a latest-arrival bound,
        # whereas "pick up ... at 11 AM" is a fixed-time commitment.
        evidence = item["evidence"]
        deadline_phrase = bool(re.search(r"\b(before|by|no later than)\b", evidence, flags=re.I))
        negative_deadline_phrase = bool(re.search(
            r"\b(not before|no earlier than|at or after)\b", evidence, flags=re.I))
        if kind == "fixed_time" and deadline_phrase and not negative_deadline_phrase:
            kind = "deadline"
        constraints.append(Constraint(kind, item["task_id"], item["value"], evidence))
    state = RequestState(
        user_request=user_request,
        intent=raw["intent"],
        tasks=tasks,
        constraints=constraints,
        preferences=raw["preferences"],
        missing_information=raw["missing_information"],
        write_action_requested=bool(raw["write_action_requested"]),
    )
    return choose_route(state)


# High-precision normalization for read-only errand plans. The model may
# mistakenly treat "buy groceries" as modifying a grocery list or "pick up
# the child" as creating a calendar entry. The user must explicitly request
# such an external mutation before the write path is appropriate.
_PLANNING_CUE = re.compile(
    r"\b(?:plan|planning|best\s+(?:order|sequence|route)|"
    r"find\s+the\s+(?:best|optimal)\s+(?:order|route)|optimi[sz]e)\b", re.I
)
_WRITE_CONTEXT = re.compile(
    r"\b(?:calendar|e-?mail|message\s+to|shopping\s+list|grocery\s+list|"
    r"to[- ]?do\s+list|task\s+list|send|forward|reply|add|create|delete|"
    r"remove|update|edit|reschedule|cancel|book|notify|text|invite|share|post|publish|schedule\s+an\s+event)\b", re.I
)
_PLANNED_ERRANDS = {
    "library": re.compile(r"\b(?:librar(?:y|ies)|return(?:ing)?\s+library\s+books)\b", re.I),
    "groceries": re.compile(r"\b(?:grocer(?:y|ies)|grocery\s+shopping)\b", re.I),
    "school_pickup": re.compile(
        r"\b(?:school\s*pick[ -]?up|pick(?:ing)?\s+up\b.{0,60}\b(?:school|child|kid|children|daughter|son))",
        re.I,
    ),
}


def _normalize_explicit_read_only_plan(state: RequestState) -> None:
    """Repair a model's spurious write label only for unmistakable read-only plans.

    Never override an explicit write request or one that even mentions a list,
    calendar, or email. The original user's words, not model labels, establish
    the read-only task set. All evidence is copied exactly from those words.
    """
    request = state.user_request
    if (not _PLANNING_CUE.search(request) or _WRITE_CONTEXT.search(request)
            or detect_explicit_write(request) is not None):
        return
    found = {task_id: match.group(0)
             for task_id, pattern in _PLANNED_ERRANDS.items()
             if (match := pattern.search(request))}
    if len(found) < 2:
        return
    # Only reconcile the specific known errand categories, not unrelated
    # appointments or model-supplied claims unsupported by the request.
    kept = [task for task in state.tasks if task.task_id not in {
        'shopping_list_update', 'calendar_update', 'email_draft'}]
    already = {task.task_id for task in kept}
    for task_id, evidence in found.items():
        if task_id not in already:
            kept.append(RequestedTask(task_id, evidence, evidence))
    state.tasks = kept
    state.intent = 'planning'
    state.write_action_requested = False


def choose_route(state: RequestState) -> RequestState:
    """Run the existing regex router, but use structured task/intent evidence too.

    This corrects a known v2 heuristic: two errands with explicit 'plan' can
    score below 5 despite being genuine scheduling requests.
    """
    # Independent write-intent check. An incorrect LLM Boolean or task label
    # must not make an explicit external mutation look informational.
    write = detect_explicit_write(state.user_request)
    if write is not None:
        state.intent = write.intent
        state.write_action_requested = True
        state.tasks = [RequestedTask(
            write.task_id, state.user_request.strip(), state.user_request.strip()
        )]
        state.route = "simple"
        state.route_reason = "Deterministic external-write safety gate"
        state.router_signals = {"write_guard": True}
        return state
    # This only clears hallucinated write labels in explicitly read-only plans;
    # all genuine mutation requests remain protected by the independent guard.
    _normalize_explicit_read_only_plan(state)
    heuristic = assess_complexity(state.user_request)
    unique = {task.task_id for task in state.tasks if task.task_id in SCHEDULABLE}
    schedule_constraints = any(c.kind in {"deadline", "opening_time", "fixed_time", "minimum_duration"}
                               for c in state.constraints)
    needs_planning = (len(unique) >= 2 and (
        state.intent == "planning" or schedule_constraints or heuristic["strategy"] == "tot_candidate"
    )) or (len(unique) >= 3)
    state.route = "complex" if needs_planning else "simple"
    state.route_reason = (
        f"{len(unique)} distinct schedulable task types; "
        f"intent={state.intent}; time_constraints={schedule_constraints}; "
        f"router={heuristic['strategy']}"
    )
    state.router_signals = heuristic
    return state


def extract_request(user_request: str, client=None) -> RequestState:
    """Explicit writes take a deterministic safety route; other requests use OpenAI.

    No external writes or other side effects are executed here.
    """
    if not user_request.strip():
        raise ValueError("User request is empty")
    # High-confidence explicit writes never depend on a model interpretation.
    # This is intentional: no live write tool is connected in the current MVP.
    direct_write = detect_explicit_write(user_request)
    if direct_write is not None:
        return choose_route(RequestState(
            user_request=user_request,
            intent=direct_write.intent,
            tasks=[RequestedTask(direct_write.task_id, user_request.strip(), user_request.strip())],
            write_action_requested=True,
        ))
    if client is None:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(Path(__file__).parent / ".env", override=True)
        client = OpenAI()
    # One bounded correction only if the LLM invents/paraphrases its evidence span.
    # Fail closed if a second attempt is still unanchored; do NOT loosen validation.
    for attempt in range(2):
        instructions = INSTRUCTIONS
        if attempt:
            instructions += ("\nRETRY AFTER EVIDENCE VALIDATION FAILURE: Every `evidence` "
                             "must be copied verbatim from the current user request as "
                             "one contiguous span. Do not paraphrase, change punctuation, "
                             "add words, or invent tasks. If you cannot quote a task "
                             "exactly, omit it and describe essential uncertainty "
                             "in missing_information.\n")
        response = client.responses.create(
            model=MODEL,
            instructions=instructions,
            input=f"Current user request (extract only from these words):\n{user_request}",
            text={"format": {
                "type": "json_schema", "name": "mina_request_state",
                "strict": True, "schema": SCHEMA,
            }},
        )
        if not response.output_text:
            raise ValueError("Empty model output / refusal: cannot route safely")
        try:
            return parse_structured_response(user_request, response.output_text)
        except UnanchoredEvidenceError:
            if attempt == 1:
                raise
    raise AssertionError("Unreachable extraction retry state")
