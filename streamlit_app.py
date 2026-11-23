"""MINA v2.11 — exact voice shopping-list removal on top of v2.10.

Start: python -m streamlit run streamlit_app.py
Streamlit >=1.52 is required for st.chat_input(accept_audio=True).
The composer submits either typed text or microphone audio in one action;
voice is transcribed automatically on submission (no second review screen).
Google Calendar operations use explicit OAuth and individually approved event writes.
No raw audio is saved to disk.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4
from calendar import monthcalendar, monthrange
from types import SimpleNamespace
from dataclasses import replace
from contextlib import nullcontext
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from html import escape
from pathlib import Path
from time import perf_counter

import streamlit as st

from mina_calendar_v27 import (
    CalendarError, LOCAL_CALENDAR, load_calendar, save_calendar,
    make_event, add_event, add_note, agenda, reminder_dates,
    due_calendar_reminders, acknowledge_reminder, load_demo_birthdays,
    parse_voice_calendar, calendar_create_intent, calendar_read_intent, format_agenda, blank_calendar,
)
from mina_google_calendar import (
    GoogleCalendarError, CLIENT_FILE, TOKEN_FILE, connected_token_present,
    credentials as google_credentials, list_events as google_list_events,
    insert_event as google_insert_event,
)
from mina_multi_store_v210 import (
    MultiStoreParseError, STORE_LABELS, is_multi_store_add_request,
    prepare_multi_store_action, preview_multi_store_action,
    commit_multi_store_action, remove_one_local_item,
)
from mina_list_removal_v211 import (
    ListRemovalError, is_list_removal_request, prepare_remove_item_action,
    preview_remove_item_action, commit_remove_item_action,
)
from mina_audio import VoiceInputError, generate_spoken_reply, transcribe_wav
from mina_route_bridge_v212 import build_route_inputs, paired_backend_plan_date
from mina_time_window_planner_v213 import (
    plan_family_route, pickup_window_from_target, LiveRouteError,
)
from mina_route_schedule_v2125 import apply_pickup_window_guard, replace_legacy_route_map_caption, repair_runtime_saved_map_legend
from mina_route_geocode_v2123 import resolve_saved_route_points, SavedRouteLocationError
from mina_geocoding_consent_v2142 import (
    load_geocoding_consent, save_geocoding_consent, GeocodingConsentError,
)
from mina_route_pins_v2124 import (
    PIN_FILE as ROUTE_PIN_FILE, PIN_LABELS as ROUTE_PIN_LABELS,
    save_verified_pin, remove_pin, active_pin, saved_pin_state, RoutePinError,
)
from mina_trip_voice_v212 import TripParseError, classify_multi_stop_route
from mina_intent_reliability_v2131 import unsaved_named_stop, missing_departure_reply
from mina_reminders_v215 import (ReminderError, read as read_standalone_reminders,
    parse_create as parse_reminder_create, is_read as is_reminder_read,
    read_query as reminder_read_query, listing as standalone_reminder_listing,
    add as add_standalone_reminder, update as update_standalone_reminder,
    describe as describe_standalone_reminder)
from mina_memory_v215 import (MemoryErrorLocal, load_opt_in as load_memory_opt_in,
    set_opt_in as save_memory_opt_in, append_exchange as archive_exchange,
    recent_turns as memory_recent_turns, search_turns as memory_search_turns,
    memory_request, pin_fact as pin_memory_fact, facts as memory_facts,
    remove_fact as remove_memory_fact, erase_history as clear_saved_history,
    erase_all as clear_all_memory)
from mina_multiturn_v215 import handle as handle_extended_followup, VERSION as MULTITURN_VERSION
from mina_conversation_state_v214 import (
    VERSION as CONVERSATION_VERSION, create_pending_route, decide_followup,
    pending_route_caption,
)
from mina_dashboard import (
    DashboardInputError, add_session_task, dashboard_weather_html,
    demo_tasks, safe_task_labels, set_done,
)
from mina_live_tools import get_weather_report, LocationRequired, ToolUnavailable
from mina_chat_input import extract_chat_submission
from mina_family_hub import (
    LOCAL_DATA as HUB_FILE, STORES as HUB_STORES, PLACES as HUB_PLACES,
    FamilyHubError, load_hub, save_hub, add_item as hub_add_item,
    set_item_done as hub_set_done, update_place as hub_update_place,
    add_visit as hub_add_visit, matched_visit as hub_matched_visit,
    parse_pending_list_add, read_hub_intent, pending_items as hub_pending_items,
    list_answer as hub_list_answer, find_nearby_pairings, pairing_answer,
    needs_live_family_mode, potential_pairs, pairing_setup_guidance,
    set_preferences as hub_set_preferences,
)
from mina_followups import (
    LOCAL_FOLLOWUPS, load_followups, save_followups, blank_followups,
    acknowledge, record_visit, record_shopping, due_reminders, due_checkins,
    parse_purchased_all, clear_store_after_purchase,
    parse_yesterday_visit_status, parse_yesterday_shopping_status,
)
from mina_auto_mode import (
    auto_route, local_schedule_answer, time_window_advice,
    apply_local_action, is_explicit_local_confirmation,
)
from mina_ui_adapter import (
    UIInputError, UISettings, execute_ui_request, save_preview_map, status_caption,
)

ROOT = Path(__file__).resolve().parent
DEMO_SAVED_PLACES = ROOT / 'examples' / 'demo_saved_places_v1_8.json'
DEMO_TODAY_TASKS = ROOT / 'examples' / 'demo_today_tasks_v2_2.json'
PUBLIC_DEMO = {
    'start': '-78.85030,35.73260',
    'library': '-78.80320,35.77210',
    'groceries': '-78.78080,35.79150',
    'school_pickup': '-78.83010,35.75220',
}

st.set_page_config(
    page_title='MINA — My Intelligent Navigation Assistant',
    page_icon='✨', layout='wide', initial_sidebar_state='collapsed',
)

# MINA v2.1: warm burgundy / powder-blue editorial theme.
# Styling is isolated so the validated agent, tools and voice pipeline remain unchanged.
THEME_CSS = ROOT / 'mina_theme_v2_1.css'
st.markdown('<style>\n' + THEME_CSS.read_text(encoding='utf-8') + '\n</style>',
            unsafe_allow_html=True)
# v2.2 visual override follows v2.1 to preserve the tested voice/chat layer.
LANDING_CSS = ROOT / 'mina_theme_v2_2.css'
st.markdown('<style>\n' + LANDING_CSS.read_text(encoding='utf-8') + '\n</style>',
            unsafe_allow_html=True)
# v2.8: last stylesheet restores sidebar controls and refines the welcome page.
UI_V28_CSS = ROOT / 'mina_theme_v2_8.css'
st.markdown('<style>\n' + UI_V28_CSS.read_text(encoding='utf-8') + '\n</style>',
            unsafe_allow_html=True)
# v2.15.2: Match the original MINA heading accent exactly, rather than
# replacing the brand word with v2.15.1's hard-coded navy.
from mina_welcome_color_v2152 import original_brand_accent
_MINA_WELCOME_ORIGINAL_ACCENT = original_brand_accent((THEME_CSS, LANDING_CSS, UI_V28_CSS))
if _MINA_WELCOME_ORIGINAL_ACCENT:
    st.markdown('<style>:root { --mina-original-name-accent: '
                + _MINA_WELCOME_ORIGINAL_ACCENT + '; }</style>', unsafe_allow_html=True)
# v2.15.1 popovers and muted supporting letters are unchanged.
WELCOME_POLISH_CSS = ROOT / 'mina_welcome_polish_v2151.css'
st.markdown('<style>\n' + WELCOME_POLISH_CSS.read_text(encoding='utf-8') + '\n</style>',
            unsafe_allow_html=True)

@st.cache_data(ttl=900, max_entries=20, show_spinner=False)
def _cached_forecast(place: str):
    """Live Open-Meteo read cached for 15 min; never create synthetic weather."""
    return get_weather_report(place, day='today')


if 'mina_chat_messages' not in st.session_state:
    st.session_state['mina_chat_messages'] = []
if 'mina_chat_seq' not in st.session_state:
    st.session_state['mina_chat_seq'] = 0
# Only the current browser's Streamlit session, never a local/remote file.
if 'mina_pending_route' not in st.session_state:
    st.session_state['mina_pending_route'] = None
if 'mina_pending_task_v215' not in st.session_state:
    st.session_state['mina_pending_task_v215'] = None
if 'mina_memory_session_v215' not in st.session_state:
    st.session_state['mina_memory_session_v215'] = str(uuid4())
if 'mina_memory_opt_in' not in st.session_state:
    try:
        st.session_state['mina_memory_opt_in'] = load_memory_opt_in()
        st.session_state['mina_memory_error'] = ''
    except MemoryErrorLocal as exc:
        st.session_state['mina_memory_opt_in'] = False
        st.session_state['mina_memory_error'] = str(exc)
if 'mina_reminders_error' not in st.session_state:
    st.session_state['mina_reminders_error'] = ''
if 'mina_show_landing' not in st.session_state:
    st.session_state['mina_show_landing'] = True
if 'mina_info_section' not in st.session_state:
    st.session_state['mina_info_section'] = ''
if 'mina_dashboard_tasks' not in st.session_state:
    st.session_state['mina_dashboard_tasks'] = demo_tasks(DEMO_TODAY_TASKS)
if 'mina_dashboard_is_demo' not in st.session_state:
    st.session_state['mina_dashboard_is_demo'] = True
if 'mina_task_seq' not in st.session_state:
    st.session_state['mina_task_seq'] = 0
if 'mina_family_hub' not in st.session_state:
    try:
        st.session_state['mina_family_hub'] = load_hub(HUB_FILE)
        st.session_state['mina_hub_loading_error'] = ''
    except FamilyHubError as exc:
        st.session_state['mina_family_hub'] = None
        st.session_state['mina_hub_loading_error'] = str(exc)
if 'mina_followups' not in st.session_state:
    try:
        st.session_state['mina_followups'] = load_followups(LOCAL_FOLLOWUPS)
        st.session_state['mina_followups_error'] = ''
    except FamilyHubError as exc:
        st.session_state['mina_followups'] = None
        st.session_state['mina_followups_error'] = str(exc)
if 'mina_next_visit_prompt' not in st.session_state:
    st.session_state['mina_next_visit_prompt'] = ''
if 'mina_hub_address_consent' not in st.session_state:
    try:
        st.session_state['mina_hub_address_consent'] = load_geocoding_consent()
        st.session_state['mina_geocoding_consent_error'] = ''
    except GeocodingConsentError as exc:
        st.session_state['mina_hub_address_consent'] = False  # fail closed
        st.session_state['mina_geocoding_consent_error'] = str(exc)
if 'mina_calendar_data' not in st.session_state:
    try:
        st.session_state['mina_calendar_data'] = load_calendar(LOCAL_CALENDAR)
        st.session_state['mina_calendar_error'] = ''
    except CalendarError as exc:
        st.session_state['mina_calendar_data'] = None
        st.session_state['mina_calendar_error'] = str(exc)
if 'mina_google_read_events' not in st.session_state:
    st.session_state['mina_google_read_events'] = []
if 'mina_calendar_sync' not in st.session_state:
    st.session_state['mina_calendar_sync'] = True
if 'mina_calendar_month' not in st.session_state:
    st.session_state['mina_calendar_month'] = date.today().strftime('%Y-%m')
if 'mina_settings_view' not in st.session_state:
    st.session_state['mina_settings_view'] = False


def _save_memory_preference_v215() -> None:
    try:
        save_memory_opt_in(bool(st.session_state['mina_memory_opt_in']))
        st.session_state['mina_memory_error'] = ''
    except (MemoryErrorLocal, OSError) as exc:
        st.session_state['mina_memory_opt_in'] = False
        st.session_state['mina_memory_error'] = str(exc)


def _archive_exchange_v215(user: str, assistant: str) -> None:
    if not st.session_state.get('mina_memory_opt_in'):
        return
    try:
        archive_exchange(st.session_state['mina_memory_session_v215'], user, assistant)
    except (MemoryErrorLocal, OSError, ValueError) as exc:
        st.session_state['mina_memory_error'] = 'Unable to save this conversation turn locally.'


def _save_geocoding_consent_setting() -> None:
    """Persist the user's explicit toggle; do not send network requests."""
    try:
        save_geocoding_consent(bool(st.session_state['mina_hub_address_consent']))
        st.session_state['mina_geocoding_consent_error'] = ''
    except GeocodingConsentError as exc:
        # Never keep a failed-to-persist grant active in the session.
        st.session_state['mina_hub_address_consent'] = False
        st.session_state['mina_geocoding_consent_error'] = str(exc)


def _store_local_hub(updated: dict) -> None:
    save_hub(updated, HUB_FILE)
    st.session_state['mina_family_hub'] = updated


def _apply_hub_action(current: dict, action: dict) -> dict:
    # Multi-store updates stage every item on a copy; persist exactly once only
    # after an explicit separate user approval (button or voice confirmation).
    if action.get('kind') == 'multi_list':
        return commit_multi_store_action(current, action, hub_add_item)
    if action.get('kind') == 'remove_item':
        return commit_remove_item_action(current, action)
    return apply_local_action(current, action)


def _status_caption_v210(status: str) -> str:
    if status == 'local_update_completed':
        return 'Confirmed local update · not an external write'
    return status_caption(status)


def _store_followups(updated: dict) -> None:
    save_followups(updated, LOCAL_FOLLOWUPS)
    st.session_state['mina_followups'] = updated


def _store_calendar(updated: dict) -> None:
    save_calendar(updated, LOCAL_CALENDAR)
    st.session_state['mina_calendar_data'] = updated


