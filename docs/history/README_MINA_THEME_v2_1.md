# MINA v2.1 — Burgundy & Powder Blue Chat Theme

This is **design option #2** (burgundy + warm cream + pale powder blue), based on the four approved interface mockups. It changes **only the Streamlit presentation layer**; the established MINA v1.8 backend and the functioning v2.0 unified text/voice flow are retained.

## Visual design

- Warm cream page background (`#F8F4F1`) with barely visible powder-blue corner gradients.
- `Welcome, I’m Mina` centered in refined serif lettering; **Mina** in burgundy (`#6A203D`).
- `My Intelligent Navigation Assistant` with the **M, I, N, A** initials highlighted in that same burgundy.
- Subtitle `Your everyday planning companion` with no period, in a soft secondary tone.
- Soft powder-blue user messages, cream MINA replies, low-contrast borders and shadows.
- One native, fixed-to-bottom Streamlit chat composer with **both microphone and send arrow**. No extra transcription or Ask buttons.
- Sidebar settings, Family Planner, maps, explanations and voice playback remain functional. The reference illustration's bell/profile icons were not added because MINA does not implement those features.

This is implemented with a separate `mina_theme_v2_1.css` file for future small color changes; the app imports that stylesheet at startup. Styling of Streamlit internal DOM selectors is best-effort and may vary with future Streamlit releases. No external fonts, images, API calls, CDN dependencies or background pictures were added.

## Install on the Mac

1. Stop running Streamlit in Terminal (`Control+C`). Download `MINA_v2_1_Burgundy_Chat_Design_patch.zip` into Downloads.
2. Run:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_v2_0_backup.py
unzip -o ~/Downloads/MINA_v2_1_Burgundy_Chat_Design_patch.zip -d .
python -m unittest -v test_mina_theme_v2_1.py
python -m streamlit run streamlit_app.py
```

If the Streamlit process is already running, Streamlit may automatically reload on file changes, but restarting is recommended.

## Smoke tests and expected results

1. Open http://localhost:8501; the empty page shows the burgundy/cream/blue theme and the three correct greeting lines.
2. Type `What time is it?` in the single composer and submit; chat bubble and MINA response should appear. This exercises unchanged Time Tool.
3. Record `What's the weather tomorrow and what should the kids wear?`; stop recording and submit via the same arrow. Confirm transcription, weather response, and optional AI voice playback.
4. Try `Add a school event to my calendar.` The result must still be `approval_required`; no write is executed.
5. Optional: use the Family Planner sidebar and verify the demo map and 3:15 PM–3:30 PM pickup window. Those capabilities are unchanged.

## Scope / evidence

Assistant-side checks: Python syntax and source-based theme/behavior regression tests. Existing app logic is unchanged except CSS/theme loading, brand wordmark and welcome markup. The assistant does **not** have the owner's running browser; the precise appearance and interactive behavior of v2.1 require confirmation on the Mac. Do not confuse the design mockup's sample weather values with an actual weather forecast.
