"""Strict, confirmation-first parsing and execution of multi-store shopping-list adds.

Only recognizes well-structured list additions. Ambiguous commands must never be
silently reinterpreted as a single-store write.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Callable


STORE_LABELS = {'target': 'Target', 'costco': 'Costco', 'trader_joes': "Trader Joe's"}
_STORE_PATTERN = r"(?:Trader\s+Joe(?:['’])?s?|Costco|Target)"
_STORE_MENTION = re.compile(rf"\b{_STORE_PATTERN}\b", re.I)
_DESTINATION = re.compile(
    rf"\b(?:to|into|on)\s+(?:(?:my|our|the)\s+)?"
    rf"(?P<store>{_STORE_PATTERN})\s+(?:(?:shopping|grocery)\s+)?list\b",
    re.I,
)
_START = re.compile(
    r"^\s*(?:(?:hey|hi)\s+)?(?:mina\s*[,!:.]?\s*)?"
    r"(?:please\s+)?(?:add|put|include)\s+",
    re.I,
)
_BAD_ITEM = re.compile(
    r"\b(?:shopping\s+list|grocery\s+list|list|send|email|delete|remove|schedule|appointment|"
    r"calendar|pay|transfer|confirm|add\s+another|also\s+add)\b", re.I)


class MultiStoreParseError(ValueError):
    """This is a multi-store request but it is unsafe to infer the mapping."""


def store_key(name: str) -> str:
    clean = re.sub(r"[’']", '', name).lower()
    if 'trader' in clean:
        return 'trader_joes'
    if 'target' in clean:
        return 'target'
    if 'costco' in clean:
        return 'costco'
    raise MultiStoreParseError('Unrecognized store.')


def is_multi_store_add_request(message: str) -> bool:
    """Early guard: even if detailed parsing fails, do not fall back to one store."""
    msg = str(message or '')
    mentions = {store_key(m.group()) for m in _STORE_MENTION.finditer(msg)}
    return len(mentions) >= 2 and bool(re.search(r'\b(?:add|put|include)\b', msg, re.I))


def _parse_items(piece: str) -> list[str]:
    # Strip only grammatical connectors, never a store instruction from inside an item.
    piece = piece.strip().strip(' ,;:')
    piece = re.sub(r'^(?:(?:and|also|then|please)\s+|[,;]\s*)+', '', piece, flags=re.I)
    piece = piece.strip().strip(' ,;:')
    if not piece or re.search(r'\b(?:to|into|on)\s+(?:my\s+|our\s+|the\s+)?(?:target|costco|trader)\b', piece, re.I):
        raise MultiStoreParseError('Shopping-list destination was mixed into an item.')
    parts = re.split(r'\s*,\s*(?:and\s+)?|\s+\band\b\s+', piece, flags=re.I)
    items = []
    for item in parts:
        item = item.strip().strip('.!?;:,')
        if not item or len(item) > 80 or _BAD_ITEM.search(item) or _STORE_MENTION.search(item):
            raise MultiStoreParseError('Could not separate the requested items safely.')
        if not re.fullmatch(r"[\w\s'’&+()\-./]+", item, re.UNICODE):
            raise MultiStoreParseError('Unrecognized wording in a shopping item.')
        items.append(item)
    if not (1 <= len(items) <= 10):
        raise MultiStoreParseError('Expected between 1 and 10 items for each store.')
    return items


def parse_multi_store_add(message: str) -> dict[str, list[str]] | None:
    """Return per-store items or None for non-multi-store requests.

    Raise MultiStoreParseError instead of guessing when two stores are mentioned
    but distinct item groups cannot be proven from syntax.
    """
    if not is_multi_store_add_request(message):
        return None
    msg = str(message or '').strip()
    beginning = _START.match(msg)
    if not beginning:
        raise MultiStoreParseError('Please start the request with “add” and name each destination list.')
    destinations = list(_DESTINATION.finditer(msg))
    if len(destinations) < 2:
        raise MultiStoreParseError('Please say which items belong to each shopping list.')
    # All store names in the request must be covered by a destination match.
    store_mentions = list(_STORE_MENTION.finditer(msg))
    if len(store_mentions) != len(destinations):
        raise MultiStoreParseError('One or more store names were not attached to a shopping list.')
    tail = msg[destinations[-1].end():].strip().strip('.!? ')
    if tail:
        raise MultiStoreParseError('Extra instructions after the last shopping list are not supported.')
    by_store: dict[str, list[str]] = {}
    prev_end = beginning.end()
    for dest in destinations:
        name = store_key(dest.group('store'))
        if name in by_store:
            raise MultiStoreParseError('Please mention each store only once per request.')
        item_segment = msg[prev_end:dest.start()]
        by_store[name] = _parse_items(item_segment)
        prev_end = dest.end()
    if sum(len(v) for v in by_store.values()) > 20:
        raise MultiStoreParseError('Too many shopping items in one request.')
    return by_store


def prepare_multi_store_action(message: str) -> dict | None:
    parsed = parse_multi_store_add(message)
    if parsed is None:
        return None
    return {'kind': 'multi_list', 'stores': parsed}


def preview_multi_store_action(action: dict) -> str:
    if action.get('kind') != 'multi_list':
        raise MultiStoreParseError('Not a multi-list action.')
    result = ['**Proposed local shopping-list updates (not saved yet):**']
    for key, items in action['stores'].items():
        result.append(f'\n**{STORE_LABELS[key]}**')
        result.extend(f'- {item}' for item in items)
    result.append('\n**Nothing has been saved.** Review both lists, then press **Confirm local list update** or cancel. No external service will be contacted.')
    return '\n'.join(result)


def commit_multi_store_action(hub: dict, action: dict, add_item_fn: Callable) -> dict:
    """Stage ALL additions on a copy, then let caller persist once after approval.

    The caller must never save until this function returns successfully.
    """
    stores = action.get('stores') if action.get('kind') == 'multi_list' else None
    if not isinstance(stores, dict) or len(stores) < 2:
        raise MultiStoreParseError('Invalid multi-store update.')
    if set(stores) - set(STORE_LABELS):
        raise MultiStoreParseError('Invalid destination store.')
    if not isinstance(hub, dict) or not isinstance(hub.get('stores'), dict):
        raise MultiStoreParseError('Local shopping lists are unavailable.')
    if not set(stores).issubset(hub['stores']):
        raise MultiStoreParseError('One or more destination lists do not exist locally.')
    current = deepcopy(hub)
    for key, items in stores.items():
        if not isinstance(items, list) or not items or len(items) > 10:
            raise MultiStoreParseError('Invalid items for a destination list.')
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item) > 80 or _BAD_ITEM.search(item) or _STORE_MENTION.search(item):
                raise MultiStoreParseError('Unsafe item detected; nothing was saved.')
            # Reuse the existing validated single-item Family Hub function.
            current = add_item_fn(current, key, item.strip())
    return current


def remove_one_local_item(hub: dict, store: str, item_id: str) -> dict:
    """One exact ID, one exact store; returns a copy, never mutates the caller."""
    if store not in STORE_LABELS or store not in hub.get('stores', {}):
        raise MultiStoreParseError('Unknown shopping list.')
    current = deepcopy(hub)
    items = current['stores'][store]
    matches = [x for x in items if x.get('id') == item_id]
    if len(matches) != 1:
        raise MultiStoreParseError('Selected item was not found; nothing was removed.')
    current['stores'][store] = [x for x in items if x.get('id') != item_id]
    return current
