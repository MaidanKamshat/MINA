"""Source-level UI regression tests; intentionally need no Streamlit installation.

They don't verify actual Mac browser visuals or a connected Google account.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'streamlit_app.py').read_text('utf-8')
CSS = (ROOT / 'mina_theme_v2_8.css').read_text('utf-8')


class UIRegressions(unittest.TestCase):
    def test_source_compiles(self):
        ast.parse(SOURCE)

    def test_accessible_settings_header_and_sidebar_backup(self):
        self.assertIn("initial_sidebar_state='collapsed'", SOURCE)
        self.assertIn("if st.session_state['mina_settings_view']:", SOURCE)
        self.assertIn("_render_settings_controls()", SOURCE)
        self.assertIn("with st.sidebar:", SOURCE)
        self.assertIn("st.stop()  # A dedicated settings view", SOURCE)
        self.assertIn("if st.button(settings_label", SOURCE)
        self.assertNotIn("with st.popover('⚙️ Settings & Family Hub'", SOURCE)

    def test_welcome_copy(self):
        self.assertIn('Welcome, I’m <span class="mina-name">MINA</span>', SOURCE)
        self.assertNotIn('Your everyday planning companion', SOURCE)
        self.assertIn('Plan your day, capture tasks, and<br>make room for what matters.', SOURCE)
        self.assertIn('<span class="mina-initial">M</span>y', SOURCE)
        self.assertIn('<span class="mina-initial">A</span>ssistant', SOURCE)
        self.assertIn('margin-bottom: 0 !important', CSS)
        self.assertIn('opacity: .63 !important', CSS)

    def test_google_calendar_actions_still_in_settings(self):
        tree = ast.parse(SOURCE)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        settings = next(n for n in functions if n.name == '_render_settings_controls')
        code = ast.get_source_segment(SOURCE, settings)
        for piece in ['Connect / reconnect Google Calendar', 'Refresh Google events',
                      'Save confirmed calendar events to Google when connected',
                      '📅 Google Calendar & Notes', '🛒 Family Hub · Lists, places and visits',
                      'Add an event or note', 'return SimpleNamespace(']:
            self.assertIn(piece, code)



if __name__ == '__main__':
    unittest.main()
