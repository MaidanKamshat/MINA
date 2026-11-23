"""MINA v2.6 local reminders and after-visit follow-ups.

These are *in-app* notices based on local user-entered appointments. No
push delivery, OS background process, calendar provider, or external writes.
Saved acknowledgements avoid repeatedly prompting after each Streamlit rerun.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any

from mina_family_hub import FamilyHubError, PAIRS, STORES, validate_hub, pending_items
from mina_saved_places import parse_clock

LOCAL_FOLLOWUPS = Path(__file__).resolve().parent / 'local_data' / 'mina_followups.json'
MAX_BYTES = 30_000
_ALLOWED_OUTCOMES = {'attended', 'missed', 'later'}
_ALLOWED_SHOPPING = {'all_purchased', 'not_yet', 'partial'}


def blank_followups() -> dict:
    return {'schema_version': '1.0', 'reminders_ack': {}, 'visit_outcomes': {}, 'shopping_outcomes': {}}


def validate_followups(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {'schema_version', 'reminders_ack', 'visit_outcomes', 'shopping_outcomes'} or data['schema_version'] != '1.0':
        raise FamilyHubError('Invalid local follow-up data.')
    for field in ('reminders_ack', 'visit_outcomes', 'shopping_outcomes'):
        if not isinstance(data[field], dict) or len(data[field]) > 250:
            raise FamilyHubError('Invalid local follow-up entries.')
        for key, value in data[field].items():
            if not isinstance(key, str) or not re.fullmatch(r'visit_[0-9]{1,5}(?::(?:24h|2h))?', key):
                raise FamilyHubError('Invalid local follow-up identifier.')
            if field == 'reminders_ack' and value is not True:
                raise FamilyHubError('Invalid reminder acknowledgement.')
            if field == 'visit_outcomes' and value not in _ALLOWED_OUTCOMES:
                raise FamilyHubError('Invalid visit outcome.')
            if field == 'shopping_outcomes' and value not in _ALLOWED_SHOPPING:
                raise FamilyHubError('Invalid shopping outcome.')
    return data


def load_followups(path: Path = LOCAL_FOLLOWUPS) -> dict:
    path = Path(path)
    if not path.exists():
        return blank_followups()
    try:
        if path.stat().st_size > MAX_BYTES:
            raise FamilyHubError('Local follow-up data too large.')
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FamilyHubError('Unable to read local follow-up data.') from exc
    return validate_followups(data)


def save_followups(data: dict, path: Path = LOCAL_FOLLOWUPS) -> Path:
    validate_followups(data)
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise FamilyHubError('Too many local follow-up entries.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.mina_followups_', dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as fp:
            fp.write(raw)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _valid_id(visit_id: str) -> str:
    if not isinstance(visit_id, str) or not re.fullmatch(r'visit_[0-9]{1,5}', visit_id):
        raise FamilyHubError('Invalid visit ID.')
    return visit_id


def acknowledge(data: dict, visit_id: str, stage: str) -> dict:
    validate_followups(data)
    _valid_id(visit_id)
    if stage not in {'24h', '2h'}:
        raise FamilyHubError('Invalid reminder stage.')
    updated = copy.deepcopy(data)
    updated['reminders_ack'][f'{visit_id}:{stage}'] = True
    return validate_followups(updated)


def record_visit(data: dict, visit_id: str, result: str) -> dict:
    validate_followups(data)
    _valid_id(visit_id)
    if result not in _ALLOWED_OUTCOMES:
        raise FamilyHubError('Invalid visit check-in response.')
    new = copy.deepcopy(data)
    new['visit_outcomes'][visit_id] = result
    return validate_followups(new)


def record_shopping(data: dict, visit_id: str, result: str) -> dict:
    validate_followups(data)
    _valid_id(visit_id)
    if result not in _ALLOWED_SHOPPING:
        raise FamilyHubError('Invalid shopping check-in response.')
    new = copy.deepcopy(data)
    new['shopping_outcomes'][visit_id] = result
    return validate_followups(new)


def visit_start(visit: dict, tzinfo: Any) -> datetime:
    hhmm = parse_clock(visit['time'])
    return datetime.fromisoformat(f"{visit['date']}T{hhmm}").replace(tzinfo=tzinfo)


def due_reminders(hub: dict, data: dict, *, now: datetime) -> list[dict]:
    """One visible stage per visit: 24h notice then 2h notice.

    Notices are shown only while the app is open, once their trigger time has
    been reached, and before the visit. No false statement of push delivery.
    """
    validate_hub(hub)
    validate_followups(data)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware now required.')
    messages = []
    for visit in hub['visits']:
        start = visit_start(visit, now.tzinfo)
        remaining = start - now
        if not timedelta(0) < remaining <= timedelta(days=1):
            continue
        stage = '2h' if remaining <= timedelta(hours=2) else '24h'
        if data['reminders_ack'].get(f"{visit['id']}:{stage}"):
            continue
        paired = next((store for place, store in PAIRS if place == visit['place']), None)
        items = pending_items(hub, paired) if paired else []
        messages.append({'visit': visit, 'stage': stage, 'paired_store': paired,
                         'pending_items': items, 'minutes_remaining': int(remaining.total_seconds() // 60)})
    return sorted(messages, key=lambda x: (x['visit']['date'], parse_clock(x['visit']['time'])))


def due_checkins(hub: dict, data: dict, *, today: date) -> list[dict]:
    """Ask about yesterday's visits, without assuming attendance/purchases."""
    validate_hub(hub)
    validate_followups(data)
    yesterday = (today - timedelta(days=1)).isoformat()
    result = []
    for visit in hub['visits']:
        if visit['date'] != yesterday:
            continue
        state = data['visit_outcomes'].get(visit['id'])
        paired_store = next((store for place, store in PAIRS if place == visit['place']), None)
        shopping_state = data['shopping_outcomes'].get(visit['id'])
        items = pending_items(hub, paired_store) if paired_store else []
        if not state or (state == 'attended' and paired_store and items and not shopping_state):
            result.append({'visit': visit, 'visit_outcome': state,
                           'paired_store': paired_store, 'shopping_outcome': shopping_state,
                           'pending_items': items})
    return result


