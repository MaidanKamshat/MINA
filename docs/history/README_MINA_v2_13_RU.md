# MINA v2.13.0 — Time-window-aware Planner → Critic → Controller

## Scope and provenance

This patch changes the **Streamlit / Family Hub live route path** and introduces a **separate deterministic time-aware planner**. It does **not** rewrite or claim to have modified MINA's frozen v1.8 backend files (they are not bundled). Existing calendar, shopping lists, voice transcription, local saved addresses/pins, and manual demonstration flows remain intact.

The previous Family Hub path passed typed coordinates into the v1.8 route engine, which did not receive the pickup window as a typed constraint. It then post-processed an unadjusted school ETA. **For routes using saved Family Hub locations, v2.13 instead evaluates each candidate order against the typed windows before Controller selection.** The legacy v2.12.5 pickup guard remains only for the explicitly confirmed public demo fallback.

## The actual request path

1. Voice/text parser reads route intent, departure time, durations, date, requested stops and (if supplied) pickup window. Write requests continue through the existing safety controls.
2. Family Hub supplies user-saved addresses/preferences and any verified map pins. User's existing public geocoder/HeiGIT permission is still required.
3. Existing geocoding preflight resolves all points; ambiguous saved points are rejected.
4. HeiGIT/openrouteservice **matrix** provides directed driving estimates for home and requested stops. No traffic by departure time is included.
5. **Planner:** bounded deterministic permutations; for school pickup, only orders with school **last** are generated (two candidate orders for Costco+library+school).
6. **Critic:** independently verifies no missing/duplicate stops; each drive leg + user-saved buffer; requested visit durations; user-entered library opening (not closing); earliest school pickup start, latest pickup completion. If early, optional flexible time is placed before the school leg. If late, candidate is rejected. Unavailable leg estimates fail closed.
7. **Controller:** chooses only Critic-approved candidates. If none fit, returns `no_feasible_plan` and **does not produce a misleading route map**.
8. On a feasible plan, one HeiGIT directions call obtains a polyline in **the exact Controller-selected stop order**. A Leaflet/OSM map is shown when geometry is available. If geometry fails, schedule remains provisional but no fake map is drawn.
9. `How MINA decided` includes steps `planner`, `critic`, `controller`, `route_map`, version `2.13.0` with no private addresses or coordinates. No list/calendar/email writes.

## Important limitations

- Estimates from HeiGIT/openrouteservice are **not live traffic** and are not departure-time dependent. Saved 15-minute travel buffers are user assumptions.
- No venue holiday closures, school availability rules, parking, real traffic, or automatically verified opening/closing times.
- A stored school pickup **target + duration** can form a modeled window if no explicit window was spoken. This is from local user preferences, not an independently verified rule.
- Only the user-entered **library opening time** is checked; no library closing time or store opening window is available in the current Family Hub profile.
- The legacy v1.8 planning backend still handles other paths. This patch is an integrated **Family Hub live-route** Planner/Critic/Controller, not a backend-wide scheduling refactor.
- The ORS Matrix endpoint must be accessible with the existing API key. It may have its own provider permissions/quotas. `missing_ors_key` or `provider_unavailable` will not generate fabricated ETAs.
- This patch uses a new map renderer for selected-order routes. Older messages in Streamlit may still display older map HTML and legends.

## Installation (stop Streamlit with Ctrl+C first)

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_v2127
cp streamlit_app.py test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py .mina_backup_v2127/
unzip -o ~/Downloads/MINA_v2_13_Time_Window_Planner_Critic_Controller.zip -d .
python -m unittest -q test_mina_time_window_planner_v213.py test_mina_route_schedule_v2125.py test_mina_route_timeline_v2126.py test_mina_route_legend_v2127.py test_mina_route_pins_v2124.py test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

The four older regression test files in the ZIP have their **source-wiring assertions** updated to reflect the new in-app Planner, replacing assertions that required a call to the obsolete Family Hub backend adapter. Existing behavioral, consent and no-write tests are retained. No test is skipped.

To roll back the app after stopping Streamlit:

```bash
cp .mina_backup_v2127/streamlit_app.py streamlit_app.py
cp .mina_backup_v2127/test_mina_route_geocode_v2123.py .
cp .mina_backup_v2127/test_mina_saved_places_pair_v2122.py .
cp .mina_backup_v2127/test_mina_route_dispatch_v2121.py .
cp .mina_backup_v2127/test_mina_trip_voice_v212.py .
python -m streamlit run streamlit_app.py
```

## Acceptance test

Use the same prompt about **Monday, November 23, 2026**, home departure at **12:30 PM**, **Costco 30 min**, **library 20 min**, pickup **3:15–3:30 PM**, with no calendar/list writes.

Expected **structural behavior** (actual route and ETAs may differ):
- `planner` generates both store/library orders;
- `critic` reports feasibility per candidate and enforces school service **end** by 3:30 PM;
- `controller` chooses only a feasible order, or returns `no_feasible_plan`;
- `pickup_window_guard` should **not** appear in the Family Hub route trace;
- the selected order matches the map; if geometry is unavailable, no map is claimed;
- the response clearly states no live traffic and no confirmed school/store hours.

The exact example 12:56 / 1:44 / 3:15 schedule is obtained from a **mocked matrix fixture** in the new tests, not from live HeiGIT or your Mac.

## Testing evidence

In the assistant's isolated local environment, **106/106 focused Python unit/structural regressions pass**. The newest 18 tests use synthetic, non-user coordinates and mocked HeiGIT matrix/directions responses, including a rejected too-late first route and selection of a feasible alternative. The previous route, geocoding, consent, map-legend and read-only tests were also run, with four wiring assertions updated for the new architecture. The code was syntax-checked with Python. There was **no live provider call or user-Mac browser test** for v2.13 at build time.

## Privacy / API

The application continues to require the existing explicit geocoding/routing consent. It sends resolved coordinates to HeiGIT/openrouteservice for its Matrix and Directions services. The displayed map requests OpenStreetMap tiles and Leaflet assets. Private addresses, verified pins and API keys are not included in MINA traces or text answers. The map necessarily contains coordinates in in-memory HTML; do not publish screenshots/HTML as anonymized evidence without reviewing location privacy.

API key lookup recognizes `ORS_API_KEY`, `OPENROUTESERVICE_API_KEY`, `HEIGIT_API_KEY`, `OPENROUTESERVICE_KEY`, or `ORS_KEY` from environment or the project `.env`. Only the key **name**, never the value, should be shared during troubleshooting.
