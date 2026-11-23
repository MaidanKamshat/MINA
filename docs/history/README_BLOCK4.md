# MINA — Block 4: Optional sanitized audit logging

## Goal
Keep a record of **which** components ran and how the synthetic planner behaved,
without saving user prompts, responses, API keys, retrieved note text, or exception messages.

## Install (Mac)
Extract all `.py` files (`mina_audit.py`, `run_mina_v1.py`,
`test_mina_audit.py`, `mina_coordinator.py`, `test_mina_coordinator.py`) into
`~/Documents/MINA_Day1_baseline`. Replace existing files when prompted.
The coordinator update introduces `school_preparation` and corrects the known
misclassification of "prepare for school" as a `meal`.
Do not copy or overwrite `.env`.

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
python -m unittest -v test_mina_audit.py
python -m unittest -v test_mina_runtime.py test_mina_coordinator.py
python run_offline_checks.py
```

## Log two real runs
```bash
python run_mina_v1.py --mode deterministic --no-rag --audit-log
python run_mina_v1.py --mode deterministic --no-rag --audit-log \
  'Tomorrow return library books, buy groceries, and pick up my daughter from school before 11:00 AM. The library opens at noon, and groceries need at least 90 minutes.'
```

The Coordinator still uses one OpenAI API call even in deterministic planner mode.
Inspect the output file safely:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('evaluation/mina_runs.jsonl')
for i, row in enumerate(p.read_text().splitlines(), 1):
    d = json.loads(row)
    print(i, d['status'], d['route'], d['planner_mode'], d['elapsed_ms'],
          f"candidates={len(d['candidate_checks'])}")
PY
```

Expected: first run `synthetic_plan`, second `no_feasible_plan` if the quoted request
extracts the specified constraints. Logs are **evidence of execution**, not
independent correctness judgments or calibrated reliability measurements.
Do not share real personal data in any public evaluation log.

## Next
Day 2: build a labeled set of synthetic cases, run repeatedly using fixed fixtures,
and compute acceptance metrics with an **independent expected-outcome label**.

## Retest the simple school request (one live Coordinator and one LLM response call)
```bash
python run_mina_v1.py --mode llm --audit-log \
  'What should I prepare for school tomorrow?'
```
Expected: `ROUTE: simple`, with `task_ids: ["school_preparation"]`.
If classification still differs, preserve the output for debugging; no live API
accuracy is asserted from mocked tests alone.
