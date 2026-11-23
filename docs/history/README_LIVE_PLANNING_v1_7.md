# MINA v1.7 — Opt-in Complex Live-Route Planning

**Scope:** Real HeiGIT/openrouteservice **estimated driving legs** enter MINA's existing Complex Planner → deterministic Python Critic → Controller workflow. This is **not** real-time traffic, a calendar-integrated itinerary, verified opening hours, a pickup guarantee, or any external write capability.

## Installation — apply on top of v1.6

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
cp mina_runtime.py mina_runtime_v1_6_backup.py
cp run_mina_v1.py run_mina_v1_v1_6_backup.py
unzip -o ~/Downloads/MINA_v1_7_Complex_Live_Routes_patch.zip -d .
```

Only these files are installed: `mina_runtime.py`, `run_mina_v1.py`, `mina_live_planning.py`, `test_mina_live_planning.py`, and this README. No `.env`, evaluation dataset, reports, or earlier routing/weather tools are overwritten. Existing `HEIGIT_API_KEY` in your local `.env` is reused; **never share or commit it**.

## Check regressions

```bash
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_7
```

Expected on the reference snapshot: 103 unit tests pass, 20/20 offline synthetic scenarios pass. These do not confirm live HeiGIT connectivity on your Mac. Preserve earlier live evaluation outputs.

## First live demonstration: all public DEMO coordinates

The following points are example coordinates for an **illustrative scenario**, NOT verified school/library/store facilities. Times and durations are user-supplied sample assumptions. Do not rely on them for actual school pickup.

```bash
python run_mina_v1.py --live-tools --live-plan --mode deterministic --no-rag \
  --origin=-78.85030,35.73260 \
  --task-location library=-78.80320,35.77210 \
  --task-location groceries=-78.78080,35.79150 \
  --task-location school_pickup=-78.83010,35.75220 \
  --start-time 10:00 \
  --library-open 12:00 \
  --duration library=15 \
  --duration groceries=60 \
  --duration school_pickup=10 \
  --travel-buffer 10 \
  --map-output evaluation/maps/live_plan_demo_v1_7.html \
  "For the demo, plan returning library books, buying groceries, and picking up a child before 4:30 PM. The library opens at noon, and grocery shopping takes at least 60 minutes."
```

Expected after an OpenAI Coordinator extraction and successful HeiGIT API lookup:
- `STATUS: provisional_live_route_plan | ROUTE: complex` **if** at least one route order meets the modelled constraints; otherwise `no_feasible_plan` is a legitimate, safe outcome.
- Trace has `live_context`, `planner`, `critic`, and `controller`; candidate checks document the selected/rejected orders.
- A local map at `evaluation/maps/live_plan_demo_v1_7.html` is written **only if** a feasible provisional order was selected.
- The printed times are **estimated**, not verified traffic or actual school-calendar information.

Open the HTML map if generated:

```bash
open evaluation/maps/live_plan_demo_v1_7.html
```

Once that works, try `--mode llm` in place of `--mode deterministic` (the LLM proposes orders, but the Python Critic also checks every authorized permutation; an LLM candidate-generation outage falls back to bounded deterministic search). Note: the **Coordinator still needs OpenAI** to extract tasks from complex natural-language requests.

## Required provenance and safe behavior

- **Real route estimates:** HeiGIT/openrouteservice. Every candidate's full ordered route is requested, and each segment's duration is rounded up and given the explicit per-leg buffer. No fabricated travel values.
- **User inputs only:** explicit origin, `--task-location` for every task, `--start-time`, `--duration` for every task, `--library-open` (or an equivalent opening time extracted from the current request), and school pickup deadline/fixed time stated in the request.
- **No hidden defaults:** The v1.4 `FIXTURE` schedule is *never* loaded for `--live-plan`; missing required context causes `needs_clarification` **before** any routing request. `--travel-buffer` defaults to 10 minutes per segment; it is a planning assumption, not a reliability guarantee.
- **Scope:** only unique `library`, `groceries`, `school_pickup` task IDs, school pickup last, up to two full trip-order alternatives. No overnight plans. All calendar/venue availability remains unverified.
- **Fail closed:** If HeiGIT fails or returns invalid/incomplete route legs, `tool_unavailable` is returned; there is no substitute synthetic route. If no candidate is feasible, return `no_feasible_plan`, not an invented recommendation.
- **Write actions:** deterministic write guard always runs first. This mode cannot modify a calendar, list, or email.
- **Privacy:** use public/synthetic places for demos. Route map HTML files contain coordinates and remain local; `evaluation/maps/` is already gitignored. Do not publish raw private routes. Audit logs use sanitized metadata and exclude coordinates, keys, and requests.

## What the evaluation numbers mean

- The **v1.4 core live benchmark 20/20** remains a separate historical observation on a synthetic test dataset and OpenAI API calls.
- Local regression results after staging v1.7: **103/103 unit tests** and **20/20 offline synthetic**.
- Live HeiGIT **route-only** v1.6 smoke test was reported successful by the user.
- v1.7 **integrated Complex live-route** test is **not verified** on the user's Mac until the demonstration command is run and its result is observed.
- Future v1.7 results should be reported as a separate `Live Route Planning` integration suite, not added to the 20-case synthetic score denominator.
