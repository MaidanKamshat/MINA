"""MINA v1.7: opt-in mixed-source planning using read-only HeiGIT routes.

Driving legs are provider estimates; all schedule inputs besides driving time
come from the current user request / explicit CLI flags. NO synthetic defaults,
calendar verification, opening-hours lookup, traffic predictions, or writes.
"""
from __future__ import annotations

import math
import json
import re
from dataclasses import dataclass, replace
from typing import Any

from mina_state import RequestState
from mina_planning import (
    SyntheticContext, NeedsClarification, SUPPORTED, allowed_sequences,
    assess_plans, TASK_LABELS,
)
from mina_route_tools import (
    RouteStop, RouteLeg, RouteReport, _require_key,
    geocode_route_stop, get_route_report,
)
from mina_live_tools import ToolUnavailable, LocationRequired
from tot_planner import minutes, format_time


@dataclass(frozen=True)
class LivePlanInputs:
    origin: str
    task_locations: dict[str, str]
    start_time: str
    durations: dict[str, int]
    library_open: str | None = None
    travel_buffer_minutes: int = 10
    saved_places_file: str | None = None
    plan_date: str | None = None


@dataclass
class LivePlanOutcome:
    status: str
    answer: str
    candidates: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    map_report: RouteReport | None = None


def _valid_clock(value: str | None) -> bool:
    return isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value) is not None


