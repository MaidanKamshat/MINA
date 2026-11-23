"""Streamlit interface adapter for MINA v1.8.

This is an opt-in presentation layer. It does not mutate Coordinator, Critic,
Controller, audit logging, fixtures, or the twenty-case benchmark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Any

from mina_saved_places import parse_clock

PROJECT_ROOT = Path(__file__).resolve().parent
UI_MAP_PATH = PROJECT_ROOT / 'evaluation' / 'maps' / 'streamlit_latest_route.html'
TASK_IDS = ('library', 'groceries', 'school_pickup')


class UIInputError(ValueError):
    """User can fix the request/settings without changing MINA's code."""


@dataclass(frozen=True)
class UISettings:
    mode: str = 'assistant'  # assistant | directions | family_plan
    city: str = 'Apex, NC'
    timezone_name: str = 'America/New_York'
    planner_mode: str = 'llm'
    use_rag: bool = False
    origin: str = ''
    destination: str = ''
    via: tuple[str, ...] = ()
    task_locations: dict[str, str] = field(default_factory=dict)
    durations: dict[str, int] = field(default_factory=dict)
    start_time: str = '10:00 AM'
    library_open: str = ''  # User-provided; never inferred from an API
    saved_places_file: str = ''
    plan_date: str = ''
    travel_buffer_minutes: int = 10


def validate_ui_settings(settings: UISettings) -> None:
    if settings.mode not in {'assistant', 'directions', 'family_plan'}:
        raise UIInputError('Select Assistant, Directions, or Family planner.')
    if settings.planner_mode not in {'llm', 'deterministic'}:
        raise UIInputError('Choose LLM or deterministic planning.')
    if settings.mode == 'directions':
        stops = [settings.origin, *settings.via, settings.destination]
        if len(stops) > 5 or len(stops) < 2 or not all(x.strip() for x in stops):
            raise UIInputError('Directions needs an origin, destination, and at most 3 via stops.')
    if settings.mode == 'family_plan':
        tasks = set(settings.task_locations)
        if not (2 <= len(tasks) <= 3 and tasks <= set(TASK_IDS)):
            raise UIInputError('Select two or three distinct supported errands for Family planner.')
        if not settings.origin.strip() or any(not value.strip() for value in settings.task_locations.values()):
            raise UIInputError('Enter a public demo location for the origin and every selected task.')
        if set(settings.durations) != tasks:
            raise UIInputError('Enter a duration in minutes for every selected task.')
        if any(type(n) is not int or n < 1 or n > 360 for n in settings.durations.values()):
            raise UIInputError('Each duration must be between 1 and 360 minutes.')
        try:
            parse_clock(settings.start_time)
        except Exception:
            raise UIInputError('Use 12-hour start time, for example 10:00 AM.') from None
        if settings.library_open.strip():
            try:
                parse_clock(settings.library_open)
            except ValueError:
                raise UIInputError('Use a confirmed library opening time in AM/PM.') from None
        if not 0 <= settings.travel_buffer_minutes <= 120:
            raise UIInputError('Travel buffer must be 0–120 minutes per leg.')
        if bool(settings.saved_places_file.strip()) != bool(settings.plan_date.strip()):
            raise UIInputError('Saved Places file and plan date must be supplied together.')
        if settings.plan_date.strip():
            try:
                date.fromisoformat(settings.plan_date)
            except ValueError:
                raise UIInputError('Plan date must be YYYY-MM-DD.') from None


def execute_ui_request(request: str, settings: UISettings, *, runner: Callable[..., Any] | None = None) -> Any:
    """Delegate to existing read-only runtime; no separate 'UI policy' can bypass write guard."""
    request = request.strip() if isinstance(request, str) else ''
    if not request:
        raise UIInputError('Record a message or type a request first.')
    if len(request) > 3000:
        raise UIInputError('Keep each request under 3,000 characters.')
    validate_ui_settings(settings)
    if runner is None:
        from mina_runtime import run_request
        runner = run_request
    kwargs = {
        'planner_mode': settings.planner_mode,
        'use_rag': settings.use_rag,
        'live_tools': True,
        'city': settings.city.strip() or None,
        'timezone_name': settings.timezone_name,
    }
    if settings.mode == 'directions':
        kwargs['route_stops'] = (settings.origin.strip(),) + tuple(x.strip() for x in settings.via) + (
            settings.destination.strip(),
        )
    elif settings.mode == 'family_plan':
        from mina_live_planning import LivePlanInputs
        kwargs['live_plan'] = LivePlanInputs(
            origin=settings.origin.strip(),
            task_locations={k: v.strip() for k, v in settings.task_locations.items()},
            start_time=settings.start_time.strip(),
            library_open=settings.library_open.strip() or None,
            durations=dict(settings.durations),
            travel_buffer_minutes=settings.travel_buffer_minutes,
            saved_places_file=settings.saved_places_file.strip() or None,
            plan_date=settings.plan_date.strip() or None,
        )
    return runner(request, **kwargs)


def save_preview_map(report: Any, *, writer: Callable[..., Path] | None = None, output_path: Path = UI_MAP_PATH) -> Path:
    """Writes only a local preview under evaluation/maps; never exports credentials."""
    if writer is None:
        from mina_route_tools import write_route_map
        writer = write_route_map
    # For the app, the location is fixed rather than any arbitrary user input path.
    return Path(writer(report, output_path))


def status_caption(status: str) -> str:
    return {
        'simple_response': 'Read-only response',
        'synthetic_plan': 'Synthetic planning demonstration — not live routing',
        'provisional_live_route_plan': 'Provisional route plan — times and hours are not independently verified',
        'approval_required': 'Write blocked — nothing changed or sent',
        'local_confirmation_required': 'Local change proposed — nothing saved until you confirm',
        'needs_clarification': 'More information is needed before planning',
        'no_feasible_plan': 'No plan satisfies the supplied constraints',
        'tool_unavailable': 'A live source is unavailable; no synthetic value substituted',
        'generation_failed': 'Planner could not validate the result',
    }.get(status, 'MINA response')