def clear_store_after_purchase(hub: dict, store_id: str, *, expected_item_ids: list[str]) -> dict:
    """Clears a *single* store only after separate explicit confirmation.

    Reject stale snapshots: items added after proposal must not be deleted.
    """
    validate_hub(hub)
    if store_id not in STORES:
        raise FamilyHubError('Unknown shopping list.')
    actual = [it['id'] for it in hub['stores'][store_id]]
    if not actual or not isinstance(expected_item_ids, list) or actual != expected_item_ids:
        raise FamilyHubError('Shopping list changed; review it again before clearing.')
    new = copy.deepcopy(hub)
    new['stores'][store_id] = []
    return validate_hub(new)


def parse_purchased_all(prompt: str) -> str | None:
    """Only explicit single-store *completed purchase* phrases qualify.

    'Yes' by itself, 'buy everything', and mixed external actions cannot clear.
    """
    if not isinstance(prompt, str) or len(prompt) > 250:
        return None
    text = re.sub(r"^\s*(?:(?:hey|hi)\s+)?mina\b\s*[,.:!]?\s*", '', prompt, flags=re.I).strip()
    if re.search(r'\b(?:calendar|email|send|book|appointment|and then|notify|invite)\b', text, re.I):
        return None
    if not re.search(r'\b(?:bought|purchased|got|picked up)\b', text, re.I):
        return None
    if not re.search(r'\b(?:all|everything|entire|whole)\b', text, re.I):
        return None
    found = []
    for key, rgx in {'target': r'\btarget\b', 'costco': r'\bcostco\b',
                     'trader_joes': r'\btrader\s+joe(?:s|\'s|’s)\b'}.items():
        if re.search(rgx, text, re.I):
            found.append(key)
    return found[0] if len(found) == 1 else None


