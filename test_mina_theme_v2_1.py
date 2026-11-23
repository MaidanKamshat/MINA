"""Source-level regression checks for MINA v2.1 theme (no Streamlit import needed)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'streamlit_app.py').read_text(encoding='utf-8')
CSS = (ROOT / 'mina_theme_v2_1.css').read_text(encoding='utf-8')

class TestMinaThemeV21(unittest.TestCase):
    def test_app_parses(self):
        ast.parse(APP)
    def test_css_separate_and_loaded(self):
        self.assertIn("ROOT / 'mina_theme_v2_1.css'", APP)
        self.assertIn("THEME_CSS.read_text", APP)
    def test_burgundy_accents(self):
        self.assertIn('#6A203D', CSS)
        self.assertIn('--mina-burgundy', CSS)
    def test_cream_background(self):
        self.assertIn('#F8F4F1', CSS)
    def test_powder_blue_messages(self):
        self.assertIn('#E6EDF5', CSS)
        self.assertIn('stChatMessageAvatarUser', CSS)
    def test_welcome_exact_lines(self):
        self.assertIn('Welcome, I’m <span class="mina-name">Mina</span>', APP)
        self.assertIn('Your everyday planning companion', APP)
    def test_acronym_four_highlights(self):
        self.assertEqual(APP.count('class="mina-initial"'), 4)
        for letter in 'MINA':
            self.assertIn(f'<span class="mina-initial">{letter}</span>', APP)
    def test_unified_voice_chat_unchanged(self):
        self.assertIn('st.chat_input(', APP)
        self.assertIn('accept_audio=True', APP)
        self.assertIn('transcribe_wav(', APP)
        self.assertIn('generate_spoken_reply(', APP)
        self.assertIn('extract_chat_submission(', APP)
    def test_backend_and_safety_are_still_called(self):
        self.assertIn('execute_ui_request(prompt, settings)', APP)
        self.assertIn('save_preview_map(', APP)
        self.assertIn('approval_required', (ROOT / 'mina_ui_adapter.py').read_text(encoding='utf-8'))
    def test_unneeded_controls_absent(self):
        self.assertNotIn("st.button('Ask MINA'", APP)
        self.assertNotIn("st.button('Transcribe recording'", APP)
    def test_not_inserting_fake_notification_ui(self):
        self.assertNotIn("st.button('Notifications'", APP)

if __name__ == '__main__':
    unittest.main()
