"""Private route-pin regression: test on synthetic addresses without network."""
import ast
import json
import tempfile
from pathlib import Path
import unittest
from mina_route_pins_v2124 import (
    save_verified_pin, remove_pin, active_pin, saved_pin_state, RoutePinError,
)
from mina_route_geocode_v2123 import resolve_saved_route_points, SavedRouteLocationError

class PinTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'pins.json'
        self.address='123 Example St, Cary, NC 27518'
    def save(self, key='home', loc='35.7326, -78.8503'):
        save_verified_pin(key,self.address,loc,path=self.path)
    def test_one_time_save_reuse_and_private_fingerprint(self):
        self.save()
        self.assertEqual(active_pin('home',self.address,path=self.path),'-78.850300,35.732600')
        self.assertEqual(saved_pin_state('home',self.address,path=self.path),'active')
        data=self.path.read_text()
        self.assertNotIn('Example St',data)
        if __import__('os').name=='posix':
            self.assertEqual(self.path.stat().st_mode&0o777,0o600)
    def test_changing_address_invalidates_pin(self):
        self.save()
        self.assertIsNone(active_pin('home','124 Example St, Cary, NC 27518',path=self.path))
        self.assertEqual(saved_pin_state('home','124 Example St, Cary, NC 27518',path=self.path),'stale')
    def test_abnormal_coordinate_order_rejected(self):
        for input_text in ('-78.8503, 35.7326','35.7','100, -78','35.7, 300','35, -78; hello'):
            with self.subTest(input=input_text),self.assertRaises(RoutePinError):
                self.save(loc=input_text)
    def test_unrecognized_place_rejected(self):
        with self.assertRaises(RoutePinError):
            self.save(key='pediatrician')
    def test_remove_pin(self):
        self.save()
        remove_pin('home',path=self.path)
        self.assertIsNone(active_pin('home',self.address,path=self.path))
    def test_override_avoids_home_lookup_but_geocodes_other_stops(self):
        self.save()
        calls=[]
        def fake(url):
            calls.append(url)
            if 'census' in url:
                return {'result':{'addressMatches':[{'matchedAddress':'10 SAMPLE AVE, CARY, NC, 27518',
                    'coordinates':{'x':-78.81,'y':35.73}}]}}
            return {'features':[]}
        r=resolve_saved_route_points(self.address,{'library':'10 Sample Ave, Cary, NC 27518'},
             fetcher=fake,verified_overrides={'origin':active_pin('home',self.address,path=self.path)})
        self.assertEqual(r.origin,'-78.850300,35.732600')
        self.assertEqual(r.provider_by_stop['origin'],'user_verified_local_pin')
        self.assertEqual(r.provider_by_stop['library'],'Census')
        self.assertEqual(len(calls),1)
        self.assertNotIn('Example',calls[0])
    def test_other_stops_can_have_pins(self):
        save_verified_pin('costco','22 Market Rd, Apex, NC 27502','35.72, -78.83',path=self.path)
        coords=active_pin('costco','22 Market Rd, Apex, NC 27502',path=self.path)
        r=resolve_saved_route_points('-78.8,35.7',{'groceries':'22 Market Rd, Apex, NC 27502'},
                verified_overrides={'groceries':coords},
                fetcher=lambda _:self.fail('Network must not be called'))
        self.assertEqual(r.provider_by_stop['groceries'],'user_verified_local_pin')
    def test_corrupt_pin_fails_safely(self):
        self.path.write_text('not json')
        with self.assertRaises(RoutePinError) as ctx:
            active_pin('home',self.address,path=self.path)
        self.assertNotIn('Example',str(ctx.exception))
    def test_no_forged_unsafe_backend_overrides(self):
        with self.assertRaises(SavedRouteLocationError):
            resolve_saved_route_points(self.address,{},verified_overrides={'origin':'-78,garbage'},
                fetcher=lambda _:self.fail('Network must not be called'))
    def test_streamlit_routes_have_pin_consent_and_no_implicit_commit(self):
        src=Path(__file__).with_name('streamlit_app.py').read_text()
        ast.parse(src)
        route=src.split("elif trip_route_kind == 'route'",1)[1].split('elif calendar_confirm:',1)[0]
        self.assertIn('verified_overrides=verified_pins',route)
        self.assertLess(route.index("if not st.session_state.get('mina_hub_address_consent',False):"),
                        route.index('active_pin('))
        self.assertNotIn('save_verified_pin(',route)
        self.assertIn('Private route pins',src)

if __name__=='__main__':unittest.main()
