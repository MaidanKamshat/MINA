"""MINA v2.2 landing-dashboard presentation helpers.

No external write endpoints or calendar sync. Task rows are browser-session state
only; sample tasks are clearly labelled as demonstration fixtures. Weather data
comes from the existing verified read-only Open-Meteo tool, never invented.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from mina_saved_places import parse_clock, display_clock

MAX_TASKS = 12
MAX_DEMO_BYTES = 15_000


class DashboardInputError(ValueError):
    """A dashboard-only input needs correction; backend remains unchanged."""


def normalize_task(title: str, time: str = '', *, identifier: str = '', done: bool = False) -> dict:
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 70:
        raise DashboardInputError('Task title must be 1–70 characters.')
    title = title.strip()
    if any(ord(c) < 32 for c in title) or '<' in title or '>' in title:
        raise DashboardInputError('Task title contains unsupported characters.')
    if not isinstance(time, str):
        raise DashboardInputError('Time must be text in AM/PM format.')
    time = time.strip()
    if time:
        try:
            time = display_clock(parse_clock(time))
        except Exception as exc:
            raise DashboardInputError('Use a time such as 3:15 PM, or leave it empty.') from exc
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', identifier):
        raise DashboardInputError('Task identifier is invalid.')
    return {'id': identifier, 'title': title, 'time': time, 'done': bool(done)}


def demo_tasks(path: Path) -> list[dict]:
    """Read small bundled public demo data; never interpret it as a real calendar."""
    try:
        if path.stat().st_size > MAX_DEMO_BYTES:
            raise DashboardInputError('Demo tasks fixture is unexpectedly large.')
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError) as exc:
        raise DashboardInputError('Demo tasks fixture is not available.') from exc
    if not isinstance(data, dict) or data.get('demo') is not True or not isinstance(data.get('tasks'), list):
        raise DashboardInputError('Sample tasks must be explicitly labelled demo.')
    if len(data['tasks']) > MAX_TASKS:
        raise DashboardInputError('Too many demo tasks.')
    tasks = []
    for item in data['tasks']:
        if not isinstance(item, dict):
            raise DashboardInputError('Invalid demo task.')
        tasks.append(normalize_task(item.get('title'), item.get('time', ''),
                                    identifier=item.get('id', ''), done=item.get('done', False)))
    if len(set(x['id'] for x in tasks)) != len(tasks):
        raise DashboardInputError('Duplicate demo task identifiers.')
    return tasks


def add_session_task(tasks: list[dict], title: str, time: str, next_index: int) -> list[dict]:
    if len(tasks) >= MAX_TASKS:
        raise DashboardInputError(f'Today\'s plan supports at most {MAX_TASKS} tasks in this demo.')
    added = normalize_task(title, time, identifier=f'session_{next_index}')
    if added['id'] in {item['id'] for item in tasks}:
        raise DashboardInputError('Task identifier conflict.')
    return [*tasks, added]


def set_done(tasks: list[dict], identifier: str, done: bool) -> list[dict]:
    if identifier not in {x['id'] for x in tasks}:
        raise DashboardInputError('Unknown task.')
    return [{**t, 'done': bool(done)} if t['id'] == identifier else dict(t) for t in tasks]


def dashboard_weather_html(report: Any | None, *, city: str, error: str | None = None) -> str:
    """Escape all external/provider-controlled text before injecting into UI HTML."""
    if report is None:
        return ("<div class='mina-weather-card mina-weather-fallback'>"
                "<span class='mina-weather-icon' aria-hidden='true'>☁</span>"
                "<span><strong>Forecast unavailable</strong>"
                f"<small>{escape(city)} · Try again later</small></span></div>")
    low, high = float(report.low_f), float(report.high_f)
    condition = str(report.condition)
    icon = '☔' if 'rain' in condition or 'drizzle' in condition else (
        '☀' if 'clear' in condition or 'sun' in condition else '☁')
    return ("<div class='mina-weather-card' role='group' aria-label='Today’s forecast'>"
            f"<span class='mina-weather-icon' aria-hidden='true'>{icon}</span>"
            "<span class='mina-weather-divider'></span>"
            f"<span class='mina-weather-temp'>High {high:g}°F</span>"
            f"<span class='mina-weather-text'>{escape(condition.capitalize())}</span>"
            "</div>"
            f"<div class='mina-weather-caption'>Today’s forecast · {escape(report.city)} · "
            f"Low {low:g}°F · Rain chance {int(report.rain_probability_pct)}% · "
            f"<a href='https://open-meteo.com/en/docs' target='_blank' rel='noopener noreferrer'>Open-Meteo</a></div>")


def safe_task_labels(tasks: list[dict]) -> list[tuple[str, str]]:
    """Plain text labels used only in native Streamlit widgets (not raw HTML)."""
    return [(task['id'], task['title'] + (f'  ·  {task["time"]}' if task['time'] else '')) for task in tasks]
