"""Locally saved, explicitly verified route pins for Family Hub.

These pins are private route inputs, not publicly geocoded addresses and not
calendar/list writes. They are bound to a fingerprint of the saved address;
changing the address invalidates an old pin. The file contains coordinates
(precise location information), so do not commit or share it.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

PIN_KEYS = ('home', 'school_pickup', 'library', 'costco', 'target', 'trader_joes')
PIN_LABELS = {'home':'Home', 'school_pickup':'School pickup', 'library':'Library',
              'costco':'Costco', 'target':'Target', 'trader_joes':"Trader Joe’s"}
PIN_FILE = Path(__file__).resolve().parent / 'local_data' / 'mina_private_route_pins.json'
_COORD_RE = re.compile(r'^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$')

class RoutePinError(ValueError):
    """A safe, non-address-bearing explanation to show to the user."""


def _lat_lon(value: str) -> tuple[float,float]:
    """User's verified Google Maps coordinate order is LATITUDE,LONGITUDE."""
    m = _COORD_RE.fullmatch((value or '').strip())
    if not m:
        raise RoutePinError('Enter two coordinates as latitude, longitude (for example, 35.7, -78.8).')
    lat,lon = map(float, m.groups())
    # The Family Hub's routing prototype uses U.S. Census/Photon geocoding.
    # Prevent accidentally swapping typical U.S. longitude and latitude.
    if not (17 <= lat <= 72 and -180 <= lon <= -60):
        raise RoutePinError('Check the order: latitude first, then negative longitude (U.S. locations only).')
    return lat,lon


def _fingerprint(address: str, salt: str) -> str:
    return hashlib.sha256((salt + '\0' + ' '.join(address.casefold().split())).encode()).hexdigest()


def _store_read(path: Path) -> dict:
    if not path.exists():
        return {'version':1, 'pins':{}}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RoutePinError('Local route-pin data cannot be read. No saved pins were used.') from None
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('pins'),dict):
        raise RoutePinError('Local route-pin data has an invalid format. No saved pins were used.')
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.route-pins-', suffix='.tmp')
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
            f.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def save_verified_pin(key: str, saved_address: str, user_coordinates: str,
                      *, path: Path = PIN_FILE) -> None:
    if key not in PIN_KEYS: raise RoutePinError('Unknown saved place.')
    if not (saved_address or '').strip(): raise RoutePinError('Save the place address first in Family Hub.')
    lat,lon=_lat_lon(user_coordinates)
    data=_store_read(Path(path))
    salt=secrets.token_hex(16)
    data['pins'][key]={'latitude':round(lat,7), 'longitude':round(lon,7),
                       'salt':salt, 'address_fingerprint':_fingerprint(saved_address,salt)}
    _write(Path(path), data)


def remove_pin(key: str, *, path: Path = PIN_FILE) -> None:
    if key not in PIN_KEYS: raise RoutePinError('Unknown saved place.')
    data=_store_read(Path(path))
    data['pins'].pop(key,None)
    _write(Path(path),data)


def active_pin(key: str, saved_address: str, *, path: Path = PIN_FILE) -> str | None:
    """Return backend coordinates longitude,latitude, or None if absent/stale."""
    if key not in PIN_KEYS:return None
    entry=_store_read(Path(path))['pins'].get(key)
    if not isinstance(entry,dict):return None
    salt=entry.get('salt');digest=entry.get('address_fingerprint')
    if not isinstance(salt,str) or not isinstance(digest,str) or not isinstance(saved_address,str):
        return None
    if _fingerprint(saved_address,salt)!=digest:return None
    try:
        lat,lon=_lat_lon(f"{entry['latitude']},{entry['longitude']}")
    except (KeyError,TypeError,RoutePinError):return None
    return f'{lon:.6f},{lat:.6f}'


def saved_pin_state(key: str, saved_address: str, *, path: Path = PIN_FILE) -> str:
    if not Path(path).exists(): return 'not_saved'
    data=_store_read(Path(path))
    if key not in data['pins']:return 'not_saved'
    return 'active' if active_pin(key,saved_address,path=path) else 'stale'
