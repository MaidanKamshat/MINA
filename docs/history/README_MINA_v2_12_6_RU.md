# MINA v2.12.6 — Coherent Route Schedule View

Requires working **v2.12.5** installation. This is a display and conservative schedule-guard refinement, **not** a new traffic-aware itinerary optimizer.

## Fixes

- When the existing pickup-window guard finds an early school ETA, MINA presents a **proposed retimed timeline first** using the *actual backend-reported stop ETAs* and user-supplied stop durations, then labels the old backend ETAs as unadjusted estimates.
- In the sample: depart 12:30, Costco 12:56–1:26, library 1:44–2:04, flexible interval 2:04–2:56, proposed school arrival 3:15 and pickup through 3:30. Times are calculated from request/ETA; no historical or personal addresses are baked into code.
- Incomplete or inconsistent stop ETAs **do not** cause MINA to invent a timeline: a conservative guard note is shown instead.
- Fixes a stale generic 'Public demo locations reconnected' preview caption when the trace confirms saved Family Hub location provenance; no map geometry is modified.
- Retains `no_feasible_plan` if arrival/service time exceeds pickup window and `needs_clarification` if school ETA is absent.
- Does NOT query future live traffic, verify store/library hours, school calendar or pickup rules, or create any calendar/list/email actions.

## Install (macOS)

Stop Streamlit with **Control+C**, then run:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2125.py
cp mina_route_schedule_v2125.py mina_route_schedule_v2125_backup.py
unzip -o ~/Downloads/MINA_v2_12_6_Route_Timeline_Fix.zip -d .
python -m unittest -q test_mina_route_timeline_v2126.py test_mina_route_schedule_v2125.py test_mina_route_pins_v2124.py test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

No changes to `mina_family_hub.json`, local private pins, saved places, shopping lists, Calendar or CSS/theme.

## Acceptance

Run exactly the same voice/text prompt for Monday, November 23, 2026. If the same ETA result is returned, the assistant response should begin **Proposed afternoon schedule · provisional**, list each time, then show **Original backend route ETAs — unadjusted**. Trace should contain `pickup_window_guard` with `version=2.12.6`, `adjusted_timeline_shown=true`. Map route geometry remains the original route, and any proposed retiming must be independently checked.

Tested here: **84/84 local mock/unit tests**. No live geocoder/HeiGIT test was performed from the user's Mac in this release.
