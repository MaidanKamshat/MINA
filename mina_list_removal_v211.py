"""MINA v2.11: confirmation-first, exact-ID voice removal from local shopping lists.

A spoken request proposes a SINGLE item deletion. It cannot write by itself.
A dedicated explicit approval path must call commit_remove_item_action and then save.
"""
from __future__ import annotations

from copy import deepcopy
import re

from mina_multi_store_v210 import STORE_LABELS


class ListRemovalError(ValueError):
    """A local removal request was ambiguous, unavailable, or stale."""


_STORE_NAME_RE = r"(?:Trader\s+Joe(?:['’])?s?|Target|Costco)"
_STORE_RE = re.compile(rf"\b{_STORE_NAME_RE}\b", re.I)
_WAKE = r"\s*(?:(?:hey|hi)\s+)?(?:mina\s*[,!:.]?\s*)?(?:please\s+)?"
_START = re.compile(rf"^{_WAKE}(?:(?:remove|delete)\s+|(?:take|cross)\s+)", re.I)
_REMOVE = re.compile(
    rf"^{_WAKE}(?:"
    rf"(?:remove|delete)\s+(?P<item_a>.+?)\s+from\s+"
    rf"|(?:take|cross)\s+(?P<item_b>.+?)\s+off\s+"
    rf")(?:(?:my|our|the)\s+)?(?P<store>{_STORE_NAME_RE})"
    rf"\s+(?:(?:shopping|grocery)\s+)?list\s*[.!?]?\s*$",
    re.I,
)
_UNSAFE = re.compile(
    r"\b(?:email|send|message|calendar|appointment|schedule|transfer|pay|"
    r"also\s+(?:add|remove|delete)|then\s+(?:add|remove|delete)|"
    r"shopping\s+list|grocery\s+list|confirm)\b",
    re.I,
)


def is_list_removal_request(message: str) -> bool:
    """Intercept shopping-list removals before the generic external-write guard."""
    s = str(message or '').strip()
    if not _START.match(s):
        return False
    return bool(_STORE_RE.search(s) or re.search(r'\b(?:shopping\s+list|grocery\s+list|list)\b', s, re.I))


def _store_key(store: str) -> str:
    s = re.sub(r"['’\s]", '', store).casefold()
    if s.startswith('traderjoe'):
        return 'trader_joes'
    if s == 'target':
        return 'target'
    if s == 'costco':
        return 'costco'
    raise ListRemovalError('The requested store is not supported.')


def _normalized_name(s: str) -> str:
    return ' '.join(s.split()).casefold()


def prepare_remove_item_action(message: str, hub: dict | None) -> dict:
    """Find exactly one matching saved item; return a proposal only, with no write."""
    if not is_list_removal_request(message):
        raise ListRemovalError('This does not look like a shopping-list removal request.')
    match = _REMOVE.fullmatch(str(message or '').strip())
    if not match:
        raise ListRemovalError(
            'Please say one item and one store, e.g., “Remove toothpaste from my Target shopping list.”'
        )
    # Do not accept extra store names in item names: the intended store is ambiguous.
    if len(_STORE_RE.findall(message)) != 1:
        raise ListRemovalError('Please use only one store per removal request.')
    name = (match.group('item_a') or match.group('item_b') or '').strip(' \t\r\n,.!?')
    if not name or len(name) > 80 or _UNSAFE.search(name) or not re.fullmatch(r"[\w\s'’&+()\-./]+", name, re.UNICODE):
        raise ListRemovalError('I could not identify one safe, specific item to remove.')
    store = _store_key(match.group('store'))
    if not isinstance(hub, dict) or not isinstance(hub.get('stores'), dict):
        raise ListRemovalError('Your local shopping-list data are not available.')
    items = hub['stores'].get(store)
    if not isinstance(items, list):
        raise ListRemovalError('That local shopping list is not available.')
    matches = [it for it in items if isinstance(it, dict)
               and isinstance(it.get('name'), str)
               and _normalized_name(it['name']) == _normalized_name(name)]
    if not matches:
        raise ListRemovalError(f'“{name}” was not found in {STORE_LABELS[store]}. Nothing was removed.')
    if len(matches) != 1:
        raise ListRemovalError(f'There is more than one “{name}” in {STORE_LABELS[store]}. Please remove the exact entry in Settings.')
    item = matches[0]
    if not isinstance(item.get('id'), str) or not item['id']:
        raise ListRemovalError('The saved item has no valid ID. Nothing was removed.')
    return {'kind': 'remove_item', 'store': store, 'item_id': item['id'], 'expected_name': item['name']}


def preview_remove_item_action(action: dict) -> str:
    if action.get('kind') != 'remove_item' or action.get('store') not in STORE_LABELS:
        raise ListRemovalError('Invalid removal preview.')
    return (
        '**Proposed local shopping-list removal (not saved yet):**\n\n'
        f'**Store:** {STORE_LABELS[action["store"]]}\n\n'
        f'**Remove exactly one item:** {action["expected_name"]}\n\n'
        '**Nothing has been removed.** Press **Confirm item removal** or **Cancel change**. '
        'No external service will be contacted.'
    )


def commit_remove_item_action(hub: dict, action: dict) -> dict:
    """Validate unchanged target, then remove exactly one ID on a copied hub.

    Persisting is the caller's responsibility, *only after explicit user approval*.
    """
    if not isinstance(action, dict) or action.get('kind') != 'remove_item':
        raise ListRemovalError('Invalid item removal action.')
    store, item_id, name = action.get('store'), action.get('item_id'), action.get('expected_name')
    if (store not in STORE_LABELS or not isinstance(item_id, str) or not item_id
            or not isinstance(name, str) or not name):
        raise ListRemovalError('Invalid target for item removal.')
    if not isinstance(hub, dict) or not isinstance(hub.get('stores'), dict):
        raise ListRemovalError('Local shopping lists are not available.')
    items = hub['stores'].get(store)
    if not isinstance(items, list):
        raise ListRemovalError('The chosen store list is no longer available.')
    by_id = [it for it in items if isinstance(it, dict) and it.get('id') == item_id]
    if len(by_id) != 1 or by_id[0].get('name') != name:
        raise ListRemovalError('The selected item has changed since the preview. Nothing was removed; please try again.')
    same_name = [it for it in items if isinstance(it, dict) and isinstance(it.get('name'), str)
                 and _normalized_name(it['name']) == _normalized_name(name)]
    if len(same_name) != 1:
        raise ListRemovalError('The item is now duplicated. Choose the exact entry in Settings; nothing was removed.')
    result = deepcopy(hub)
    result['stores'][store] = [it for it in result['stores'][store] if it.get('id') != item_id]
    return result
