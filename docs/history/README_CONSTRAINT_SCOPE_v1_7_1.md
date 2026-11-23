# MINA v1.7.1 — Live planning constraint-scope guard

**Why this patch:** In the first user-reported integrated v1.7 live-route attempt, MINA recognized `library`, `groceries` and `school_pickup` but returned `needs_clarification`: `An extracted planning constraint is unassigned or not requested.` This is a validation failure **before** any provider route fetch. The trace does not include the individual extracted constraints, so the precise misassigned entry is not identified. The lack of a new HTML map was expected because no plan was selected.

## What changed

Only `mina_live_planning.py` changes in the v1.7 runtime. The `mina_coordinator.py` prompt, 20-case core benchmark dataset, `mina_runtime.py`, route-only v1.6 tool, Open-Meteo/Time tools and write guard are **not changed**.

For a constraint whose model-assigned `task_id` is `null` or not among the requested errands, `mina_live_planning` attempts one **deterministic**, limited correction **only** if:

- The model's `evidence` is a literal anchored quote in the original user request.
- Its immediate sentence/comma clause contains **exactly one** explicitly named task.
- The type is unambiguous: pickup `before/by` a deadline (or at a fixed time), library `opens` at a time, or groceries `takes/at least` a duration.
- The model's normalized numeric time or duration **matches the value actually stated** in that clause.
- That task appears in the current requested task set.

If any check fails, `needs_clarification` still blocks the route; there is **no** guessing, silent constraint dropping or synthetic substitution. Existing supported task IDs and schedule constraints are unchanged. No external write features are introduced.

## Install on top of MINA v1.7

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
cp mina_live_planning.py mina_live_planning_v1_7_backup.py
unzip -o ~/Downloads/MINA_v1_7_1_Constraint_Scope_patch.zip -d .
```

No environment keys, evaluation fixtures, or user results are overwritten.

## Verify locally

```bash
python -m unittest -v test_mina_v1_7_1_constraint_scope.py
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_7_1
```

Assistant-side snapshot verified: **111/111 unit tests passed** (103 baseline v1.7 + 8 new), and **20/20 core offline structural scenarios passed**. Route-provider responses are MOCKED in these tests; this does NOT establish live HeiGIT success on your Mac.

## Re-run the existing public-coordinate live demo

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
  --map-output evaluation/maps/live_plan_demo_v1_7_1.html \
  "For the demo, plan returning library books, buying groceries, and picking up a child before 4:30 PM. The library opens at noon, and grocery shopping takes at least 60 minutes."
```

Expected IF the Coordinator emits a recoverable anchored scope and HeiGIT responds: `STATUS: provisional_live_route_plan | ROUTE: complex` plus `LOCAL MAP`. `needs_clarification`, `no_feasible_plan` and `tool_unavailable` are possible valid safe outcomes, and must not be relabeled as successful route-planning integration.

```bash
open evaluation/maps/live_plan_demo_v1_7_1.html
```

Only open the map after `LOCAL MAP` is printed. All places/times in this demo are **illustrative**, not verified school/library locations or real operating hours, and HeiGIT estimates do not incorporate live traffic.

If `needs_clarification` persists, inspect a fresh Coordinator extraction using **only this public synthetic prompt**, and send the printed `constraints` (no keys or private addresses):

```bash
python - <<'PY'
from mina_coordinator import extract_request
q = ('For the demo, plan returning library books, buying groceries, and picking up '
     'a child before 4:30 PM. The library opens at noon, and grocery shopping '
     'takes at least 60 minutes.')
s = extract_request(q)
for c in s.constraints:
    print('KIND:', c.kind, '| TASK:', c.task_id, '| VALUE:', c.value, '| EVIDENCE:', repr(c.evidence))
PY
```

The independent core benchmark remains v1.4's historical **20/20 in one successful live run**; integration tests are logged separately.