def _commit_calendar_action(action: dict, *, google_sync: bool, tz_name: str) -> str:
    """Called only by a specific confirm button or explicit voice confirmation."""
    current = st.session_state.get('mina_calendar_data')
    if current is None:
        raise CalendarError('Local calendar is unavailable. Please repair it before adding entries.')
    if action.get('kind') == 'note':
        _store_calendar(add_note(current, action['content']))
        return f'Saved to **MINA Notes**: {action["content"]}. No Google event was created.'
    if action.get('kind') != 'event':
        raise CalendarError('Unknown calendar action.')
    event = action['event']
    if any(x['id'] == event['id'] for x in current['events']):
        raise CalendarError('This event was already saved; not creating a duplicate.')
    _store_calendar(add_event(current, event))  # durable local-first; safe if Google is offline
    notice = [f'**Saved:** {event["title"]} · {event["date"]} at {event["time"]}.']
    dates = reminder_dates(event, tz_name=tz_name)
    notice.append('**Reminders:** ' + dates['24h'].strftime('%B %d, %Y at %I:%M %p')
                  + ' and ' + dates['2h'].strftime('%B %d, %Y at %I:%M %p') + '.')
    if not event['end_time']:
        notice.append('End time was not provided. A Google event will use an **assumed 60-minute duration**; edit it if needed.')
    if event['kind'] == 'birthday':
        notice.append('Birthday repeats **every year** (9:00 AM reminder anchor).')
    if event['source'] == 'demo':
        notice.append('**DEMO ONLY:** not uploaded to Google.')
    elif google_sync and connected_token_present():
        try:
            result = google_insert_event(event, tz_name=tz_name)
            fresh = st.session_state['mina_calendar_data']
            _store_calendar(__import__('mina_calendar_v27').update_google_status(fresh, event['id'], result['id'], 'synced'))
            notice.append('**Google Calendar: event created** with 24-hour and 2-hour popup reminders.')
            if result.get('htmlLink'):
                notice.append('[Open event in Google Calendar](' + result['htmlLink'] + ')')
        except (GoogleCalendarError, CalendarError) as exc:
            fresh = st.session_state['mina_calendar_data']
            _store_calendar(__import__('mina_calendar_v27').update_google_status(fresh, event['id'], '', 'failed'))
            notice.append('**Google sync failed:** locally saved, but Google confirmation is NOT available. Check Google Calendar before attempting to add this event again. ' + str(exc))
    else:
        notice.append('**Saved locally only.** Connect Google Calendar in Settings to save future approved events there.')
    # Preserve the older Family Hub pairing planner for dentist/pediatrician visits.
    if event['kind'] == 'appointment':
        place = 'dentist' if 'dentist' in event['title'].lower() else ('pediatrician' if 'pediatrician' in event['title'].lower() else None)
        hub = st.session_state.get('mina_family_hub')
        if place and hub is not None:
            matched = any(v['place'] == place and v['date'] == event['date'] and v['time'] == event['time'] for v in hub['visits'])
            if not matched:
                try:
                    _store_local_hub(hub_add_visit(hub, place_id=place, day=event['date'], time=event['time'], end_time=event['end_time'], title=event['title']))
                except FamilyHubError:
                    notice.append('Family Hub pairing note could not be added; the MINA calendar entry is saved.')
    return '\n\n'.join(notice)


def _calendar_preview(action: dict, tz_name: str) -> str:
    if action['kind'] == 'note':
        return f'**Proposed MINA note:** {action["content"]}\n\nConfirm to save locally.'
    e = action['event']
    ts = reminder_dates(e, tz_name=tz_name)
    prefix = '**Proposed birthday (yearly)**' if e['kind']=='birthday' else '**Proposed calendar event**'
    tail = ('\n\nEnd time not supplied: Google Calendar will show **60 minutes (assumed)**.' if not e['end_time'] else f'\n\nEnds at **{e["end_time"]}**.')
    return (f'{prefix}: {e["title"]}\n\n**Date:** {e["date"]} · **Start:** {e["time"]}'
            + tail + '\n\n**Reminder 1:** ' + ts['24h'].strftime('%B %d · %I:%M %p')
            + '\n\n**Reminder 2:** ' + ts['2h'].strftime('%B %d · %I:%M %p')
            + '\n\n**Not saved yet.** Confirm below. If Google is connected and sync is enabled, confirmation will also create the Google Calendar event.')


def _queue_calendar_action(action: dict, tz_name: str) -> None:
    st.session_state['mina_chat_seq'] += 1
    seq = st.session_state['mina_chat_seq']
    st.session_state['mina_chat_messages'].append({'role':'assistant','seq':seq,
        'text':_calendar_preview(action, tz_name),'status':'calendar_confirmation_required',
        'latency_ms':0,'map_path':None,'trace':[{'step':'calendar_preview','no_write':True}],
        'candidates':[],'voice_bytes':None,'pending_calendar_action':action,
        'calendar_action_completed':False})
    st.session_state['mina_show_landing'] = False


def _calendar_read_reply(intent: tuple, now: datetime) -> str:
    data = st.session_state.get('mina_calendar_data')
    if data is None: return 'Cannot read your local calendar; please repair the file in Settings.'
    typ, day = intent
    if typ == 'notes':
        return ('**Saved MINA Notes:**\n' + '\n'.join('- '+n['content'] for n in data['notes'][-15:])
                if data['notes'] else 'No local notes saved yet.')
    answer = format_agenda(data, day=day, now=now.date())
    hub = st.session_state.get('mina_family_hub')
    if hub:
        local_visits = [v for v in hub['visits'] if v['date'] >= now.date().isoformat() and (not day or v['date'] == day.isoformat())]
        if local_visits:
            answer += '\n\n**Older Family Hub visits (local):**\n' + '\n'.join(f'- {v["date"]} · {v["time"]} · {v["title"]}' for v in local_visits[:10])
    if connected_token_present():
        try:
            remote = google_list_events(days=max(60, min(365, (day - now.date()).days + 2)) if day else 60, tz_name=str(now.tzinfo), now=now)
            if day:
                remote = [v for v in remote if v['start'][:10] == day.isoformat()]
            answer += ('\n\n**Google Calendar (live):**\n' + '\n'.join(f'- {v["start"]} · {v["title"]}' for v in remote[:15])
                       if remote else '\n\nGoogle Calendar: no events found in the next 60 days.')
        except GoogleCalendarError as exc:
            answer += '\n\nGoogle Calendar could not be checked: ' + str(exc)
    else:
        answer += '\n\nGoogle Calendar is not connected; this is only your MINA local schedule.'
    return answer


def _mark_hub_done(store_id: str, item_id: str) -> None:
    key = f'mina_hub_item_{store_id}_{item_id}'
    updated = hub_set_done(st.session_state['mina_family_hub'], store_id, item_id,
                           bool(st.session_state[key]))
    _store_local_hub(updated)


def _toggle_dashboard_task(task_id: str) -> None:
    key = f'mina_dashboard_done_{task_id}'
    st.session_state['mina_dashboard_tasks'] = set_done(
        st.session_state['mina_dashboard_tasks'], task_id, bool(st.session_state[key])
    )

