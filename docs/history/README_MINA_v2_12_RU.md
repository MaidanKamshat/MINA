# MINA v2.12 — Voice Multi-Stop Route Constraints Fix

**Installation target:** working MINA v2.11. This is a patch; it is NOT a full standalone project. It does not contain any credentials, `.env`, OAuth tokens, `local_data/`, or user's addresses.

## Observed problem

On Nov 21, 2026, the user requested a hypothetical route on Mon Nov 23, leaving home at 12:30 PM, stopping at the library for 20 minutes and Costco for 30 minutes, then picking up at school between 3:15–3:30 PM. The live voice flow returned `needs_clarification: Unassigned fixed_time_constraint: 'leave home at 12:30 p.m.'`.

The backend's strict fixed-time scoping applies to a task, while this departure time belongs to the *route*. The previous Streamlit Auto branch also lacked `Costco` as a `groceries` synonym, selected Target's saved address by default, and used saved 15/45-minute durations instead of the explicit voice 20/30-minute values. The older school pickup pattern did not catch the phrase `school for pickup`.

## Fix

- Parse a narrow class of home-departure phrases, including `12:30 p.m.`, `12:30 PM`, and `10 a.m.`; supply `12:30 PM` as typed `UISettings.start_time` instead of a floating `fixed_time_constraint` in the prompt. The user-visible transcript is unchanged; only the backend query is normalized from `leave home at ...` to `start from home`.
- Parse explicit future plan dates and reject inconsistent weekday and date.
- Recognize `Costco`, `Target`, `Trader Joe's`, `library`, `school pickup` and `school for pickup` as route stops. Route planner supports only one shopping stop in its existing `groceries` task slot: multiple distinct stores ask for clarification, not guesses.
- For a named store, pass its exact locally saved address. If Costco has no address, ask for it instead of silently routing to Target.
- Explicit spoken stop durations override locally saved defaults for this request only. No preferences are modified.
- Recognize pickup window 3:15–3:30 PM and keep the original user sentence for the backend's Critic. User-provided vs locally saved schedule sources are marked as unverified; **the patch does not itself prove that the final route obeys the school window.** Check the resulting Critic trace and ETA.
- Do not modify existing Planner/Critic/Controller, local lists, calendar, TTS or OAuth. Preserve manually confirmed generic PUBLIC DEMO route flow. No persistent changes occur during trip planning.

## Install

From Terminal on the Mac:

```bash
# Stop the Streamlit process first: Control+C
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v211.py
unzip -o ~/Downloads/MINA_v2_12_Voice_Route_Constraints_Fix.zip -d .
python -m unittest -v test_mina_trip_voice_v212.py test_mina_list_removal_v211.py test_mina_multi_store_v210.py
python -m streamlit run streamlit_app.py
```

Expected: 90 tests OK, assuming files from v2.10–v2.11 are present. If tests fail, don't erase the saved hub or token files; share only traceback (redact private paths/tokens).

## E2E retest

Use **Auto (recommended)**; ensure *Saved Places* contains the user's chosen home, library, Costco, school locations, and family settings contain library opening time. Then speak:

> Mina, help me plan a hypothetical afternoon on Monday, November 23. I want to leave home at 12:30 PM, stop at the library for 20 minutes and Costco for 30 minutes, and arrive at school for pickup between 3:15 and 3:30 PM. Find the best order using road travel estimates and tell me if the plan is feasible. Don't create any calendar events or change my shopping lists.

Check (1) no `Unassigned fixed_time_constraint`, (2) home is origin, (3) Costco, not Target, (4) 12:30 PM departure, (5) library 20 / Costco 30, (6) school pickup within the user-specified window, (7) Critic evaluated sequence and feasibility, (8) map only if live routing succeeded, (9) no calendar/list writes. The route is provisional and HeiGIT estimates do **not** imply live traffic or independently verified school/store hours. If any check fails, classify E2E as failed and share the reply plus the *How MINA decided* trace (without private addresses). Do **not** claim E2E success from local tests alone.

## Test scope

90/90 offline tests passed on patch snapshot (33 v2.12 + 57 earlier shopping-list tests), using pure parsing and static app checks. The original baseline modules, live HeiGIT network request, and the real microphone/UI weren't present in the assistant's test environment. This ZIP contains only 4 files: `streamlit_app.py`, `mina_trip_voice_v212.py`, `mina_route_bridge_v212.py`, `test_mina_trip_voice_v212.py`, plus this README.
