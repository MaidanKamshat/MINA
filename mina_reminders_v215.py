"""MINA v2.15: standalone user-owned reminders independent from calendar.

Preview/confirm via Streamlit UI; no background or push delivery, no Gmail writes.
"""
from __future__ import annotations
import json, os, re, uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

VERSION='2.15.0'
STORE=Path.home()/'.mina'/'reminders_v215.json'
class ReminderError(ValueError): pass

def read(path:Path=STORE):
    if not path.exists(): return []
    try:
        d=json.loads(path.read_text(encoding='utf-8'))
        if d.get('version')!=1 or not isinstance(d.get('reminders'), list): raise ValueError()
        out=d['reminders']
        ids=set()
        for item in out:
            if not isinstance(item,dict) or set(item) != {'id','title','due','done'}: raise ValueError()
            if not isinstance(item['title'],str) or not item['title'].strip() or len(item['title'])>240: raise ValueError()
            if type(item['done']) is not bool or not isinstance(item['id'],str) or item['id'] in ids: raise ValueError()
            if datetime.fromisoformat(item['due']).tzinfo is None: raise ValueError()
            ids.add(item['id'])
        return out
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise ReminderError('Saved standalone reminders need repair.') from exc

def write(items:list,path:Path=STORE):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=='posix':
        try: path.parent.chmod(0o700)
        except OSError: pass
    with NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.reminders-',delete=False) as f:
        temp=Path(f.name)
        try:
            os.chmod(temp,0o600)
            json.dump({'version':1,'reminders':items},f,ensure_ascii=False,indent=2)
            f.flush();os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True);raise
    os.replace(temp,path)

def _parse_date(s:str,today:date):
    s=s.strip().strip('.,')
    if s.lower()=='tomorrow': return today+timedelta(days=1)
    if s.lower()=='today': return today
    for pattern in ('%B %d, %Y','%B %d %Y','%b %d, %Y','%Y-%m-%d'):
        try:return datetime.strptime(s,pattern).date()
        except ValueError: pass
    raise ReminderError('Please include the complete date, e.g. November 24, 2026.')

def _parse_time(s:str):
    s=s.strip().upper().replace('.','')
    s=re.sub(r'\s+', ' ', s)
    for pattern in ('%I:%M %p','%I %p'):
        try: return datetime.strptime(s,pattern).time()
        except ValueError: pass
    raise ReminderError('Please specify time with AM/PM, e.g. 9:00 AM.')

def parse_create(text:str,*,today:date,timezone_name:str):
    s=re.sub(r'^(?:mina\s*[,.:!]\s*)?','',text.strip(),flags=re.I)
    if not re.search(r'\bremind me\b',s,re.I): return None
    # Reminders have their own explicit intent, not the Calendar Agent.
    m=re.fullmatch(r'remind me (?:on )?(today|tomorrow|[A-Za-z]{3,9} \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}) at (\d{1,2}(?::\d{2})?\s*[AaPp]\.?[Mm]\.?) to (.{3,240})[.!]?',s,re.I)
    if not m: raise ReminderError('For a reminder, say “Remind me on November 24, 2026 at 9:00 AM to check the library books.”')
    day=_parse_date(m.group(1),today)
    when=_parse_time(m.group(2))
    try: local=datetime.combine(day,when,tzinfo=ZoneInfo(timezone_name))
    except (KeyError,ValueError) as exc:raise ReminderError('Invalid time zone.') from exc
    title=m.group(3).strip().rstrip('.')
    if len(title)>240:raise ReminderError('Reminder text is too long.')
    return {'title':title,'due':local.isoformat()}

def _clock(dt:datetime):return dt.strftime('%b %d, %Y at %-I:%M %p')

def describe(item:dict):
    return f"{item['title']} — {_clock(datetime.fromisoformat(item['due']))}"

def add(action:dict,*,path:Path=STORE):
    if not action or not action.get('title') or not action.get('due'):raise ReminderError('Missing reminder fields.')
    due=datetime.fromisoformat(action['due'])
    if due.tzinfo is None: raise ReminderError('Timezone is required.')
    current=read(path)
    r={'id':str(uuid.uuid4()),'title':str(action['title']).strip(),'due':due.isoformat(),'done':False}
    if len(r['title'])>240 or not r['title']:raise ReminderError('Invalid reminder name.')
    current.append(r);write(current,path)
    return r

def update(item_id:str,operation:str,*,path:Path=STORE):
    current=read(path)
    matching=[x for x in current if x['id']==item_id]
    if len(matching)!=1:raise ReminderError('Reminder no longer exists.')
    if operation=='done': matching[0]['done']=True
    elif operation=='delete': current=[x for x in current if x['id']!=item_id]
    else:raise ReminderError('Unsupported reminder operation.')
    write(current,path)

def listing(*,start:date|None=None,end:date|None=None,only_open=False,path:Path=STORE):
    items=read(path)
    if start is not None:items=[x for x in items if datetime.fromisoformat(x['due']).date()>=start]
    if end is not None:items=[x for x in items if datetime.fromisoformat(x['due']).date()<=end]
    if only_open: items=[x for x in items if not x['done']]
    return sorted(items,key=lambda x:x['due'])

def is_read(text:str):
    s=text.lower().strip()
    return bool(re.search(r'\b(?:what|show|list|do i have|any)\b',s) and re.search(r'\breminders?\b',s) and not re.search(r'\b(?:add|delete|remove|mark|set)\b',s))

def read_query(text:str,today:date):
    s=text.lower()
    if 'today' in s:return today,today
    if 'tomorrow' in s:return today+timedelta(days=1),today+timedelta(days=1)
    if 'this week' in s: return today,today+timedelta(days=6)
    # Standard date range with two full dates.
    dates=re.findall(r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}',s)
    if len(dates)>=2:return _parse_date(dates[0],today),_parse_date(dates[1],today)
    # Natural range such as 'November 22 through November 28, 2026'.
    ranged = re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s+(?:through|to|until|-)\s+(?:(january|february|march|april|may|june|july|august|september|october|november|december)\s+)?(\d{1,2}),?\s+(\d{4})',s)
    if ranged:
        m1,d1,m2,d2,y=ranged.groups()
        a=_parse_date(f'{m1} {d1}, {y}',today)
        b=_parse_date(f'{m2 or m1} {d2}, {y}',today)
        if b<a: raise ReminderError('Reminder range ends before it starts.')
        return a,b
    if len(dates)==1:
        d=_parse_date(dates[0],today);return d,d
    return None,None
