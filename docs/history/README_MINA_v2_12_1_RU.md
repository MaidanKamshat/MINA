# MINA v2.12.1 — Explicit Multi-Stop Route Dispatch Hotfix

**Install target:** your existing MINA v2.12 project. This ZIP is **not** a standalone project and does not include `.env`, OAuth files, passwords, tokens, local shopping lists, or private Saved Places. Do not delete `local_data/` or your existing project files.

## The user-reported failure

On November 21, 2026, the voice request to plan a November 23 multi-stop trip from home at 12:30 PM, with 20 minutes at the library, 30 minutes at Costco, and school pickup between 3:15–3:30 PM, still returned:

`needs_clarification: Unassigned fixed_time constraint: 'leave home at 12:30 p.m.'`

The **How MINA decided** trace contained `coordinator → retrieval → fallback` and **did not show** `route_voice_adapter`. The v2.12 parser itself correctly extracted the departure; this points to the Streamlit request dispatch bypassing it, not a parser failure. The exact cause cannot be proven without a full runtime trace on the user's Mac.

## What changed

1. Explicit multi-stop planning commands (two or more supported stops and words such as plan, route, best order or feasible) now enter the voice route adapter **before the generic Auto Router, calendar and legacy write gates**. This also works if the user selected Assistant or Family Planner in Settings.
2. The departure timestamp is passed as a typed `start_time=12:30 PM` in `UISettings`; the backend prompt strips the `leave home at 12:30 p.m.` phrase so it will not be mistaken for a task-specific fixed time.
3. Route-only requests that explicitly say *don't create calendar events or change my lists* remain read-only. Positive mixed requests such as *plan this route and add eggs to Costco* fail closed with a clarification instead of bypassing approval.
4. Route traces now begin with `route_voice_adapter`, including `version: 2.12.1`, and report typed departure, date, stop durations, selected store and the pickup window when a profile is usable.
5. Previous local shopping, removal, calendar, Google authentication and visual layout are unchanged. No new user data is stored by installing this patch.

## Install on Mac

Stop the active Streamlit server first (`Control+C` in its Terminal window).

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v212.py
cp mina_trip_voice_v212.py mina_trip_voice_v212_backup.py
unzip -o ~/Downloads/MINA_v2_12_1_Route_Dispatch_Hotfix.zip -d .
python -m unittest -v test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py test_mina_list_removal_v211.py test_mina_multi_store_v210.py
python -m streamlit run streamlit_app.py
```

Use the new **Local URL shown by Terminal** after restarting. If multiple Streamlit instances are running, stop the old ones and confirm you are viewing the fresh server.

## Verify

Keep **Auto (recommended)** in Settings. Test first by **typing** the *same request that failed*, then test by microphone if typing succeeds. Do not change any personal data. If the saved home, school, Costco, or library addresses (or locally-entered library opening time) are absent, a `missing_user_saved_route_profile` request to supply them is safe; the app must not invent a location or route.

Expand **How MINA decided**. The **first trace entry** should now be `step: route_voice_adapter` and `version: 2.12.1`, with one of these statuses:

- `user_constraints_applied`: adapter succeeded and the Coordinator was called with typed settings. This does not prove the final itinerary is feasible.
- `missing_user_saved_route_profile`: saved profile is incomplete; no route computed.
- `input_rejected`: the parser needs a more precise date, time or unsupported stop.
- `mixed_read_write_blocked`: the request contains both route planning and a **positive** write command; nothing changed.

If the trace still only shows `coordinator → retrieval → fallback` **without** `route_voice_adapter`, verify that the new files were unzipped into the folder from which Streamlit was launched and restart its process. If an adapter trace exists but the Coordinator still rejects a constraint, share the **entire redacted trace**: that points to a **separate downstream backend issue** needing investigation. Redact private home/school addresses and coordinates.

## Scope and limitations

**101/101 local offline tests PASS** on November 21, 2026, covering route parsing, static dispatch priority, no-write guards and prior local shopping-list regression tests. These local tests do **not** execute the complete live baseline Coordinator, Planner, Critic, HeiGIT API, Google Calendar, or the user Mac microphone. An actual multi-stop plan or map is **not yet verified**. HeiGIT base durations are road estimates, not live traffic, and pickup/store hours are saved user notes, not external confirmation.

Do not report the v2.12.1 route E2E as passed until the user verifies correct stops, timing, Critic trace, route/map (if available), and no writes.
