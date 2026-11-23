# MINA v2.3 — Read-only Errand Planning vs Write-Action Intent

**Patch type:** Backend safety/routing correctness fix, not a new integration.
**Status:** Offline-regression tested in a reconstructed project; live Streamlit re-test required.

## Problem observed on 2026-11-21

For the main family-planning demonstration (return library books, buy groceries, pick up a child before 4:30 PM, with library opening/duration constraints), the running UI returned:

> I can prepare that change, but no list/calendar/email write tool is connected. I have not changed or sent anything.

This sentence comes from `mina_runtime.run_state`'s `approval_required` branch. The user did **not** request an external mutation. The direct deterministic guard does **not** classify the documented request as a write command, so an incorrect model-generated write flag and/or task label is the likely explanation. The precise offending model field was **not logged in the supplied screenshot/output**, so this is a high-confidence diagnosis, not a reproduced OpenAI live trace.

## Patch behavior

- `mina_coordinator.py`: instruction clarification plus **high-precision repair** of hallucinated write flags for requests explicitly asking for the best order/plan of **at least two** recognizable `library`, `groceries`, `school_pickup` errands. Repair is based on quoted text evidence. It is disabled if the message mentions calendars, lists, emails, send/add/delete/update, booking or similar possible write context. Real `calendar_update`/`shopping_list_update`/`email_draft` tasks are never silently executed.
- `mina_write_guard.py`: adds conservative detection of **compound** mutations such as “Plan my errands and add a school event to my calendar.” The independent runtime gate remains unchanged. It still blocks all recognized external write requests, and there are still **no connected external write tools**.
- `test_mina_v2_3_planning_intent.py`: 13 no-network regression tests, including a mocked hallucinated write response, runtime read-only route dispatch, W03, grocery-list mutation, and compound write tests.

**No change to** `mina_runtime.py`, `mina_live_planning.py`, `mina_planning.py`, the saved-place clock parsing, speech/audio, UI styling, or evaluation fixtures.

## Install (Mac)

Stop Streamlit with **Ctrl+C** in its terminal. In the current MINA project:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp mina_coordinator.py mina_coordinator_before_v2_3.py
cp mina_write_guard.py mina_write_guard_before_v2_3.py
unzip -o ~/Downloads/MINA_v2_3_Plan_vs_Write_Fix.zip -d .
python -m unittest -v test_mina_v2_3_planning_intent.py
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v2_3
python -m streamlit run streamlit_app.py
```

The tests do not require a live API key; browser demo does. `.env` and saved places are unaffected.

## Important UI setting for an actual map

The v2.2 chat is **not yet a general-purpose automatic tool selector for real routing**. Open the sidebar and choose **Mode → Family planner**, select the three demo errands, check the public demo coordinates and task durations, enable demo Saved Places, choose a **weekday demo date** (e.g., **Monday, November 23, 2026** in the synthetic calendar; this is **not** verified as a real school attendance day), and check **I reviewed the locations, durations and hours**. The app defaults to Assistant mode, which will **not** supply a `live_plan` object and therefore cannot generate the live family-plan map.

### Voice or text test

> Mina, I need to return library books, buy groceries, and pick up my child from school before 4:30 PM. The library opens at noon, and grocery shopping takes at least 60 minutes. Please find the best order for these errands.

Expected **if the external tools and the user-supplied demo constraints cooperate**: `provisional_live_route_plan`, a route map, and schedule constraints including pickup window 3:15–3:30 PM. If the route doesn't fit, `no_feasible_plan` is acceptable. `approval_required` **is not correct** for this read-only prompt.

Also retest:

1. `Add a school event to my calendar.` → `approval_required`
2. `Add milk to my grocery list.` → `approval_required`
3. `Plan my library and grocery trip and add a school event to my calendar.` → `approval_required`

## Test evidence

In one **reconstructed** baseline project, 190/190 Python unit tests passed (177 pre-patch tests available in that reconstructed copy + 13 new tests); the 20-case **offline structural** evaluation remained 20/20. These counts may differ from the Mac working tree because not all earlier intermediate scratch tests are distributed in the patches. No fresh full **live** 20-case LLM evaluation or real HeiGIT route test is claimed for v2.3; those must be run on the Mac.

## Restore

```bash
cp mina_coordinator_before_v2_3.py mina_coordinator.py
cp mina_write_guard_before_v2_3.py mina_write_guard.py
```
