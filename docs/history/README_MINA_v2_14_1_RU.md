# MINA v2.14.1 — Natural-language Cancel hotfix

**Base:** MINA v2.14.0 already installed on the Mac. **Do not install v2.13.2.**

**User-observed bug:** after MINA asked for a departure time, `Cancel that route plan` incorrectly fell into the generic route helper and displayed CLI flags (`--origin`, `--destination`, `--via`). The pending route did not resume afterwards, but the user never received an acknowledgement.

**Root cause:** `mina_conversation_state_v214.py` accepted `Cancel route` but did not accept the natural phrase `Cancel that route plan`; it returned `new_request` instead of `cancel`. Streamlit's existing `cancel` handler was therefore bypassed.

**Fix:** recognize common standalone, route-scoped cancellation phrases (including `Cancel that route plan`, `Cancel the pending route plan`, `Never mind`, `Stop planning this trip`) while a verified route is pending. Route cancel goes through Streamlit's existing no-write, no-routing acknowledgement. A request to cancel a dentist appointment is **not** treated as a route cancel. A new topic still clears the waiting route. Version in conversation trace is `2.14.1`.

**Scope:** only `mina_conversation_state_v214.py` changes; a new `test_mina_cancel_lifecycle_v2141.py` is added. Streamlit, Family Hub JSON, saved pins, lists, calendar, API tokens and all private files are left untouched. No emails or calendar events are changed.

## Install on Mac

Stop Streamlit with Control + C. Then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
mkdir -p .mina_backup_before_v2141
cp -p mina_conversation_state_v214.py .mina_backup_before_v2141/
unzip -o ~/Downloads/MINA_v2_14_1_Cancel_Task_Lifecycle_Fix.zip -d .
python -m unittest -q test_mina_cancel_lifecycle_v2141.py test_mina_conversation_state_v214.py
python -m streamlit run streamlit_app.py
```

For the **full local suite**, rerun the seven test modules used for v2.14 if they are already installed. The patch ZIP contains no dependencies beyond the existing v2.14 installation.

## Mac acceptance

1. Start the same Costco → Library → School request **without departure time**. Wait for `What time would you like to leave?`.
2. Send exactly: `Cancel that route plan`.
3. Expect **`Cancelled the pending route. No route was calculated and no data was changed.`** and a `conversation_state` trace with `status: cancel`, `version: 2.14.1`.
4. Send `12:30 PM` separately. It must **not** resume the cancelled route.
5. Optionally retest new-topic switch to Target list, then `12:30 PM`: no old route should resume.

**Evidence classification:** local unit tests are not Mac acceptance tests. Record the prior failure and next Mac result together in the later consolidated Evidence Log. Do not create a separate log for each test. Do not send unredacted saved routes/address pins into a public report.

## Revert

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
cp -p .mina_backup_before_v2141/mina_conversation_state_v214.py .
python -m streamlit run streamlit_app.py
```
