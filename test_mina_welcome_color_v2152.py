"""Color-regression tests; no Streamlit/LLM/network required."""
import tempfile
import unittest
from pathlib import Path

from mina_welcome_color_v2152 import original_brand_accent

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'streamlit_app.py').read_text(encoding='utf-8')
CSS = (ROOT / 'mina_welcome_polish_v2151.css').read_text(encoding='utf-8')


class WelcomeColorTests(unittest.TestCase):
    def _theme(self, *blocks):
        with tempfile.TemporaryDirectory() as d:
            paths=[]
            for i, src in enumerate(blocks):
                p=Path(d)/f'theme{i}.css'
                p.write_text(src, encoding='utf-8')
                paths.append(p)
            return original_brand_accent(tuple(paths))

    def test_original_brand_color_from_all_layers(self):
        self.assertEqual(self._theme(
            '.mina-name{color:#A14E5C;}',
            '.mina-hero .mina-name{color:#327C85;}',
            '.mina-hero .mina-name{color:#258B82 !important;}'), '#258B82')

    def test_can_return_original_css_var_exactly(self):
        self.assertEqual(self._theme('.mina-name { color: var(--mina-teal); }'), 'var(--mina-teal)')

    def test_missing_theme_does_not_invent_color(self):
        self.assertIsNone(self._theme('.mina-hello{color:#093044;}'))

    def test_ignores_unrelated_selectors_and_comments(self):
        self.assertEqual(self._theme('/* .mina-name{color:#FF0000} */'
                                    '.mina-names { color:#FF0000; }'
                                    '.mina-name { font-weight:700; color: rgb(47, 120, 118); }'),
                         'rgb(47, 120, 118)')

    def test_new_css_does_not_color_heading(self):
        self.assertNotIn('.mina-hero .mina-hello .mina-name,', CSS)
        self.assertNotIn('color: #0D1B2A !important;', CSS)
        self.assertIn('color: var(--mina-original-name-accent) !important;',CSS)
        self.assertIn('--mina-welcome-muted: #8A9AA9', CSS)

    def test_style_injected_after_originals_before_polish(self):
        self.assertLess(APP.index('UI_V28_CSS ='), APP.index('original_brand_accent'))
        self.assertLess(APP.index('original_brand_accent'), APP.index('WELCOME_POLISH_CSS ='))

    def test_nav_popovers_unchanged(self):
        self.assertIn("st.popover('How it works  ▾'",APP)
        self.assertIn("st.popover('Features  ▾'", APP)


if __name__ == '__main__':
    unittest.main()
