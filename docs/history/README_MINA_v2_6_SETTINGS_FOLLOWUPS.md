# MINA v2.6 — Visible Settings, Updated Lists & Family Follow-ups

**What this patch does:** Refines the existing v2.5 local Streamlit app. No real Google Calendar, email, iOS push, or external shopping service integration is added. It is a **local-only in-app reminder MVP**.

## New user-visible features

1. **Settings is no longer hidden behind the sidebar arrow.** The top navigation now includes a functional **⚙️ Settings & Family Hub** popover. It displays pending items for each store, a quick-add form and upcoming saved visits. Advanced planner, schedule, and route settings remain in the sidebar (toggle arrow upper left).
2. **Full store list after voice confirmation.** Say, e.g. `Mina, add milk, bread and eggs to my Target shopping list`, then `Confirm my local update`. MINA shows the updated **entire pending Target list**, not only an Added message. The button confirmation does the same.
3. **Appointment reminders:** Based solely on user-entered saved visit dates/times, MINA offers an in-app reminder starting **24 hours before** the visit and again starting **2 hours before** it; each has its own **Got it** acknowledgement. The reminder section refreshes about once per minute while the Streamlit page remains open (Streamlit supports fragments in the project's required version). Reminders do **not** send push notifications, emails or iPhone notifications, and cannot alert you when the Streamlit app/browser is closed.
4. **Yesterday's check-ins:** The day after a saved dentist, pediatrician, or library visit, MINA asks **“Did you attend?”** with Yes/Missed/Ask me later. It also understands conservative spoken responses such as `Mina, I went to the dentist yesterday` or `I missed my dentist appointment yesterday`. After confirmation, MINA asks about the next appointment; user can save a new visit by voice in the usual local-confirmation flow.
5. **Store follow-up:** After an attended visit paired with a store (Dentist–Target, Pediatrician–Trader Joe's, Library–Costco), if that store has pending items, MINA asks if the user bought everything. No items are silently deleted. `Yes, all bought` (or `Mina, I bought everything at Target`) yields an **explicit clear-list proposal**. Only the separate Confirm button or `Confirm my local update` actually empties **that store only**. MINA then displays `list cleared` and asks `Is there anything else you need to buy?`. **No/partial** responses preserve the list; marking partial purchases done remains available in sidebar item checkboxes.
6. **Data persistence:** Existing shopping, Saved Places, visits and preferences retain their existing `local_data/mina_family_hub.json` file. Reminder acknowledgements and visit/shop outcomes are saved *separately* in `local_data/mina_followups.json`, atomically with private local file permissions. No private data is included in the ZIP patch.

## Install on your Mac

1. Download `MINA_v2_6_Settings_Reminders_Followups_patch.zip` to `~/Downloads`.
2. Stop Streamlit with **Control + C** (not Command + C).
3. Run:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate

cp streamlit_app.py streamlit_app_before_v2_6.py
cp mina_auto_mode.py mina_auto_mode_before_v2_6.py

unzip -o ~/Downloads/MINA_v2_6_Settings_Reminders_Followups_patch.zip -d .

python -m unittest -v test_mina_followups_v2_6.py
python -m unittest discover -p 'test_*.py' -q
python -m streamlit run streamlit_app.py
```

This is a **patch on top of MINA v2.5**, not a complete project replacement. `mina_family_hub.py`, the weather/route APIs and the CSS themes remain unchanged.

## Test script (voice-first)

**Shopping addition:** `Mina, add apples and milk to my Target shopping list.` → `Confirm my local update.` → whole updated list appears in the chat.

**Appointment test:** `Mina, I had a dentist appointment yesterday from 11 AM to 1 PM.` → `Confirm my local update.` → the **Family reminders & check-ins** card asks if you attended. Choose `Yes, I went` or say `Mina, I went to the dentist yesterday`. MINA asks when the next dentist visit is scheduled. If Target has pending items, it also asks whether you bought all of them.

**Purchased-all test:** Say `Mina, I bought everything at Target.` → MINA proposes clearing the Target list → **explicitly confirm** → Target list becomes empty and MINA asks if you need anything else. Costco and Trader Joe's lists are untouched.

**Reminder test:** Create a *new upcoming* dentist or pediatrician visit using voice. An upcoming visit within 24 hours triggers a `Within 24 hours` card; 2 hours or less triggers a distinct `Starting within 2 hours` card. Acknowledge each using `Got it`. As triggers are relative to the current local time, not the calendar date alone, use an appropriate test time. Dates/times displayed and stored use 12-hour AM/PM.

## Safety and scope

- A spoken statement that something was purchased **does not clear the list automatically**. Clearing is a destructive local operation requiring a second explicit confirmation. The operation compares the list's item IDs to its proposal snapshot and fails closed if the list has changed.
- All external calendar/list/email write actions remain blocked by the pre-existing independent guard. An appointment note does **not** book a doctor or write to Google Calendar. An appointment from a local note is not independently verified.
- Opening MINA is necessary to see reminders and the next-day follow-up. No `launchd` service or mobile notification token was configured, so reminders are **not delivered when the app/browser is closed**. Persistent notifications would require a separately opted-in calendar/notification integration and a reliable always-on delivery service.
- `local_data/`, `.streamlit/secrets.toml`, `evaluation/maps/` must remain in `.gitignore` for public GitHub.

## Assistant-side offline validation (not Mac acceptance)

- **299/299 Python unit tests PASS**, including **36 new v2.6 tests** for 24-hour/2-hour triggers, acknowledgement persistence, yesterday's check-in state, spoken outcomes, single-store list clearing, stale confirmations and compatibility.
- **20/20 unchanged synthetic structural scenarios PASS** using the deterministic offline evaluation. Synthetic success does not demonstrate real-world reliability or live OpenAI/HeiGIT availability.
- `python -m py_compile` succeeds for the updated three Python modules.
- Streamlit itself is not installed in the assistant's test environment; therefore v2.6 rendering and actual voice speech-to-text/TTS on the user's Mac remain to be confirmed.
