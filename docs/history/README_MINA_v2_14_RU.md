# MINA v2.14.0 — Multi-turn Route Slot Filling

**Build date:** 2026-11-22
**Expected base:** MINA **v2.13.1** on the user's Mac. **v2.13.2 is not needed and is not included.**
**Change scope:** One active unfinished Family Hub route, missing `departure_time`. This is **session-level conversational state**, not persistent memory across browser/server restarts.

## What this patch adds

1. When a multi-stop route has saved places/pickup but lacks the departure time, MINA asks **when to leave** and saves a small *session-only* pending route state. It retains the user's original words and the date anchor; private addresses/coords are loaded later from the existing Family Hub only when actually routing.
2. After a short reply like **`12:30 PM`**, **`At 12:30 p.m.`**, or **`I am leaving home at 12:30 PM`**, MINA fills the missing slot and re-enters the existing time-aware Planner → Critic → Controller, retaining the original route's date, Costco/Library stop choice, and durations. The chat displays/stores the actual short reply, not an artificially combined request.
3. A visible **Cancel pending route** button or a chat message **`Cancel route`** clears the state without routing or data writes.
4. If the user starts a different request (for example weather or shopping), the prior pending route is discarded rather than wrongly applied. A nonspecific `yes` or ambiguous `12:30` triggers a clarification. Pending route expires after **30 minutes**; **Clear conversation** also clears it.
5. The trace shows `conversation_state → awaiting_departure_time`, then `conversation_state → slot_filled_and_resumed` on the next turn. It does not include saved addresses or map coordinates in these new trace steps.

This patch **does not** add multi-turn memory for email/calendar, background reminders, conversational persistence across browser restarts, or departure-time recommendations. It also does not change the Google sync safeguards, Saved Places, route provider, weather, or shopping data.

## Installation (Terminal on Mac)

Stop Streamlit in its Terminal with **Control + C**, then run:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate

mkdir -p .mina_backup_before_v214
cp -p streamlit_app.py .mina_backup_before_v214/

unzip -o ~/Downloads/MINA_v2_14_Multi_Turn_Route_Continuation.zip -d .

python -m unittest -q \
  test_mina_conversation_state_v214.py \
  test_mina_intent_reliability_v2131.py \
  test_mina_time_window_planner_v213.py \
  test_mina_route_dispatch_v2121.py \
  test_mina_trip_voice_v212.py \
  test_mina_saved_places_pair_v2122.py \
  test_mina_route_geocode_v2123.py

python -m streamlit run streamlit_app.py
```

**Only these files from v2.14 ZIP will be placed in the app folder:** `streamlit_app.py` (overwritten), `mina_conversation_state_v214.py` (new), `test_mina_conversation_state_v214.py` (new), and documentation/manifest. Your private `.env`, saved Family Hub JSON, route pins, calendar database and shopping lists are **not** in the ZIP and are not overwritten.

### Revert if necessary

Stop Streamlit, then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v214/streamlit_app.py .
python -m streamlit run streamlit_app.py
```

The extra pure Python module can safely remain unused after rollback.

## Mac acceptance tests

**Test A: Two-turn continuation (priority).** With **Auto (recommended)** and previously saved Family Hub pickup/stops, say:

> Mina, I need to visit Costco and the library before picking up my child from school tomorrow. Help me plan the best route. I haven't decided what time I'll leave home.

MINA should ask only for the departure time and show `conversation_state.awaiting_departure_time`.

Then reply as **a separate message**:

> 12:30 PM

Expected: the assistant should now compute the **same original** multi-stop route (not merely say “Noted”). In “How MINA decided,” expect `conversation_state.status = slot_filled_and_resumed`, then the standard route, Planner, Critic and Controller steps. Output remains **provisional**; external calls require preexisting permissions and connectivity.

**Test B: Cancel.** Repeat the first prompt, then send `Cancel route` (or press the small Cancel pending route button). Expect cancellation, no route, no data changes.

**Test C: Validated failure.** Repeat first prompt, answer `3:00 PM`. Under the same hypothetical pickup/visit durations, Critic should reject the infeasible route.

**Test D: New topic.** After the first prompt, ask “What's the weather in Apex today?” The new topic should work and discard the pending route.

## Test evidence

The local developer run (synthetic hub data, mocked ORS route matrix/geometry, no network) passed **103/103 selected tests** on 2026-11-22, including 10 new route slot filling tests. It did **not** run the complete Streamlit UI with your real files or live provider. Do not mark the Mac acceptance tests PASS until the user shares actual screenshots.

**Evidence Log:** Collect user screenshots and record test outcomes for a later consolidated update, following the user's request to avoid one file per test.
