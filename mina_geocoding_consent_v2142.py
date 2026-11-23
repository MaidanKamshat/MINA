"""Local, revocable opt-in for external route geocoding providers.

This file stores only a boolean consent, never addresses or coordinates.  No
network call is performed on load or save. An absent/corrupt file fails closed.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

VERSION = 1
CONSENT_FILE = Path.home() / '.mina' / 'route_provider_consent.json'


class GeocodingConsentError(RuntimeError):
    """Local consent cannot be read or saved reliably."""


def load_geocoding_consent(path: Path = CONSENT_FILE) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not (isinstance(data, dict) and data.get('version') == VERSION
                and type(data.get('enabled')) is bool):
            raise ValueError('invalid consent schema')
        return data['enabled']
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise GeocodingConsentError('Cannot validate the local consent file; external routing remains disabled.') from exc


def save_geocoding_consent(enabled: bool, path: Path = CONSENT_FILE) -> None:
    if type(enabled) is not bool:
        raise TypeError('Consent value must be explicitly True or False.')
    path = Path(path)
    temp_path = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix='.consent-', dir=str(path.parent))
        temp_path = Path(filename)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump({'version': VERSION, 'enabled': enabled}, handle)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            # fdopen owns descriptor after successfully opening it.
            raise
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise GeocodingConsentError('Failed to save the local geocoding consent; routing stays disabled.') from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
