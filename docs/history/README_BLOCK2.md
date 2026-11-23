# MINA — Block 2: Structured State + Coordinator

This patch is designed for your existing `~/Documents/MINA_Day1_baseline` folder.
Copy these NEW .py files directly into that folder. Nothing in this patch
replaces `.env`, `family_notes.json`, or your original Python modules.

## What it implements
- `mina_state.py`: typed request state.
- `mina_coordinator.py`: OpenAI structured-output extraction, task/constraint
  evidence checks, and selective `simple` / `complex` routing.
- `test_mina_coordinator.py`: offline mocked tests.
- `try_coordinator.py`: one actual LLM call to inspect an example request.

## What it does NOT implement yet
- No real calendar, maps, or weather calls.
- No list/calendar/email writes.
- No end-to-end Planner / Critic / Controller execution from this entry point.
- No security guarantee from evidence matching alone; extraction can still
  misunderstand negation or task semantics, so later evaluation is required.

## Mac commands
```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
python -m unittest -v test_mina_coordinator.py
python try_coordinator.py
```

Running `try_coordinator.py` uses the API key stored in this folder's `.env`
and calls the OpenAI API once. It can incur a small charge.

Expected `route` for the default sample query: `complex`. The printed result
should include `library`, `groceries`, `school_pickup`, the 14:30 deadline,
12:00 library opening, and 90-minute grocery duration.
