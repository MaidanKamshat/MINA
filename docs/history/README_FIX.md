# MINA Coordinator v1.3 — bounded repair for unanchored evidence

Why: after v1.2 live evaluation, P06 failed because the LLM supplied task evidence that was **not an exact contiguous substring** of the user's actual message.

What changes: when and **only when** an `UnanchoredEvidenceError` occurs, retry the same structured extraction **once** with stronger exact-quotation instructions. Validation is unchanged, and second invalid evidence still fails closed. There is no automatic rewriting of a questionable task ID. Valid first attempts cost no extra model call.

## Install

From the project root (with `.venv` activated):

```bash
cp mina_coordinator.py mina_coordinator_v1_2_backup.py
unzip -o ~/Downloads/MINA_Coordinator_v1_3_evidence_retry.zip -d .
python -m unittest -v test_mina_v1_3_evidence_retry.py test_mina_v1_2_regressions.py test_mina_coordinator.py test_eval_mina.py
```

## Live retest

```bash
python eval_mina.py --mode live --cases P06 --output-prefix evaluation/results/live_P06_retry_v1_3
```

Check `P06 PASS synthetic_plan`. If it fails, preserve the result and inspect; do not change the ground-truth dataset. On success, run the full 20-case regression and save it under a **new** prefix:

```bash
python eval_mina.py --mode live --output-prefix evaluation/results/live_full_v1_3 --show-manual-answers
```

## Important limitations

- Retrying model extraction can add one API call and latency for an affected case.
- This patch does **not** guarantee a correct result for P06 or any new input.
- The model still may select incorrect task IDs; evidence anchoring only verifies that a quoted span exists in the input.
- It does not replace independent runtime validation of constraints and authorization.