def parse_yesterday_visit_status(prompt: str, hub: dict, data: dict, *, today: date) -> dict | None:
    """Explicit spoken yes/no for one locally recorded visit from yesterday.

    Does not act on a bare 'yes' or any compound external write request.
    """
    import re
    if not isinstance(prompt, str) or len(prompt) > 210:
        return None
    validate_hub(hub)
    validate_followups(data)
    text = re.sub(r'^\s*(?:(?:hey|hi)\s+)?mina\b[,.:!\s-]*', '', prompt, flags=re.I).strip()
    if re.search(r'\b(?:and|also|calendar|email|send|book|add|cancel|reschedule|remind|notify)\b', text, re.I):
        return None
    positive = re.fullmatch(
        r"(?:(?:yes|yeah)[,!]?\s+)?i\s+(?:went\s+to|made\s+it\s+to|visited|attended)\s+"
        r"(?:(?:my|the)\s+)?(?:dentist|pediatrician|library)(?:\s+appointment)?"
        r"(?:\s+yesterday)?[.!?]?", text, re.I,
    )
    negative = re.fullmatch(
        r"(?:(?:no|nope)[,!]?\s+)?i\s+(?:missed|did(?:n'?t| not)\s+go\s+to|"
        r"could(?:n'?t| not)\s+make\s+it\s+to)\s+(?:(?:my|the)\s+)?"
        r"(?:dentist|pediatrician|library)(?:\s+appointment)?(?:\s+yesterday)?[.!?]?",
        text, re.I,
    )
    if not positive and not negative:
        return None
    place = next((p for p in ('dentist','pediatrician','library') if p in text.lower()), None)
    if not place:
        return None
    yesterday = (today - timedelta(days=1)).isoformat()
    matches = [v for v in hub['visits'] if v['place'] == place and v['date'] == yesterday
               and v['id'] not in data['visit_outcomes']]
    if len(matches) != 1:
        return None
    return {'visit_id': matches[0]['id'], 'place': place,
            'outcome': 'attended' if positive else 'missed'}


def parse_yesterday_shopping_status(prompt: str, hub: dict, data: dict, *, today: date) -> dict | None:
    """Explicit 'not yet' or 'only some' after yesterday's paired appointment."""
    if not isinstance(prompt, str) or len(prompt) > 220:
        return None
    validate_hub(hub)
    validate_followups(data)
    text = re.sub(r'^\s*(?:(?:hey|hi)\s+)?mina\b[,.:!\s-]*', '', prompt, flags=re.I).strip()
    if re.search(r'\b(?:and|also|calendar|email|send|book|add|cancel|reschedule)\b', text, re.I):
        return None
    matched_store = None
    for store, name in [('costco','Costco'), ('target','Target'), ('trader_joes',"Trader Joe's")]:
        phrase = r'trader\s+joe(?:\'s|s|’s)' if store=='trader_joes' else re.escape(name)
        if re.search(r'\b'+phrase+r'\b', text, re.I):
            if matched_store:
                return None
            matched_store = store
    if not matched_store:
        return None
    if re.fullmatch(r"(?:no[,]?\s+)?i\s+(?:did(?:n'?t| not)\s+(?:go\s+to|shop\s+at)|"
                    r"haven'?t\s+(?:gone\s+to|shopped\s+at))\s+(?:the\s+)?"
                    r".+?(?:\s+yesterday)?[.!?]?", text, re.I):
        outcome = 'not_yet'
    elif re.fullmatch(r'(?:i\s+)?(?:bought|purchased|got)\s+(?:only\s+)?some\s+'
                      r'(?:items\s+)?(?:at|from)\s+(?:the\s+)?'
                      r'.+?(?:\s+yesterday)?[.!?]?', text, re.I):
        outcome = 'partial'
    else:
        return None
    yesterday = (today - timedelta(days=1)).isoformat()
    matches = [v for v in hub['visits'] if v['date'] == yesterday
               and any(v['place'] == p and matched_store == store for p, store in PAIRS)
               and data['visit_outcomes'].get(v['id']) == 'attended'
               and v['id'] not in data['shopping_outcomes']]
    if len(matches) != 1:
        return None
    return {'visit_id':matches[0]['id'], 'store': matched_store, 'outcome': outcome}
