"""Targeted regressions: saved-location map caption, v2.12.7."""
import ast
from pathlib import Path
import unittest

from mina_route_schedule_v2125 import repair_runtime_saved_map_legend


class MapLegendV2127Tests(unittest.TestCase):
    def test_static_caption_replaced_but_map_left_intact(self):
        html = '<html><body><div>Public demo locations reconnected</div><div id="map">leaflet map</div></body></html>'
        fixed = repair_runtime_saved_map_legend(html)
        self.assertIn('Route locations from Family Hub', fixed)
        self.assertIn('id="map">leaflet map', fixed)
        self.assertLess(fixed.index('mina-family-hub-map-legend-v2127'), fixed.index('</body>'))

    def test_catches_caption_rendered_after_load(self):
        fixed = repair_runtime_saved_map_legend('<html><body><div id="map"></div></body></html>')
        # Runtime code updates text nodes, including DOM mutations after load.
        for expected in ('MutationObserver(update)', 'createTreeWalker',
                         'characterData: true', 'childList: true',
                         'Public[\\s\\u00a0]+demo', 'addEventListener(\'load\''):
            self.assertIn(expected, fixed)

    def test_adding_same_fix_twice_is_idempotent(self):
        once = repair_runtime_saved_map_legend('<html><body>example</body></html>')
        twice = repair_runtime_saved_map_legend(once)
        self.assertEqual(once, twice)
        self.assertEqual(once.count('id="mina-family-hub-map-legend-v2127"'), 1)

    def test_only_verified_family_hub_branch_uses_runtime_fix(self):
        app = Path(__file__).with_name('streamlit_app.py').read_text(encoding='utf-8')
        ast.parse(app)
        self.assertIn("e.get('geocoding') == 'matched_all_requested_stops'", app)
        self.assertIn('map_html = repair_runtime_saved_map_legend(map_html)', app)
        self.assertLess(app.index("e.get('geocoding') == 'matched_all_requested_stops'"),
                        app.index('map_html = repair_runtime_saved_map_legend(map_html)'))
        self.assertNotIn('coordinates', repair_runtime_saved_map_legend('<html></html>').split('newCaption = ')[1].split(';')[0].lower())


if __name__ == '__main__':
    unittest.main()
