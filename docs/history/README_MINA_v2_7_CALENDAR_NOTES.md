# MINA v2.7 — Calendar, Notes, two reminders and opt-in Google Calendar

## What's in this patch

- The **Auto** chat accepts a limited set of English voice/text commands to propose appointments, events, yearly birthdays and private notes. It does **not** book an appointment with a provider.
- Each proposed change shows a preview and requires a **Confirm** button or a separate spoken instruction such as **“Mina, confirm my calendar event.”** / **“Mina, confirm my note.”**
- Every approved item is saved to `local_data/mina_calendar_v27.json` (private, atomic JSON). Older shopping lists and Family Hub files are not overwritten. Notes are local-only.
- Appointments, other events and recurring birthdays get a **24-hour** and **2-hour** reminder window. App-local notifications appear while Streamlit is running and browser open. Acknowledgements are saved locally.
- A **monthly calendar**, an upcoming-events list, and a **Notes** section are rendered in Streamlit. The Settings sidebar offers form-based entry and Google OAuth setup.
- Google Calendar sync is **opt-in**. Events are only sent after OAuth and a per-event confirmation. Calendar event `reminders.overrides` are popup reminders at `1440` and `120` minutes. Existing Google events are READ, not changed; older Google events do not automatically inherit new reminders.
- Seven fictional annual demo birthdays can be loaded once. They are **labelled DEMO**, remain in local-only JSON, and survive later code-only upgrades. They are never uploaded to Google.
- A voice-created dentist/pediatrician appointment is also mirrored into local Family Hub visits when possible, so the old Target/Trader Joe's pairing workflow can find it. Legacy duplicate in-app reminders for those mirrored visits are hidden. The original Planner and write guard remain in place.

**Honest boundaries:** This implementation has been statically compiled and tested with local unit tests and fake Google API services. It has NOT yet been connected to the user's Google account or visually smoke-tested in Streamlit on Mac. Google OAuth for this local desktop MVP requires the Mac user to complete the Google Cloud project setup and OAuth consent. The code is not a generic deployed-web OAuth flow.

## Install on top of MINA v2.6 (Mac)

