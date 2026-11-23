# MINA v1.9 — Streamlit + voice-first interface

**Status:** Assistant-side implementation and mocked tests complete. Actual Streamlit browser/audio/provider acceptance on the user's Mac is pending. This is **not** a newly re-evaluated 20-case live benchmark or a shipped production app.

## What this patch does

Adds UI files **without editing any v1.8 backend code**:

- `streamlit_app.py`: voice-first app with microphone, transcription review, text fallback, Assistant / Directions / Family planner modes, route map, trace and optional spoken reply.
- `mina_audio.py`: audio transcription with current OpenAI `gpt-transcribe`; optional speech synthesis with `gpt-4o-mini-tts` (see deprecation note).
- `mina_ui_adapter.py`: validates user options and invokes the existing `mina_runtime.run_request` with opt-in live tools, applying the same Python Critic, Controller, and independent write guard.
- `test_mina_audio.py`, `test_mina_ui_adapter.py`: offline tests with fake audio/runner clients plus real local write-guard regression.
- `requirements_ui.txt`: Streamlit only. Your existing `requirements.txt` and virtual environment already contain OpenAI and MINA dependencies.

### Quick start on Mac

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate

# Download MINA_v1_9_Streamlit_Voice_UI_patch.zip to Downloads first.
unzip -o ~/Downloads/MINA_v1_9_Streamlit_Voice_UI_patch.zip -d .
python -m pip install -r requirements_ui.txt

# Confirm previous backend behavior still works.
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_9

# Run browser app:
python -m streamlit run streamlit_app.py
```

Streamlit will print a local URL, usually `http://localhost:8501`. Use Chrome/Safari on the same Mac and allow **microphone access**. The Python process must stay running while you use the app. Press **Control+C** in Terminal to stop it.

If your project lives elsewhere, use **that project's directory** instead. The app does not need to be moved to `~/Documents`.

## Four quick acceptance checks

1. **Time (no audio):** Select **Assistant**, type `What time and date is it right now?`, click **Ask MINA**. Confirm `simple_response` and the correct local time. You can turn RAG off for this test.
2. **Weather:** Keep **Assistant** selected; ensure forecast city is explicit (`Apex, NC` is an example), type `What's the weather tomorrow and what should the kids wear?`. Confirm Open-Meteo source and appropriate next-day forecast. No real-time weather is invented when unavailable.
3. **Voice-first:** Record a short English message with the microphone. Click **Transcribe recording**. Confirm the transcript is accurate or correct it in the text area, then click **Ask MINA**. The app never silently executes a transcription without the second action. If **Speak after a voice request** is enabled, a separate OpenAI TTS call generates an **AI-generated** audio reply; otherwise click **Read this answer aloud**.
4. **Write safety:** Type `Add a school event to my calendar.` Confirm status `approval_required` and **no calendar modification**. The UI has no write tools, and backend write guard runs before other tools. If speech recognition mishears a write command, correct the transcript before submitting.

**Optional map demo:** Select **Family planner**, leave the **public demo coordinates** and **fictional Saved Places JSON**, click **Load sample family-planning request**, review all supplied inputs and check the confirmation checkbox, then **Ask MINA**. You need the existing private `HEIGIT_API_KEY` in `.env`. On a supported weekday, the school pickup window is 3:15–3:30 PM. If feasible, the page shows status `provisional_live_route_plan`, candidate checks and the interactive HTML map. This mode can incur OpenAI / routing requests; it does not verify real school or venue opening times.

Use **Directions** for a read-only origin/destination trip; enter locations in `longitude,latitude` format or public addresses. This will not by itself schedule errands.

## Data and costs

- `OPENAI_API_KEY` (existing `.env`): required for live Coordinator requests and voice STT/TTS, not for deterministic current-time reading. Never put it in GitHub or screenshots.
- `HEIGIT_API_KEY` (existing `.env`): required for maps/directions/planning.
- `gpt-transcribe` transcription and `gpt-4o-mini-tts` synthesis incur **separate** usage charges. Live `gpt-4.1-mini` Coordinator/Planner also incurs charges. Open-Meteo's noncommercial tier uses its stated fair-use limits.
- Mic recording is sent to OpenAI **only when `Transcribe recording` is clicked**. Raw audio is kept only in browser/Streamlit session memory, not saved to a project file by this patch. Transcribed text may be processed by the backend API; privacy also depends on external provider policies.
- TTS is disclosed as **AI-generated**, not a human voice. Spoken replies and chat history are session-only and **not automatically persisted** by this UI. No background monitoring, event writing, or sending email.
- Saved Places file is loaded locally; demo entries are fictional and public demo points are intentionally not your real home/school. Map HTML persists in `evaluation/maps/streamlit_latest_route.html` (gitignored in previous step). The map may contain user-provided coordinates: do not publish private map files.

## Known constraints

- **One-turn push-to-talk**, not continuous realtime speech or natural conversational interruption.
- The UI does **not** interpret voice commands directly into new calendar/list/email writes; this is a read-only MVP, guarded by Python.
- Family planner currently requires explicit recognized errands, their coordinates, durations and start time plus either known hours or Saved Places. The demo JSON is user-provided mock data and may not match real schedules or holidays.
- HeiGIT duration estimates have no traffic information; routes and pickup feasibility are provisional, not arrival guarantees.
- STT may misrecognize names or locations. Review each transcript before running MINA.
- `gpt-4o-mini-tts` is deprecated and scheduled for shutdown **January 6, 2027**. We use it as a temporary, opt-in voice output for the November 2026 capstone; the recommended longer-term direction is OpenAI Realtime voice workflow, which requires different integration. For this deadline, keep text fallback working.
- Microphone permissions and local browser behavior must be verified manually on the user's Mac; offline unit tests do not prove voice/browser acceptance.

### Verification & report language

Assistant-side test results after adding UI: **156/156 unit tests PASS** and **20/20 core offline structural scenarios PASS** on a reconstructed local v1.8 baseline. Neither proves the UI runs in the user's browser or the TTS/STT API is available in their account. Record the real Mac smoke tests and screenshots separately in the Capstone evidence log, without changing earlier live-evaluation results.

Official references:

- https://docs.streamlit.io/develop/api-reference/widgets/st.audio_input
- https://docs.streamlit.io/develop/api-reference/text/st.iframe
- https://developers.openai.com/api/docs/guides/speech-to-text
- https://developers.openai.com/api/docs/guides/text-to-speech
