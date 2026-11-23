# MINA v2.12.5 — Pickup schedule validation + map legend fix

This patch **replaces only** `streamlit_app.py` and adds `mina_route_schedule_v2125.py` and `test_mina_route_schedule_v2125.py`.
Requires all v2.12.4 modules already installed. Retains local Family Hub data and route pins.

## What changed

- A post-route **pickup time-window safety guard** reads the backend's explicit school ETA and verifies it against the user's pickup window and saved pickup duration.
- Example: base ETA 2:23 PM, window 3:15–3:30 PM, 15 min pickup -> **52 min flexible hold before the school leg**; provisional arrival 3:15 PM; pickup completion 3:30 PM, under unchanged driving assumptions.
- If pickup finish exceeds the window end, returns `no_feasible_plan`; if school ETA is absent, returns `needs_clarification`, rather than falsely declaring feasibility.
- Replaces the misleading legacy 'Public demo locations reconnected' map caption **only when verified/geocoded Family Hub locations are confirmed in trace**.
- Does not make another traffic query at the later departure time; does not independently verify venue hours, school rules, or school calendar. The v1.8 Critic itself still does not receive a Saved Places JSON/plan_date in this Family Hub route flow. This is a UI-side safety check, **not a complete time-window-aware backend planner**.
- Does not write events, emails, lists or addresses.

## Install (stop Streamlit first)

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2124.py
unzip -o ~/Downloads/MINA_v2_12_5_Pickup_Window_Guard.zip -d .
python -m unittest -q test_mina_route_schedule_v2125.py test_mina_route_pins_v2124.py test_mina_route_geocode_v2123.py test_mina_saved_places_pair_v2122.py test_mina_route_dispatch_v2121.py test_mina_trip_voice_v212.py
python -m streamlit run streamlit_app.py
```

Repeat the original hypothetical planning prompt, inspect the new `pickup_window_guard` trace and adjusted note. This is not a guarantee that the day's school pickup is allowed; Monday, Nov 23 2026 could fall during school break. Confirm independently.
