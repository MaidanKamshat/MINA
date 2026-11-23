"""MINA v2.12.5/2.12.6: deterministic post-route pickup-window safety check.

A *presentation/schedule guard*, not a claim that the v1.8
Coordinator/Planner/Critic enforced real-world calendar constraints.
Only parses explicitly shown school ETAs; never invents traffic or changes
route coordinates. Pure, no network, no writes, no sensitive location data.
"""
from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
from types import SimpleNamespace
import re

from mina_trip_voice_v212 import clock_minutes, normalize_clock

_SCHOOL_ETA_RE = re.compile(
    r"(?:pick\s+up\s+child\s+from\s+school|school\s+pickup)"
    r"\s*[—–-]\s*(?:estimated\s+arrival|ETA)\s*:?[ \t]*"
    r"(?P<eta>(?:1[0-2]|0?[1-9]):[0-5]\d\s*[AP]\.?M\.?)",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class PickupCheck:
    decision: str
    baseline_arrival: str | None
    scheduled_arrival: str | None
    earliest: str
    latest: str
    service_end: str | None
    hold_minutes: int | None
    duration_minutes: int


def _display(minutes: int) -> str:
    if not 0 <= minutes < 1440:
        raise ValueError('Schedule time outside the planning day')
    h24, m = divmod(minutes, 60)
    return f'{((h24 + 11) % 12) + 1}:{m:02d} {"AM" if h24 < 12 else "PM"}'


def check_pickup_window(answer: str, window: tuple[str, str], duration_minutes: int) -> PickupCheck:
    start, end = (clock_minutes(normalize_clock(x)) for x in window)
    if not 0 < duration_minutes <= 360 or not start < end:
        raise ValueError('Invalid school pickup schedule assumptions')
    match = _SCHOOL_ETA_RE.search(answer or '')
    arrival_text = normalize_clock(match['eta']) if match else None
    if not arrival_text:
        return PickupCheck('eta_not_available',None,None,window[0],window[1],None,None,duration_minutes)
    arrival = clock_minutes(arrival_text)
    if duration_minutes > end - start or arrival + duration_minutes > end:
        return PickupCheck('window_not_feasible',arrival_text,None,window[0],window[1],
                           _display(arrival+duration_minutes) if arrival+duration_minutes<1440 else None,
                           None,duration_minutes)
    hold = max(0, start - arrival)
    adjusted = max(start,arrival)
    return PickupCheck('retime_required' if hold else 'inside_window', arrival_text, _display(adjusted),
                       window[0],window[1],_display(adjusted+duration_minutes),hold,duration_minutes)


def _patched_result(result, **changes):
    if is_dataclass(result) and not isinstance(result,type):
        return replace(result,**changes)
    return SimpleNamespace(**{**vars(result),**changes})


_STOP_ETA_RE = re.compile(
    r"(?m)^\s*\d+\.\s+(?P<title>Buy groceries|Return library books|Pick up child from school)"
    r"\s*[—–-]\s*estimated arrival\s*:?[ \t]*"
    r"(?P<eta>(?:1[0-2]|0?[1-9]):[0-5]\d\s*[AP]\.?M\.?)",
    re.IGNORECASE,
)


def _scheduled_timeline(answer: str, *, hold_minutes: int, pickup_start: str,
                        pickup_end: str, departure_time: str | None,
                        durations: dict[str, int] | None,
                        shopping_label: str = 'Groceries') -> str | None:
    """Render a *proposed* itinerary from observed ETAs, never fabricate times.

    This does not update geometry or re-query traffic. When the backend text is
    incomplete/inconsistent, return None instead of constructing a fake schedule.
    """
    if not durations:
        return None
    matches = list(_STOP_ETA_RE.finditer(answer or ''))
    if len(matches) != 3:
        return None
    kinds = {'buy groceries': 'groceries', 'return library books': 'library',
             'pick up child from school': 'school_pickup'}
    tasks = [kinds[m['title'].lower()] for m in matches]
    if set(tasks) != {'groceries','library','school_pickup'} or tasks[-1] != 'school_pickup':
        return None
    raw_minutes = [clock_minutes(normalize_clock(m['eta'])) for m in matches]
    if not (raw_minutes[0] <= raw_minutes[1] <= raw_minutes[2]):
        return None
    lines = ['### Proposed afternoon schedule · provisional',
             '', 'These times are based on the original HeiGIT driving estimates, '
             '**not live traffic or verified school/store hours**.', '']
    if departure_time:
        lines += [f'- **{departure_time}** — Leave home (requested departure).']
    prev_end = None
    for kind,eta in zip(tasks[:-1],raw_minutes[:-1]):
        duration=durations.get(kind)
        if not isinstance(duration,int) or duration <= 0 or eta + duration >= 1440:
            return None
        if prev_end is not None and eta < prev_end:
            return None
        end=eta+duration
        label = shopping_label if kind == 'groceries' else 'Library'
        lines += [f'- **{_display(eta)}–{_display(end)}** — {label} '
                  f'({duration} minutes).']
        prev_end=end
    if prev_end is None or prev_end > raw_minutes[-1]:
        return None
    hold_start=prev_end
    hold_end=hold_start+hold_minutes
    if hold_end >= 1440 or hold_end > clock_minutes(pickup_start):
        return None
    if hold_minutes:
        lines += [f'- **{_display(hold_start)}–{_display(hold_end)}** — '
                  f'Flexible time after the final errand ({hold_minutes} extra minutes). '
                  'This is not an additional trip or a confirmed venue opening.']
    lines += [f'- **{pickup_start}** — Proposed arrival at school (estimated, after retiming).',
              f'- **{pickup_start}–{pickup_end}** — School pickup (user-supplied duration).',
              '', '**Important:** Departure on the last leg is shifted, but routing/traffic '
              'were **not recalculated** for that later time. The map shows only the '
              'original geographic route. Confirm school availability independently.']
    return '\n'.join(lines)


def apply_pickup_window_guard(result, *, window: tuple[str,str] | None,
                              duration_minutes: int, plan_date: str | None = None,
                              departure_time: str | None = None,
                              stop_durations: dict[str,int] | None = None,
                              shopping_label: str = "Groceries"):
    """Prepend a conservative timing assessment to a provisional route.

    Never upgrades an unverified backend estimate to verified. Fail closed if
    raw school arrival is missing or the estimated pickup cannot finish in time.
    """
    if not window or getattr(result,'status',None) != 'provisional_live_route_plan':
        return result
    summary = check_pickup_window(result.answer,window,duration_minutes)
    trace = list(result.trace or []) + [{
        'step':'pickup_window_guard', 'version':'2.12.6',
        'decision':summary.decision, 'raw_school_eta':summary.baseline_arrival,
        'target_arrival_window':list(window),
        'pickup_duration_minutes':duration_minutes,
        'flexible_delay_before_school_minutes':summary.hold_minutes,
        'proposed_arrival_after_retiming':summary.scheduled_arrival,
        'proposed_pickup_completion':summary.service_end,
        'source':'backend_raw_eta_and_user_constraints_only',
        'not_live_traffic':True,
    }]
    date_text = f' on {plan_date}' if plan_date else ''
    if summary.decision == 'retime_required':
        timeline = _scheduled_timeline(result.answer,
            hold_minutes=summary.hold_minutes,
            pickup_start=summary.scheduled_arrival,
            pickup_end=summary.service_end,
            departure_time=departure_time,
            durations=stop_durations,
            shopping_label=shopping_label)
        if timeline:
            trace[-1]['adjusted_timeline_shown'] = True
            note=(timeline + '\n\n---\n\n'
                  '**Original backend route ETAs — unadjusted (comparison only):**\n\n')
        else:
            trace[-1]['adjusted_timeline_shown'] = False
            note=(f'**School pickup timing — adjustment required{date_text} (provisional):** '
                  f'The unadjusted route reaches school at **{summary.baseline_arrival}**, '
                  f'earlier than your **{summary.earliest}–{summary.latest}** window. '
                  f'Leave **{summary.hold_minutes} extra minutes of flexible time after the final errand '
                  f'and before the school leg**, rather than arriving at school early. '
                  f'Using the same *unverified* driving estimate, your proposed school arrival would be '
                  f'**{summary.scheduled_arrival}**, followed by **{summary.duration_minutes} minutes** '
                  f'for pickup (until **{summary.service_end}**). '
                  f'This does **not** re-query traffic for the later departure or verify school rules. '
                  f'The route below shows the original, unadjusted ETAs.\n\n')
        return _patched_result(result,answer=note+result.answer,trace=trace)
    if summary.decision == 'inside_window':
        note=(f'**School pickup time-window check{date_text} (provisional):** '
              f'Estimated arrival **{summary.scheduled_arrival}**, '
              f'estimated pickup completion **{summary.service_end}**; '
              f'both fit the saved/user-supplied window **{summary.earliest}–{summary.latest}**. '
              f'No live traffic or school rules verified.\n\n')
        return _patched_result(result,answer=note+result.answer,trace=trace)
    if summary.decision == 'window_not_feasible':
        note=(f'**No feasible school pickup schedule under these estimates{date_text}.** '
              f'The calculated school arrival (**{summary.baseline_arrival}**) and '
              f'**{summary.duration_minutes}-minute pickup** cannot fit within your '
              f'**{summary.earliest}–{summary.latest}** window. '
              'The geographic route below is *not* a valid time-window plan. '
              'Change the departure time, shorten another stop, or choose a different route.\n\n'
              '**Geographic route only (timing rejected):**\n\n')
        return _patched_result(result,status='no_feasible_plan',answer=note+result.answer,trace=trace)
    note=(f'**School pickup timing could not be verified{date_text}.** '
          f'MINA could not read a school ETA from the returned itinerary, so '
          f'it cannot confirm your **{summary.earliest}–{summary.latest}** pickup window. '
          'The map is only a geographic preview; do not rely on these times.\n\n'
          '**Unvalidated route output:**\n\n')
    return _patched_result(result,status='needs_clarification',answer=note+result.answer,trace=trace)


def replace_legacy_route_map_caption(html: str) -> str:
    """Fix only outdated provider boilerplate when saved location provenance is known.

    Caller must first verify the trace says geocoded/confirmed Family Hub points.
    Does not imply that real-world venue hours or traffic are verified.
    """
    return re.sub(
        r'Public(?:\s|&nbsp;|&#32;)+demo(?:\s|&nbsp;|&#32;)+locations'
        r'(?:\s|&nbsp;|&#32;)+reconnected',
        'Route locations from Family Hub (not independently venue-verified)',
        html, flags=re.IGNORECASE)


# V2.12.7: For HTML map producers that append their visible legend via JS
# after Python has already replaced strings in the source HTML.
def repair_runtime_saved_map_legend(html: str) -> str:
    """Correct a stale demo caption only after the caller verifies saved-place provenance.

    The injected script edits text nodes in the rendered map, *not* markers,
    coordinates, routing data, school windows, or provider response fields.
    It supports captions created after the static HTML has loaded.
    """
    html = replace_legacy_route_map_caption(html)
    marker = 'mina-family-hub-map-legend-v2127'
    if marker in html:
        return html
    script = r'''<script id="mina-family-hub-map-legend-v2127">
(function () {
  "use strict";
  const oldCaption = /Public[\s\u00a0]+demo[\s\u00a0]+locations[\s\u00a0]+reconnected/gi;
  const newCaption = 'Route locations: Family Hub saved places (not independently venue-verified)';
  function updateDocument(doc) {
    if (!doc || !doc.body || !doc.createTreeWalker) return;
    const walker = doc.createTreeWalker(doc.body, 4 /* SHOW_TEXT */);
    const matches = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || /^(SCRIPT|STYLE|TEXTAREA)$/.test(parent.tagName)) continue;
      const value = node.nodeValue || '';
      oldCaption.lastIndex = 0;
      if (oldCaption.test(value)) matches.push(node);
    }
    for (const node of matches) {
      oldCaption.lastIndex = 0;
      node.nodeValue = node.nodeValue.replace(oldCaption, newCaption);
    }
    for (const frame of doc.querySelectorAll('iframe')) {
      try {
        if (frame.contentDocument) updateDocument(frame.contentDocument);
        if (!frame.dataset.minaLegendListener) {
          frame.dataset.minaLegendListener = '1';
          frame.addEventListener('load', () => {
            try { updateDocument(frame.contentDocument); } catch (_) { /* cross-origin */ }
          });
        }
      } catch (_) { /* cross-origin iframes are never modified */ }
    }
  }
  function update() { try { updateDocument(document); } catch (_) {} }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', update);
  else update();
  const observer = new MutationObserver(update);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
</script>'''
    # Append after the map HTML so that existing Leaflet/Folium initialization
    # executes unchanged. Streamlit components.html accepts complete documents.
    body_end = re.search(r'</body\s*>', html, flags=re.IGNORECASE)
    if body_end:
        return html[:body_end.start()] + '\n' + script + '\n' + html[body_end.start():]
    return html + '\n' + script
