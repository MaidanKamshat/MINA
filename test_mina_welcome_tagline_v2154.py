"""Static copy regression: v2.15.4 changes only the welcome tagline."""
from pathlib import Path
import unittest

class WelcomeTaglineV2154Test(unittest.TestCase):
    def test_exact_requested_copy(self):
        txt = (Path(__file__).parent / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn("Plan your day, capture tasks, and<br>make room for what truly matters.", txt)
        self.assertNotIn("make room for what matters.", txt)
        self.assertEqual(txt.count("Plan your day, capture tasks, and<br>make room for what truly matters."), 1)

    def test_brand_and_navigation_unchanged(self):
        txt = (Path(__file__).parent / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('Welcome, I’m <span class="mina-name">MINA</span>', txt)
        self.assertIn('<span class="mina-initial">M</span>y', txt)
        self.assertIn('<span class="mina-initial">A</span>ssistant', txt)
        self.assertIn("mina_info_section",txt)

if __name__ == "__main__":
    unittest.main()