def _render_settings_controls() -> SimpleNamespace:
    st.header('MINA · Settings')
    st.caption('Settings are optional. The main screen stays focused on your conversation.')
    with st.expander('📅 Google Calendar & Notes', expanded=bool(st.session_state.get('mina_settings_view'))):
        st.caption('Events, appointments and birthdays can be saved in MINA. For phone notifications, connect Google Calendar.')
        if st.session_state.get('mina_calendar_error'):
            st.error('Local calendar unavailable: ' + st.session_state['mina_calendar_error'])
        else:
            entries = st.session_state['mina_calendar_data']
            st.caption(f"Saved locally: {len(entries['events'])} events · {len(entries['notes'])} notes")
        if CLIENT_FILE.exists():
            st.caption('Google OAuth client configuration found on this Mac.')
        else:
            st.warning('Google OAuth not configured. See README: Google Cloud → Calendar API → OAuth Desktop app, then save JSON to local_data/google_oauth_client.json.')
        if connected_token_present():
            st.caption('Google token stored locally (validity not yet verified).')
        if st.button('Connect / reconnect Google Calendar', key='mina_google_oauth'):
            try:
                google_credentials(allow_interactive=True)
                st.success('Google Calendar authorized. Test access with Refresh Google events.')
            except GoogleCalendarError as exc:
                st.warning(str(exc))
        google_sync = st.checkbox('Save confirmed calendar events to Google when connected',
                                  key='mina_calendar_sync')
        if st.button('Refresh Google events', key='mina_google_refresh'):
            try:
                st.session_state['mina_google_read_events'] = google_list_events(tz_name='America/New_York')
                st.success('Google Calendar events refreshed (next 60 days).')
            except GoogleCalendarError as exc:
                st.warning(str(exc))
        for e in st.session_state.get('mina_google_read_events', [])[:6]:
            st.caption(f"{e['start'][:16]} · {e['title']}")
        if st.button('Load 7 FICTIONAL demo birthdays into MINA only', key='mina_load_demo_birthdays'):
            try:
                _store_calendar(load_demo_birthdays(st.session_state['mina_calendar_data']))
                st.success('Seven fictional recurring birthdays saved locally. None sent to Google.')
                st.rerun()
            except CalendarError as exc:
                st.warning(str(exc))
        st.caption('These local files survive patch upgrades and must never be published to GitHub.')
    view_mode = st.radio('Mode', ['Auto (recommended)', 'Assistant', 'Directions', 'Family planner'], index=0)
    mode = {'Auto (recommended)': 'auto', 'Assistant': 'assistant', 'Directions': 'directions', 'Family planner': 'family_plan'}[view_mode]
    if mode == 'auto':
        st.caption('MINA chooses a tool from your request automatically. Advanced routing data is only needed for a real multi-stop map.')
    city = st.text_input('Forecast city', value='Apex, NC',
                         help='MINA does not read your GPS position.')
    timezone_name = st.text_input('Time zone', value='America/New_York')
    use_rag = st.checkbox('Use synthetic family-note RAG', value=False)
    planner_choice = st.selectbox('Planner', ['LLM + Critic', 'Deterministic + Critic'])
    planner_mode = 'llm' if planner_choice.startswith('LLM') else 'deterministic'
    auto_voice = st.checkbox('Speak replies after voice requests (paid TTS)', value=True)
    voice = st.selectbox('Voice', ['coral', 'alloy', 'sage', 'nova', 'shimmer'])
    with st.expander('📝 Add an event or note', expanded=False):
        st.caption('All entries require a separate confirmation before saving.')
        with st.form('mina_calendar_event_form',clear_on_submit=False):
            event_title = st.text_input('Event title', placeholder='Dentist appointment')
            event_kind = st.selectbox('Event type', ['appointment','event','birthday'])
            event_day = st.date_input('Event date', value=date.today(), key='mina_cal_event_date')
            event_at = st.text_input('Start time (AM/PM)', value='11:30 AM')
            event_end = st.text_input('End time (optional; AM/PM)', placeholder='1:00 PM')
            event_notes = st.text_area('Notes (optional)',height=75)
            event_add_pressed = st.form_submit_button('Review event & reminders')
        if event_add_pressed:
            try:
                ev = make_event(event_title,event_day,event_at,event_end,
                   kind=event_kind,repeat='yearly' if event_kind=='birthday' else 'none',notes=event_notes)
                _queue_calendar_action({'kind':'event','event':ev},timezone_name)
                st.rerun()
            except (CalendarError, ValueError) as exc:
                st.warning(str(exc))
        with st.form('mina_calendar_note_form',clear_on_submit=True):
            memo = st.text_area('Quick note',height=70,placeholder='Bring insurance card')
            note_add_pressed = st.form_submit_button('Review note')
        if note_add_pressed:
            try:
                if len(memo.strip())<3: raise CalendarError('Write a note before saving.')
                _queue_calendar_action({'kind':'note','content':memo.strip()},timezone_name)
                st.rerun()
            except CalendarError as exc: st.warning(str(exc))

    origin = ''
    destination = ''
    via: tuple[str, ...] = ()
    task_locations: dict[str, str] = {}
    durations: dict[str, int] = {}
    start_time = '10:00 AM'
    saved_places_file = ''
    plan_date = ''
    travel_buffer = 10
    confirm_schedule = True

    if mode == 'directions':
        st.divider()
        st.subheader('Directions · Public demo locations')
        origin = st.text_input('Origin (longitude,latitude or public address)')
        destination = st.text_input('Destination')
        via_lines = st.text_area('Via stops (max 3, one per line)', height=85)
        via = tuple(x.strip() for x in via_lines.splitlines() if x.strip())
        st.caption('Coordinates are sent to HeiGIT. Estimated road durations exclude traffic.')
    elif mode in {'family_plan', 'auto'}:
        with (st.expander('Advanced route settings · only needed for live multi-stop planning', expanded=False)
              if mode == 'auto' else nullcontext()):
            st.divider()
            st.subheader('Live multi-stop route inputs' if mode == 'auto' else 'Family planner · Demo assumptions')
            if mode == 'auto':
                st.caption('Only used when Auto detects multi-stop planning. Enter your own locations or explicitly opt into the public demo points.')
                use_public_demo_route = st.checkbox('Use PUBLIC DEMO route locations (not real addresses)', value=False)
            else:
                use_public_demo_route = True
            selected_tasks = st.multiselect(
                'Errands', ['library', 'groceries', 'school_pickup'],
                default=['library', 'groceries', 'school_pickup'],
            )
            origin = st.text_input('Start location', value=PUBLIC_DEMO['start'] if use_public_demo_route else '')
            for task in selected_tasks:
                task_locations[task] = st.text_input(
                    f'{task} location', value=PUBLIC_DEMO[task] if use_public_demo_route else '', key=f'mina_place_{task}',
                )
                durations[task] = int(st.number_input(
                    f'{task} duration (minutes)', min_value=1, max_value=360,
                    value={'library': 15, 'groceries': 60, 'school_pickup': 10}[task],
                    key=f'mina_duration_{task}',
                ))
            start_time = st.text_input('Start time (AM/PM)', value='10:00 AM')
            plan_date = st.date_input('Plan date', value=date.today()).isoformat()
            travel_buffer = int(st.number_input('Travel buffer (minutes per leg)',
                                                min_value=0, max_value=120, value=10))
            use_saved = st.checkbox('Use demo Saved Places (unverified hours)', value=(mode == 'family_plan' and use_public_demo_route))
            if use_saved:
                saved_places_file = st.text_input('Local Saved Places JSON', value=str(DEMO_SAVED_PLACES))
            confirm_schedule = st.checkbox('I reviewed the locations, durations and hours', value=False)
            if not confirm_schedule:
                st.caption('Confirm these demo assumptions before submitting a family plan.')
    st.divider()
    with st.expander('🛒 Family Hub · Lists, places and visits', expanded=False):
        st.caption('Locally saved, independent of Google Calendar. Addresses and visits remain '
                   'in a gitignored file on this Mac. Confirm before sharing an address with HeiGIT.')
        if st.session_state.get('mina_hub_loading_error'):
            st.error('Saved Hub JSON needs repair: ' + st.session_state['mina_hub_loading_error'])
        else:
            hub = st.session_state['mina_family_hub']
            st.markdown('**Shopping lists**')
            store_id = st.selectbox('Store', list(HUB_STORES),
                                    format_func=lambda key: HUB_STORES[key], key='mina_hub_store')
            items = hub['stores'][store_id]
            if not items:
                st.caption('No items yet.')
            for item in items:
                st.checkbox(item['name'], value=item['done'],
                            key=f'mina_hub_item_{store_id}_{item["id"]}',
                            on_change=_mark_hub_done, args=(store_id, item['id']))
            with st.form('mina_hub_add_item', clear_on_submit=True):
                item_name = st.text_input('New shopping item', placeholder='Milk')
                add_shopping_pressed = st.form_submit_button('Add to selected store list')
            if add_shopping_pressed:
                try:
                    _store_local_hub(hub_add_item(hub, store_id, item_name))
                    st.rerun()
                except FamilyHubError as exc:
                    st.warning(str(exc))

            # An item can be removed without editing local_data JSON manually.
            # Deliberate two-step confirmation; delete exactly one item ID.
            if items:
                with st.expander('Remove one shopping item', expanded=False):
                    item_ids = [it['id'] for it in items]
                    label_map = {it['id']: it['name'] for it in items}
                    with st.form(f'mina_remove_item_{store_id}'):
                        chosen_id = st.selectbox('Item to remove', item_ids,
                            format_func=lambda x: label_map.get(x, 'Unknown item'))
                        agreed = st.checkbox('I confirm I want to remove this one item from this list')
                        remove_pressed = st.form_submit_button('Remove selected item')
                    if remove_pressed:
                        if not agreed:
                            st.warning('Check the confirmation box before removing an item.')
                        else:
                            try:
                                updated = remove_one_local_item(hub, store_id, chosen_id)
                                _store_local_hub(updated)
                                st.rerun()
                            except (MultiStoreParseError, FamilyHubError) as exc:
                                st.warning(f'Could not remove item: {exc}')

            st.divider()
            st.markdown('**Saved Places**')
            place_id = st.selectbox('Location', list(HUB_PLACES),
                                    format_func=lambda key: HUB_PLACES[key], key='mina_hub_place')
            place = hub['places'][place_id]
            with st.form('mina_hub_edit_place'):
                place_name = st.text_input('Place name', value=place['name'],
                                           key=f'mina_hub_name_{place_id}')
                place_address = st.text_input('Public/store/clinic address (full address + city)',
                                              value=place['address'], key=f'mina_hub_address_{place_id}')
                place_notes = st.text_area('Optional notes', value=place['notes'],
                                            key=f'mina_hub_notes_{place_id}', height=65)
                save_place_pressed = st.form_submit_button('Save this place locally')
            if save_place_pressed:
                try:
                    _store_local_hub(hub_update_place(
                        hub, place_id, name=place_name, address=place_address, notes=place_notes))
                    st.success('Saved locally — not shared with a map provider.')
                except FamilyHubError as exc:
                    st.warning(str(exc))

            st.divider()
            st.markdown('**Appointments and library visits**')
            with st.form('mina_hub_visit_form', clear_on_submit=False):
                visit_place = st.selectbox('Visit location', ['dentist', 'pediatrician', 'library'],
                                            format_func=lambda k: HUB_PLACES[k])
                visit_day = st.date_input('Visit date', value=date.today(), key='mina_hub_visit_date')
                visit_time = st.text_input('Visit time (AM/PM)', value='3:15 PM')
                visit_end_time = st.text_input('Optional visit end time (AM/PM)', placeholder='1:00 PM')
                visit_title = st.text_input('Visit label (no patient details)', value='Appointment')
                add_visit_pressed = st.form_submit_button('Save visit locally')
            if add_visit_pressed:
                try:
                    _store_local_hub(hub_add_visit(hub, place_id=visit_place,
                                                   day=visit_day.isoformat(), time=visit_time,
                                                   title=visit_title, end_time=visit_end_time))
                    st.success('Visit saved locally; no calendar event created.')
                except FamilyHubError as exc:
                    st.warning(str(exc))
            upcoming = [v for v in hub_matched_visit(hub) if v['date'] >= date.today().isoformat()]
            for visit in upcoming[:5]:
                st.caption(f'{visit["date"]} · {visit["time"]}'
                           f'{"–" + visit["end_time"] if visit.get("end_time") else ""} · '
                           f'{HUB_PLACES[visit["place"]]} · {visit["title"]}')
            st.divider()
            st.markdown('**Family schedule preferences (user-provided)**')
            pref = hub.get('preferences') or {}
            with st.form('mina_hub_schedule_preferences'):
                pref_pickup = st.text_input('School pickup target (AM/PM)',
                    value=pref.get('pickup_time', ''), placeholder='3:15 PM')
                pref_school = st.text_input('School address for route comparison',
                    value=pref.get('school_address', ''), placeholder='Public school address, city, state')
                pref_home = st.text_input('Optional route origin address',
                    value=pref.get('home_address', ''), placeholder='Saved privately on this Mac')
                pref_shop = st.number_input('Shopping duration (minutes)', min_value=0, max_value=180,
                    value=pref.get('shopping_minutes', 45), step=5)
                pref_lunch = st.number_input('Lunch duration (minutes)', min_value=0, max_value=180,
                    value=pref.get('lunch_minutes', 45), step=5)
                pref_buffer = st.number_input('Safety buffer (minutes)', min_value=0, max_value=180,
                    value=pref.get('buffer_minutes', 15), step=5)
                pref_library = st.number_input('Time at library (minutes)', min_value=1, max_value=180,
                    value=pref.get('library_minutes', 15), step=5)
                pref_pickup_duration = st.number_input('Time needed for pickup (minutes)',
                    min_value=1, max_value=180, value=pref.get('pickup_minutes', 10), step=5)
                pref_library_open = st.text_input('Library opening time, if verified (AM/PM)',
                    value=pref.get('library_open_time', ''), placeholder='12:00 PM')
                save_pref = st.form_submit_button('Save schedule preferences locally')
            if save_pref:
                try:
                    _store_local_hub(hub_set_preferences(hub, pickup_time=pref_pickup,
                        school_address=pref_school, home_address=pref_home,
                        shopping_minutes=int(pref_shop), lunch_minutes=int(pref_lunch),
                        buffer_minutes=int(pref_buffer), library_minutes=int(pref_library),
                        pickup_minutes=int(pref_pickup_duration), library_open_time=pref_library_open))
                    st.success('Saved locally. These are your notes, not calendar verification.')
                except FamilyHubError as exc:
                    st.warning(str(exc))
            st.divider()
            with st.expander('Private route pins · if an address cannot be located', expanded=False):
                st.caption('One-time fallback for a real saved location that Census/Photon cannot match. '
                           'In Google Maps, find the correct building, right-click its entrance and '
                           'choose What’s here? Copy the two coordinates (latitude, longitude). '
                           'Verify the pin is exactly where you want to arrive. '
                           'Coordinates stay in a private local file; they are sent to HeiGIT for routing.')
                pin_key = st.selectbox('Place to verify on a map',
                    list(ROUTE_PIN_LABELS),format_func=lambda k: ROUTE_PIN_LABELS[k],
                    key='mina_route_pin_selected')
                pin_current = st.session_state.get('mina_family_hub') or hub
                pin_prefs = (pin_current.get('preferences') or {})
                pin_places = (pin_current.get('places') or {})
                pin_address = ((pin_prefs.get('home_address') if pin_key=='home'
                    else pin_prefs.get('school_address') if pin_key=='school_pickup'
                    else (pin_places.get(pin_key) or {}).get('address')) or '').strip()
                try:
                    pin_status = saved_pin_state(pin_key, pin_address,path=ROUTE_PIN_FILE)
                    if pin_status=='active':
                        st.caption('A verified private pin is saved for this unchanged address.')
                    elif pin_status=='stale':
                        st.warning('The saved address changed. The older pin will not be used; verify a new one.')
                except RoutePinError as exc:
                    st.warning(str(exc))
                with st.form('mina_route_pin_form',clear_on_submit=True):
                    pin_coordinates=st.text_input('Verified coordinates · latitude, longitude',
                        placeholder='35.7, -78.8')
                    save_pin_pressed=st.form_submit_button('Save verified route pin locally')
                if save_pin_pressed:
                    try:
                        save_verified_pin(pin_key, pin_address, pin_coordinates,path=ROUTE_PIN_FILE)
                        st.success('Verified pin saved privately for this address. It will be used on future routes.')
                    except RoutePinError as exc:
                        st.warning(str(exc))
                if st.button('Remove saved pin for this location',key='mina_route_pin_delete'):
                    try:
                        remove_pin(pin_key,path=ROUTE_PIN_FILE)
                        st.success('Private route pin removed.')
                    except RoutePinError as exc:
                        st.warning(str(exc))
            st.divider()
            st.caption('Suggested pairs: Library + Costco · Dentist + Target · '
                       'Pediatrician + Trader Joe’s. Actual closeness must be checked using routes.')
            st.checkbox('Allow public geocoding (US Census / Photon) and HeiGIT routing for saved addresses',
                        help=('Opt in to external routing. Route requests may send saved home, school, shop and '
                              'clinic addresses to Census/Photon for geocoding, and coordinates to HeiGIT. '
                              'Your choice is saved locally on this Mac until you turn it off. '
                              'Opening MINA alone never starts a route request.'),
                        key='mina_hub_address_consent', on_change=_save_geocoding_consent_setting)
            st.caption('Permission is remembered on this Mac, including across app restarts and updates. '
                       'Turn it off here any time; this does not retract previously sent requests. '
                       'MINA does not run geocoding just because the setting is on.')
            if st.session_state.get('mina_geocoding_consent_error'):
                st.warning(st.session_state['mina_geocoding_consent_error'])
            st.caption('Ask MINA: “What shopping can I combine with my dentist appointment?” '
                       'or “What is on my Target shopping list?”')

    st.divider()
    st.subheader('Today’s plan · local session only')
    st.caption('Tasks in this dashboard are not connected to Google Calendar. '
               'Sample tasks are clearly labelled and are not real appointments.')
    with st.form('mina_add_task_form', clear_on_submit=True):
        new_title = st.text_input('Task name', placeholder='Return library books')
        new_time = st.text_input('Optional time (AM/PM)', placeholder='3:15 PM')
        add_pressed = st.form_submit_button('Add task')
    if add_pressed:
        try:
            current = ([] if st.session_state['mina_dashboard_is_demo']
                       else st.session_state['mina_dashboard_tasks'])
            next_seq = st.session_state['mina_task_seq'] + 1
            st.session_state['mina_dashboard_tasks'] = add_session_task(
                current, new_title, new_time, next_seq)
            st.session_state['mina_task_seq'] = next_seq
            st.session_state['mina_dashboard_is_demo'] = False
            st.success('Added to this browser session only.')
        except DashboardInputError as exc:
            st.warning(str(exc))
    if st.button('Restore demo tasks', key='mina_restore_demo_tasks'):
        st.session_state['mina_dashboard_tasks'] = demo_tasks(DEMO_TODAY_TASKS)
        st.session_state['mina_dashboard_is_demo'] = True
        st.rerun()
    st.divider()
    with st.expander('🔔 Standalone Reminders · separate from Calendar', expanded=False):
        st.caption('Local reminders persist on this Mac. They are NOT Google Calendar events and cannot send push notifications while MINA is closed.')
        with st.form('mina_reminders_form_v215'):
            reminder_title = st.text_input('Reminder', placeholder='Return library books', key='mina_reminder_title_v215')
            reminder_day = st.date_input('Reminder date', value=date.today(), key='mina_reminder_date_v215')
            reminder_clock = st.text_input('Reminder time (AM/PM)', value='9:00 AM', key='mina_reminder_time_v215')
            review_reminder = st.form_submit_button('Review standalone reminder')
        if review_reminder:
            try:
                proposed = parse_reminder_create(
                    f'Remind me on {reminder_day.strftime("%B %d, %Y")} at {reminder_clock} to {reminder_title}',
                    today=date.today(), timezone_name=timezone_name)
                st.session_state['mina_settings_pending_reminder_v215'] = {'kind':'create','action':proposed}
            except ReminderError as exc:
                st.warning(str(exc))
        ui_pending = st.session_state.get('mina_settings_pending_reminder_v215')
        if ui_pending:
            if ui_pending['kind'] == 'create':
                st.info('Preview: ' + describe_standalone_reminder(ui_pending['action']))
            else:
                st.info(f"Review: {ui_pending['kind']} the selected reminder? No change yet.")
            yes, no = st.columns(2)
            with yes:
                if st.button('Confirm reminder change', key='mina_reminder_ui_confirm_v215'):
                    try:
                        if ui_pending['kind'] == 'create': add_standalone_reminder(ui_pending['action'])
                        else: update_standalone_reminder(ui_pending['id'],ui_pending['kind'])
                        st.session_state['mina_settings_pending_reminder_v215'] = None
                        st.success('Standalone reminder saved locally.')
                        st.rerun()
                    except (ReminderError, OSError, ValueError) as exc: st.warning(str(exc))
            with no:
                if st.button('Cancel reminder change',key='mina_reminder_ui_cancel_v215'):
                    st.session_state['mina_settings_pending_reminder_v215'] = None
                    st.rerun()
        try:
            current_reminders = standalone_reminder_listing()
            if not current_reminders: st.caption('No standalone reminders yet.')
            for item in current_reminders[:25]:
                st.markdown(('✅ ' if item['done'] else '⏰ ') + describe_standalone_reminder(item))
                b1,b2=st.columns(2)
                with b1:
                    if not item['done'] and st.button('Mark done',key='mina_done_'+item['id']):
                        st.session_state['mina_settings_pending_reminder_v215']={'kind':'done','id':item['id']};st.rerun()
                with b2:
                    if st.button('Delete',key='mina_delete_'+item['id']):
                        st.session_state['mina_settings_pending_reminder_v215']={'kind':'delete','id':item['id']};st.rerun()
        except (ReminderError,OSError,ValueError) as exc: st.warning(str(exc))
    with st.expander('🧠 Private conversation memory',expanded=False):
        st.caption('Opt-in LOCAL text archive. Stored on this Mac as unencrypted SQLite. No audio or raw map files are saved. Only messages sent after enabling are archived. No cloud backup or automatic semantic recall.')
        st.checkbox('Save my MINA conversations after restart (local text only)',
                    key='mina_memory_opt_in',on_change=_save_memory_preference_v215)
        if st.session_state.get('mina_memory_error'): st.warning(st.session_state['mina_memory_error'])
        if st.session_state.get('mina_memory_opt_in'):
            st.caption('To search past chats, ask: “What did I tell you about library books?” To pin a fact, say: “Remember that I prefer morning appointments.”')
            try:
                for f in memory_facts()[:8]:
                    a,b=st.columns([5,1])
                    with a: st.caption('Pinned: '+f['text'])
                    with b:
                        if st.button('Remove',key=f'mina_remove_fact_v215_{f["id"]}'):
                            remove_memory_fact(f['id']);st.rerun()
                recent=memory_recent_turns(limit=12)
                if recent:
                    st.caption('Recent archived messages (private):')
                    for e in recent[-8:]: st.caption(f"{e['role']}: {e['text'][:240]}")
            except (MemoryErrorLocal,OSError,ValueError) as exc: st.warning(str(exc))
            st.checkbox('I understand clearing history cannot be undone',key='mina_memory_erase_confirm_v215')
            if st.button('Erase all saved conversation history',key='mina_memory_erase_v215',
                        disabled=not st.session_state.get('mina_memory_erase_confirm_v215',False)):
                try:
                    clear_saved_history();st.session_state['mina_memory_erase_confirm_v215']=False;st.success('Saved history erased. Pinned facts remain.');st.rerun()
                except (MemoryErrorLocal,OSError) as exc:st.warning(str(exc))
            if st.button('Erase ALL saved history and pinned facts',key='mina_memory_erase_all_v215',
                        disabled=not st.session_state.get('mina_memory_erase_confirm_v215',False)):
                try:
                    clear_all_memory();st.session_state['mina_memory_erase_confirm_v215']=False
                    st.success('All saved conversation history and pinned facts erased locally.');st.rerun()
                except (MemoryErrorLocal,OSError) as exc:st.warning(str(exc))
    st.divider()
    st.caption('External email/list writes remain disabled. Approved Google Calendar event writes are supported only after OAuth. Family Hub lists '
               'can be changed locally only after a button press or explicit confirmation. '
               'Microphone audio is sent to OpenAI for transcription when submitted.')
    st.caption('Chat is shown in this browser session; optional private text history can be enabled above. Pending writes still need explicit confirmation.')
    if st.button('Clear conversation', use_container_width=True):
        st.session_state['mina_chat_messages'] = []
        st.session_state['mina_pending_route'] = None
        st.session_state['mina_pending_task_v215'] = None
        st.session_state['mina_memory_session_v215'] = str(uuid4())
        st.session_state['mina_show_landing'] = True
        st.rerun()
    return SimpleNamespace(
        mode=mode, city=city, timezone_name=timezone_name, use_rag=use_rag,
        planner_mode=planner_mode, auto_voice=auto_voice, voice=voice,
        origin=origin, destination=destination, via=via,
        task_locations=task_locations, durations=durations,
        start_time=start_time, saved_places_file=saved_places_file,
        plan_date=plan_date, travel_buffer=travel_buffer,
        confirm_schedule=confirm_schedule,
    )


