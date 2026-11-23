"""Small deterministic multi-turn slot-filler for local list/calendar proposals.

Session-scoped. Never writes anything; existing confirmation buttons still govern
real writes. Route continuation lives independently in v2.14.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
from time import time
from mina_reminders_v215 import _parse_date, _parse_time, ReminderError

VERSION='2.15.0'
STORES={'target':'target','costco':'costco','trader joes':'trader_joes',"trader joe's":'trader_joes', 'grocery':'grocery'}

@dataclass(frozen=True)
class Decision:
    kind:str='none'
    message:str=''
    pending:dict|None=None
    action:dict|None=None

def _clean(text:str):
    return re.sub(r'^(?:mina\s*[,.:!]\s*)?','',text.strip(),flags=re.I).strip()

def _store(text:str):
    key=re.sub(r'\s+',' ',text.lower().strip(' .!?,')).replace('’',"'")
    return STORES.get(key)

def _calendar_time_answer(text:str,anchor:date):
    """Full date plus AM/PM; never invent user-omitted year or hour."""
    s=text.strip().strip('.!? ')
    datepart=r'(tomorrow|today|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})'
    timepart=r'(\d{1,2}(?::\d{2})?\s*[AaPp]\.?[Mm]\.?)'
    m=re.fullmatch(datepart+r'\s+(?:at\s+)?'+timepart,s,re.I)
    if not m:return None
    try:
        d=_parse_date(m.group(1),anchor);t=_parse_time(m.group(2))
    except ReminderError:return None
    return {'date':d.isoformat(),'time':t.strftime('%I:%M %p').lstrip('0')}

def _new_request(s:str):
    # No arbitrary NLP guesses. Only supported incomplete commands are captured.
    m=re.fullmatch(r'(?:please\s+)?add\s+(.{1,100}?)\s+to\s+(?:my\s+)?(?:shopping|grocery)\s+list[.!]?',s,re.I)
    if m:
        item=m.group(1).strip()
        if item and len(item)<=100 and not re.search(r'\b(?:delete|remove|clear|all)\b',item,re.I):
            return Decision('ask_store',f'Which store should I add **{item}** to: Target, Costco, or Trader Joe\'s?',
                            {'kind':'list','item':item,'created_at':time()})
    m=re.fullmatch(r'(?:please\s+)?(?:schedule|add(?: a)? calendar event for)\s+(?:an?\s+)?(.{3,100}?)\s*(?:appointment|meeting|event)?[.!]?',s,re.I)
    if m and not re.search(r'\b(?:at\s+\d|on\s+(?:november|tomorrow|today|\d{4}))\b',s,re.I):
        title=m.group(1).strip()
        if title and len(title)>2:
            return Decision('ask_calendar',f'When should I schedule **{title}**? Please say the full date and time, e.g. November 24, 2026 at 10:00 AM.',
                            {'kind':'calendar','title':title,'created_at':time()})
    return Decision()

def handle(pending:dict|None,text:str,*,today:date):
    s=_clean(text)
    if pending:
        if time() - float(pending.get('created_at',0)) > 1800:
            return Decision('expired','That unfinished request expired. Please start a new request; nothing was changed.')
        if re.fullmatch(r'(?:cancel|never mind|nevermind|stop)(?:\s+(?:that|this|pending|the|my|task|request|event|list|calendar|change|update|plan))*\s*[.!]?',s,re.I):
            return Decision('cancel','Cancelled that pending request. No list or calendar changes were made.')
        # New actionable request supersedes the pending task, not the opposite.
        if re.match(r'^(?:what|show|list|remind|plan|navigate|find|add|remove|delete|schedule|send|draft)\b',s,re.I):
            d=_new_request(s)
            return d if d.kind!='none' else Decision('new_request')
        if pending.get('kind')=='list':
            store=_store(s)
            if store:
                return Decision('list_ready',pending=None,
                    action={'kind':'list','store':store,'items':[pending['item']]})
            return Decision('reprompt',f'Please choose a store for **{pending["item"]}**: Target, Costco, or Trader Joe\'s. Or say Cancel.',pending)
        if pending.get('kind')=='calendar':
            when=_calendar_time_answer(s,today)
            if when:
                return Decision('calendar_ready',pending=None,
                    action={'title':pending['title'],**when})
            return Decision('reprompt','Please provide a full date and AM/PM time, e.g. November 24, 2026 at 10:00 AM. Or say Cancel.',pending)
        return Decision('new_request')
    return _new_request(s)
