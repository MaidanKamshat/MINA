# MINA v2.13.1 — Reliability & Intent Routing Patch

**Type:** targeted patch over the installed MINA v2.13.0 (do not use as a standalone application).

## What changed

1. **Calendar read and explicit negative safety clauses.** Requests such as “show me only my calendar events for November 24, 2026 ... Don't change anything” now stay on the read-only calendar path. Affirmative commands to modify calendar data still do not pass that branch. The patch does **not** implement calendar deletion or Gmail sending.
2. **Incomplete family-plan input (REG-05).** “Costco and library before picking up my child from school tomorrow ... haven't decided when I'll leave home” now routes to the Family Hub planner adapter. The date `tomorrow` is resolved relative to the current local date, and the saved pickup target is used as user-provided context. When departure time is missing, MINA asks for it rather than guessing the present time or incorrectly claiming the pickup target is missing. It does not run geocoding on an incomplete route.
3. **Unknown named stops (REG-03/04).** Common named-stop requests are intercepted before the generic CLI fallback, with a clear request for the unsaved stop's full public address. No placeholder location is selected and no route is calculated. The logic covers the specifically observed phrasing; it is not a universal natural-language geocoder.
4. **Route date parser.** Recognizes `today` and `tomorrow` for typed family routes; rejects competing date references rather than silently choosing one.

**Unchanged:** shopping lists, local calendar storage, Google Calendar OAuth/creation, private route pins, saved addresses, route matrix logic, Planner/Critic/Controller, map renderer and UI theme.

## Installation on the existing Mac project

1. Download `MINA_v2_13_1_Reliability_Intent_Routing_Fix.zip` into Downloads.
2. In the Terminal running Streamlit, stop with **Control + C**.
3. Run in Terminal:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_v2130
cp -p streamlit_app.py mina_calendar_v27.py mina_trip_voice_v212.py .mina_backup_v2130/
unzip -o ~/Downloads/MINA_v2_13_1_Reliability_Intent_Routing_Fix.zip -d .
python -m unittest -q test_mina_intent_reliability_v2131.py test_mina_time_window_planner_v213.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py test_mina_saved_places_pair_v2122.py
python -m streamlit run streamlit_app.py
```

**If the tests fail:** do not assume the patched feature works. Share the Terminal test output. You can restore the three backed-up files before restarting:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_v2130/streamlit_app.py .
cp -p .mina_backup_v2130/mina_calendar_v27.py .
cp -p .mina_backup_v2130/mina_trip_voice_v212.py .
# Stop Streamlit first and then restart it normally.
```

The extra `mina_intent_reliability_v2131.py` file may remain in the directory after rollback; the old app does not import it.

## User-Mac acceptance tests (run after installation)

**A — Calendar negation and exact date:**

> Mina, show only my local MINA and Google Calendar events for November 24, 2026. Don't change anything.

Expected: `simple_response`, correct date-only events, no HH:MM warning. No write confirmations.

**B — Missing departure (REG-05):**

> Mina, I need to visit Costco and the library before picking up my child from school on November 23, 2026. Help me plan the best route. I haven't decided what time I'll leave home.

Expected: `needs_clarification` with trace `route_voice_adapter.status = missing_departure_time` and version `2.13.1`; mention saved pickup target `3:15 PM` (if it remains saved); **no route**. The adapter must not claim the saved pickup target is missing.

**C — Unknown stop (REG-04):**

> Mina, I need to stop at MINA QA Unspecified Stop before picking up my child from school. Find the best driving route from home.

Expected: `needs_clarification`, trace `unknown_named_stop`, request the named stop's address, no `--origin/--destination/--via`, no route.

**D — Existing positive route remains intact:**

> Mina, plan Monday, November 23, 2026. Leave home at 12:30 PM, visit Costco for 30 minutes and the library for 20 minutes, and arrive at school for pickup between 3:15 and 3:30 PM.

Expected: the existing v2.13 Planner → Critic → Controller flow, conditional on saved places, geocoding consent and provider availability. Driving estimates are not live traffic. Do not claim real-world opening hours/school schedule verified.

## Testing and limitations

Local patch build: **83 selected offline tests passed**, including **16 new focused tests**. Unit tests use synthetic places and mocked matrix/geometric data, not real personal locations or a live Google connection. The offline calendar reader tests replace unavailable dependencies in a temporary module environment; the actual Mac application must pass the acceptance tests before the real-world result is marked PASS.

Not yet addressed: broader reminder date-range support and independent reminder creation, email draft phrase normalization, Google Calendar event deletion, genuine traffic-aware planning, all alternative ways of naming unknown stops, and the old map caption. The shared `Time must be in HH:MM format` error may still appear on unsupported query routes; this patch specifically repairs the demonstrated calendar read path and missing-departure route path.

**Evidence Log:** do not mark new Mac tests as PASS until results/screenshots are supplied. Consolidate evidence at the end of acceptance testing, per user preference. Never publish private coordinates, addresses or OAuth files.
