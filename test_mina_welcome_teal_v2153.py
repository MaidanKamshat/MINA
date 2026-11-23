"""MINA v2.15.3 scoped welcome CSS regression tests (no Streamlit needed)."""
from pathlib import Path
import unittest

CSS = (Path(__file__).parent / 'mina_welcome_polish_v2151.css').read_text(encoding='utf-8')


class WelcomeTealTests(unittest.TestCase):
    def test_title_name_unchanged(self):
        self.assertNotIn('.mina-hero .mina-hello .mina-name', CSS)
        self.assertNotIn('.mina-name {', CSS)

    def test_initials_have_full_brand_color(self):
        self.assertIn('color: var(--mina-original-name-accent, #088F94) !important;', CSS)
        self.assertIn('-webkit-text-fill-color: var(--mina-original-name-accent, #088F94) !important;', CSS)

    def test_parent_never_fades_initials(self):
        self.assertIn('.mina-hero .mina-expansion {', CSS)
        self.assertIn('opacity: 1 !important;', CSS)
        self.assertIn('filter: none !important;', CSS)

    def test_subtitle_letters_remain_muted(self):
        self.assertIn('--mina-welcome-muted: #8A9AA9;', CSS)
        self.assertIn('-webkit-text-fill-color: var(--mina-welcome-muted) !important;', CSS)

    def test_popover_style_unchanged(self):
        self.assertIn('div[data-testid="stPopover"] button:hover', CSS)
        self.assertIn('div[data-testid="stPopover"] button:focus-visible', CSS)


if __name__ == '__main__':
    unittest.main()
