# MINA — Day 2 Evaluation (synthetic cases)

This is a **patch for the Day 1 MINA project**, not a standalone agent. It reuses yesterday's `mina_coordinator.py`, `mina_runtime.py`, `mina_planning.py`, `mina_state.py`, etc.

## What's included

- `evaluation/scenarios.json`: 20 human-labeled **synthetic** requests and expected outputs.
- `eval_mina.py`: runs the same MINA pipeline, computes structurally verifiable metrics, saves JSON/CSV/Markdown reports.
- `test_eval_mina.py`: 5 tests of dataset validity, score integrity, and a mocked live call chain.
- `evaluation/manual_review_sheet.csv`: a small form for evaluating simple LLM answers that automated status checks cannot judge semantically.

**Do not replace your existing `evaluation/` directory**, because it contains yesterday's `mina_runs.jsonl`. Merge the new `scenarios.json` and review sheet into it.

## Step 1: Install patch without changing `.env`

Extract the ZIP. Move `eval_mina.py`, `test_eval_mina.py`, and `README_DAY2.md` into your `~/Documents/MINA_Day1_baseline/` folder. Place `scenarios.json` and `manual_review_sheet.csv` inside its `evaluation/` folder.

Alternatively, in Terminal after downloading the ZIP:

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
unzip -o ~/Downloads/MINA_Day2_Evaluation_patch.zip -d .
```

The ZIP has files at its root, so it merges into the working project. It **does not contain `.env` or `mina_runs.jsonl`** and does not replace any Day 1 Python modules.

## Step 2: Test evaluation infrastructure (NO API calls)

```bash
python -m unittest -v test_eval_mina.py
```

Expected: `Ran 5 tests` and `OK`.

## Step 3: Run all 20 offline evaluations (NO API calls)

```bash
python eval_mina.py --mode offline
```

Expected for this known baseline: `20/20 structural PASS`. Three files will be generated:

- `evaluation/results/offline_deterministic.json`
- `evaluation/results/offline_deterministic.csv`
- `evaluation/results/offline_deterministic.md`

**CRITICAL:** Offline mode supplies the correct, human-annotated structured intent to MINA and uses deterministic candidate generation. It does *not* measure how well an actual LLM understands requests or follows RAG context. It is essentially a deterministic runtime regression test. Never label its millisecond latency as real API latency or its 100% pass rate as end-to-end LLM accuracy.

## Step 4: Four live end-to-end smoke cases (USES OPENAI API)

Run only after offline test passes:

```bash
python eval_mina.py --mode live --cases S01 W01 P01 F01 --show-manual-answers
```

- S01: school preparation information (simple path, retrieval)
- W01: add milk to grocery list (blocked, no write tools)
- P01: errands + library noon opening + 90-minute groceries + 2:30 pickup
- F01: groceries + dentist (unsupported scheduling context, clarification)

This uses your real OpenAI Coordinator (and specialized LLM planner for P01), plus RAG on non-write requests. Multiple paid API calls will be made; results will vary and errors are informative. The first RAG call might need to download the public embeddings model. **We cannot predict the live pass rate in advance.**

You will get three report files in `evaluation/results/live_llm.*`.

The `--show-manual-answers` flag prints S01's informational answer to Terminal for review but does not persist that text in the JSON/CSV/Markdown reports.

Read `SUMMARY` and any `FAIL` lines. Send **case IDs and error summaries only**; never send your API key, `.env` file, or unredacted personal information.

## Step 5: Full live evaluation (after smoke review)

```bash
python eval_mina.py --mode live --show-manual-answers
```

20 cases; the number of LLM calls varies depending on router decisions, so it can incur additional API usage charges. Results overwrite `evaluation/results/live_llm.*`. Save or rename preliminary smoke reports if you want to retain them.

Optional: disable RAG for troubleshooting:

```bash
python eval_mina.py --mode live --no-rag --cases P01
```

Use the full `--mode live` run (with RAG) as the primary end-to-end evidence if it completes, not an offline number.

## What's being measured

Automated structural checks include:

1. Correct top-level result status and simple/complex route.
2. Correct intent, authorized task ID set, and extracted constraints compared against human-labeled inputs.
3. Feasibility of any **selected** synthetic plan according to deterministic Critic, plus expected outcome label.
4. No unauthorized task IDs in a selected schedule.
5. Explicit deadline checks in the selected synthetic timeline.
6. No write actions: list/calendar/email changes must be blocked.
7. Correct safe response when no feasible schedule exists or fixture lacks required information.
8. Measured wall-clock latency and reported OpenAI token usage (live only).

The manually labeled dataset is small, and all scenarios are synthetic; metric values cannot be generalized as production reliability. The planner's bounded exhaustive fallback is part of the implementation, so **do not attribute selected-plan success exclusively to LLM planning**.

**Manual answer review:** S01–S04 are informational. Their automatic `simple_response` status can pass while the actual answer is unhelpful or ungrounded. Use the review sheet to score groundedness and unsupported claims. In particular, MINA has no live weather API, so S03 should not claim a verified forecast.

**No external writes:** `approval_required` means MINA blocked an action because no write tool exists. It does not prove a completed human-approval workflow.

## For the final Capstone report

Keep separate numbers for:

- **Offline runtime checks** (correct extraction already supplied; no OpenAI calls).
- **Live end-to-end checks** (LLM parsing, planning, RAG, Python Critic and Controller; synthetic scheduling fixtures).
- **Manual factual/groundedness review** of informational answers, if completed.

Suggested accurate sentence, after collecting actual results:

> In 20 manually labeled synthetic test scenarios, MINA achieved [X/20] automated structural passes in the live end-to-end evaluation. The deterministic runtime regression suite passed [Y/20] checks when supplied with ground-truth structured requests. All scheduling feasibility claims were limited to simulated opening hours and travel times; no live Calendar/Maps integrations were used.

Do not replace X and Y until you have observed the results on your Mac.
