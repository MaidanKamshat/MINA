# MINA v2.15 — Local Memory, Standalone Reminders and Basic Multi-turn Slots

**Build:** 2026-11-22. **Target:** install over working v2.14.2 on Mac. **Scope:** additive pre-submission feature extension; no model changes or remote writes added.

## What's new

1. **Standalone Reminders**: user-owned JSON stored in `~/.mina/reminders_v215.json`. Voice create → preview → explicit Confirm/Cancel. Read voice queries by date/day/range. In Settings, manually mark done/delete with a separate confirmation. Reminders are independent from MINA Calendar / Google Calendar. They appear as in-app due reminders **while MINA is open**; **no push notifications or background scheduling**.
2. **Persistent conversation history**: text-only SQLite archive `~/.mina/conversation_memory_v215.sqlite3`. **Off by default**; manually opt in under Settings → Private conversation memory. Remembers future text exchanges across restarts (no audio, map HTML or debug traces). Literal-text lookup via “What did I tell you about Costco?”; explicit pinned facts via “Remember that ...” + Confirm. View, delete pinned facts, clear archive or clear all. Memory is **local plaintext, not encrypted**, does not backfill prior unrecorded chats and does **not** automatically inject all messages into LLM prompts. This is searchable long-term history, **not yet semantic RAG/memory summarization**.
3. **Small multi-turn flows**: “Add oatmeal to my shopping list” → “Which store?” → “Target” → **Confirm local list update**. “Schedule a dentist appointment” → date/time → **Confirm calendar event** (Google synchronization retains previous setting). Intermediate slot collection **does not write**. Pending list/calendar states expire after 30 minutes and are session-only.
4. The underlying LLM is **unchanged**. Model choice should be assessed by a separate A/B test once submission-critical features are stable.

## Install

Stop Streamlit in Terminal using Control+C, then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v215
cp -p streamlit_app.py .mina_backup_before_v215/
unzip -o ~/Downloads/MINA_v2_15_Lite_Reminders_Memory_Multiturn.zip -d .
python -m unittest -q test_mina_v215.py
python -m streamlit run streamlit_app.py
```

Do not delete other project files. Patch only overwrites `streamlit_app.py` and adds three standalone modules and a test file. Saved Places, private pins, calendars and shopping lists are untouched by installation.

## Two-minute acceptance tests (avoid real appointments)

- **Reminder**: Say “Mina, remind me on November 24, 2026 at 9:00 AM to check MINA QA TEST.” Expect standalone reminder preview, click Confirm. Then say “Mina, what reminders do I have for November 24, 2026?” In Settings mark done/delete with confirmation to clean up. **No Google event should be created.**
- **Local history**: Settings → Private conversation memory → check opt-in. Say “Mina, remember that MINA QA prefers early appointments.” Confirm pinned memory. Restart Streamlit, ask “Mina, what do you remember about early appointments?” This uses literal matching, not semantic inference. Test deletion using Settings.
- **Shopping slot**: “Mina, add MINA QA oatmeal to my shopping list.” → “Target.” Expect preview; press Cancel to avoid modifying real list.
- **Calendar slot**: “Mina, schedule a dentist appointment.” → “November 24, 2026 at 10:00 AM.” Expect calendar Preview, press **Cancel** (Google sync may be enabled).
- **Smoke regression**: read Target list; ask weather; verify existing route continuation and Cancel; check persistent geocoding toggle.

## Revert if any problems

Stop Streamlit and run:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v215/streamlit_app.py ./streamlit_app.py
python -m streamlit run streamlit_app.py
```

New module files can remain unused without affecting v2.14.2. Do not delete local `~/.mina` without a backup if you wish to preserve saved reminders/history.

## Privacy / limitations

- Text history is opt-in, local, plain SQLite (not encrypted). Avoid saving secrets and sensitive data; do not publish it or your route data.
- OpenAI STT and regular API calls still use existing remote services. Local history is not itself uploaded or added to model prompts.
- App UI may show private content if the user opens the Settings history panel.
- No background timers or notifications after closing MINA.
- Reminder parser uses explicit full date + AM/PM time. Natural language variants beyond demonstrated formats are not promised.
- Calendar/list multi-turn is intentionally constrained. Existing deterministic confirmation gates are preserved.
- Only selected local tests and syntax checks have been run in this build environment. A full on-Mac integration test is required before demonstrating v2.15 as complete.
- The model currently used by the active backend is not confirmed by this patch. Do not assume old `gpt-4.1-mini` references still reflect active configuration.

**Submission advice:** Keep v2.14.2 as your proven demo fallback. Do not delay CMU report/video to expand v2.15 indefinitely.
