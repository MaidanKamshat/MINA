"""MINA v2.7 local event + notes store and deterministic reminder previews.

User data belongs in gitignored local_data. DEMO data is explicit and never
written to a Google account automatically. No autonomous write side effects.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from mina_saved_places import display_clock, parse_clock
from mina_auto_mode import _date_from_text, _local_list_command_text

ROOT = Path(__file__).resolve().parent
LOCAL_CALENDAR = ROOT / 'local_data' / 'mina_calendar_v27.json'
DEMO_BIRTHDAYS = ROOT / 'examples' / 'mina_demo_birthdays_v27.json'
REMINDER_MINUTES = (1440, 120)
TZ_DEFAULT = 'America/New_York'
MAX_BYTES = 160_000

class CalendarError(ValueError):
    pass


def blank_calendar() -> dict:
    return {'schema_version': '2.7', 'events': [], 'notes': [], 'acknowledged': []}


def _text(s, maxlen=240, optional=False):
    if not isinstance(s, str) or len(s.strip()) > maxlen or (not optional and not s.strip()) or any(ord(c) < 32 for c in s) or '<' in s or '>' in s:
        raise CalendarError('Please enter plain text without special markup (maximum %d characters).' % maxlen)
    return s.strip()


def _valid_event(e):
    if not isinstance(e, dict) or set(e) != {'id','title','date','time','end_time','kind','notes','repeat','source','google_event_id','google_sync_state'}:
        raise CalendarError('Invalid event fields.')
    if not re.fullmatch(r'[a-z0-9_-]{6,50}', e['id']):
        raise CalendarError('Invalid event ID.')
    _text(e['title'], 90)
    _text(e['notes'], 800, optional=True)
    date.fromisoformat(e['date'])
    start = parse_clock(e['time'])
    if e['end_time'] and parse_clock(e['end_time']) <= start:
        raise CalendarError('End time must be after start time.')
    if e['kind'] not in ('appointment','event','birthday') or e['repeat'] not in ('none','yearly') or e['source'] not in ('user','demo'):
        raise CalendarError('Invalid event type.')
    if e['kind'] == 'birthday' and e['repeat'] != 'yearly':
        raise CalendarError('Birthdays must recur yearly.')
    _text(e['google_event_id'], 150, optional=True)
    if e['google_sync_state'] not in ('local','synced','failed'):
        raise CalendarError('Invalid synchronization status.')
    return e


def validate(data):
    if not isinstance(data, dict) or set(data) != {'schema_version','events','notes','acknowledged'} or data['schema_version'] != '2.7':
        raise CalendarError('Invalid MINA calendar format.')
    if not isinstance(data['events'], list) or len(data['events']) > 300 or not isinstance(data['notes'], list) or len(data['notes']) > 200 or not isinstance(data['acknowledged'], list) or len(data['acknowledged']) > 1000:
        raise CalendarError('Calendar entry limit reached or invalid data.')
    seen = set()
    for e in data['events']:
        _valid_event(e)
        if e['id'] in seen:
            raise CalendarError('Duplicate event ID.')
        seen.add(e['id'])
    for n in data['notes']:
        if not isinstance(n, dict) or set(n) != {'id','content','created_at'}:
            raise CalendarError('Invalid note.')
        if not re.fullmatch(r'note_[0-9a-f]{12}', n['id']):
            raise CalendarError('Invalid note ID.')
        _text(n['content'], 800)
        datetime.fromisoformat(n['created_at'])
    for a in data['acknowledged']:
        if not isinstance(a, str) or not re.fullmatch(r'[a-z0-9_-]{6,50}:\d{4}-\d{2}-\d{2}:(1440|120)', a):
            raise CalendarError('Invalid reminder acknowledgement.')
    return data


def load_calendar(path=LOCAL_CALENDAR):
    path=Path(path)
    if not path.exists(): return blank_calendar()
    if path.stat().st_size > MAX_BYTES: raise CalendarError('Calendar file too large.')
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError, UnicodeError) as exc: raise CalendarError('Calendar data unreadable; not overwriting it.') from exc
    return validate(data)


def save_calendar(data, path=LOCAL_CALENDAR):
    validate(data)
    path=Path(path)
    raw=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
    if len(raw)>MAX_BYTES: raise CalendarError('Calendar too large.')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.mina_calendar_',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f: f.write(raw)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)
    return path


def clock_12(value):
    if isinstance(value, datetime):
        return value.strftime('%I:%M %p').lstrip('0')
    text=str(value).upper().strip().replace('.', '')
    text=re.sub(r'(?<=\d)(?=[AP]M\b)', ' ', text)
    if re.fullmatch(r'\d{1,2}\s*[AP]M',text):
        text=re.sub(r'^(\d{1,2})\s*([AP]M)$',r'\1:00 \2',text)
    return display_clock(parse_clock(text))


def make_event(title, day, start, end='', kind='event', notes='', repeat='none', source='user', event_id=None):
    if isinstance(day,date): day=day.isoformat()
    item={'id':event_id or 'evt_'+uuid4().hex[:14], 'title':_text(title,90),
          'date':str(day),'time':clock_12(start),'end_time':clock_12(end) if end else '',
          'kind':kind,'notes':_text(notes,800,optional=True),'repeat':repeat,
          'source':source,'google_event_id':'','google_sync_state':'local'}
    return _valid_event(item)


def add_event(data, e):
    validate(data); _valid_event(e)
    if any(x['id']==e['id'] for x in data['events']): raise CalendarError('Event already saved.')
    updated=copy.deepcopy(data); updated['events'].append(copy.deepcopy(e)); return validate(updated)


def update_google_status(data, event_id, google_id, state):
    updated=copy.deepcopy(data)
    matching=[e for e in updated['events'] if e['id']==event_id]
    if len(matching)!=1: raise CalendarError('Saved event not found.')
    matching[0]['google_event_id']=google_id
    matching[0]['google_sync_state']=state
    return validate(updated)


def add_note(data, content, now=None):
    validate(data); updated=copy.deepcopy(data)
    now=now or datetime.now(ZoneInfo(TZ_DEFAULT))
    updated['notes'].append({'id':'note_'+uuid4().hex[:12], 'content':_text(content,800), 'created_at':now.isoformat()})
    return validate(updated)


def upcoming_occurrence(e, today):
    original=date.fromisoformat(e['date'])
    if e['repeat']=='none': return original if original>=today else None
    for year in range(today.year,today.year+9):
        try: candidate=original.replace(year=year)
        except ValueError: continue   # leap-day birthday → next leap year
        if candidate>=today: return candidate
    return None


def agenda(data, start=None, days=60):
    validate(data); start=start or date.today()
    limit=start+timedelta(days=days)
    rows=[]
    for e in data['events']:
        day=upcoming_occurrence(e,start)
        if day and day<=limit: rows.append((day,parse_clock(e['time']),e))
    return [{**copy.deepcopy(e), 'date':d.isoformat()} for d,_,e in sorted(rows,key=lambda x:(x[0],x[1]))]


def reminder_dates(event, occurrence_day=None, tz_name=TZ_DEFAULT):
    day=occurrence_day or date.fromisoformat(event['date'])
    hhmm=parse_clock(event['time'])
    start=datetime(day.year,day.month,day.day,int(hhmm[:2]),int(hhmm[3:]),tzinfo=ZoneInfo(tz_name))
    return {'24h':start-timedelta(hours=24),'2h':start-timedelta(hours=2)}


def due_calendar_reminders(data, now, days=2):
    validate(data)
    if now.tzinfo is None: raise CalendarError('Current time must include a time zone.')
    ack=set(data['acknowledged']); seen=[]
    startday=now.date()-timedelta(days=1)
    for e in data['events']:
        for offset in range((days or 2)+2):
            day=startday+timedelta(days=offset)
            if e['repeat']=='yearly':
                if (day.month,day.day)!=(date.fromisoformat(e['date']).month,date.fromisoformat(e['date']).day): continue
            elif e['date']!=day.isoformat(): continue
            times=reminder_dates(e,day,str(now.tzinfo))
            start_dt=times['2h']+timedelta(hours=2)
            if not times['24h']<=now<start_dt: continue
            stage='120' if now>=times['2h'] else '1440'
            key=f"{e['id']}:{day.isoformat()}:{stage}"
            if key not in ack:
                seen.append({'event':e,'day':day.isoformat(),'stage':stage,'key':key,'trigger':times['2h' if stage=='120' else '24h']})
    return sorted(seen,key=lambda x:x['trigger'])


def acknowledge_reminder(data,key):
    validate(data)
    if not re.fullmatch(r'[a-z0-9_-]{6,50}:\d{4}-\d{2}-\d{2}:(1440|120)',key): raise CalendarError('Bad reminder key.')
    updated=copy.deepcopy(data)
    if key not in updated['acknowledged']: updated['acknowledged'].append(key)
    return validate(updated)


def load_demo_birthdays(data, source=DEMO_BIRTHDAYS):
    """Opt-in; idempotent. DEMO events stay in local calendar only."""
    validate(data)
    source=Path(source)
    fixtures=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(fixtures,list) or len(fixtures)!=7: raise CalendarError('Demo fixture must have exactly seven birthdays.')
    updated=copy.deepcopy(data)
    for item in fixtures:
        identifier='demo_'+_text(item['id'],20)
        if any(e['id']==identifier for e in updated['events']): continue
        e=make_event('DEMO · '+item['title'],item['date'],'9:00 AM',kind='birthday',
                     notes='Fictional capstone fixture; not a real family birthday.',
                     repeat='yearly',source='demo',event_id=identifier)
        updated=add_event(updated,e)
    return validate(updated)


def _wake(text):
    return re.sub(r'^\s*(?:(?:hey|hi|hello)\s+)?mina\b[,.:!\s-]*','',text,flags=re.I).strip()



# v2.9: normalize ASR punctuation and everyday spoken time expressions only
# for calendar intent parsing. The original transcript is still shown to the user.
_SPOKEN_HOURS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12,
}
_SPOKEN_DURATIONS = {'five': 5, 'ten': 10, 'fifteen': 15,
                     'twenty': 20, 'thirty': 30, 'forty-five': 45,
                     'forty five': 45, 'sixty': 60, 'one': 1,
                     'two': 2}
_MONTHS = {name: i for i, names in enumerate((
    ('january','jan'), ('february','feb'), ('march','mar'),
    ('april','apr'), ('may',), ('june','jun'), ('july','jul'),
    ('august','aug'), ('september','sept','sep'), ('october','oct'),
    ('november','nov'), ('december','dec')), start=1) for name in names}
_WEEKDAYS = {'monday':0,'tuesday':1,'wednesday':2,'thursday':3,
             'friday':4,'saturday':5,'sunday':6}


def _normalize_calendar_speech(text):
    # Whisper/other STT providers often produce "10 a.m." or "10 A. M.".
    out = re.sub(r'\b([ap])\s*\.?\s*m\.?(?=[^a-z]|$)',
                 lambda m: m.group(1).upper()+'M', text, flags=re.I)
    hour_names = '|'.join(_SPOKEN_HOURS)
    def word_to_digit(m):
        return str(_SPOKEN_HOURS[m.group(1).lower()]) + ' ' + m.group(2).upper()
    out = re.sub(r'\b('+hour_names+r')\s+(AM|PM)\b',
                 word_to_digit, out, flags=re.I)
    # Clearly specified parts of day are safe to normalize; don't guess "at ten".
    def daypart_to_clock(m):
        raw = m.group(1).lower()
        hour = _SPOKEN_HOURS.get(raw, int(raw) if raw.isdigit() else 0)
        part = m.group(2).lower()
        meridian = 'AM' if part == 'morning' else 'PM'
        return f'{hour}:00 {meridian}'
    out = re.sub(
        r"\b(1[0-2]|[1-9]|"+hour_names+r")\s+(?:o['’]clock\s+)?in\s+the\s+(morning|afternoon|evening)\b",
        daypart_to_clock, out, flags=re.I)
    return out


def _explicit_month_date(text, today):
    """Parse explicit month/day including an ordinal even if older routing missed it.

    None means unsupported, invalid, or a conflicting named weekday; do not
    invent a date for conflicting speech.
    """
    pattern = r'\b('+'|'.join(sorted(_MONTHS, key=len, reverse=True))+r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b'
    found = re.search(pattern, text, re.I)
    if not found:
        return False, None  # no explicit month, defer to baseline date parser
    month = _MONTHS[found.group(1).lower()]
    try:
        year = int(found.group(3)) if found.group(3) else today.year
        day = date(year, month, int(found.group(2)))
        if not found.group(3) and day < today:
            day = day.replace(year=year+1)
    except ValueError:
        return True, None
    prefix = text[max(0, found.start()-25):found.start()]
    preceding = re.search(r'\b('+ '|'.join(_WEEKDAYS) + r')\s*,?\s*$', prefix, re.I)
    if preceding and day.weekday() != _WEEKDAYS[preceding.group(1).lower()]:
        return True, None
    return True, day


def _duration_minutes(text):
    found = re.search(r'\b(?:for|lasting)\s+(\d{1,3}|forty[- ]five|fifteen|thirty|twenty|sixty|five|ten|one|two)\s*(minutes?|mins?|hours?|hrs?)\b', text, re.I)
    if found:
        number = _SPOKEN_DURATIONS.get(found.group(1).lower())
        if number is None:
            number = int(found.group(1))
        return number * (60 if found.group(2).lower().startswith(('hour','hr')) else 1)
    if re.search(r'\b(?:for|lasting)\s+(?:an?|one)\s+hour\b', text, re.I):
        return 60
    if re.search(r'\b(?:for|lasting)\s+half\s+an?\s+hour\b', text, re.I):
        return 30
    return None


def calendar_create_intent(prompt):
    """Catch incomplete single calendar commands before the generic write guard.

    Never approve/save here. Compound or destructive requests remain blocked
    by the existing agent/guardrail rather than being treated as calendar drafts.
    """
    if not isinstance(prompt, str) or len(prompt) > 520:
        return False
    text = _wake(prompt)
    if re.search(r'\b(?:email|send|invite|share|delete|cancel|reschedule|move|also|and then|as well as|plus)\b', text, re.I):
        return False
    if re.match(r'^(?:please\s+)?(?:schedule|create|add|save|record|put)\b', text, re.I):
        return bool(re.search(r'\b(?:calendar|events?|appointments?|meetings?|birthdays?)\b', text, re.I))
    return bool(re.match(r'^(?:i\s+(?:have|will\s+have)|remember\s+that\s+i\s+have)\b', text, re.I)
                and re.search(r'\b(?:appointments?|birthdays?|meetings?)\b', text, re.I))

def parse_voice_calendar(prompt, today=None):
    """Propose a single event/note; never execute writes or combine requests."""
    if not isinstance(prompt,str) or not 3<len(prompt)<520: return None
    text=_normalize_calendar_speech(_wake(prompt))
    if re.search(r'\b(?:email|send|invite|share|delete|cancel|reschedule|move|also|and then|as well as|plus)\b',text,re.I): return None
    note=re.fullmatch(r'(?:make|save|write|take|add)\s+(?:me\s+)?a\s+note\s*(?:that|to|:)?\s*(.{3,400})',text,re.I)
    if note: return {'kind':'note','content':note.group(1).strip().rstrip('.')}
    note=re.fullmatch(r'(?:note\s+to\s+self|remember\s+this)\s*:\s*(.{3,400})',text,re.I)
    if note: return {'kind':'note','content':note.group(1).strip().rstrip('.')}
    note=re.fullmatch(r'(?:please\s+)?(?:remember|note)\s+that\s+(?!i\s+have\s+(?:a\s+)?(?:dentist|pediatrician|doctor)\s+appointment)(.{3,400})',text,re.I)
    if note: return {'kind':'note','content':note.group(1).strip().rstrip('.')}
    event_intent=bool(re.match(r'(?:i\s+(?:have|will\s+have)\b|(?:please\s+)?(?:create|add|save|schedule|record|put)\b|remember\s+that\s+i\s+have\b)',text,re.I))
    if not event_intent: return None
    # Do not attempt to book an external provider or claim appointment availability.
    if re.search(r'\b(?:book\s+me|find\s+(?:me\s+)?an?\s+(?:available|open)\s+(?:slot|appointment))\b',text,re.I):return None
    reference_day = today or date.today()
    explicitly_dated, explicit_day = _explicit_month_date(text, reference_day)
    day = explicit_day if explicitly_dated else _date_from_text(text, reference_day)
    if day is None:return None
    birthday=re.search(r'\bbirthday\b',text,re.I)
    if birthday:
        name=re.search(r'(?:(?:for|my)\s+)?([A-Za-zÀ-žА-Яа-я][\wÀ-žА-Яа-я-]{0,40})\s*[\'’]s\s+birthday\b',text,re.I)
        if not name: name=re.search(r'\bbirthday\s+(?:for|of)\s+([A-Za-zÀ-žА-Яа-я][\wÀ-žА-Яа-я\s-]{0,50}?)(?:\s+(?:on|at)\b|$)',text,re.I)
        if not name: name=re.search(r'\b(?:add|save|schedule|create)\s+(?:my\s+)?([A-Za-zÀ-žА-Яа-я][\wÀ-žА-Яа-я-]{0,50})\s+birthday\b',text,re.I)
        label=(name.group(1).strip() if name else 'Family')+' birthday'
        return {'kind':'event','event':make_event(label,day,'9:00 AM',kind='birthday',repeat='yearly',notes='Annual birthday; 9:00 AM reminder anchor (editable).')}
    time_matches=re.findall(r'(?<!\w)(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*[AP]M\b',text,re.I)
    if not time_matches: return None
    try:
        start=clock_12(time_matches[0]); end=clock_12(time_matches[1]) if len(time_matches)>1 else ''
        duration = _duration_minutes(text)
        if duration is not None:
            if duration <= 0 or duration > 720: return None  # no silently inferred overnight end
            hhmm = parse_clock(start)
            start_minutes = int(hhmm[:2]) * 60 + int(hhmm[3:])
            end_minutes = start_minutes + duration
            if end_minutes >= 1440: return None  # current calendar model: single-day events
            # v2.9.1: Format the end time directly as a 12-hour clock.
            # mina_saved_places.parse_clock() accepts user-facing 12-hour strings,
            # but does not necessarily accept a bare 24-hour string like "10:15".
            end_hour_24, end_minute = divmod(end_minutes, 60)
            end_meridian = 'AM' if end_hour_24 < 12 else 'PM'
            derived_end = f'{end_hour_24 % 12 or 12}:{end_minute:02d} {end_meridian}'
            if end and parse_clock(end) != parse_clock(derived_end): return None
            end = derived_end
        if end and parse_clock(end)<=parse_clock(start): return None
    except (CalendarError,ValueError): return None
    if re.search(r'\bdentist|dental\b',text,re.I): title='Dentist appointment'; k='appointment'
    elif re.search(r'\bpediatrician|pediatric\b',text,re.I):title='Pediatrician appointment'; k='appointment'
    elif re.search(r'\bdoctor|appointment|checkup\b',text,re.I):
        k='appointment'; title='Appointment'
        named = re.search(
            r'^(?:please\s+)?(?:schedule|create|add|save|record|put)\s+(?:an?\s+)?(.+?)'
            r'(?=\s+(?:(?:on|for)\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|today|tomorrow)\b'
            r'|\s+(?:on|for)\s+\d{1,2}[/.\-]\d{1,2})', text, re.I)
        if named and re.search(r'\b(?:appointment|checkup)\b',named.group(1),re.I):
            title=named.group(1).strip().capitalize()[:90]
    else:
        # extract a simple title before a date expression; do not pretend to parse arbitrary text
        title_match=re.search(r'(?:create|add|schedule|save|record|put|i\s+have)\s+(?:an?\s+)?(?:event\s*:?\s+)?(.+?)\s+(?:for|on)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|tomorrow|today|\d)',text,re.I)
        title=(title_match.group(1).strip() if title_match else 'Family event')[:90]
        k='event'
    return {'kind':'event','event':make_event(title,day,start,end,kind=k)}


# v2.13.1: explicit negative safety instructions are not positive writes.
# Restrict stripping to simple negated action + object spans; affirmative writes
# in the rest of a compound request must still block the read-only path.
_READONLY_NEGATION = re.compile(
    r"\b(?:don['\u2019]t|do\s+not|never)\s+"
    r"(?:add|create|delete|change|update|modify|cancel|schedule|save|send)"
    r"(?:\s+(?:or|and)\s+(?:add|create|delete|change|update|modify|cancel|schedule|save|send))*"
    r"\s+(?:anything|any\s+events?|my\s+(?:events?|calendar|schedule)|"
    r"calendar\s+events?|appointments?|notes?|shopping\s+lists?)\b", re.I)


def _read_only_calendar_text(prompt):
    return _READONLY_NEGATION.sub(' ', prompt)


def calendar_read_intent(prompt, today=None):
    """Detect agenda/notes questions without letting generic external guard intercept."""
    if not isinstance(prompt,str) or len(prompt)>360:return None
    text=_read_only_calendar_text(_wake(prompt))
    if re.search(r'\b(?:add|create|delete|send|book|schedule|cancel|change|update|modify|save)\b',text,re.I):return None
    if re.search(r'(?:show|read|what(?:\'s| is)?\s+in)\s+(?:me\s+)?(?:my\s+)?notes\b|what\s+notes\s+do\s+i\s+have',text,re.I): return ('notes',None)
    if re.search(r'(?:what|show|tell|when|list|do\s+i\s+have|any)\b',text,re.I) and re.search(r'\b(?:calendar|schedule|appointments?|events?|birthdays?|plans?)\b',text,re.I):
        day=_date_from_text(text,today or date.today())
        return ('agenda',day)
    return None


def format_agenda(data,day=None,now=None):
    now=now or date.today(); a=agenda(data,start=now,days=400)
    if day: a=[e for e in a if e['date']==day.isoformat()]
    if not a: return 'No saved MINA events for that date. Google Calendar is checked separately when connected.'
    lines=['**Your MINA calendar** (local entries; DEMO entries are fictional):']
    for e in a[:15]:
        prefix='[DEMO] ' if e['source']=='demo' else ''
        recurring=' · yearly' if e['repeat']=='yearly' else ''
        lines.append(f"- {e['date']} · {e['time']} · {prefix}{e['title']}{recurring}")
    return '\n'.join(lines)
