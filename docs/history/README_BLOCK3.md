# MINA Block 3 — Integration: Planner → Critic → Controller

This is a PATCH for the existing `~/Documents/MINA_Day1_baseline` folder.
It adds **4** new `.py` files. It does not modify `.env`, the prior Coordinator,
old experiments, or `family_notes.json`.

## Flow
1. Existing `mina_coordinator.py` extracts authorized task IDs and constraints
   with a real OpenAI Responses API call.
2. `mina_runtime.py` selects simple vs complex handling. Simple requests **do not**
   execute the scheduling Planner, Critic, or Controller.
3. Complex requests use `mina_planning.build_context()` to combine a **synthetic**
   local fixture with explicit request constraints. No actual calendar/maps/hours.
4. The Planner generates candidate task orders (LLM or deterministic smoke-test mode).
5. Python Critic checks only authorized tasks, task order, opening time, duration,
   known simulated travel durations, and deadline. No LLM self-evaluation.
6. Programmatic Controller selects a feasible candidate, rejects all if none are
   feasible, or requests missing context. Small bounded search enumerates all
   allowed orders to prevent model omissions within this limited 3-task fixture.
7. The final answer is assembled from the checked plan; **not** freely rewritten.

## Install patch (Mac)

1. Download and unzip `MINA_Block3_patch.zip`.
2. Copy `mina_planning.py`, `mina_runtime.py`, `run_mina_v1.py`, and
   `test_mina_runtime.py` into `~/Documents/MINA_Day1_baseline`.
3. Do **not** copy or upload `.env` anywhere.
4. From Terminal:

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
python -m unittest -v test_mina_runtime.py
python -m unittest -v test_mina_coordinator.py
python run_offline_checks.py
```

## First end-to-end run

**First run with no RAG, deterministic candidate search:**

```bash
python run_mina_v1.py --mode deterministic --no-rag
```

This makes **one paid API call** for Coordinator extraction, but no paid
planning call, and uses no embedding model.

**Then test LLM Planner (two API calls total):**

```bash
python run_mina_v1.py --mode llm --no-rag
```

**Finally test full MINA with RAG:**

```bash
python run_mina_v1.py --mode llm
```

RAG may download the pretrained embedding model on first use.
All outputs and travel times remain **synthetic**, even when RAG and the LLM
Planner are activated.

**Example impossible deadline:**

```bash
python run_mina_v1.py --mode deterministic --no-rag "Tomorrow I need to return library books, buy groceries, and pick up my daughter from school before 11:00 AM. The library opens at noon, and groceries take at least 90 minutes."
```

## Supported scope / known limitations

- Supports scheduling only unique tasks of types `library`, `groceries`, and
  `school_pickup` (up to three). Other task types fail closed and ask for context.
- In this MVP, school pickup is modeled as the last stop.
- Default test fixture: start 10:00, school pickup window opens 14:00, pickup
  deadline 14:30 unless overridden by a request, library opening 10:00 unless
  overridden by a request, with invented durations/travel times from previous
  `tot_planner.FIXTURE`. These are **not** sourced from actual venues.
- Time math uses same-day HH:MM clocks; no overnight scheduling, timezone/DST,
  live route updates, or real-world feasibility claims.
- A small exhaustive bounded search is **not** a full multi-level Tree of Thought.
- Coordinator checks exact evidence excerpts. That check does not guarantee
  semantic correctness (e.g., negation), so the end-to-end system needs further
  evaluation against natural-language edge cases.
- The simple branch can return a non-actionable answer from an LLM, but any
  request for writes is blocked because no write tools exist yet.
- `approval_required` means no change has occurred; it is not a completed
  approval or working calendar integration.

## What to send for review

Send the terminal output starting with `STATUS`, then `TRACE`, `CANDIDATE CHECKS`
and `MINA`. Do not send `.env` or the API key.
