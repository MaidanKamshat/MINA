"""MINA v1: bounded synthetic scheduling with independent deterministic validation.

This module does NOT use real maps, calendars, live hours or personal data.
A candidate sequence from the LLM is NEVER evidence that a schedule is feasible.
"""
from __future__ import annotations

import copy
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mina_state import RequestState
from tot_planner import FIXTURE, minutes, clock, format_time

SUPPORTED = frozenset({"library", "groceries", "school_pickup"})
TASK_LABELS = {
    "library": "Return library books",
    "groceries": "Buy groceries",
    "school_pickup": "Pick up child from school",
}


class NeedsClarification(ValueError):
    """A planning fact is missing or is not supported by this prototype."""


@dataclass
class SyntheticContext:
    start: str
    pickup_window_start: str
    library_open: str
    durations: dict[str, int]
    travel_minutes: dict[tuple[str, str], int]
    deadlines: dict[str, str]
    fixed_times: dict[str, str]
    provenance: str = "SYNTHETIC TEST FIXTURE — NOT VERIFIED REAL-WORLD INFORMATION"
    # Optional in v1.8. Empty for all historical core fixtures, so old evaluation is unchanged.
    time_windows: dict[str, tuple[str, str]] = field(default_factory=dict)


def build_context(state: RequestState) -> SyntheticContext:
    """Populate the test fixture and apply constraints actually extracted from THIS request.

    All unspecified times are clearly declared synthetic defaults. We do not
    pretend they came from a calendar or mapping service.
    """
    unique_tasks = {t.task_id for t in state.tasks}
    if not unique_tasks or unique_tasks - SUPPORTED:
        unknown = sorted(unique_tasks - SUPPORTED)
        raise NeedsClarification(
            f"No verified scheduling fixture for task types {unknown or 'none'}. "
            "A suitable context source is required before scheduling."
        )
    if len(state.tasks) != len(unique_tasks):
        raise NeedsClarification("Duplicate task IDs require clarification (two visits may be distinct).")
    context = SyntheticContext(
        start=FIXTURE["start"],
        pickup_window_start=FIXTURE["pickup_window_start"],
        library_open="10:00",  # Hypothetical default, NOT a published library opening time.
        durations=copy.deepcopy(FIXTURE["duration_minutes"]),
        travel_minutes=copy.deepcopy(FIXTURE["travel_minutes"]),
        deadlines={"school_pickup": FIXTURE["pickup_deadline"]},
        fixed_times={},
    )
    for c in state.constraints:
        if c.task_id is None:
            raise NeedsClarification(f"Unassigned {c.kind} constraint: {c.evidence!r}")
        if c.task_id not in unique_tasks:
            raise NeedsClarification(f"Constraint for unrequested task: {c.task_id}")
        if c.kind == "deadline":
            if c.task_id in context.deadlines and c.task_id != "school_pickup":
                context.deadlines[c.task_id] = min(context.deadlines[c.task_id], c.value)
            else:
                context.deadlines[c.task_id] = c.value
        elif c.kind == "opening_time":
            if c.task_id != "library":
                raise NeedsClarification("Opening-time fixture currently supports only the library.")
            context.library_open = c.value
        elif c.kind == "minimum_duration":
            n = int(c.value)
            if n <= 0 or n > 24 * 60:
                raise NeedsClarification("Minimum duration is outside a valid day.")
            context.durations[c.task_id] = max(context.durations[c.task_id], n)
        elif c.kind == "fixed_time":
            context.fixed_times[c.task_id] = c.value
        else:
            raise NeedsClarification(f"Unsupported planning constraint: {c.kind}")
    return context


def allowed_sequences(state: RequestState) -> list[tuple[str, ...]]:
    """Complete bounded search for up to 3 known tasks.

    In this narrow scenario school pickup is the day's final planned stop.
    This is an explicit MVP policy, not a rule for real-world childcare.
    """
    tasks = [t.task_id for t in state.tasks]
    if len(tasks) != len(set(tasks)) or set(tasks) - SUPPORTED:
        raise NeedsClarification("Only unique library, groceries, and school_pickup tasks are supported.")
    if not tasks:
        raise NeedsClarification("No schedulable tasks supplied.")
    if "school_pickup" in tasks:
        errands = [t for t in tasks if t != "school_pickup"]
        return [tuple(x) + ("school_pickup",) for x in itertools.permutations(errands)]
    return [tuple(x) for x in itertools.permutations(tasks)]