def _approval_message(action: dict, updated_hub: dict | None = None) -> str:
    if action['kind'] == 'remove_item':
        return (f'**Removed {action["expected_name"]}** from your local '
                f'**{STORE_LABELS[action["store"]]}** shopping list after your confirmation. '
                'No external service was contacted.')
    if action['kind'] == 'multi_list':
        heading = ['**Saved to local shopping lists after your confirmation:**']
        for store, items in action['stores'].items():
            heading.append(f'\n**{STORE_LABELS[store]}:** ' + ', '.join(items))
            if updated_hub is not None:
                heading.append('\n' + hub_list_answer(updated_hub, store))
        heading.append('\nNothing was sent to an external service.')
        return '\n'.join(heading)
    if action['kind'] == 'list':
        items = ', '.join(action['items'])
        heading = f'Added **{items}** to your local **{HUB_STORES[action["store"]]}** list. Nothing was sent to an external service.'
        if updated_hub is not None:
            heading += '\n\n' + hub_list_answer(updated_hub, action['store'])
        return heading
    if action['kind'] == 'clear_list':
        return (f'**{HUB_STORES[action["store"]]} list cleared** after your confirmation. '
                'Your shopping list is now empty. Is there anything else you need to buy? '
                'You can add items with your voice, for example: “Mina, add apples to my Target shopping list.”')
    v = action['visit']
    time_range = v['time'] + (f"–{v['end_time']}" if v.get('end_time') else '')
    return (f'Saved locally: **{v["title"]}** on **{v["date"]}**, **{time_range}**. '
            'This is not a booking or a Google Calendar event.')


def _pairing_response(hub: dict, prompt: str):
    # Real road checks only when the user has granted session permission.
    permitted = bool(st.session_state['mina_hub_address_consent'])
    hints, notes = find_nearby_pairings(hub, day=None, allow_address_lookup=permitted)
    requested = []
    lower = prompt.lower()
    for place in ('dentist', 'pediatrician', 'library'):
        if place in lower or (place == 'dentist' and 'dental' in lower):
            requested.append(place)
    if requested:
        hints = [h for h in hints if h.visit['place'] in requested]
        notes = [x for x in notes if any(hub['places'][p]['name'].lower() in x.lower() for p in requested)]
    advice = (pairing_answer(hints, notes) if hints or notes
              else pairing_setup_guidance(hub, prompt))
    map_report = hints[0].route_report if hints else None
    if hints:
        hint = hints[0]
        prefs = hub.get('preferences') or {}
        school_leg = None
        school_trip_verified = False
        if permitted and prefs.get('school_address'):
            try:
                from mina_route_tools import get_route_report
                address = hub['places'][hint.store_id]['address']
                whole = get_route_report([
                    hub['places'][hint.visit['place']]['address'],
                    address, prefs['school_address'],
                ])
                if len(whole.legs) == 2 and whole.legs[1].duration_minutes > 0:
                    school_leg = whole.legs[1].duration_minutes
                    school_trip_verified = True
                    map_report = whole
            except (OSError, ValueError, RuntimeError):
                school_leg = None
            except Exception:
                # Unknown network error: never assert arrival or schedule feasibility.
                school_leg = None
        advice += '\n\n**Time-window check (provisional)**\n' + time_window_advice(
            hint.visit, pickup_time=prefs.get('pickup_time', ''),
            first_leg_minutes=hint.driving_minutes, school_leg_minutes=school_leg,
            shopping_minutes=prefs.get('shopping_minutes', 45),
            lunch_minutes=prefs.get('lunch_minutes', 45),
            buffer_minutes=prefs.get('buffer_minutes', 15),
        )
    result = SimpleNamespace(
        status='simple_response' if hints else 'needs_clarification',
        answer=advice,
        trace=[{'step': 'auto_hub_pairing', 'road_checked': len(hints),
                'consent': permitted, 'school_route_checked': bool(hints and school_trip_verified)}],
        candidates=[], map_report=map_report,
    )
    return result


def _render_assistant(message: dict, index: int) -> None:
    """Render one stored answer, including its own audio and optional route map."""
    with st.chat_message('assistant', avatar=':material/auto_awesome:'):
        st.markdown(message['text'])
        status = message.get('status', '')
        if status:
            st.caption(f"{status} · {_status_caption_v210(status)}")
        if message.get('voice_bytes'):
            st.caption('AI-generated voice')
            st.audio(message['voice_bytes'], format='audio/mp3')
        elif st.button('🔊 Listen', key=f'mina-listen-{message["seq"]}', type='tertiary'):
            try:
                with st.spinner('Generating speech…'):
                    message['voice_bytes'] = generate_spoken_reply(message['text'], voice=voice)
                st.caption('AI-generated voice')
                st.audio(message['voice_bytes'], format='audio/mp3')
            except Exception as exc:
                st.warning(f'Audio unavailable ({type(exc).__name__}). Text is still available.')
        map_path_str = message.get('map_path')
        if map_path_str:
            path = Path(map_path_str)
            if path.is_file():
                st.caption('Provisional route · HeiGIT estimates, not live traffic')
                try:
                    import streamlit.components.v1 as components
                    components.html(path.read_text(encoding='utf-8'), height=525, scrolling=True)
                except Exception:
                    st.info(f'Map saved locally: {path}')
        if message.get('route_map_html'):
            import streamlit.components.v1 as components
            st.caption('Selected feasible order · HeiGIT estimates, not live traffic')
            components.html(message['route_map_html'], height=525, scrolling=True)
        calendar_pending = message.get('pending_calendar_action')
        if calendar_pending and not message.get('calendar_action_completed'):
            yes_col, no_col = st.columns(2)
            with yes_col:
                label = ('Confirm & save calendar event' if calendar_pending['kind']=='event' else 'Confirm & save note')
                if st.button(label, key=f'mina_calendar_confirm_{message["seq"]}'):
                    try:
                        msg = _commit_calendar_action(calendar_pending,
                            google_sync=bool(st.session_state.get('mina_calendar_sync')),
                            tz_name=timezone_name)
                        message['calendar_action_completed'] = True
                        message['pending_calendar_action'] = None
                        message['voice_bytes'] = None
                        message['text'] = msg
                        message['status'] = 'simple_response'
                        st.rerun()
                    except (CalendarError, ValueError) as exc:
                        st.warning(str(exc))
            with no_col:
                if st.button('Cancel event/note',key=f'mina_calendar_cancel_{message["seq"]}'):
                    message['pending_calendar_action'] = None
                    message['text'] = 'Cancelled. Nothing was saved to MINA or Google Calendar.'
                    st.rerun()
        reminder_pending = message.get('pending_reminder_action')
        if reminder_pending and not message.get('reminder_action_completed'):
            left, right = st.columns(2)
            with left:
                if st.button('Confirm & save standalone reminder', key=f'mina_reminder_confirm_{message["seq"]}'):
                    try:
                        item=add_standalone_reminder(reminder_pending)
                        message['pending_reminder_action']=None
                        message['reminder_action_completed']=True
                        message['voice_bytes']=None
                        message['text']='Standalone reminder saved locally: '+describe_standalone_reminder(item)
                        message['status']='local_update_completed'
                        st.rerun()
                    except (ReminderError,OSError,ValueError) as exc: st.warning(str(exc))
            with right:
                if st.button('Cancel reminder',key=f'mina_reminder_cancel_{message["seq"]}'):
                    message['pending_reminder_action']=None
                    message['text']='Cancelled. No standalone reminder was saved.'
                    message['status']='simple_response'
                    st.rerun()
        memory_pending = message.get('pending_memory_fact')
        if memory_pending and not message.get('memory_action_completed'):
            a,b=st.columns(2)
            with a:
                if st.button('Confirm & remember locally',key=f'mina_memory_confirm_{message["seq"]}'):
                    try:
                        pin_memory_fact(memory_pending)
                        message['pending_memory_fact']=None
                        message['memory_action_completed']=True
                        message['text']='Saved this pinned memory locally.'
                        st.rerun()
                    except (MemoryErrorLocal,OSError,ValueError) as exc:st.warning(str(exc))
            with b:
                if st.button('Cancel memory',key=f'mina_memory_cancel_{message["seq"]}'):
                    message['pending_memory_fact']=None
                    message['text']='Cancelled. No pinned memory was added.'
                    st.rerun()
        pending = message.get('pending_hub_action')
        if pending and not message.get('local_action_completed'):
            left, right = st.columns(2)
            with left:
                button_label = ('Confirm clearing this list' if pending['kind'] == 'clear_list' else
                                'Confirm local list update' if pending['kind'] in {'list','multi_list'} else
                                'Confirm item removal' if pending['kind'] == 'remove_item' else 'Confirm local visit note')
                if st.button(button_label, key=f'mina_hub_confirm_{message["seq"]}'):
                    try:
                        current = st.session_state.get('mina_family_hub')
                        if current is None:
                            raise FamilyHubError('Family Hub local file is not available.')
                        updated = _apply_hub_action(current, pending)
                        _store_local_hub(updated)
                        message['local_action_completed'] = True
                        message['pending_hub_action'] = None
                        message['voice_bytes'] = None
                        message['text'] = _approval_message(pending, updated)
                        message['status'] = 'local_update_completed'
                        if pending['kind'] == 'clear_list' and st.session_state.get('mina_followups') and pending.get('visit_id'):
                            _store_followups(record_shopping(st.session_state['mina_followups'], pending['visit_id'], 'all_purchased'))
                        st.rerun()
                    except (FamilyHubError, MultiStoreParseError, ListRemovalError, TypeError, ValueError) as exc:
                        st.warning(str(exc))
            with right:
                if st.button('Cancel change', key=f'mina_hub_cancel_{message["seq"]}'):
                    message['pending_hub_action'] = None
                    message['text'] = 'Local change cancelled. Nothing was saved.'
                    st.rerun()
        if message.get('trace'):
            with st.expander('How MINA decided'):
                st.json(message['trace'])
                if message.get('candidates'):
                    st.dataframe([
                        {'Route': ' → '.join(c['sequence']), 'Pass': c['feasible'], 'Reason': c['reason']}
                        for c in message['candidates']
                    ], hide_index=True, use_container_width=True)




def _propose_completed_shopping(store_id: str, visit_id: str = '') -> bool:
    hub = st.session_state.get('mina_family_hub')
    if hub is None or store_id not in HUB_STORES or not hub['stores'][store_id]:
        return False
    # Confirmation snapshot makes the destructive change fail closed if the list changes.
    proposal = {'kind': 'clear_list', 'store': store_id,
                'expected_item_ids': [it['id'] for it in hub['stores'][store_id]]}
    if visit_id:
        proposal['visit_id'] = visit_id
    st.session_state['mina_chat_seq'] += 1
    seq = st.session_state['mina_chat_seq']
    st.session_state['mina_chat_messages'].append({
        'role': 'assistant', 'seq': seq,
        'text': (f'You said you purchased everything at **{HUB_STORES[store_id]}**. '
                 f'Would you like MINA to **clear all {len(proposal["expected_item_ids"])} entries** '
                 'from this local list? Please confirm below or say **“Confirm my local update.”** '
                 'Nothing is removed yet.'),
        'status': 'local_confirmation_required', 'latency_ms': 0,
        'map_path': None, 'trace': [{'step': 'user_shopping_checkin', 'operation': 'propose_clear_list'}],
        'candidates': [], 'voice_bytes': None,
        'pending_hub_action': proposal, 'local_action_completed': False,
    })
    st.session_state['mina_show_landing'] = False
    return True


@st.fragment(run_every='60s')
def _family_checkins_panel() -> None:
    # Refresh in-app reminders while page is open; no push notifications.
    hub = st.session_state.get('mina_family_hub')
    records = st.session_state.get('mina_followups')
    if hub is None or records is None:
        if st.session_state.get('mina_followups_error'):
            st.warning('Local reminder notes need repair: ' + st.session_state['mina_followups_error'])
        return
    try:
        local_now = datetime.now(ZoneInfo(timezone_name))
        reminders = due_reminders(hub, records, now=local_now)
        # A v2.7 calendar event may also be mirrored into the legacy pairing Hub.
        # Do not show the same appointment twice in the in-app reminders.
        calendar_events = (st.session_state.get('mina_calendar_data') or {}).get('events', [])
        reminders = [notice for notice in reminders if not any(
            e['date'] == notice['visit']['date'] and e['time'] == notice['visit']['time']
            and e['title'] == notice['visit']['title'] for e in calendar_events)]
        checks = due_checkins(hub, records, today=local_now.date())
    except (ValueError, FamilyHubError, ZoneInfoNotFoundError):
        return
    if not reminders and not checks and not st.session_state.get('mina_next_visit_prompt'):
        return
    with st.container(border=True):
        st.markdown('#### 🔔 Family reminders & check-ins')
        st.caption('In-app notices from your locally saved dates, not verified Google Calendar events. These appear only while MINA is open.')
        for notice in reminders[:5]:
            visit = notice['visit']
            stage = notice['stage']
            lead = 'Starting within 2 hours' if stage == '2h' else 'Within 24 hours'
            st.markdown(f'**{lead}: {visit["title"]}** · {visit["date"]}, {visit["time"]}')
            if notice['paired_store'] and notice['pending_items']:
                st.caption(f"Your {HUB_STORES[notice['paired_store']]} shopping list: " + ', '.join(notice['pending_items']))
                st.caption('Paired errand only; route proximity and schedule are not verified.')
            if st.button('Got it', key=f'mina_reminder_{visit["id"]}_{stage}'):
                _store_followups(acknowledge(records, visit['id'], stage))
                st.rerun()
        for check in checks[:4]:
            visit = check['visit']
            if not check['visit_outcome']:
                st.markdown(f'**Yesterday: {visit["title"]}** · Did you attend?')
                yes, no, later = st.columns(3)
                with yes:
                    if st.button('Yes, I went', key=f'mina_visit_yes_{visit["id"]}'):
                        _store_followups(record_visit(records, visit['id'], 'attended'))
                        st.session_state['mina_next_visit_prompt'] = visit['place']
                        st.rerun()
                with no:
                    if st.button('I missed it', key=f'mina_visit_no_{visit["id"]}'):
                        _store_followups(record_visit(records, visit['id'], 'missed'))
                        st.session_state['mina_next_visit_prompt'] = visit['place']
                        st.rerun()
                with later:
                    if st.button('Ask me later', key=f'mina_visit_later_{visit["id"]}'):
                        _store_followups(record_visit(records, visit['id'], 'later'))
                        st.rerun()
            elif check['visit_outcome'] == 'attended' and check['paired_store'] and check['pending_items']:
                if any(m['role'] == 'assistant' and m.get('pending_hub_action', {}).get('visit_id') == visit['id']
                       for m in st.session_state['mina_chat_messages'] if isinstance(m.get('pending_hub_action'), dict)):
                    st.caption('The shopping-list clearance is awaiting your confirmation in the chat below.')
                    continue
                store = check['paired_store']
                st.markdown(f'**Did you visit {HUB_STORES[store]} and buy everything on your list?**')
                st.caption('Still on your list: ' + ', '.join(check['pending_items']))
                yes, no, partial = st.columns(3)
                with yes:
                    if st.button('Yes, all bought', key=f'mina_buy_yes_{visit["id"]}'):
                        _propose_completed_shopping(store, visit['id'])
                        st.rerun()
                with no:
                    if st.button('Not yet', key=f'mina_buy_no_{visit["id"]}'):
                        _store_followups(record_shopping(records, visit['id'], 'not_yet'))
                        st.rerun()
                with partial:
                    if st.button('Only some items', key=f'mina_buy_part_{visit["id"]}'):
                        _store_followups(record_shopping(records, visit['id'], 'partial'))
                        st.session_state['mina_next_visit_prompt'] = 'partial_shopping'
                        st.rerun()
        followup = st.session_state.get('mina_next_visit_prompt')
        if followup:
            if followup == 'partial_shopping':
                st.info('You can check off purchased items in Settings & Family Hub. The remaining items stay on your list.')
            else:
                st.info(f'When is your next {HUB_PLACES.get(followup, followup).lower()} visit? Tell MINA by voice, e.g. “Mina, I have a dentist appointment next Tuesday at 11 AM.” If it is not scheduled yet, there is nothing to save.')
            if st.button('Dismiss check-in note', key='mina_followup_dismiss'):
                st.session_state['mina_next_visit_prompt'] = ''
                st.rerun()