Stop Streamlit with **Control+C**, then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_before_v2_7.py
unzip -o ~/Downloads/MINA_v2_7_Google_Calendar_Notes_patch.zip -d .
python -m pip install -r requirements_calendar_v2_7.txt
python -m unittest -v test_mina_calendar_v27.py
python -m streamlit run streamlit_app.py
```

### Protect local data from GitHub

```bash
mkdir -p local_data
printf '\nlocal_data/\n.streamlit/secrets.toml\n' >> .gitignore
```

Don't commit `local_data`, OAuth downloads, token files, your family's real birthdays, appointments, doctors' details, or home address. `unzip` only updates the code and `examples/`; it does **not** include or erase any `local_data/` files.

## Google Calendar OAuth — user's action is necessary

1. Open [Google Cloud Console](https://console.cloud.google.com/). Create/select a project and **enable Google Calendar API**.
2. Configure the **OAuth consent screen**. For a personal test application, add the Google account you'll sign in with as a **test user** if Google requires it.
3. Under **APIs & Services → Credentials → Create credentials → OAuth client ID**, choose application type **Desktop app**, then download its client JSON file.
4. Save that download to the project at `local_data/google_oauth_client.json`. For example (replace the downloaded filename):

   ```bash
   mkdir -p local_data
   cp ~/Downloads/<your-downloaded-oauth-client-file>.json local_data/google_oauth_client.json
   ```

5. Run MINA, open the left sidebar with the top-left arrow, expand **Google Calendar & Notes**, and click **Connect / reconnect Google Calendar**. Google's login/consent happens in the browser. Review and approve the requested scope to read and manage calendar events. OAuth refresh tokens are saved as `local_data/google_calendar_token.json` with owner-only permissions.
6. Click **Refresh Google events** and verify that MINA can read your actual upcoming events. Confirm that **Save confirmed calendar events to Google when connected** is enabled if you want future approved creations synced.

Official references: [Google Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python), [reminder settings](https://developers.google.com/workspace/calendar/api/concepts/reminders), [Google Calendar event creation](https://developers.google.com/workspace/calendar/api/guides/create-events).

**OAuth caveat:** With an unverified app in Google's testing status, access may be limited to listed test users and token sessions may need renewed authorization. Never upload or paste OAuth credentials in a chat.

## Test a real event (after connection)

Type or say:

> Mina, I have a dentist appointment on March 6 at 11:30 AM.

Given today's date in November 2026, the proposed entry should be March 6, **2027** at 11:30 AM Eastern Time. MINA previews:

- **Reminder #1:** March 5, 2027 at **11:30 AM** (24 hours prior).
- **Reminder #2:** March 6, 2027 at **9:30 AM** (2 hours prior).
- **End time:** no end specified, so Google event defaults to **12:30 PM**, explicitly marked as an assumption. Specify the real end time to avoid this default.

MINA must **not** save anything on the first utterance. Click **Confirm & save calendar event**, or say **“Mina, confirm my calendar event.”** Check the resulting Google event and its reminder settings. If Google is unconnected, MINA will save **local-only** and explicitly say so. A Google API failure may leave a local copy: check Google before retrying to avoid duplicates.

Other tests:

- “Mina, create an event: school science fair on December 3 at 5 PM.” → preview → confirm.
- “Mina, add Emma birthday on June 17.” → yearly reminder at 9:00 AM on each birthday (a timed reminder anchor, **not** an all-day birthday event) → confirm.
- “Mina, make a note: bring my insurance card to the dentist.” → note preview → confirm with “Mina, confirm my note.” Notes stay in MINA only.
- “Mina, show my notes.” → list of notes.
- “Mina, what is on my calendar tomorrow?” → local calendar + live Google read when connected.
- “Mina, what is on my calendar on March 6?” → the requested date, also live Google if connected.

### Fictional demo dataset

Open Settings → **Google Calendar & Notes** → click **Load 7 FICTIONAL demo birthdays into MINA only**. They will remain in `local_data/mina_calendar_v27.json`, tagged `source=demo` and displayed as **DEMO**. This is idempotent: clicking twice does not duplicate them. To demonstrate real birthdays, add them by voice or form; no real family names or dates are bundled in the patch.

## When do reminders actually appear?

- **In-app (MINA only):** 24-hour and 2-hour windows, refreshed about once per minute **while Streamlit/browser is open**, acknowledging them locally prevents repeated prompt spam. These are visible notices, not iPhone push notifications.
- **Google Calendar:** MINA sends two `popup` reminders with each newly approved Google event. For the device to notify you while MINA is closed, your Google Calendar app/phone notifications must be enabled. Delivery behavior depends on device/app settings. This code cannot guarantee a notification on an unconfigured phone.
- **Existing Google Calendar events:** MINA can read them, but does not automatically modify them to add reminders. Syncing a pre-existing event's reminder rules would require a separately approved event update feature.
- **Anniversaries / birthdays:** MINA uses a 9:00 AM local *timed* event repeated yearly so the 2-hour reminder makes sense. Edit the reminder anchor as desired. Demo birthdays are never sent to Google.

## Testing and limitations

- The patch was reconstructed from the sequential MINA v1.x–v2.6 ZIPs available in conversation. **346/346 unit tests PASS** in the reconstructed tree (299 existing + 47 new); offline baseline `run_offline_checks.py` PASS. Google integration was tested with **mock Google API responses only**, **not** a real account. `streamlit_app.py` passed `python -m py_compile`; a visual browser test has NOT been run here.
- The current event parser is conservative and handles English voice commands with recognizable date and time. Unusual expressions may require a clearer rephrasing or the Settings form. No arbitrary LLM output can trigger a Google write.
- Appointments are NOT bookings with healthcare offices. No calendars are written automatically without consent; no email/list external writes are enabled. Storing clinical details is discouraged; use general appointment titles and optional logistics notes.
- Family Hub's older visit notes can still appear in the schedule separately. No automatic Google-to-Family-Hub import of historical Google events exists. MINA does not reschedule existing Google appointments yet.
