# MINA v2.0 — Minimalist unified chat + voice

**Status:** UI redesign completed locally. Browser acceptance on the owner's Mac pending. The stable MINA backend v1.8 and the existing 20-scenario fixture evaluation have **not** been changed by this patch.

## User-requested behavior

- White, quiet interface with a centered **Welcome! I am MINA — My Intelligent Navigation Assistant.** greeting on the initial empty page.
- ONE bottom-aligned Streamlit chat input containing keyboard input, built-in microphone and send arrow (`st.chat_input(accept_audio=True)`). No separate transcription/review pane or Ask MINA button.
- After sending text: the text appears in a user chat bubble, and the answer appears immediately below as an assistant bubble once the backend returns.
- After recording voice: finish the recording and press the **same chat-input send arrow** once. MINA automatically runs speech-to-text and then the unchanged read-only backend; the transcript appears as a user bubble, the answer appears as an assistant bubble. There is **no separate Transcribe or Ask MINA click**. The browser's recording/stop/send gestures still exist; this is not a hands-free always-listening assistant.
- A voice request may trigger optional TTS response, playable from the assistant chat bubble. Modern browsers may require pressing Play rather than allowing unattended autoplay. A short `🔊 Listen` action is available for responses without generated audio.
- The chat history remains visible *within the Streamlit session*. Each backend request currently runs as a separate task; visible chat history does not add multi-turn reasoning/memory to the MINA Coordinator.
- The Settings sidebar is collapsed initially. Directions and Family Planner stay accessible there, with the same public demo data and explicit confirmation of unverified planning assumptions. Route maps, candidate checks and trace stay attached to the relevant assistant response.
- A voice transcript is **automatically submitted after chat send**; it is not manually reviewed beforehand. All actions remain read-only and write requests must still produce `approval_required` through the existing backend safety gate.

## Installing on the user's Mac

1. Download `MINA_v2_0_Minimal_Chat_UI_patch.zip` to Downloads.
2. Stop the currently running Streamlit server in its Terminal window with **Control+C**.
3. In Terminal:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_v1_9_backup.py
unzip -o ~/Downloads/MINA_v2_0_Minimal_Chat_UI_patch.zip -d .
python -m pip install --upgrade -r requirements_ui.txt
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v2_0
python -m streamlit run streamlit_app.py
```

If the project path is different, `cd` into the actual project directory. The project `.env`, Saved Places, personal notes and stable backend files are not included in this ZIP and should not be uploaded publicly.

**Streamlit >=1.52** is required: earlier versions do not support microphone recording inside `st.chat_input`. The requirement file requests an upgrade, but network access on the user's Mac is needed for installation.

## Recommended browser acceptance

1. **Clean landing:** The welcome text is centered; no red button, transcription pane or separately displayed Ask MINA button. One composer with mic and send arrow is anchored to bottom.
2. **Keyboard → weather:** In Assistant mode, type `What's the weather tomorrow and what should the kids wear?` and press Enter/send. A chat reply with a real Open-Meteo source should appear. No voice capture is required.
3. **Mic → reply:** Use the mic in the SAME composer, say `What time is it right now?`, stop, then press Send. Expect the transcript user bubble, a time response below, and, if configured, a playable generated voice response. The voice recording is sent for paid transcription only on submission.
4. **Safety:** Ask `Add a school event to my calendar.` Status should be `approval_required`; no calendar edits occur.
5. **Family planning:** In the collapsed sidebar choose Family planner; review and explicitly confirm demo assumptions. Request a plan and verify the 3:15 PM–3:30 PM school pickup window and optional map. The chosen date must be a weekday and match the demo settings.

**Data/safety:** The UI itself never invokes calendar, email, or list writes. Raw microphone bytes are handled in memory for STT and not saved to a project file. Transcribed text can be logged by the existing backend and sent to OpenAI; don't speak sensitive private data in the capstone demo. Voice STT/TTS and LLM calls may incur API charges. A failed STT/API request reports an error and does not invent a response. The app stores chat text and optional TTS bytes in Streamlit session state; HTML map files remain local under `evaluation/maps/`, which must remain gitignored. TTS playback is not guaranteed to autoplay.

## Verification status

- Assistant-side reconstruction of MINA v1.8 + v1.9 UI + this patch: **165/165 unit tests passed**, including 9 added unified-input parsing tests.
- Original **20/20 core offline structural scenarios passed** unchanged.
- **No live Streamlit browser acceptance has been observed yet for v2.0**; live voice and voice UX must be checked on the owner's Mac.
- Streamlit itself was not importable in the assistant's runtime, and package installation could not complete due restricted network; the code is syntax-checked and the native API is grounded in official Streamlit docs.

Official source: https://docs.streamlit.io/1.52.0/develop/api-reference/chat/st.chat_input