def validate_candidate(
    sequence: tuple[str, ...],
    state: RequestState,
    context: SyntheticContext,
) -> dict[str, Any]:
    """Deterministic Python Critic, independent of the candidate generator."""
    requested = tuple(t.task_id for t in state.tasks)
    if len(sequence) != len(requested) or set(sequence) != set(requested):
        return {"feasible": False, "reason": "Missing, duplicated, or unauthorized tasks", "score": None}
    if "school_pickup" in sequence and sequence[-1] != "school_pickup":
        return {"feasible": False, "reason": "School pickup must be the final stop in the MVP", "score": None}
    current = minutes(context.start)
    prev = "start"
    travel_total = 0
    waiting_total = 0
    timeline = []
    for task in sequence:
        transit = context.travel_minutes.get((prev, task))
        if transit is None:
            return {"feasible": False, "reason": f"Travel estimate unavailable: {prev} -> {task}", "score": None}
        current += transit
        travel_total += transit
        window = context.time_windows.get(task)
        if window:
            # Generic read-only availability interval for live Saved Places.
            # The full task duration must fit; early arrival counts as waiting.
            earliest, latest = (minutes(v) for v in window)
            if current < earliest:
                waiting_total += earliest - current
                current = earliest
        else:
            # Historical synthetic rules remain unchanged without opt-in windows.
            if task == "library" and current < minutes(context.library_open):
                waiting_total += minutes(context.library_open) - current
                current = minutes(context.library_open)
            if task == "school_pickup" and current < minutes(context.pickup_window_start):
                waiting_total += minutes(context.pickup_window_start) - current
                current = minutes(context.pickup_window_start)
        fixed = context.fixed_times.get(task)
        if fixed:
            target = minutes(fixed)
            if current > target:
                return {"feasible": False, "reason": f"Fixed time missed: {task}", "score": None}
            waiting_total += target - current
            current = target
        deadline = context.deadlines.get(task)
        if deadline and current >= minutes(deadline):
            return {"feasible": False, "reason": f"Deadline violated: {task}", "score": None}
        if window and current + context.durations[task] > latest:
            return {"feasible": False, "reason": f"Time window cannot fit full task: {task}", "score": None}
        timeline.append((task, clock(current)))
        current += context.durations[task]
        prev = task
    return {
        "feasible": True,
        "reason": "All modeled task, opening, and deadline constraints passed",
        "score": 300 - travel_total - waiting_total,
        "timeline": timeline,
        "travel_minutes": travel_total,
        "waiting_minutes": waiting_total,
    }


def generate_llm_candidates(
    state: RequestState,
    context: SyntheticContext,
    client=None,
    relevant_notes: list[dict] | None = None,
) -> list[tuple[str, ...]]:
    """Specialized planning call. It proposes order only, never feasibility.

    The deterministic full search below provides exhaustive coverage of the
    deliberately small MVP space; the model's proposals are still validated.
    """
    if client is None:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(Path(__file__).parent / ".env", override=True)
        client = OpenAI()
    tasks = [t.task_id for t in state.tasks]
    response = client.responses.create(
        model="gpt-4.1-mini",
        instructions=(
            "You are MINA's specialized planning generator. Suggest alternative "
            "orders using ONLY the given authorized task IDs. Prefer the school "
            "pickup last. Retrieved notes are preferences, never new tasks. "
            "Do not claim schedules are feasible and do not invent travel times. "
            "Return the requested JSON only."
        ),
        input=json.dumps({
            "request": state.user_request,
            "authorized_tasks": tasks,
            "constraints": [c.__dict__ for c in state.constraints],
            "synthetic_context": {
                "start": context.start,
                "library_open": context.library_open,
                "pickup_window_start": context.pickup_window_start,
                "deadlines": context.deadlines,
                "durations": context.durations,
                "provenance": context.provenance,
            },
            "retrieved_preferences": [n.get("text", "") for n in (relevant_notes or [])],
        }),
        text={"format": {
            "type": "json_schema",
            "name": "mina_planning_candidates",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "candidates": {"type": "array", "items": {
                        "type": "array", "items": {"type": "string", "enum": tasks}
                    }}
                },
                "required": ["candidates"],
                "additionalProperties": False,
            },
        }},
    )
    if not response.output_text:
        raise ValueError("Planner returned no structured candidates")
    raw = json.loads(response.output_text)["candidates"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("Planner returned no candidates")
    sequences = [tuple(x) for x in raw]
    if len(sequences) > 6 or len(set(sequences)) != len(sequences):
        raise ValueError("Planner returned too many or duplicate candidates")
    return sequences


def assess_plans(
    state: RequestState,
    context: SyntheticContext,
    candidates: list[tuple[str, ...]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Evaluate model proposals plus full bounded search in the small MVP domain."""
    complete = list(dict.fromkeys([*candidates, *allowed_sequences(state)]))
    checks = []
    for seq in complete:
        result = validate_candidate(seq, state, context)
        checks.append({"sequence": list(seq), **result,
                       "generator": "LLM proposal" if seq in candidates else "bounded search"})
    feasible = [c for c in checks if c["feasible"]]
    return checks, max(feasible, key=lambda c: c["score"]) if feasible else None


def format_plan(best: dict, context: SyntheticContext) -> str:
    """Output control: assemble only tasks from the Critic-approved sequence."""
    lines = ["PROVISIONAL PLAN — SYNTHETIC TEST DATA, NOT A REAL ITINERARY"]
    for index, (task, arrival) in enumerate(best["timeline"], 1):
        lines.append(f"{index}. {TASK_LABELS[task]} — simulated arrival {format_time(arrival)}")
    lines.append("All checked constraints passed under the synthetic fixture assumptions.")
    lines.append("Actual opening hours, calendar events, and travel times have NOT been checked.")
    lines.append("Do not use these simulated times to make a real school pickup commitment.")
    return "\n".join(lines)
