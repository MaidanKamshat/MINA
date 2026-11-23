import json
import os
import tempfile
import unittest
from pathlib import Path

from mina_geocoding_consent_v2142 import (
    GeocodingConsentError, load_geocoding_consent, save_geocoding_consent,
)


class TestRouteProviderConsent(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '.mina' / 'route_provider_consent.json'

    def test_new_install_is_opt_out(self):
        self.assertFalse(load_geocoding_consent(self.path))

    def test_explicit_consent_persists_after_reload(self):
        save_geocoding_consent(True, self.path)
        self.assertTrue(load_geocoding_consent(self.path))
        self.assertTrue(load_geocoding_consent(self.path))

    def test_revocation_persists_after_reload(self):
        save_geocoding_consent(True, self.path)
        save_geocoding_consent(False, self.path)
        self.assertFalse(load_geocoding_consent(self.path))

    def test_file_contains_no_address_or_location(self):
        save_geocoding_consent(True, self.path)
        self.assertEqual(json.loads(self.path.read_text()), {'version': 1, 'enabled': True})
        self.assertNotIn('address', self.path.read_text())

    def test_corrupt_json_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('not json')
        with self.assertRaises(GeocodingConsentError):
            load_geocoding_consent(self.path)

    def test_invalid_schema_and_strings_are_rejected(self):
        self.path.parent.mkdir(parents=True)
        for obj in ({'enabled': True}, {'version': 1, 'enabled': 'true'},
                    {'version': 2, 'enabled': True}, []):
            self.path.write_text(json.dumps(obj))
            with self.subTest(obj=obj), self.assertRaises(GeocodingConsentError):
                load_geocoding_consent(self.path)

    def test_does_not_accept_truthy_non_bool(self):
        for item in ('true', 1, None):
            with self.subTest(item=item), self.assertRaises(TypeError):
                save_geocoding_consent(item, self.path)

    @unittest.skipIf(os.name == 'nt', 'POSIX file permissions')
    def test_permissions_private_to_owner(self):
        save_geocoding_consent(True, self.path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_static_ui_wiring_is_explicit(self):
        content = (Path(__file__).resolve().parent / 'streamlit_app.py').read_text()
        self.assertIn("st.session_state['mina_hub_address_consent'] = load_geocoding_consent()", content)
        self.assertIn('on_change=_save_geocoding_consent_setting', content)
        self.assertIn("if not st.session_state.get('mina_hub_address_consent',False):", content)


if __name__ == '__main__':
    unittest.main()
