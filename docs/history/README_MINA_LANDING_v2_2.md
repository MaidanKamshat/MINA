# MINA v2.2 — Teal/Navy Landing + Live Weather + Today's Plan

This patch implements the user-provided design reference `MINA_ Your Intelligent Planning Companion.png` as a responsive **Streamlit landing screen**. The previous **v2.1 unified voice/text chat** and the existing **v1.8 MINA backend** are preserved.

## Visual/UX implementation

- Top wordmark **MINA** with functioning **How it works** and **Features** controls.
- Welcome hero: **Welcome, I’m Mina**; the **M I N A** initials in `My Intelligent Navigation Assistant` are highlighted in teal; `Your everyday planning companion` has no period.
- Navy text, teal accents, lavender tagline, warm yellow **Get started** button, soft near-white background.
- Right dashboard panel with two widgets:
  - **Today's forecast:** calls the EXISTING **Open-Meteo** tool for the city configured in the sidebar (`Apex, NC` by default). It displays **daily high/low and condition**, **not live current temperature**. Cached for 15 minutes. When unavailable, says `Forecast unavailable`; does NOT substitute example weather as if real.
  - **Today's plan:** contains **explicitly labeled SAMPLE tasks** on first launch (school drop-off 8:30 AM, groceries). They are **not real appointments**. The user can add tasks in **Settings → Today's plan** via the sidebar. User-added tasks and checkbox completion states are held only in the **current Streamlit browser session**, not written to files or synced with Google Calendar. All task times shown/stored for this dashboard use 12-hour AM/PM formatting.
- **Get started** and **Ask Mina** switch to the familiar single-composer chat; **Explore Mina**, **How it works**, **Features** display explanatory panels. No fake account, notification, or calendar controls.
- The single native `st.chat_input(accept_audio=True)` at the bottom is still the only text/voice composer. Existing audio transcription, reply speech, family planning, map, Critic trace and write-action guard were not modified.

## Install on your Mac

1. Stop Streamlit with **Control+C** in the Terminal where it runs.
2. Download `MINA_v2_2_Teal_Landing_Dashboard_patch.zip` into Downloads.
3. Run these commands (adjust the project location only if you moved it):

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_v2_1_backup.py
unzip -o ~/Downloads/MINA_v2_2_Teal_Landing_Dashboard_patch.zip -d .
python -m unittest -v test_mina_dashboard_v2_2.py
python -m streamlit run streamlit_app.py
```

**Prerequisite:** The v2.1 files (including `mina_theme_v2_1.css`) must still be present; this patch adds a second overriding CSS file. It does not touch `.env`, the HeiGIT API key, MINA's validated backend or saved planning windows.

## Acceptance smoke tests

1. On initial open, inspect the two-column hero/dashboard, navy/teal colors and yellow **Get started**. If it opens in an existing conversation, select **Clear conversation** in Settings, then reload.
2. Verify the card says **Today’s forecast** and shows real Open-Meteo source, a daily HIGH (not a measured current temperature), and the city. If the API is unavailable, it must state so, without fabricated numbers.
3. Verify the task panel states **SAMPLE TASKS · Not synced with a calendar**. In the sidebar add a local task `Return library books` at `3:15 PM`. The sample list should be replaced by your new **SESSION TASKS** list. Mark it done using the checkbox. Changes are session-only.
4. Click **Explore Mina** and **How it works**; verify text opens. Click **Get started** or **Ask Mina**; confirm the single input bar remains available.
5. Record a 5-second voice prompt such as `What's the weather tomorrow and what should the kids wear?`, press the ONE submit arrow; confirm transcript, answer and optional TTS audio.
6. Send `Add a school event to my calendar.` The normal **approval_required** guard must still stop external writes.
7. Optionally test Family planner using public demo coordinates; the existing v1.8 saved pickup window and route map should continue unchanged.

## Verification and boundaries

In a **reconstructed integrated copy** of MINA v2.1+v1.8, the code passed **194/194 Python unit tests** and the existing **20/20 offline structural evaluation**. The 18 new tests cover sample-data provenance, AM/PM task formatting, task mutation logic, weather/source escaping, error fallback, and UI source safeguards. These checks do **not** constitute a new 20-case live LLM evaluation. Browser rendering, actual Open-Meteo availability and session UI actions **still require user acceptance on the Mac**.

Changing CSS selectors or Streamlit versions can affect pixel placement. This is a **functional approximation** of the reference mockup rather than a pixel-perfect HTML recreation. The backend is intentionally unchanged. This patch does not provide a Google Calendar integration, persistent task storage, or real-time traffic.
