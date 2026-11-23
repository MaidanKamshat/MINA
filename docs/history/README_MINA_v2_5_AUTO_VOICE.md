# MINA v2.5 — Auto Mode + Voice Shopping & Local Appointment Notes

**Scope:** Update of the tested v2.4.1 local project. The Streamlit UI defaults to **Auto (recommended)**. All external list, email and calendar writes remain blocked. This is not a Google Calendar sync, doctor's appointment booking tool or background notification service.

## What changes

- **Automatic intent selection** for ordinary assistant/weather/time, read-only local shopping lists, candidate paired trips, read-only directions with explicit `from X to Y` addresses, and complex family errands. The three previous manual modes remain accessible for debugging.
- **Voice shopping lists**: one command can propose up to ten items for ONE store at a time (Costco, Target, Trader Joe's). For example: `Mina, could you please add milk, eggs and bread to my Target shopping list?` → preview → **Confirm local list update** OR say `Mina, confirm my local update.` Items are only saved after explicit user approval; a compound email/calendar command is NOT authorized.
- **Voice visit notes**: `Mina, I have a dentist appointment on November 23 from 11 AM to 1 PM.` → local visit proposal → confirmation. Date and start must be explicit; end time is optional but needed for schedule-window calculations. Date phrases currently support today, tomorrow, named month/day, ISO, US full numeric date and weekday. This does **not** book or add a calendar event.
- **Read saved schedule**: `What do I have today?` retrieves local Family Hub visits, relevant pending shopping items and the user-provided pickup time. These are never represented as Google Calendar facts. On the landing screen, visits saved for the current date appear with a reminder of matching store lists.
- **Pairing and time-window advice**: existing Library→Costco, Dentist→Target, Pediatrician→Trader Joe's. When a user asks to pair errands and has explicitly allowed HeiGIT to check saved addresses, MINA checks clinic→store driving time. If a school address is also saved it fetches a two-leg clinic→store→school route, embeds the map in chat, and calculates slack using appointment end, pickup target and user-saved duration/buffer preferences. Routes are provider estimates, **not** live traffic. If a school leg/end time/pickup hour is missing, MINA refuses to claim that shopping fits. A plan with under 15 minutes leftover is flagged tight.
- **Saved route profile**: after the user enters home, school, library and Target addresses and confirms pickup / library opening and estimated visit durations in Family Hub, Auto can use these user-provided values for the next library+groceries+pickup request. Real locations are not fabricated. The profile is local and may need updates if hours or school schedules change. The old explicit PUBLIC DEMO route mode remains for a clearly labeled fictional example.

## Install on Mac

Stop running Streamlit with **Control+C** and download `MINA_v2_5_Auto_Voice_Family_Planner_patch.zip` to `~/Downloads`.

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate

cp streamlit_app.py streamlit_app_before_v2_5.py
cp mina_family_hub.py mina_family_hub_before_v2_5.py
cp mina_ui_adapter.py mina_ui_adapter_before_v2_5.py

unzip -o ~/Downloads/MINA_v2_5_Auto_Voice_Family_Planner_patch.zip -d .

printf '\nlocal_data/\nevaluation/maps/\n.streamlit/secrets.toml\n' >> .gitignore
python -m unittest -v test_mina_auto_v2_5.py
python -m unittest discover -p 'test_*.py' -q
python -m streamlit run streamlit_app.py
```

The ZIP is a patch, **not a full repo**. It must be applied over v2.4.1 / the previous integrated version with `mina_theme_v2_2.css`, `mina_audio.py`, core runtime and the other modules already installed. The patch contains no private appointments or addresses. Existing `local_data/mina_family_hub.json` is never overwritten by the ZIP.

## One-time Family Hub setup

Open **Settings → Family Hub**:

1. **Saved Places**: enter real **business** addresses for Dentist, Target, Library, Costco, Pediatrician and Trader Joe's as needed. Never put patient records in the public demo. You may save a home/school address privately in schedule preferences; sending saved addresses to HeiGIT requires explicit consent.
2. **Family schedule preferences**: add your own school pickup target, optional home origin and school destination, library opening time *if confirmed*, library duration, grocery duration, lunch duration and buffer. Save locally. These are user notes, not verified hours or calendar updates.
3. Enable **Allow HeiGIT to geocode saved addresses when I ask** if you want a real road check and inline map; the consent is session-only. Without approval MINA gives only non-proximity reminders.

## Smoke tests

**Voice multiple items**: `Mina, could you add milk, bread and eggs to my Target shopping list?` → 3-item proposal → `Mina, confirm my local update.` → ask `What's on my Target shopping list?`

**Voice appointment** (use a *real* date from today onward for your own notes): `Mina, I have a dentist appointment on November 23 from 11 AM to 1 PM.` → confirm local note. On that date ask `Mina, what do I have today?` (or use a current-date note for testing).

**Pairing & route**: enter dentist/Target addresses, school address, pickup target and pending Target list items; consent to HeiGIT; ask `Mina, what shopping can I combine with my dentist appointment?` Expect a verified <=15-minute clinic→Target road hint **only if HeiGIT confirms it**, a provisional time-window assessment, and an inline map if the route was retrieved.

**Multi-errand Auto**: with an adequate saved profile, say `Mina, plan my library, grocery shopping and school pickup. The library opens at noon.` The agent chooses family planning and runs the existing Planner/Critic with estimated road travel; when the saved profile is incomplete, it lists missing inputs instead of substituting synthetic times.

**External write guard**: `Mina, add an appointment to my calendar` must remain blocked; MINA has no external Google Calendar write API.

## Evaluation and limitations

- Assistant-side local tests on a reconstructed project: **263/263 Python unit tests PASS** (37 newly added), and **20/20 structural offline scenarios PASS**. New router / pairing tests are **offline** and do not prove voice recognition, Streamlit rendering, real HeiGIT availability or actual schedule outcomes. Live Mac acceptance is pending.
- The app displays reminders when the page is opened and the local notes are present, not push notifications while the app is closed. No background schedule monitoring occurs.
- The model does **not** currently search, rank or verify specific lunch restaurants; a numeric lunch duration can be budgeted, but no venue is asserted without an up-to-date places source.
- Voice grammar is intentionally restricted for safety. Unsupported phrasing may require a clearer request or manual entry; it is not general natural-language calendar integration.
- To protect school pickup, feasibility claims require confirmed destinations and buffers. Hours and school timetables from user notes are not externally verified. Extra uncertainties (live traffic, cancellations, parking) remain open issues.
- `local_data/`, private addresses, appointments, user audio and map previews must not be committed to public GitHub. Raw microphone audio is not written to disk by this patch.
