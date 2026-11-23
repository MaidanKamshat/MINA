"""Static regression checks for v2.15.1 welcome-only patch.

Do not import Streamlit here; tests should work offline and do not trigger APIs.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'streamlit_app.py').read_text(encoding='utf-8')
CSS = (ROOT / 'mina_welcome_polish_v2151.css').read_text(encoding='utf-8')

class WelcomePolishTests(unittest.TestCase):
    def test_valid_acronym_and_title_markup(self):
        self.assertIn('<span class="mina-name">MINA</span>', APP)
        for letter in 'MINA':
            self.assertIn(f'<span class="mina-initial">{letter}</span>', APP)

    def test_style_follows_existing_layers(self):
        self.assertLess(APP.index("UI_V28_CSS = ROOT / 'mina_theme_v2_8.css'"), APP.index("WELCOME_POLISH_CSS = ROOT / 'mina_welcome_polish_v2151.css'"))
        self.assertIn('WELCOME_POLISH_CSS.read_text', APP)

    def test_original_title_accent_is_preserved_and_initials_share_it(self):
        self.assertNotIn('.mina-hero .mina-hello .mina-name,', CSS)
        self.assertIn('.mina-hero .mina-expansion .mina-initial {', CSS)
        self.assertIn('color: var(--mina-original-name-accent) !important;', CSS)
        self.assertIn('_MINA_WELCOME_ORIGINAL_ACCENT', APP)
        self.assertNotIn('--mina-welcome-accent: #0D1B2A', CSS)

    def test_muted_supporting_letters_not_parent_opacity(self):
        self.assertIn('color: var(--mina-welcome-muted) !important;', CSS)
        self.assertNotIn('opacity: 0.', CSS)

    def test_navigation_popovers_show_information_in_place(self):
        self.assertIn("st.popover('How it works  ▾'", APP)
        self.assertIn("st.popover('Features  ▾'", APP)
        self.assertIn('Reminders do not send push notifications when MINA is closed.', APP)

    def test_no_old_navigation_rerun_buttons(self):
        self.assertNotIn("st.button('How it works', key='mina_nav_how'", APP)
        self.assertNotIn("st.button('Features', key='mina_nav_features'", APP)
        self.assertIn("if st.button('Get started'", APP)
        self.assertIn("if st.button('Explore MINA'", APP)
        self.assertIn("if st.button(settings_label", APP)

if __name__ == '__main__':
    unittest.main()