# Functional navigation — no dummy notification/profile buttons.
logo_col, links_col = st.columns([1.0, 2.4], vertical_alignment='center')
with logo_col:
    st.markdown('<div class="mina-brand">MINA</div>', unsafe_allow_html=True)
with links_col:
    how_col, features_col, settings_col = st.columns([1.3,1.0,1.2], gap='small')
    # Native popovers: show the answer next to its nav item, not below the fold.
    # Deliberately keep the old Explore MINA section behavior unchanged.
    with how_col:
        with st.popover('How it works  ▾', use_container_width=True):
            st.markdown('**How MINA works**')
            st.markdown(
                '1. **Ask** by voice or text.\n'
                '2. **Route** the request to relevant tools or family notes.\n'
                '3. **Plan and check** multi-stop routes against saved time constraints.\n'
                '4. **Review and confirm** changes before anything is saved.'
            )
            st.caption('Route estimates are provisional; MINA does not use live traffic.')
    with features_col:
        with st.popover('Features  ▾', use_container_width=True):
            st.markdown('**Explore MINA**')
            st.markdown(
                '• Voice chat and spoken responses\n\n'
                '• Weather and family-friendly planning\n\n'
                '• Route proposals and saved places\n\n'
                '• Shopping lists and calendar approvals\n\n'
                '• Standalone in-app reminders\n\n'
                '• Optional local conversation history'
            )
            st.caption('Reminders do not send push notifications when MINA is closed.')
    with settings_col:
        settings_label = ('← Back to MINA' if st.session_state['mina_settings_view']
                          else '⚙️ Settings')
        if st.button(settings_label, key='mina_nav_settings', use_container_width=True,
                     help='Open full-page Google Calendar, Family Hub and planner settings.'):
            st.session_state['mina_settings_view'] = not st.session_state['mina_settings_view']
            st.rerun()

# Settings are reachable directly from the header, even if Streamlit hides its
# native sidebar toggle in a split-screen browser window. Only one set of
# form widgets is rendered at a time, so widget keys and local data stay intact.
if st.session_state['mina_settings_view']:
    st.markdown("""<div class="mina-settings-intro">
      <h2>Settings &amp; Family Hub</h2>
      <p>Connect Google Calendar, manage your family lists and customize MINA.</p>
    </div>""", unsafe_allow_html=True)
    with st.container(border=True, key='mina_settings_page'):
        _render_settings_controls()
    st.stop()  # A dedicated settings view: keep the landing/chat hidden until Back.

with st.sidebar:
    _settings = _render_settings_controls()
mode = _settings.mode
city = _settings.city
timezone_name = _settings.timezone_name
use_rag = _settings.use_rag
planner_mode = _settings.planner_mode
auto_voice = _settings.auto_voice
voice = _settings.voice
origin = _settings.origin
destination = _settings.destination
via = _settings.via
task_locations = _settings.task_locations
durations = _settings.durations
start_time = _settings.start_time
saved_places_file = _settings.saved_places_file
plan_date = _settings.plan_date
travel_buffer = _settings.travel_buffer
confirm_schedule = _settings.confirm_schedule

landing_placeholder = st.empty()
if not st.session_state['mina_chat_messages'] and st.session_state['mina_show_landing']:
    with landing_placeholder.container():
        left_col, right_col = st.columns([1.72, 1.0], gap='large', vertical_alignment='center')
        with left_col:
            # Preserve the exact v2.1 acronym semantics; v2.2 adopts the new teal palette.
            st.markdown('''
            <div class="mina-hero">
              <h1 class="mina-hello">Welcome, I’m <span class="mina-name">MINA</span></h1>
              <p class="mina-expansion">
                <span class="mina-initial">M</span>y
                <span class="mina-initial">I</span>ntelligent
                <span class="mina-initial">N</span>avigation
                <span class="mina-initial">A</span>ssistant
              </p>
              <p class="mina-hero-description">Plan your day, capture tasks, and<br>make room for what truly matters.</p>
            </div>''', unsafe_allow_html=True)
            cta1, cta2 = st.columns([1.0, 1.0], gap='small')
            with cta1:
                if st.button('Get started', key='mina_get_started', use_container_width=True):
                    st.session_state['mina_show_landing'] = False
                    st.rerun()
            with cta2:
                if st.button('Explore MINA', key='mina_explore', use_container_width=True):
                    st.session_state['mina_info_section'] = 'features'
                    st.rerun()
        with right_col:
            with st.container(border=True, key='mina_dashboard_panel'):
                st.markdown('<div class="mina-dash-title">MINA</div>', unsafe_allow_html=True)
                try:
                    today_weather = _cached_forecast(city)
                    forecast_markup = dashboard_weather_html(today_weather, city=city)
                except (LocationRequired, ToolUnavailable, OSError, ValueError):
                    forecast_markup = dashboard_weather_html(None, city=city,
                                                             error='Provider unavailable')
                st.markdown(forecast_markup, unsafe_allow_html=True)
                st.markdown('<div class="mina-plan-head">Today’s calendar</div>', unsafe_allow_html=True)
                saved = st.session_state.get('mina_calendar_data')
                calendar_today = agenda(saved,start=date.today(),days=0) if saved else []
                if calendar_today:
                    for e in calendar_today[:4]:
                        st.caption(f"{e['time']} · {e['title']}" + (' (DEMO)' if e['source']=='demo' else ' (MINA local)'))
                recent_google = [x for x in st.session_state.get('mina_google_read_events', [])
                                 if x['start'].startswith(date.today().isoformat())]
                for item in recent_google[:4]:
                    st.caption(f"{item['start'][11:16] if 'T' in item['start'] else 'All day'} · {item['title']} (Google · last refresh)")
                if not calendar_today and not recent_google:
                    st.caption('No local calendar events today · refresh Google in Settings to check connected events')
                st.markdown('<div class="mina-plan-head">Today’s plan</div>', unsafe_allow_html=True)
                if st.session_state['mina_dashboard_is_demo']:
                    st.markdown('<div class="mina-demo-notice">SAMPLE TASKS · Not synced with a calendar</div>',
                                unsafe_allow_html=True)
                else:
                    st.markdown('<div class="mina-demo-notice">SESSION TASKS · Not synced with a calendar</div>',
                                unsafe_allow_html=True)
                if st.session_state.get('mina_family_hub'):
                    candidate_pairs = potential_pairs(st.session_state['mina_family_hub'])
                    if candidate_pairs:
                        st.caption('Possible errands from your local notes · Not yet route-checked')
                        for a_visit, store_key, number in candidate_pairs[:3]:
                            st.caption(f'{a_visit["date"]} · {HUB_PLACES[a_visit["place"]]} + '
                                       f'{HUB_STORES[store_key]} ({number} list items)')
                    visits_today = hub_matched_visit(st.session_state['mina_family_hub'],
                                                     date.today().isoformat())
                    if visits_today:
                        st.caption('Saved visits today · Local notes, not calendar events')
                        for saved_visit in visits_today[:3]:
                            endpoint = ('–' + saved_visit['end_time']) if saved_visit.get('end_time') else ''
                            st.text(f'{saved_visit["time"]}{endpoint} · {HUB_PLACES[saved_visit["place"]]}')
                            for paired_place, paired_store in (
                                ('dentist','target'), ('library','costco'), ('pediatrician','trader_joes')):
                                if saved_visit['place'] == paired_place:
                                    shopping = hub_pending_items(st.session_state['mina_family_hub'], paired_store)
                                    if shopping:
                                        st.caption(f'Remember your {HUB_STORES[paired_store]} list: '
                                                   f'{", ".join(shopping[:4])}. Proximity not yet checked.')
                current_tasks = st.session_state['mina_dashboard_tasks']
                if current_tasks:
                    for task_id, task_label in safe_task_labels(current_tasks):
                        task = next(t for t in current_tasks if t['id'] == task_id)
                        st.checkbox(task_label, key=f'mina_dashboard_done_{task_id}',
                                    value=task['done'], on_change=_toggle_dashboard_task,
                                    args=(task_id,))
                else:
                    st.caption('No tasks yet. Open Settings → Today’s plan to add one.')
                if st.button('🎤  Ask MINA', key='mina_dashboard_ask', use_container_width=True,
                             help='Opens the chat. Use the microphone in the message field.'):
                    st.session_state['mina_show_landing'] = False
                    st.rerun()
        section = st.session_state['mina_info_section']
        if section == 'how':
            st.markdown('''<div class="mina-info-panel"><h3>How MINA works</h3>
                Speak or type a request → MINA chooses the right tools → for complex plans,
                the Python Critic checks constraints → MINA explains the result.
                Google Calendar events are saved only after OAuth and individual approval; email and external list writes remain disabled. Local Family Hub
                lists are edited only with confirmation.</div>''',
                unsafe_allow_html=True)
        elif section == 'features':
            st.markdown('''<div class="mina-info-panel"><h3>Features</h3>
                <strong>Voice-first chat</strong> · Open-Meteo weather · Local time ·
                HeiGIT driving routes and maps · Family planning with saved time windows ·
                Reviewable decisions and write-action safety · Three local shopping lists ·
                Calendar appointments, yearly birthdays, private notes, two reminders per approved event, and nearby errand-pair suggestions.
                The Today’s plan widget is a session/demo list, not Google Calendar.</div>''',
                unsafe_allow_html=True)
elif not st.session_state['mina_chat_messages']:
    st.markdown('<div class="mina-info-panel"><h3>What would you like to plan?</h3>'
                'Type a request or tap the microphone in the chat box below.</div>',
                unsafe_allow_html=True)

# Navigation stays meaningful even after the conversation begins.
if st.session_state['mina_chat_messages'] and st.session_state['mina_info_section'] in {'how', 'features'}:
    if st.session_state['mina_info_section'] == 'how':
        st.markdown('<div class="mina-info-panel"><h3>How MINA works</h3>'
                    'Speak or type → tools → optional planning → independent Critic → safe response. '
                    'Google Calendar writes require OAuth and per-event approval; email and external list writes stay disabled.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="mina-info-panel"><h3>Features</h3>'
                    'Voice/text · Open-Meteo weather · Local time · HeiGIT routes · '
                    'Family planning, Saved Places and local shopping lists. The Today’s plan widget is session-only.</div>',
                    unsafe_allow_html=True)

_family_checkins_panel()

@st.fragment(run_every='60s')
def _calendar_reminders_panel():
    data = st.session_state.get('mina_calendar_data')
    if data is None: return
    try:
        now = datetime.now(ZoneInfo(timezone_name))
        reminders = due_calendar_reminders(data,now)
    except (CalendarError,ZoneInfoNotFoundError,ValueError): return
    if reminders:
        with st.container(border=True):
            st.markdown('#### 📅 Calendar reminders')
            st.caption('Local in-app alerts. For background notifications use Google Calendar and enable notifications on your device.')
            for r in reminders[:6]:
                e=r['event']
                st.markdown(f'**{e["title"]}** · {r["day"]} at {e["time"]} · '
                            + ('2 hours before' if r['stage']=='120' else '24 hours before'))
                if st.button('Dismiss reminder',key='mina_calendar_ack_'+r['key']):
                    _store_calendar(acknowledge_reminder(data,r['key']))
                    st.rerun()

_calendar_reminders_panel()

@st.fragment(run_every='60s')
def _standalone_reminders_due_v215():
    try:
        now = datetime.now(ZoneInfo(timezone_name))
        due = [r for r in standalone_reminder_listing(only_open=True)
               if datetime.fromisoformat(r['due']) <= now]
    except (ReminderError,OSError,ValueError):
        return
    if due:
        with st.expander(f'🔔 Standalone reminders due ({len(due)})',expanded=False):
            st.caption('Shown while MINA is open; not a background notification.')
            for r in due[:8]: st.markdown('• '+describe_standalone_reminder(r))
_standalone_reminders_due_v215()

