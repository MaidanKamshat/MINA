"""Explicit OAuth integration with Google Calendar (desktop-local Streamlit MVP).

Nothing is transmitted to Google until the user clicks Connect, Refresh, or
confirms a specifically previewed event. Credentials/tokens live in gitignored
local_data and are not bundled with the distributable patch.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mina_calendar_v27 import ROOT, TZ_DEFAULT, CalendarError
from mina_saved_places import parse_clock

CLIENT_FILE = ROOT / 'local_data' / 'google_oauth_client.json'
TOKEN_FILE = ROOT / 'local_data' / 'google_calendar_token.json'
SCOPE = 'https://www.googleapis.com/auth/calendar.events'
SCOPES = [SCOPE]

class GoogleCalendarError(RuntimeError):
    pass


def _deps():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleCalendarError('Install Google Calendar dependencies from requirements_calendar_v2_7.txt.') from exc
    return Credentials, Request, InstalledAppFlow, build


def _save_token(creds, path=TOKEN_FILE):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Token contains refresh credential. Readable only by the owner.
    fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as file: file.write(creds.to_json())
    finally:
        try: os.close(fd)
        except OSError: pass


def credentials(allow_interactive=False,client_path=CLIENT_FILE,token_path=TOKEN_FILE):
    Credentials, Request, InstalledAppFlow, _ = _deps()
    client_path=Path(client_path);token_path=Path(token_path)
    creds=None
    if token_path.exists():
        try: creds=Credentials.from_authorized_user_file(str(token_path),SCOPES)
        except (ValueError, OSError) as exc: raise GoogleCalendarError('Saved Google token cannot be read; reconnect manually.') from exc
    if creds and creds.valid:return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request());_save_token(creds,token_path)
            return creds
        except Exception as exc:
            raise GoogleCalendarError('Google token refresh failed; reconnect Google Calendar.') from exc
    if not allow_interactive:raise GoogleCalendarError('Google Calendar not connected. Use Settings → Connect Google Calendar.')
    if not client_path.is_file():raise GoogleCalendarError('Missing local_data/google_oauth_client.json; see README.')
    try:
        flow=InstalledAppFlow.from_client_secrets_file(str(client_path),SCOPES)
        creds=flow.run_local_server(host='localhost',port=0,open_browser=True,access_type='offline',prompt='consent')
        _save_token(creds,token_path)
        return creds
    except Exception as exc:
        raise GoogleCalendarError('Google OAuth authorization did not complete. No calendar changes were made.') from exc


def connected_token_present(path=TOKEN_FILE):
    """Token-on-disk only; does NOT imply Google accepted it."""
    return Path(path).is_file()


def _service():
    *_, build = _deps()
    return build('calendar','v3',credentials=credentials(allow_interactive=False),cache_discovery=False)


def google_event_body(event,tz_name=TZ_DEFAULT):
    """API payload with individual 24h and 2h reminders. Pure/testable."""
    if event.get('source') == 'demo':raise CalendarError('Fictional DEMO birthdays cannot be exported to Google.')
    day=event['date'];start=parse_clock(event['time'])
    hh,mm=(int(x) for x in start.split(':'))
    begin=datetime.fromisoformat(day).replace(hour=hh,minute=mm,tzinfo=ZoneInfo(tz_name))
    if event.get('end_time'):
        end=parse_clock(event['end_time'])
        eh,em=(int(x) for x in end.split(':'))
        finish=begin.replace(hour=eh,minute=em)
        if finish<=begin: raise CalendarError('Appointment end must follow start.')
    else:
        # Real Google events need an end; 60 minutes is a DISPLAYED assumption.
        finish=begin+timedelta(hours=1)
    detail=event.get('notes') or ''
    if not event.get('end_time'):
        detail=(detail+'\n\n' if detail else '')+'Duration: 60 minutes assumed by MINA; edit if needed.'
    description=(detail+'\n\n' if detail else '')+'Added via MINA after explicit user confirmation.'
    payload={
        'summary':event['title'], 'description':description,
        'start':{'dateTime':begin.isoformat(),'timeZone':tz_name},
        'end':{'dateTime':finish.isoformat(),'timeZone':tz_name},
        'reminders':{'useDefault':False,'overrides':[
            {'method':'popup','minutes':1440}, {'method':'popup','minutes':120},
        ]},
        'extendedProperties':{'private':{'mina_event_id':event['id']}},
    }
    if event['repeat']=='yearly':payload['recurrence']=['RRULE:FREQ=YEARLY']
    return payload


def insert_event(event,tz_name=TZ_DEFAULT,service=None,calendar_id='primary'):
    """Call only AFTER distinct confirmation. No auto retry on ambiguous errors."""
    if event.get('google_event_id'):
        raise GoogleCalendarError('Already synchronized; refuse duplicate insertion.')
    payload=google_event_body(event,tz_name)
    service=service or _service()
    try:
        result=service.events().insert(calendarId=calendar_id,body=payload,sendUpdates='none').execute()
    except Exception as exc:
        raise GoogleCalendarError('Google Calendar event creation failed; local copy may still be saved.') from exc
    if not result.get('id'):
        raise GoogleCalendarError('Google returned no event identifier; check Google Calendar before retrying.')
    return {'id':result['id'],'htmlLink':result.get('htmlLink','')}


def list_events(days=60,tz_name=TZ_DEFAULT,service=None,now=None,calendar_id='primary'):
    if not 1<=days<=365:raise GoogleCalendarError('Date window must be between 1 and 365 days.')
    now=now or datetime.now(ZoneInfo(tz_name))
    if now.tzinfo is None:raise GoogleCalendarError('Expected timezone-aware date.')
    service=service or _service()
    try:
        result=service.events().list(calendarId=calendar_id,timeMin=now.isoformat(),
            timeMax=(now+timedelta(days=days)).isoformat(),singleEvents=True,
            orderBy='startTime',maxResults=100).execute()
    except Exception as exc:
        raise GoogleCalendarError('Could not read Google Calendar events.') from exc
    records=[]
    for ev in result.get('items',[]):
        start=ev.get('start') or {}
        records.append({'id':ev.get('id',''), 'title':ev.get('summary','(No title)'),
                        'start':start.get('dateTime') or start.get('date',''),
                        'htmlLink':ev.get('htmlLink','')})
    return records
