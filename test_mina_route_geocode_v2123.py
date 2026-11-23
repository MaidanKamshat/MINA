"""Offline regression: request stubs only, no address or network usage."""
import ast
from datetime import date
from pathlib import Path
import unittest
from urllib.parse import urlparse,parse_qs
from mina_route_geocode_v2123 import (
    resolve_saved_route_points, SavedRouteLocationError, _census_match, _photon_match,
)

ADDRESSES={
 'origin':'123 Example St, Cary, NC 27518',
 'library':'10 Sample Ave, Cary, NC 27511',
 'groceries':'22 Market Rd, Apex, NC 27502',
 'school_pickup':'31 School Dr, Cary, NC 27511',
}
PINS={
 ADDRESSES['origin']:(-78.81,35.70),
 ADDRESSES['library']:(-78.82,35.71),
 ADDRESSES['groceries']:(-78.83,35.72),
 ADDRESSES['school_pickup']:(-78.84,35.73),
}

def census_fake(url):
    q=parse_qs(urlparse(url).query)['address'][0]
    lo,la=PINS[q]
    return {'result':{'addressMatches':[{'matchedAddress':q.replace(', NC ', ', NC, '),
                                        'coordinates':{'x':lo,'y':la}}]}}

class RouteGeocodeTests(unittest.TestCase):
 def test_exact_census_match(self):
    r=resolve_saved_route_points(ADDRESSES['origin'],{k:v for k,v in ADDRESSES.items() if k!='origin'},fetcher=census_fake)
    self.assertEqual(r.origin,'-78.810000,35.700000')
    self.assertEqual(r.locations['groceries'],'-78.830000,35.720000')
    self.assertEqual(set(r.provider_by_stop.values()),{'Census'})
 def test_existing_coordinates_do_not_need_geocoding(self):
    r=resolve_saved_route_points('-78.8,35.7',{'library':'-78.9,35.75'},fetcher=lambda _:self.fail('network must not be called'))
    self.assertEqual(r.provider_by_stop['origin'],'already_coordinates')
 def test_number_mismatch_cannot_route_wrong_house(self):
    def mismatch(url):
        if 'census' in url:return {'result':{'addressMatches':[{'matchedAddress':'999 EXAMPLE ST, CARY, NC, 27518','coordinates':{'x':-78.81,'y':35.7}}]}}
        return {'features':[]}
    with self.assertRaises(SavedRouteLocationError) as ctx:
        resolve_saved_route_points(ADDRESSES['origin'],{'library':'10 Sample Ave, Cary, NC 27511'},fetcher=mismatch)
    self.assertEqual(ctx.exception.key,'origin')
    self.assertEqual(ctx.exception.reason,'not_confidently_matched')
 def test_incomplete_raises_name_only_not_address(self):
    with self.assertRaises(SavedRouteLocationError) as ctx:
        resolve_saved_route_points('123 Example St, Cary',{},fetcher=lambda _:self.fail('No http'))
    self.assertEqual(ctx.exception.reason,'incomplete_street_address')
    self.assertNotIn('Example',str(ctx.exception))
 def test_provider_error_is_explicit_not_fabricated_location(self):
    with self.assertRaises(SavedRouteLocationError) as ctx:
        resolve_saved_route_points(ADDRESSES['origin'],{},fetcher=lambda _:(_ for _ in ()).throw(OSError('Timeout at private address')))
    self.assertEqual(ctx.exception.reason,'geocoding_unavailable')
    self.assertNotIn('private',str(ctx.exception))
 def test_suite_number_not_sent_to_provider(self):
    def stub(url):
        q=parse_qs(urlparse(url).query)['address'][0]
        self.assertEqual(q,'110 Kildaire Park Dr, Cary, NC 27518')
        return {'result':{'addressMatches':[{'matchedAddress':'110 KILDAIRE PARK DR, CARY, NC, 27518',
                                            'coordinates':{'x':-78.80,'y':35.70}}]}}
    for address in ('110 Kildaire Park Dr Ste 410, Cary, NC 27518',
                    '110 Kildaire Park Dr, Ste 410, Cary, NC 27518'):
        with self.subTest(address=address):
            r=resolve_saved_route_points(address,{},fetcher=stub)
            self.assertEqual(r.origin,'-78.800000,35.700000')
 def test_photon_fallback(self):
    def respond(url):
        if 'census' in url:return {'result':{'addressMatches':[]}}
        return {'features':[{'properties':{'housenumber':'123','street':'Example Street','postcode':'27518','countrycode':'US'},'geometry':{'coordinates':[-78.81,35.7]}}]}
    r=resolve_saved_route_points(ADDRESSES['origin'],{},fetcher=respond)
    self.assertEqual(r.origin,'-78.810000,35.700000')
    self.assertEqual(r.provider_by_stop['origin'],'Photon')
 def test_photon_requires_street_zip_house_match(self):
    v={'features':[{'properties':{'housenumber':'123','street':'Wrong Street','postcode':'27518'}, 'geometry':{'coordinates':[-78.8,35.8]}}]}
    self.assertIsNone(_photon_match(v, {'house':'123','street':('EXAMPLE','ST'),'zip':'27518'}))
 def test_no_geocoding_without_consent_and_backend_coords(self):
    src=Path(__file__).with_name('streamlit_app.py').read_text()
    ast.parse(src)
    route=src.split("elif trip_route_kind == 'route'",1)[1].split('elif calendar_confirm:',1)[0]
    self.assertIn("if not st.session_state.get('mina_hub_address_consent',False):",route)
    self.assertLess(route.index("if not st.session_state.get('mina_hub_address_consent',False):"),route.index('resolve_saved_route_points('))
    self.assertIn('origin=resolved_route.origin,',route)
    self.assertIn('depart_time=start_value,',route)
    self.assertIn('pickup_window=schedule_window',route)
    self.assertIn('resolved_route.locations[t]',route)
    self.assertIn('geocoding_sources',route)
    self.assertNotIn('_store_local_hub(',route)
    self.assertNotIn('google_insert_event(',route)
 def test_keeps_old_date_pair_rule(self):
    from mina_route_bridge_v212 import paired_backend_plan_date
    self.assertEqual(paired_backend_plan_date('','2026-11-23'),'')

if __name__=='__main__':unittest.main()