if st.session_state.get('mina_calendar_data') is not None:
    calendar_entries = agenda(st.session_state['mina_calendar_data'],start=date.today(),days=60)
    with st.expander('🗓️ Monthly calendar · appointments, events & birthdays', expanded=False):
        month_year, month_num = (int(x) for x in st.session_state['mina_calendar_month'].split('-'))
        previous_month, month_title, next_month = st.columns([1, 3, 1])
        with previous_month:
            if st.button('◀ Previous', key='mina_calendar_previous_month'):
                prev = date(month_year-1,12,1) if month_num==1 else date(month_year,month_num-1,1)
                st.session_state['mina_calendar_month'] = prev.strftime('%Y-%m')
                st.rerun()
        with month_title:
            st.markdown(f'**{date(month_year,month_num,1).strftime("%B %Y")}**')
        with next_month:
            if st.button('Next ▶', key='mina_calendar_next_month'):
                nxt = date(month_year+1,1,1) if month_num==12 else date(month_year,month_num+1,1)
                st.session_state['mina_calendar_month'] = nxt.strftime('%Y-%m')
                st.rerun()
        month_events = agenda(st.session_state['mina_calendar_data'],
            start=date(month_year,month_num,1),days=monthrange(month_year,month_num)[1]-1)
        by_day = {}
        for e in month_events:
            by_day.setdefault(int(e['date'][-2:]),[]).append(e)
        for e in st.session_state.get('mina_google_read_events',[]):
            event_start = e.get('start','')
            if event_start.startswith(st.session_state['mina_calendar_month']):
                by_day.setdefault(int(event_start[8:10]),[]).append({'title':e['title'],'source':'google'})
        week_names=st.columns(7)
        for col,name in zip(week_names,['Mon','Tue','Wed','Thu','Fri','Sat','Sun']):
            with col: st.caption(name)
        for week in monthcalendar(month_year,month_num):
            cols=st.columns(7)
            for col,daynum in zip(cols,week):
                with col:
                    if daynum:
                        st.markdown(f'**{daynum}**')
                        for ev in by_day.get(daynum,[])[:3]:
                            mark = ' · DEMO' if ev.get('source')=='demo' else (' · Google' if ev.get('source')=='google' else '')
                            st.caption(ev['title'][:22]+mark)
                    else:
                        st.caption('·')
        st.caption('Google events appear here after Refresh in Settings. Fictional demo birthdays are labelled DEMO.')
    with st.expander('📅 Calendar & Notes · your upcoming events', expanded=False):
        if calendar_entries:
            for e in calendar_entries[:12]:
                st.markdown(f'**{e["date"]} · {e["time"]}** — {e["title"]}'
                            + (' · **DEMO**' if e['source']=='demo' else ''))
        else:
            st.caption('No saved events. Create one by voice, or open Settings → Add an event or note.')
        st.caption(f"{len(st.session_state['mina_calendar_data']['notes'])} private local notes saved")
        for n in st.session_state['mina_calendar_data']['notes'][-5:]:
            st.markdown('- '+n['content'])

for index, message in enumerate(st.session_state['mina_chat_messages']):
    if message['role'] == 'user':
        with st.chat_message('user'):
            st.markdown(message['text'])
    else:
        _render_assistant(message, index)

# Visible, cancellable task continuation. No private addresses are displayed.
route_caption_text = pending_route_caption(st.session_state.get('mina_pending_route'))
if route_caption_text:
    st.caption(route_caption_text)
    if st.button('Cancel pending route', key='mina_cancel_pending_route_v214'):
        st.session_state['mina_pending_route'] = None
        st.session_state['mina_chat_seq'] += 1
        st.session_state['mina_chat_messages'].append({
            'role':'assistant', 'seq':st.session_state['mina_chat_seq'],
            'text':'Cancelled the pending route. No route was calculated and no data was changed.',
            'status':'simple_response', 'trace':[{'step':'conversation_state',
                'status':'cancel','version':CONVERSATION_VERSION,'no_write':True}],
            'candidates':[], 'map_path':None,
        })
        st.rerun()

# In the main page, chat_input is natively anchored at the bottom (and includes
# its own microphone and send button). No separate transcription/Ask buttons.
submitted = st.chat_input(
    'Message MINA or record a voice message…',
    key='mina_unified_input',
    accept_audio=True,
    audio_sample_rate=16000,
)