def _scope_matches_extracted_value(clause: str, constraint) -> bool:
    """Do not rebind a quote if the LLM normalized a different number/time."""
    if constraint.kind == 'minimum_duration':
        observed = set(re.findall(r'\b(\d{1,3})\s*(?:minutes?|mins?)\b', clause, re.I))
        return observed == {str(constraint.value)}
    if constraint.kind not in {'opening_time', 'deadline', 'fixed_time'}:
        return False
    clocks: set[str] = set()
    for hour, minute, period in re.findall(
            r'\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(AM|PM)\b', clause, re.I):
        hour24 = int(hour) % 12 + (12 if period.lower() == 'pm' else 0)
        clocks.add(f'{hour24:02d}:{int(minute or 0):02d}')
    if re.search(r'\bnoon\b', clause, re.I):
        clocks.add('12:00')
    if re.search(r'\bmidnight\b', clause, re.I):
        clocks.add('00:00')
    # A 24-hour time without a 12-hour AM/PM marker.
    if not clocks:
        clocks.update(re.findall(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b', clause))
    return clocks == {constraint.value}


def _resolve_unassigned_constraint(request: str, constraint, requested: set[str]) -> str | None:
    """Bind an unassigned constraint ONLY when its quoted clause is unambiguous.

    This is a narrow safety repair for live-route scheduling. It never infers
    calendar times, cross-clause dependencies, unstated tasks or constraints.
    If the exact quoted evidence is not found, or contains more than one
    plausible task, validation still fails closed before routing-network calls.
    """
    evidence = constraint.evidence.strip()
    if not evidence:
        return None
    exact_quote = r'\s+'.join(re.escape(part) for part in evidence.split())
    matches = list(re.finditer(exact_quote, request, flags=re.I))
    if not matches:
        return None
    possible: set[str] = set()
    for match in matches:
        # Tight local clause, not the full user request. Comma-separated and
        # sentence-separated demo requests can be safely scoped; ambiguous
        # multi-task clauses must not be silently attributed to one task.
        start = max(request.rfind(delimiter, 0, match.start()) for delimiter in ',;.!?\n') + 1
        clause = request[start:match.end()]
        library = bool(re.search(r'\blibrar(?:y|ies)\b', clause, re.I))
        groceries = bool(re.search(r'\bgrocer(?:y|ies)\b', clause, re.I))
        pickup = bool(re.search(r'\b(?:pick(?:ing)?\s+up|school\s+pick[\s-]?up)\b', clause, re.I))
        if sum([library, groceries, pickup]) != 1 or not _scope_matches_extracted_value(clause, constraint):
            return None
        if constraint.kind == 'opening_time' and library and re.search(r'\bopen(?:s|ing)?\b', clause, re.I):
            possible.add('library')
        elif constraint.kind == 'minimum_duration' and groceries and re.search(
                r'\b(?:take|takes|last|lasts|at least|minimum|spend)\b', clause, re.I):
            possible.add('groceries')
        elif constraint.kind == 'deadline' and pickup and re.search(
                r'\b(?:before|by|no later than)\b', clause, re.I):
            possible.add('school_pickup')
        elif constraint.kind == 'fixed_time' and pickup and re.search(
                r'\bat\s+\d', clause, re.I):
            possible.add('school_pickup')
        else:
            return None
    return next(iter(possible)) if len(possible) == 1 and possible <= requested else None


def _validate_inputs(state: RequestState, params: LivePlanInputs) -> SyntheticContext:
    requested = [t.task_id for t in state.tasks]
    if not requested or len(set(requested)) != len(requested) or set(requested) - SUPPORTED:
        raise NeedsClarification('Live planning supports distinct library, groceries and school_pickup tasks only.')
    from mina_saved_places import parse_clock
    start_internal = parse_clock(params.start_time, legacy=True)
    if not params.origin or not isinstance(params.origin, str):
        raise NeedsClarification('Specify --origin as an explicit public place or longitude,latitude.')
    if set(params.task_locations) != set(requested):
        raise NeedsClarification('Specify exactly one --task-location for each requested task ID.')
    if set(params.durations) != set(requested):
        raise NeedsClarification('Specify --duration TASK=MINUTES for every requested task. No fixture durations are used.')
    if any(type(v) is not int or v <= 0 or v > 360 for v in params.durations.values()):
        raise NeedsClarification('Each task duration must be a whole number from 1 to 360 minutes.')
    if type(params.travel_buffer_minutes) is not int or not (0 <= params.travel_buffer_minutes <= 120):
        raise NeedsClarification('Travel buffer must be from 0 to 120 minutes per leg.')
    if not all(isinstance(v, str) and v.strip() for v in params.task_locations.values()):
        raise NeedsClarification('Every task must have a nonempty explicit location.')
    ctx = SyntheticContext(
        start=start_internal,
        pickup_window_start='00:00',  # No invented pickup window; use only explicit task constraint.
        library_open='00:00',
        durations=dict(params.durations),
        travel_minutes={},
        deadlines={},
        fixed_times={},
        provenance='MIXED: HeiGIT model driving estimates + user-supplied schedule inputs; '
                   'NO verified live traffic, calendar, opening hours, or pickup availability',
    )
    request_open = None
    for c in state.constraints:
        task_id = c.task_id
        if task_id is None or task_id not in requested:
            task_id = _resolve_unassigned_constraint(state.user_request, c, set(requested))
            if task_id is None:
                raise NeedsClarification(
                    f'Unassigned {c.kind} constraint. Explicitly state which errand '
                    'the deadline/opening/duration applies to. No route was fetched.'
                )
        if c.kind == 'minimum_duration':
            n = int(c.value)
            if not (0 < n <= 360):
                raise NeedsClarification('Duration constraint outside supported 1–360 minute range.')
            ctx.durations[task_id] = max(n, ctx.durations[task_id])
        elif c.kind == 'deadline':
            if not _valid_clock(c.value):
                raise NeedsClarification('Invalid deadline time in request.')
            ctx.deadlines[task_id] = min(ctx.deadlines.get(task_id, c.value), c.value)
        elif c.kind == 'fixed_time':
            if not _valid_clock(c.value):
                raise NeedsClarification('Invalid fixed time in request.')
            if task_id in ctx.fixed_times and ctx.fixed_times[task_id] != c.value:
                raise NeedsClarification('Conflicting fixed-time constraints.')
            ctx.fixed_times[task_id] = c.value
        elif c.kind == 'opening_time':
            if task_id != 'library' or not _valid_clock(c.value):
                raise NeedsClarification('Only an explicit library opening time is supported.')
            request_open = c.value if request_open is None else max(request_open, c.value)
        else:
            raise NeedsClarification('Unsupported constraint in live planning; do not guess.')
    if 'library' in requested:
        # AM/PM for user CLI; legacy 24-hour CLI remains backwards compatible.
        library_open_cli = parse_clock(params.library_open, legacy=True) if params.library_open else None
        if not library_open_cli and not request_open and not params.saved_places_file:
            raise NeedsClarification('Library opening time is unverified; supply --library-open 12:00 PM or state it in request.')
        if request_open and library_open_cli and request_open != library_open_cli:
            raise NeedsClarification('Conflicting library opening times in request and CLI flags.')
        ctx.library_open = request_open or library_open_cli or '00:00'
    if params.saved_places_file:
        from mina_saved_places import load_saved_hours
        saved = load_saved_hours(params.saved_places_file, params.plan_date, set(requested))
        for task, (opens, closes) in saved.windows.items():
            # A direct user instruction must not silently contradict saved notes.
            if task == 'library' and ctx.library_open not in {'00:00', opens}:
                raise NeedsClarification('Library opening time conflicts with Saved Places; confirm the hours.')
            ctx.time_windows[task] = (opens, closes)
        if 'school_pickup' in saved.windows:
            ctx.pickup_window_start = saved.windows['school_pickup'][0]
            # An earlier user deadline is allowed but may make the plan infeasible.
            # No separate deadline is needed when a complete pickup window exists.
        if 'library' in saved.windows:
            ctx.library_open = saved.windows['library'][0]
        ctx.provenance += ('; Saved Places time windows: ' + ','.join(sorted(saved.windows))
                           + (' (FICTIONAL DEMO DATA)' if saved.demo else ' (user supplied; NOT independently verified)'))
    elif params.plan_date:
        raise NeedsClarification('--plan-date is used with --saved-places.')
    if 'school_pickup' in requested and not (
        'school_pickup' in ctx.deadlines or 'school_pickup' in ctx.fixed_times
        or 'school_pickup' in ctx.time_windows
    ):
        raise NeedsClarification('School pickup requires an explicit deadline, fixed time or Saved Places pickup window.')
    if any(minutes(c) < minutes(start_internal) for c in [*ctx.deadlines.values(), *ctx.fixed_times.values()]):
        raise NeedsClarification('A deadline/fixed time is before the start time; overnight planning is unsupported.')
    return ctx


def _pretty_map(report: RouteReport, names: list[str], points: list[RouteStop]) -> RouteReport:
    stops = tuple(RouteStop(name, point.longitude, point.latitude) for name, point in zip(names, points))
    legs = tuple(RouteLeg(names[i], names[i + 1], leg.distance_km, leg.duration_minutes)
                 for i, leg in enumerate(report.legs))
    return replace(report, stops=stops, legs=legs)


def _generate_live_candidates(state: RequestState, ctx: SyntheticContext, client) -> list[tuple[str, ...]]:
    if client is None:
        from dotenv import load_dotenv
        from pathlib import Path
        from openai import OpenAI
        load_dotenv(Path(__file__).parent / '.env', override=True)
        client = OpenAI()
    tasks = [t.task_id for t in state.tasks]
    response = client.responses.create(
        model='gpt-4.1-mini',
        instructions=(
            'You suggest candidate orders of explicitly authorized errands only. '
            'They are not guaranteed feasible. Suggest up to six distinct full orders. '
            'Pickup is the final stop if requested. Do not invent travel, opening times, '
            'or locations. The travel estimates are read-only routing-provider data; '
            'schedule inputs are user supplied, not calendar verified. Return JSON only.'
        ),
        input=json.dumps({
            'request': state.user_request, 'authorized_tasks': tasks,
            'user_supplied_start': ctx.start, 'user_supplied_durations': ctx.durations,
            'user_supplied_deadlines': ctx.deadlines, 'user_supplied_fixed_times': ctx.fixed_times,
            'user_supplied_library_open': ctx.library_open if 'library' in tasks else None,
            'context_provenance': ctx.provenance,
        }),
        text={'format': {'type': 'json_schema', 'name': 'mina_live_candidate_orders',
                         'strict': True, 'schema': {
                             'type': 'object', 'properties': {'candidates': {
                                 'type': 'array', 'items': {'type': 'array', 'items': {'type': 'string', 'enum': tasks}}
                             }}, 'required': ['candidates'], 'additionalProperties': False}}},
    )
    if not response.output_text:
        raise ValueError('Empty LLM candidate result')
    candidates = json.loads(response.output_text)['candidates']
    if not isinstance(candidates, list) or len(candidates) > 6:
        raise ValueError('Invalid candidate list')
    result = [tuple(x) for x in candidates]
    if len(result) != len(set(result)):
        raise ValueError('Duplicate candidate orders')
    return result


def plan_with_live_routes(
    state: RequestState, params: LivePlanInputs, *,
    planner_mode: str = 'llm', client=None, opener=None,
) -> LivePlanOutcome:
    """Fetch actual HeiGIT estimated legs, then run existing Python Critic/Controller.

    If *any* required route fails, returns ToolUnavailable; never substitute
    synthetic times. No network calls until all required schedule inputs validate.
    """
    if planner_mode not in {'llm', 'deterministic'}:
        raise ValueError('Unknown planner mode')
    ctx = _validate_inputs(state, params)
    sequences = allowed_sequences(state)
    # Resolve each explicit location once and only once; never consult family-note locations.
    key = _require_key()
    locs = {'start': params.origin, **params.task_locations}
    points = {name: geocode_route_stop(value, api_key=key, opener=opener)
              for name, value in locs.items()}
    reports = {}
    # Two candidate orders max in current MVP; all checked by the same deterministic Critic.
    for seq in sequences:
        names = ['start', *seq]
        coords = [f'{points[t].longitude:.6f},{points[t].latitude:.6f}' for t in names]
        raw = get_route_report(coords, api_key=key, opener=opener)
        if len(raw.legs) != len(seq):
            raise ToolUnavailable('Incomplete route legs: cannot verify a candidate plan.')
        reports[seq] = _pretty_map(raw, names, [points[t] for t in names])
        for a, b, leg in zip(names, names[1:], raw.legs):
            if not math.isfinite(leg.duration_minutes) or leg.duration_minutes <= 0:
                raise ToolUnavailable('Invalid provider travel duration.')
            conservative = math.ceil(leg.duration_minutes) + params.travel_buffer_minutes
            # A shared directed leg could differ between route responses; keep the larger estimate.
            ctx.travel_minutes[a, b] = max(ctx.travel_minutes.get((a, b), 0), conservative)
    trace = [
        {'step': 'live_context', 'source': 'HeiGIT', 'status': 'ok', 'count': len(reports)},
        {'step': 'schedule_inputs', 'source': 'user_provided', 'status': 'ok'},
    ]
    proposals = sequences
    if planner_mode == 'llm':
        try:
            proposals = _generate_live_candidates(state, ctx, client)
            trace.append({'step': 'planner', 'method': 'LLM plus exhaustive bounded search', 'count': len(proposals)})
        except Exception as exc:
            # Candidate generation is not a source of truth; bounded search remains complete.
            proposals = sequences
            trace.append({'step': 'planner', 'method': 'bounded fallback', 'error_type': type(exc).__name__})
    else:
        trace.append({'step': 'planner', 'method': 'bounded deterministic search', 'count': len(sequences)})
    checked, best = assess_plans(state, ctx, proposals)
    # No overnight schedules supported. Fail closed when planning exceeds local calendar day.
    for candidate in checked:
        if candidate['feasible'] and candidate.get('timeline'):
            # All arrivals must be within the same local day.
            if (any(not _valid_clock(t) for _, t in candidate['timeline'])
                    or (minutes(candidate['timeline'][-1][1])
                        + ctx.durations[candidate['timeline'][-1][0]] >= 24 * 60)):
                candidate.update(feasible=False, score=None,
                                 reason='Schedule crosses midnight; unsupported')
                continue
            # Unlike pickup deadlines (arrival before cutoff), other task deadlines
            # are conservatively treated as task-COMPLETION deadlines in live mode.
            for task, arrival in candidate['timeline']:
                deadline = ctx.deadlines.get(task)
                if (task != 'school_pickup' and deadline
                        and minutes(arrival) + ctx.durations[task] >= minutes(deadline)):
                    candidate.update(feasible=False, score=None,
                                     reason=f'Task would not finish before deadline: {task}')
                    break
    feasible = [c for c in checked if c['feasible']]
    best = max(feasible, key=lambda c: c['score']) if feasible else None
    trace.append({'step': 'critic', 'passed': len(feasible), 'evaluated': len(checked),
                  'source': 'HeiGIT + user_provided'})
    if best is None:
        trace.append({'step': 'controller', 'decision': 'no feasible candidate'})
        return LivePlanOutcome(
            'no_feasible_plan',
            'No plan meets the SUPPLIED time constraints using HeiGIT estimated driving times '
            f'plus a {params.travel_buffer_minutes}-minute buffer per driving leg. '
            'This is not a calendar/opening-hours/traffic verification. '
            'No synthetic travel time was substituted.',
            checked, trace,
        )
    seq = tuple(best['sequence'])
    report = reports[seq]
    text = [
        'PROVISIONAL LIVE-ROUTE PLAN — NOT A VERIFIED REAL-WORLD SCHEDULE',
        f'Route source: HeiGIT/openrouteservice, retrieved UTC {report.retrieved_at_utc}.',
        f'Start: {format_time(ctx.start)} (user supplied, local time).',
    ]
    for i, (task, arrival) in enumerate(best['timeline'], start=1):
        window = ctx.time_windows.get(task)
        suffix = ''
        if window:
            from mina_saved_places import display_clock
            suffix = (f' (saved time window {display_clock(window[0])}–'
                      f'{display_clock(window[1])}; not independently verified)')
        text.append(f'{i}. {TASK_LABELS[task]} — estimated {"service start" if window else "arrival"} {format_time(arrival)}{suffix}.')
    text.extend([
        f'Route total: ~{report.distance_km:g} km; base driving estimate '
        f'~{report.duration_minutes:g} min; planning adds {params.travel_buffer_minutes} min per leg.',
        ('Time windows are loaded from Saved Places for ' + str(params.plan_date) +
         ' (user-entered/DEMO, NOT independently verified). Confirm public holidays and school hours.'
         if params.saved_places_file else
         'Task durations, deadlines and opening times are from the request/CLI, NOT verified '
         'against real calendars, venues, or school schedules.'),
        'No live traffic, parking, pickup availability or arrival guarantee. '
        'Confirm critical commitments independently; no calendar/list/email changes made.',
    ])
    trace.append({'step': 'controller', 'decision': 'selected', 'sequence': list(seq), 'score': best['score']})
    return LivePlanOutcome('provisional_live_route_plan', '\n'.join(text), checked, trace, report)
