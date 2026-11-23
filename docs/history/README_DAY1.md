# MINA — Day 1 baseline (not final capstone MVP)

This is a cleaned copy of the user's previously uploaded prototype modules. No new features are asserted.

## Status and limitations
- Router is regex-based (`complexity_router.py`) and returns `direct` / `tot_candidate`.
- Retrieval embeds 100 synthetic notes with `all-MiniLM-L6-v2`.
- ToT is a **single-level synthetic candidate comparison**, not full Tree-of-Thought.
- Integrated agent only uses a special controlled fixture for a query with library + shopping + school pickup at 2:30 PM. The general planning workflow is **NOT yet implemented**.
- No real calendar/maps/weather tool is connected, and no write actions are performed.
- For non-fixture queries the interactive agent calls the OpenAI API, which requires your API key and can incur charges.

## Local quickstart (Mac terminal)
```bash
cd MINA_Day1_baseline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Open .env locally and replace placeholder key. Never upload this file to GitHub.
python run_offline_checks.py
python mina_agent_tot_integrated.py
```

To test only the **offline** deterministic parts, you can omit the dependencies installation, provided `python3` is installed, and run `python3 run_offline_checks.py`.

## Today
1. Verify this baseline.
2. Introduce structured task and fixture data (no more hard-coded text-specific schedule).
3. Unify simple and complex routing.
4. Wire Planner → Critic → Controller and enforce output safety.
5. Run offline regression tests.

## Source
All code here is copied from the uploaded experimental files without changing their behavior. Original uploaded files remain untouched.

## Small test-harness repair
The uploaded latest AM/PM-format integrated script uses `format_time()` inside `synthetic_plan_answer()`. Its AST-isolating test did not provide that helper, so it failed when used with the latest version. The test in this starter package injects that existing helper into its test namespace. The agent implementation was not changed.