if submitted is not None:
    try:
        submission = extract_chat_submission(submitted)
        prompt = submission.text
        if submission.from_microphone:
            # Sending the microphone recording is the user's single submit action.
            # Transcript shown before a read or a proposed local change.
            with st.spinner('Listening…'):
                prompt = transcribe_wav(submission.audio_wav or b'')
        if not prompt.strip():
            raise UIInputError('Type a message or record a voice note.')
        try:
            local_today = datetime.now(ZoneInfo(timezone_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            raise UIInputError('Choose a valid time zone, for example America/New_York.') from None
        # v2.14: preserve the *actual* voice transcript for display and history.
        # A standalone time answer may extend only an existing, validated route.
        spoken_prompt = prompt
        conversation = decide_followup(st.session_state.get('mina_pending_route'),
                                       spoken_prompt)
        route_today = local_today
        if conversation.kind == 'resume':
            prompt = conversation.effective_request
            route_today = conversation.original_date_anchor
        if conversation.kind in {'resume', 'cancel', 'expired', 'new_request'}:
            # No old pending route can accidentally trigger again on a later turn.
            st.session_state['mina_pending_route'] = None
        # v2.15 small slot filler; preserves original spoken transcript. It never
        # commits a list or calendar operation itself; existing approval remains.
        multi_decision = handle_extended_followup(st.session_state.get('mina_pending_task_v215'),
                                                   spoken_prompt,today=local_today)
        if multi_decision.kind in {'ask_store','ask_calendar','reprompt'}:
            st.session_state['mina_pending_task_v215'] = multi_decision.pending
        elif multi_decision.kind in {'list_ready','calendar_ready','cancel','new_request','expired'}:
            st.session_state['mina_pending_task_v215'] = None
        reminder_parse_error = None
        try:
            reminder_proposal = parse_reminder_create(spoken_prompt,today=local_today,
                                                       timezone_name=timezone_name)
        except ReminderError as exc:
            reminder_proposal = None
            reminder_parse_error = str(exc)
        reminder_read = is_reminder_read(spoken_prompt)
        memory_intent = memory_request(spoken_prompt) if st.session_state.get('mina_memory_opt_in') else None
        # Do NOT run older Calendar parser on a standalone reminder: it can
        # raise a misleading HH:MM error or turn a reminder into an event.
        v215_direct = bool(reminder_proposal is not None or reminder_parse_error or
                           reminder_read or memory_intent or
                           multi_decision.kind in {'ask_store','ask_calendar','reprompt',
                                                   'cancel','expired','list_ready','calendar_ready'})
        calendar_proposal = None if v215_direct else parse_voice_calendar(prompt, today=local_today)
        if multi_decision.kind == 'calendar_ready':
            try:
                a=multi_decision.action
                d=date.fromisoformat(a['date'])
                ev=make_event(a['title'],d,a['time'],'',kind='appointment',repeat='none',notes='')
                calendar_proposal={'kind':'event','event':ev}
            except (CalendarError,ValueError):
                multi_decision = type(multi_decision)('reprompt',
                    'That calendar date or time could not be validated. Please provide a full date and time.',
                    {'kind':'calendar','title':a['title']})
                st.session_state['mina_pending_task_v215']=multi_decision.pending
        calendar_read = None if v215_direct else calendar_read_intent(prompt, today=local_today)
        calendar_confirm = bool(__import__('re').fullmatch(
            r'\s*(?:mina[,.:! ]+)?(?:confirm (?:my |the |this )?(?:calendar event|calendar update|note|event)|save (?:my |the |this )?(?:calendar event|note|event))\s*[.!?]?\s*',
            prompt, __import__('re').I))
        multi_store_detected = is_multi_store_add_request(prompt)
        removal_detected = is_list_removal_request(prompt)
        removal_action = None
        removal_error = None
        if removal_detected:
            try:
                removal_action = prepare_remove_item_action(prompt, st.session_state.get('mina_family_hub'))
            except ListRemovalError as exc:
                removal_error = str(exc)
        multi_store_action = None
        multi_store_parse_error = None
        if multi_store_detected:
            try:
                multi_store_action = prepare_multi_store_action(prompt)
            except MultiStoreParseError as exc:
                multi_store_parse_error = str(exc)
        trip_route_kind = classify_multi_stop_route(prompt)
        # v2.13.1: detect a named but unsaved stop BEFORE the generic CLI route
        # fallback can ask users for --origin/--via or guess a location.
        unknown_stop = unsaved_named_stop(prompt, st.session_state.get('mina_family_hub'))
        auto_intent = (SimpleNamespace(kind='v215_direct',data=None) if v215_direct
                       else auto_route(prompt, today=local_today))
        purchased_at_store = parse_purchased_all(prompt)
        hub_for_checkin = st.session_state.get('mina_family_hub')
        followups_for_checkin = st.session_state.get('mina_followups')
        spoken_visit_status = (parse_yesterday_visit_status(prompt, hub_for_checkin, followups_for_checkin, today=local_today)
                               if hub_for_checkin is not None and followups_for_checkin is not None else None)
        spoken_shopping_status = (parse_yesterday_shopping_status(prompt, hub_for_checkin, followups_for_checkin, today=local_today)
                                  if hub_for_checkin is not None and followups_for_checkin is not None else None)
        if mode == 'family_plan' and trip_route_kind == 'none' and unknown_stop is None and not confirm_schedule and auto_intent.kind not in {
            'local_list_proposal', 'local_visit_proposal', 'hub_read', 'schedule_read',
            'external_write',
        } and not (calendar_proposal or calendar_read or calendar_confirm or multi_store_detected or removal_detected):
            # Cancellation and short-slot re-prompts must bypass the generic
            # family-plan input gate, without bypassing the live-route guard.
            if conversation.kind not in {'cancel','reprompt','expired'}:
                raise UIInputError('Open Settings and confirm the route schedule assumptions first.')
        settings = UISettings(
            mode='assistant' if mode == 'auto' else mode,
            city=city, timezone_name=timezone_name,
            planner_mode=planner_mode, use_rag=use_rag,
            origin=origin, destination=destination, via=via,
            task_locations=task_locations, durations=durations,
            start_time=start_time, saved_places_file=saved_places_file,
            plan_date=paired_backend_plan_date(saved_places_file, plan_date),
            travel_buffer_minutes=travel_buffer,
        )
        landing_placeholder.empty()
        with st.chat_message('user'):
            st.markdown(spoken_prompt)
            if submission.from_microphone:
                st.caption('Transcribed from voice · local changes still require confirmation')
        # All local actions are proposals. A separate explicit user action
        # (button or clear voice confirmation) is the only path to local writes.
        pending_hub_action = None
        pending_calendar_action = None
        pending_reminder_action = None
        pending_memory_fact = None
        with st.chat_message('assistant', avatar=':material/auto_awesome:'):
            started = perf_counter()
            with st.spinner('MINA is thinking…'):
                hub_current = st.session_state.get('mina_family_hub')
                confirm_target = None
                if is_explicit_local_confirmation(prompt):
                    unresolved = [m for m in st.session_state['mina_chat_messages']
                                  if m['role'] == 'assistant' and m.get('pending_hub_action')
                                  and not m.get('local_action_completed')]
                    if len(unresolved) == 1:
                        confirm_target = unresolved[0]
                if multi_decision.kind in {'ask_store','ask_calendar','reprompt','cancel','expired'}:
                    result=SimpleNamespace(status='needs_clarification' if multi_decision.kind not in {'cancel','expired'} else 'simple_response',
                        answer=multi_decision.message, trace=[{'step':'multi_turn_state',
                        'status':multi_decision.kind,'version':MULTITURN_VERSION,'no_write':True}],
                        candidates=[],map_report=None)
                elif multi_decision.kind == 'list_ready':
                    if hub_current is None:
                        result=SimpleNamespace(status='needs_clarification',
                            answer='Family Hub is unavailable; nothing was added.',
                            trace=[{'step':'multi_turn_state','status':'missing_hub','no_write':True}],
                            candidates=[],map_report=None)
                    else:
                        pending_hub_action=multi_decision.action
                        result=SimpleNamespace(status='local_confirmation_required',
                            answer=f'Add **{multi_decision.action["items"][0]}** to **{STORE_LABELS.get(multi_decision.action["store"],multi_decision.action["store"])}**? Confirm below. Nothing saved yet.',
                            trace=[{'step':'multi_turn_state','status':'slots_filled','kind':'shopping',
                                    'version':MULTITURN_VERSION,'requires_confirmation':True}],
                            candidates=[],map_report=None)
                elif memory_intent is not None:
                    if memory_intent[0]=='pin':
                        pending_memory_fact=memory_intent[1]
                        result=SimpleNamespace(status='local_confirmation_required',
                            answer='Remember this private fact locally? **'+pending_memory_fact+'**. Confirm below; nothing saved yet.',
                            trace=[{'step':'memory','status':'preview','version':'2.15.0','no_write':True}],
                            candidates=[],map_report=None)
                    else:
                        hits=memory_search_turns(memory_intent[1]); current_facts=memory_facts()
                        matching=[f['text'] for f in current_facts if memory_intent[1].lower() in f['text'].lower()]
                        text_out=('Matching pinned facts:\n'+'\n'.join('- '+x for x in matching[:5])+'\n' if matching else '')
                        text_out+='\n'.join('- '+h['role']+' ('+h['time'][:10]+'): '+h['text'][:240] for h in hits)
                        result=SimpleNamespace(status='simple_response',
                            answer=(text_out or 'No matching locally stored conversation text was found. I will not invent a memory.'),
                            trace=[{'step':'memory','status':'local_text_search','version':'2.15.0',
                                    'matches':len(hits),'no_external_request':True}],
                            candidates=[],map_report=None)
                elif reminder_parse_error is not None:
                    result=SimpleNamespace(status='needs_clarification',answer=reminder_parse_error+' No reminder was saved.',
                        trace=[{'step':'standalone_reminders','status':'missing_details','version':'2.15.0','no_write':True}],
                        candidates=[],map_report=None)
                elif reminder_proposal is not None:
                    pending_reminder_action=reminder_proposal
                    result=SimpleNamespace(status='local_confirmation_required',
                        answer='Create a separate local reminder: **'+describe_standalone_reminder(reminder_proposal)+'**? Confirm below. No calendar event or Google action.',
                        trace=[{'step':'standalone_reminders','status':'preview','version':'2.15.0','no_write':True}],
                        candidates=[],map_report=None)
                elif reminder_read:
                    start_day,end_day=reminder_read_query(spoken_prompt,local_today)
                    reminders=standalone_reminder_listing(start=start_day,end=end_day)
                    text_out=('\n'.join('- '+describe_standalone_reminder(r)+(' (done)' if r['done'] else '') for r in reminders)
                              if reminders else 'No standalone reminders found for that date range.')
                    result=SimpleNamespace(status='simple_response',answer=text_out,
                        trace=[{'step':'standalone_reminders','status':'read','version':'2.15.0',
                                'count':len(reminders),'no_write':True}],candidates=[],map_report=None)
                elif conversation.kind in {'cancel', 'reprompt', 'expired'}:
                    # A pending route can be cancelled or clarified without touching
                    # local files, calendar, lists, address providers or the Planner.
                    status = ('simple_response' if conversation.kind == 'cancel'
                              else 'needs_clarification')
                    result = SimpleNamespace(status=status,
                        answer=conversation.message,
                        trace=[{'step':'conversation_state',
                                'version':CONVERSATION_VERSION,
                                'status':conversation.kind,
                                'session_only':True,'no_write':True}],
                        candidates=[],map_report=None)
                elif unknown_stop is not None:
                    # Unknown named places are NOT assigned a demo/saved coordinate.
                    # The label is a simple extracted name, never a stored address.
                    result = SimpleNamespace(status='needs_clarification',
                        answer=(f'I cannot verify the location of **{unknown_stop}** in your Saved Places. '
                                'Please provide its full public address or save it in Family Hub. '
                                'I will not guess coordinates, and no route was calculated.'),
                        trace=[{'step':'coordinator','intent':'planning','route':'needs_location',
                                'version':'2.13.1'},
                               {'step':'route_voice_adapter','status':'unknown_named_stop',
                                'version':'2.13.1','no_route_calculated':True}],
                        candidates=[],map_report=None)
                elif trip_route_kind == 'mixed':
                    result = SimpleNamespace(status='needs_clarification',
                        answer=('This combines route planning with a request to change calendar, shopping-list or email data. '
                                'Please ask for the route first, then make any changes as a separate confirmed request. '
                                '**Nothing was saved or sent.**'),
                        trace=[{'step':'route_voice_adapter', 'status':'mixed_read_write_blocked', 'version':'2.12.1', 'no_write':True}],
                        candidates=[], map_report=None)
                elif trip_route_kind == 'route' or (mode == 'auto' and auto_intent.kind == 'family_plan'):
                    # Voice route constraints are resolved into typed inputs BEFORE
                    # entering the unchanged Coordinator/Planner/Critic/Controller.
                    # 'leave home at...' is a route start_time, not a task fixed_time.
                    try:
                        bridge = build_route_inputs(prompt, today=route_today,
                            hub=st.session_state.get('mina_family_hub'))
                    except TripParseError as exc:
                        result = SimpleNamespace(status='needs_clarification',
                            answer=str(exc) + ' Nothing was changed.',
                            trace=[{'step':'route_voice_adapter','status':'input_rejected', 'version':'2.12.1'}],
                            candidates=[],map_report=None)
                    else:
                        requested = set(bridge.requested)
                        has_profile = bool(bridge.origin and len(requested) >= 2
                            and not bridge.missing
                            and all(bridge.locations.get(t) for t in requested))
                        if has_profile and not bridge.start_time:
                            # Keep only the original route text and a fixed date anchor
                            # while waiting for one explicitly supplied departure time.
                            st.session_state['mina_pending_route'] = create_pending_route(
                                spoken_prompt, date_anchor=route_today,
                                plan_date=bridge.plan_date, requested=requested)
                            # Ask for a missing departure constraint instead of
                            # silently using today's wall-clock time or incorrectly
                            # claiming the saved pickup target is missing.
                            saved_pickup = ((st.session_state.get('mina_family_hub') or {})
                                            .get('preferences') or {}).get('pickup_time')
                            if 'school_pickup' in requested and saved_pickup:
                                text = missing_departure_reply(day=bridge.plan_date,
                                                               pickup=str(saved_pickup))
                            else:
                                text = ('I found your saved stops, but no departure time or window was '
                                        'provided. What time would you like to leave home? '
                                        'No route was calculated or assumed.')
                            result = SimpleNamespace(status='needs_clarification',
                                answer=text,
                                trace=[{'step':'route_voice_adapter',
                                        'status':'missing_departure_time',
                                        'version':CONVERSATION_VERSION,
                                        'plan_date':bridge.plan_date,
                                        'saved_pickup_target_present':bool(saved_pickup),
                                        'no_route_calculated':True},
                                       {'step':'conversation_state',
                                        'status':'awaiting_departure_time',
                                        'version':CONVERSATION_VERSION,
                                        'session_only':True,
                                        'pending_slots':['departure_time']}],
                                candidates=[],map_report=None)
                        elif has_profile:
                            if not st.session_state.get('mina_hub_address_consent',False):
                                result = SimpleNamespace(status='needs_clarification',
                                    answer=('To calculate this route, first allow external address lookup in '
                                            '**Settings → Family Hub → Allow public geocoding ...** '
                                            'Saved private addresses will be sent to US Census/Photon for '
                                            'location lookup, then coordinates to HeiGIT for the road route. '
                                            'Nothing was changed.'),
                                    trace=[{'step':'route_geocode_preflight', 'status':'consent_required',
                                            'version':'2.12.3'}],
                                    candidates=[],map_report=None)
                            else:
                                try:
                                    # Bind private, user-verified pins to the SAME saved
                                    # addresses. Edited addresses invalidate earlier pins.
                                    pin_places = {'origin':('home',bridge.origin)}
                                    if 'library' in requested:
                                        pin_places['library']=('library',bridge.locations['library'])
                                    if 'groceries' in requested:
                                        pin_places['groceries']=(bridge.source_store or 'target',
                                                                  bridge.locations['groceries'])
                                    if 'school_pickup' in requested:
                                        pin_places['school_pickup']=('school_pickup',
                                                                      bridge.locations['school_pickup'])
                                    verified_pins={}
                                    for stop,(place_key,place_address) in pin_places.items():
                                        point=active_pin(place_key,place_address,path=ROUTE_PIN_FILE)
                                        if point: verified_pins[stop]=point
                                    resolved_route = resolve_saved_route_points(
                                        bridge.origin, {t:bridge.locations[t] for t in requested},
                                        verified_overrides=verified_pins)
                                except SavedRouteLocationError as exc:
                                    reason = {
                                        'invalid_verified_coordinates':'has invalid verified pin coordinates',
                                        'invalid_stored_pin':'has invalid locally stored route-pin data',
                                        'incomplete_street_address':'has an incomplete street/city/state/ZIP entry',
                                        'invalid_coordinates':'has invalid coordinates',
                                        'geocoding_unavailable':'could not be checked because the geocoding providers were unavailable',
                                        'not_confidently_matched':'could not be matched to an exact street address',
                                    }.get(exc.reason, 'could not be confidently located')
                                    result = SimpleNamespace(status='needs_clarification',
                                        answer=(f'The saved **{exc.label}** location {reason}. '
                                            'Check that address or use **Settings → Family Hub → Private route pins** '
                                            'to save a verified map pin for that specific place. '
                                            'No route was calculated and no coordinates were guessed.'),
                                        trace=[{'step':'route_geocode_preflight',
                                                'status':'unresolved_saved_location',
                                                'version':'2.12.4',
                                                'stop':exc.label, 'reason':exc.reason}],
                                        candidates=[],map_report=None)
                                except RoutePinError:
                                    result = SimpleNamespace(status='needs_clarification',
                                        answer=('Private route-pin settings could not be read. '
                                                'Review Settings → Family Hub → Private route pins. '
                                                'No route was calculated.'),
                                        trace=[{'step':'route_geocode_preflight','status':'invalid_local_pin_file',
                                                'version':'2.12.4'}],
                                        candidates=[],map_report=None)
                                else:
                                    # v2.13: real time windows are enforced INSIDE
                                    # Planner -> deterministic Critic -> Controller.
                                    # The v1.8 backend and the old post-hoc pickup
                                    # guard are intentionally bypassed on this
                                    # fully geocoded Family Hub route path.
                                    from mina_saved_places import display_clock
                                    start_value = bridge.start_time  # validated above; never assume 'now'
                                    saved_target = ((st.session_state.get('mina_family_hub') or {})
                                        .get('preferences') or {}).get('pickup_time')
                                    try:
                                        schedule_window = bridge.pickup_window
                                        window_provenance = 'explicit_user_request'
                                        if 'school_pickup' in requested and not schedule_window:
                                            schedule_window = pickup_window_from_target(
                                                saved_target, bridge.durations['school_pickup'])
                                            window_provenance = 'saved_target_plus_duration' if schedule_window else 'missing'
                                        result = plan_family_route(
                                            origin=resolved_route.origin,
                                            locations={t:resolved_route.locations[t] for t in requested},
                                            tasks=tuple(sorted(requested)),
                                            depart_time=start_value,
                                            plan_date=bridge.plan_date,
                                            durations=bridge.durations,
                                            pickup_window=schedule_window,
                                            library_open=bridge.library_open,
                                            buffer_minutes=bridge.buffer_minutes,
                                            store_label={'target':'Target','costco':'Costco',
                                                'trader_joes':"Trader Joe's"}.get(
                                                    bridge.source_store,'Groceries'))
                                    except LiveRouteError as exc:
                                        result = SimpleNamespace(status='needs_clarification',
                                            answer=str(exc) + ' Nothing was changed.',
                                            trace=[{'step':'time_window_planning',
                                                    'version':'2.13.0','status':'failed_closed',
                                                    'reason':exc.code}],
                                            candidates=[],map_report=None,route_map_html=None)
                                    result.trace.insert(0, {'step':'route_voice_adapter',
                                        'status':'time_window_inputs_applied',
                                        'version':'2.13.0',
                                        'geocoding':'matched_all_requested_stops',
                                        'verified_pin_stops':list(verified_pins),
                                        'geocoding_sources':resolved_route.provider_by_stop,
                                        'departure_time':start_value,
                                        'plan_date':bridge.plan_date,
                                        'duration_minutes':bridge.durations,
                                        'shopping_stop':bridge.source_store or 'default Target',
                                        'pickup_window':schedule_window,
                                        'window_source':window_provenance,
                                        'input_provenance':'voice_and_private_user_saved_notes',
                                        'warning':'no live traffic, independently verified hours or school rules'})
                        else:
                            # Keep the existing manually confirmed PUBLIC DEMO flow
                            # for generic errands; never pass a concrete named store
                            # to a different demo-store coordinate.
                            configured = bool(bridge.source_store is None and confirm_schedule
                                and origin.strip() and len(requested) >= 2
                                and requested <= set(task_locations)
                                and all(task_locations[t].strip() for t in requested))
                            if configured:
                                demo_settings = replace(settings, mode='family_plan',
                                    start_time=bridge.start_time or settings.start_time,
                                    plan_date=paired_backend_plan_date(
                                        settings.saved_places_file,
                                        bridge.plan_date or settings.plan_date),
                                    task_locations={t: task_locations[t] for t in requested},
                                    durations={t: bridge.duration_overrides.get(t, durations[t])
                                               for t in requested})
                                result = execute_ui_request(bridge.prompt_for_planner, demo_settings)
                                # Legacy v1.8 demo still needs the conservative guard.
                                result = apply_pickup_window_guard(
                                    result, window=bridge.pickup_window,
                                    duration_minutes=bridge.durations.get('school_pickup', 15),
                                    plan_date=bridge.plan_date,
                                    departure_time=bridge.start_time,
                                    stop_durations=bridge.durations,
                                    shopping_label='Groceries')
                                result.trace.insert(0, {'step':'route_voice_adapter',
                                    'mode':'user_confirmed_public_demo',
                                    'version':'2.12.1',
                                    'departure_time':bridge.start_time,
                                    'warning':'synthetic addresses, no verified hours or live traffic'})
                            else:
                                missing = list(bridge.missing)
                                if len(requested) < 2:
                                    missing.append('at least two supported route stops')
                                result = SimpleNamespace(status='needs_clarification',
                                    answer=('For a multi-stop plan, please complete '
                                        '**Settings → Family Hub → Saved Places / Family schedule preferences**: '
                                        + ', '.join(missing) + '. No route has been calculated. '
                                        'I will not invent store locations, travel times or school rules.'),
                                    trace=[{'step':'route_voice_adapter',
                                            'status':'missing_user_saved_route_profile',
                                            'version':'2.12.1',
                                            'missing':missing}],
                                    candidates=[],map_report=None)
                elif calendar_confirm:
                    outstanding = [m for m in st.session_state['mina_chat_messages']
                                   if m['role']=='assistant' and m.get('pending_calendar_action')
                                   and not m.get('calendar_action_completed')]
                    if len(outstanding) != 1:
                        result = SimpleNamespace(status='needs_clarification',
                            answer='I need exactly one pending calendar event or note to confirm. Use the Confirm button if several are pending.',
                            trace=[{'step':'calendar_confirmation','status':'not_unique'}],candidates=[],map_report=None)
                    else:
                        target = outstanding[0]
                        action = target['pending_calendar_action']
                        try:
                            text = _commit_calendar_action(action,google_sync=bool(st.session_state.get('mina_calendar_sync')),
                                tz_name=timezone_name)
                            target['pending_calendar_action'] = None
                            target['calendar_action_completed'] = True
                            target['text'] = text
                            target['status'] = 'simple_response'
                            result = SimpleNamespace(status='simple_response',answer=text,
                                trace=[{'step':'calendar_confirmation','method':'explicit_voice_or_text'}],candidates=[],map_report=None)
                        except CalendarError as exc:
                            result = SimpleNamespace(status='needs_clarification',answer=str(exc),
                                trace=[{'step':'calendar_confirmation','status':'failed'}],candidates=[],map_report=None)
                elif calendar_proposal:
                    if st.session_state.get('mina_calendar_data') is None:
                        result = SimpleNamespace(status='needs_clarification',
                           answer='Local calendar data cannot be loaded; no calendar change proposed.',
                           trace=[{'step':'calendar_proposal','status':'unavailable'}],candidates=[],map_report=None)
                    else:
                        pending_calendar_action = calendar_proposal
                        result = SimpleNamespace(status='calendar_confirmation_required',
                            answer=_calendar_preview(calendar_proposal,timezone_name),
                            trace=[{'step':'calendar_proposal','confirmation_required':True}],candidates=[],map_report=None)
                elif calendar_read:
                    result = SimpleNamespace(status='simple_response',
                        answer=_calendar_read_reply(calendar_read,datetime.now(ZoneInfo(timezone_name))),
                        trace=[{'step':'calendar_read','connected':connected_token_present()}],
                        candidates=[],map_report=None)
                elif calendar_create_intent(prompt):
                    # A speech-transcription/parsing failure is NOT lack of a
                    # Google write tool. Respond safely rather than falling
                    # through to the legacy generic external-write guard.
                    result = SimpleNamespace(status='needs_clarification',
                        answer=('I recognized a calendar request, but I could not confidently '
                                'read the date or time. Please repeat the date, start time and '
                                'duration (for example, “November 30 at 10 a.m. for 15 minutes”). '
                                'Nothing was saved or sent.'),
                        trace=[{'step':'calendar_parse','status':'needs_clarification',
                                'no_write':True,'source':'speech_or_text'}],
                        candidates=[],map_report=None)
                elif is_explicit_local_confirmation(prompt) and confirm_target is None:
                    result = SimpleNamespace(status='needs_clarification',
                        answer='Please make exactly one local change proposal before confirming. If several are pending, use the corresponding Confirm button.',
                        trace=[{'step':'local_confirmation','status':'no_unique_pending_action'}],
                        candidates=[], map_report=None)
                elif confirm_target is not None:
                    action = confirm_target['pending_hub_action']
                    try:
                        updated = _apply_hub_action(hub_current, action)
                        _store_local_hub(updated)
                        confirm_target['pending_hub_action'] = None
                        confirm_target['local_action_completed'] = True
                        confirm_target['voice_bytes'] = None
                        confirm_target['text'] = _approval_message(action, updated)
                        confirm_target['status'] = 'local_update_completed'
                        if action['kind'] == 'clear_list' and st.session_state.get('mina_followups') and action.get('visit_id'):
                            _store_followups(record_shopping(st.session_state['mina_followups'], action['visit_id'], 'all_purchased'))
                        result = SimpleNamespace(status='local_update_completed',
                            answer=_approval_message(action, updated),
                            trace=[{'step':'local_confirmation', 'method':'user_voice_or_text'}],
                            candidates=[], map_report=None)
                    except (FamilyHubError, MultiStoreParseError, ListRemovalError, TypeError, ValueError) as exc:
                        result = SimpleNamespace(status='needs_clarification',
                            answer=f'Cannot save the local change: {exc}. No modification was made.',
                            trace=[{'step':'local_confirmation','status':'invalid'}],
                            candidates=[], map_report=None)
                elif multi_store_detected:
                    # IMPORTANT: two store names must never fall back to the
                    # legacy single-store parser. Ambiguous => no write.
                    previous = [m for m in st.session_state['mina_chat_messages']
                                if m['role'] == 'assistant' and m.get('pending_hub_action')
                                and not m.get('local_action_completed')]
                    if hub_current is None:
                        reason = 'Local Family Hub data are unavailable.'
                    elif previous:
                        reason = 'Please confirm or cancel your previous local change first.'
                    elif multi_store_parse_error or multi_store_action is None:
                        reason = (multi_store_parse_error or 'Could not separate the lists safely.')
                    else:
                        reason = None
                    if reason:
                        result = SimpleNamespace(status='needs_clarification',
                            answer=(f'I understood this as a request involving multiple stores, but {reason} '
                                    'Please say which items belong to each store. **Nothing was saved.**'),
                            trace=[{'step':'multi_store_guard','status':'blocked_no_write',
                                    'reason':reason}], candidates=[], map_report=None)
                    else:
                        pending_hub_action = multi_store_action
                        result = SimpleNamespace(status='local_confirmation_required',
                            answer=preview_multi_store_action(multi_store_action),
                            trace=[{'step':'multi_store_parser', 'stores':list(multi_store_action['stores']),
                                    'requires_approval':True, 'no_write':True}],
                            candidates=[], map_report=None)
                elif removal_detected:
                    # Dedicated local removal route; never fall through to the
                    # generic external-write guard and never delete on parsing.
                    previous = [m for m in st.session_state['mina_chat_messages']
                                if m['role'] == 'assistant' and m.get('pending_hub_action')
                                and not m.get('local_action_completed')]
                    if hub_current is None:
                        reason = 'Your local shopping lists are unavailable.'
                    elif previous:
                        reason = 'Please confirm or cancel your previous local change first.'
                    elif removal_error or removal_action is None:
                        reason = removal_error or 'I could not identify the exact item.'
                    else:
                        reason = None
                    if reason:
                        result = SimpleNamespace(status='needs_clarification',
                            answer=f'{reason} **Nothing was removed.**',
                            trace=[{'step':'local_item_removal_guard','status':'blocked_no_write',
                                    'reason':reason}],candidates=[],map_report=None)
                    else:
                        pending_hub_action = removal_action
                        result = SimpleNamespace(status='local_confirmation_required',
                            answer=preview_remove_item_action(removal_action),
                            trace=[{'step':'local_item_removal', 'store':removal_action['store'],
                                    'approval_required':True,'no_write':True}],
                            candidates=[],map_report=None)
                elif spoken_visit_status and st.session_state.get('mina_followups') is not None:
                    _store_followups(record_visit(st.session_state['mina_followups'],
                        spoken_visit_status['visit_id'], spoken_visit_status['outcome']))
                    st.session_state['mina_next_visit_prompt'] = spoken_visit_status['place']
                    followup_store = next((s for p, s in (('dentist','target'), ('pediatrician','trader_joes'), ('library','costco'))
                                          if p == spoken_visit_status['place']), None)
                    list_to_check = hub_pending_items(hub_current, followup_store) if followup_store else []
                    text = ('Thanks for confirming your visit. ' if spoken_visit_status['outcome'] == 'attended'
                            else 'I noted that you missed the visit. ')
                    text += f'When is your next {spoken_visit_status["place"]} appointment? You can tell me by voice.'
                    if spoken_visit_status['outcome'] == 'attended' and list_to_check:
                        text += (f' Did you also make it to {HUB_STORES[followup_store]} and buy everything? '
                                 f'Your pending list is: {", ".join(list_to_check)}.')
                    result = SimpleNamespace(status='simple_response',answer=text,
                        trace=[{'step':'spoken_visit_checkin','result':spoken_visit_status['outcome']}],
                        candidates=[],map_report=None)
                elif spoken_shopping_status and st.session_state.get('mina_followups') is not None:
                    _store_followups(record_shopping(st.session_state['mina_followups'],
                        spoken_shopping_status['visit_id'], spoken_shopping_status['outcome']))
                    text = ('No problem. Your list stays unchanged.' if spoken_shopping_status['outcome'] == 'not_yet'
                            else 'I kept your shopping list. Please mark bought items in Settings & Family Hub; the rest will stay pending.')
                    result = SimpleNamespace(status='simple_response',answer=text,
                        trace=[{'step':'spoken_shopping_checkin','result':spoken_shopping_status['outcome']}],
                        candidates=[],map_report=None)
                elif purchased_at_store and hub_current is not None:
                    previous = [m for m in st.session_state['mina_chat_messages']
                                if m['role'] == 'assistant' and m.get('pending_hub_action')
                                and not m.get('local_action_completed')]
                    if previous:
                        result = SimpleNamespace(status='needs_clarification',
                            answer='Please confirm or cancel your previous local update before proposing another list change.',
                            trace=[{'step':'local_shopping', 'status':'outstanding_proposal'}],
                            candidates=[],map_report=None)
                    elif not hub_current['stores'][purchased_at_store]:
                        result = SimpleNamespace(status='simple_response',
                            answer=f'Your {HUB_STORES[purchased_at_store]} list is already empty. Is there anything else you need to buy?',
                            trace=[{'step':'local_shopping','status':'already_empty'}],
                            candidates=[],map_report=None)
                    else:
                        pending_hub_action = {'kind': 'clear_list', 'store': purchased_at_store,
                            'expected_item_ids': [it['id'] for it in hub_current['stores'][purchased_at_store]]}
                        result = SimpleNamespace(status='local_confirmation_required',
                            answer=(f'You said you bought everything at **{HUB_STORES[purchased_at_store]}**. '
                                    f'Clear all **{len(pending_hub_action["expected_item_ids"])}** entries from that local list? '
                                    'Please press **Confirm clearing this list** or say **“Confirm my local update.”** '
                                    'Nothing has been removed yet.'),
                            trace=[{'step':'local_shopping','status':'pending_clear_confirmation'}],
                            candidates=[],map_report=None)
                elif auto_intent.kind in {'local_list_proposal','local_visit_proposal',
                                          'hub_read','schedule_read'} and hub_current is None:
                    result = SimpleNamespace(status='needs_clarification',
                        answer='Private Family Hub data cannot be loaded. Check Settings → Family Hub; nothing was modified.',
                        trace=[{'step':'auto_route','decision':'missing_local_file'}],
                        candidates=[], map_report=None)
                elif auto_intent.kind == 'local_list_proposal':
                    pending_hub_action = {'kind':'list', **auto_intent.data}
                    label = HUB_STORES[auto_intent.data['store']]
                    items = ', '.join(auto_intent.data['items'])
                    result = SimpleNamespace(status='local_confirmation_required',
                        answer=f'Add **{items}** to the local **{label}** shopping list? '
                               'Press **Confirm local list update** below or say **“Confirm my local update.”** '
                               'Nothing has been saved yet.',
                        trace=[{'step':'auto_route','decision':'local_list_proposal',
                                'item_count':len(auto_intent.data['items'])}],
                        candidates=[], map_report=None)
                elif auto_intent.kind == 'local_visit_proposal':
                    visit = auto_intent.data
                    pending_hub_action = {'kind':'visit', 'visit':visit}
                    interval = visit['time'] + (f"–{visit['end_time']}" if visit.get('end_time') else '')
                    result = SimpleNamespace(status='local_confirmation_required',
                        answer=(f'Save a **local {visit["title"]} note** for **{visit["date"]}** '
                                f'at **{interval}**? Confirm below or say **“Confirm my local update.”** '
                                'This will not book an appointment or create a Google Calendar event.'),
                        trace=[{'step':'auto_route','decision':'local_visit_proposal'}],
                        candidates=[], map_report=None)
                elif auto_intent.kind == 'hub_read':
                    subtype, store_key = auto_intent.data
                    if subtype == 'list':
                        result = SimpleNamespace(status='simple_response',
                            answer=hub_list_answer(hub_current, store_key),
                            trace=[{'step':'auto_route','decision':'read_local_list','store':store_key}],
                            candidates=[],map_report=None)
                    else:
                        result = _pairing_response(hub_current, prompt)
                elif auto_intent.kind == 'schedule_read':
                    day = local_today + timedelta(days=1 if auto_intent.data.get('tomorrow') else 0)
                    result = SimpleNamespace(status='simple_response',
                        answer=local_schedule_answer(hub_current, day=day),
                        trace=[{'step':'auto_route','decision':'read_local_schedule','date':day.isoformat()}],
                        candidates=[],map_report=None)
                elif auto_intent.kind == 'external_write':
                    # Remove only wake/polite prefix before passing through independent write guard.
                    from mina_family_hub import _local_list_command_text
                    result = execute_ui_request(_local_list_command_text(prompt), replace(settings, mode='assistant'))
                elif mode == 'auto' and auto_intent.kind == 'directions':
                    result = execute_ui_request(prompt, replace(settings, mode='directions',
                        origin=auto_intent.data[0], destination=auto_intent.data[1], via=()))
                elif mode == 'assistant' and needs_live_family_mode(prompt):
                    result = SimpleNamespace(status='needs_clarification',
                        answer='This is a Family planner request. Choose **Auto** for automatic routing, then enter and confirm route locations in Settings. Synthetic fixture times are not a real route.',
                        trace=[{'step':'manual_route_gate','decision':'needs_live_inputs'}],
                        candidates=[],map_report=None)
                else:
                    result = execute_ui_request(prompt, settings)
                if multi_decision.kind == 'calendar_ready':
                    result.trace.insert(0, {'step':'multi_turn_state',
                        'status':'slots_filled','kind':'calendar','version':MULTITURN_VERSION,
                        'requires_confirmation':True})
                if conversation.kind == 'resume':
                    # Shows the slot resolution *before* Planner/Critic/Controller
                    # in the audit trace. Only non-sensitive metadata is recorded.
                    result.trace.insert(0, {'step':'conversation_state',
                        'status':'slot_filled_and_resumed',
                        'version':CONVERSATION_VERSION,
                        'filled_slot':'departure_time',
                        'departure_time':conversation.departure_time,
                        'session_only':True,'no_write':True})
            latency_ms = round((perf_counter() - started) * 1000)
            st.markdown(result.answer)
            st.caption(f'{result.status} · {_status_caption_v210(result.status)}')
            seq = st.session_state['mina_chat_seq'] + 1
            path_str = None
            if result.map_report is not None:
                try:
                    map_file = ROOT / 'evaluation' / 'maps' / f'mina_chat_map_{seq:04d}.html'
                    path_str = str(save_preview_map(result.map_report, output_path=map_file))
                    st.caption('Provisional route · HeiGIT estimates, not live traffic')
                    import streamlit.components.v1 as components
                    map_html = Path(path_str).read_text(encoding='utf-8')
                    # Legacy map preview contains a generic public-demo legend
                    # even when the route inputs came from Family Hub coordinates.
                    # Correct that legend ONLY for independently geocoded/verified
                    # saved places; do not claim store hours or school verification.
                    if any(e.get('step') == 'route_voice_adapter' and
                           e.get('geocoding') == 'matched_all_requested_stops'
                           for e in (result.trace or [])):
                        map_html = map_html.replace('Public demo locations reconnected',
                            'Route locations from Family Hub (user-saved, not venue-verified)')
                        # Legacy renderer may encode whitespace in its own banner.
                        map_html = replace_legacy_route_map_caption(map_html)
                        # v2.12.7 also handles captions added by the map renderer after load.
                        map_html = repair_runtime_saved_map_legend(map_html)
                        st.caption('Map locations: saved Family Hub / verified pins, not demo coordinates')
                        Path(path_str).write_text(map_html, encoding='utf-8')
                    components.html(map_html, height=525, scrolling=True)
                except (OSError, ValueError, RuntimeError) as exc:
                    st.info(f'Map preview unavailable ({type(exc).__name__}). The text plan is still available.')
                    path_str = None
            # v2.13 directions geometry follows Controller's exact selected
            # stop order. No map is shown if route geometry could not be obtained.
            if getattr(result, 'route_map_html', None):
                import streamlit.components.v1 as components
                st.caption('Selected feasible order · HeiGIT map estimates, not live traffic')
                components.html(result.route_map_html, height=525, scrolling=True)
            voice_bytes = None
            if submission.from_microphone and auto_voice:
                try:
                    with st.spinner('Preparing spoken reply…'):
                        voice_bytes = generate_spoken_reply(result.answer, voice=voice)
                    st.caption('AI-generated voice')
                    st.audio(voice_bytes, format='audio/mp3')
                except Exception as exc:
                    st.info(f'Voice reply unavailable ({type(exc).__name__}); text is ready.')
            with st.expander('How MINA decided'):
                st.json(result.trace)
                if result.candidates:
                    st.dataframe([
                        {'Route': ' → '.join(c['sequence']), 'Pass': c['feasible'], 'Reason': c['reason']}
                        for c in result.candidates
                    ], hide_index=True, use_container_width=True)
        st.session_state['mina_chat_seq'] = seq
        st.session_state['mina_chat_messages'].extend([
            {'role': 'user', 'text': spoken_prompt},
            {'role': 'assistant', 'seq': seq, 'text': result.answer,
             'status': result.status, 'latency_ms': latency_ms,
             'map_path': path_str, 'route_map_html': getattr(result, 'route_map_html', None), 'trace': result.trace,
             'candidates': result.candidates, 'voice_bytes': voice_bytes,
             'pending_hub_action': pending_hub_action, 'local_action_completed': False,
             'pending_calendar_action': pending_calendar_action, 'calendar_action_completed':False,
             'pending_reminder_action': pending_reminder_action, 'reminder_action_completed':False,
             'pending_memory_fact': pending_memory_fact, 'memory_action_completed':False},
        ])
        _archive_exchange_v215(spoken_prompt, result.answer)
        if (pending_hub_action or pending_calendar_action or pending_reminder_action or pending_memory_fact
                or multi_decision.kind in {'ask_store','ask_calendar','reprompt','cancel','expired','list_ready','calendar_ready'}
                or conversation.kind in {'resume','cancel','expired','reprompt'}
                or st.session_state.get('mina_pending_route') is not None):
            st.rerun()  # Refresh pending-route status and explicit confirm UI.
    except (UIInputError, VoiceInputError, ValueError) as exc:
        st.warning(str(exc))
    except Exception as exc:
        st.error(f'MINA could not complete the request ({type(exc).__name__}). '
                 'Please check connectivity and settings. No write action was performed.')
