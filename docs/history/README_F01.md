# MINA Evaluation: F01 ambiguity correction (dataset v1.1)

## Why
Original F01: `Plan grocery shopping and a dentist appointment before 2:30 PM.`
This could mean the deadline applies to both errands or just to the appointment.
The original gold label assumed the latter without sufficient evidence, and the live
LLM assigned the deadline to both. This is not necessarily a model failure.

## What changed
Only the F01 request and rationale were clarified. The labeled constraint is
still deadline(appointment, 14:30), with literal evidence `before 2:30 PM`.
All other 19 cases and all expected outcomes are unchanged.

## Scientific integrity
Keep a copy of the original dataset (v1.0) and its 3/4 live pilot results.
Report that the pilot surfaced an ambiguous evaluation item. Treat the new
v1.1 run as a separate evaluation dataset with a different SHA256 hash.

## Installation on Mac
From the MINA project folder:

```sh
cp evaluation/scenarios.json evaluation/scenarios_v1_0.json
unzip -o ~/Downloads/MINA_F01_dataset_clarification_v1_1.zip -d .
python eval_mina.py --mode offline
python eval_mina.py --mode live --cases F01 --output-prefix evaluation/results/live_F01_v1_1
```

The live command uses OpenAI API and incurs API cost. It does NOT call real
maps or calendar tools. After a successful pilot, run the full 20 cases and
preserve outputs under an explicit prefix such as
`evaluation/results/live_final_v1_1`.
