# MINA v2.15.4 — Testing and Verification

**Project:** MINA — My Intelligent Navigation Assistant
**Release designation:** Final Integrated and Validated Prototype
**Document scope:** Test inventory, reproducible commands, known evidence, and outstanding release verification.

> **Evidence policy:** A test existing in the repository is **not** evidence that it was run or passed. Distinguish code inspection, automated execution, and user-observed Mac/browser acceptance tests. Never mark unexecuted checks as PASS.

## 1. Testing layers

| Layer | Purpose | Evidence and current state |
| --- | --- | --- |
| Static inspection | Check Python syntax, file structure and imports | Prior audit of the supplied code archive reported no Python syntax errors; this does not imply that all runtime imports or API calls will succeed. |
| Offline unit/regression tests | Test deterministic business rules without live external services | Selected subset executed in an isolated extraction; results below. |
| Integration tests | Verify connections among coordinator, runtime, adapters, calendar, routing and other components | Test modules exist; a complete current run has **not** been verified. |
| End-to-end user acceptance | Verify browser actions, consent, approval/cancellation and user-facing workflows on macOS | Seven v2.15 targeted acceptance scenarios are recorded as PASS within their stated scope in the consolidated private Evidence Log; they are **not** seven independent backend tests rerun on v2.15.4. |
| Clean-install / repository verification | Verify the public GitHub checkout on a new virtual environment | **PENDING**. The audit ZIP omits runtime data/examples and some local configuration. |

## 2. Verified execution in this documentation pass

The following commands were run against a temporary extraction of the uploaded `MINA_CODE_AUDIT.zip` without changing the user's Mac project:

```bash
python -m unittest -q \
  test_mina_welcome_tagline_v2154 \
  test_mina_welcome_teal_v2153 \
  test_mina_geocoding_consent_v2142 \
  test_mina_cancel_lifecycle_v2141
```

**Observed output:** `Ran 23 tests in 0.016s` followed by `OK` (23 passed, 0 failures/errors in this particular run). The runtime and environment for this result are the audit environment, **not** the user's Mac/browser. This is a narrow offline regression result, not a full-system validation.

In addition, `test_mina_welcome_tagline_v2154.py` confirms the exact final Welcome tagline and selected brand/navigation markup. The version-specific README describes v2.15.4 as a **UI-only patch applied over v2.15.3**, not a standalone ZIP release.

## 3. Test inventory (selected groups)

The archive includes many `test_*.py` files, including tests for:

| Area | Examples found in supplied code archive |
| --- | --- |
| UI / branding | `test_mina_welcome_tagline_v2154.py`, `test_mina_welcome_teal_v2153.py`, `test_mina_welcome_color_v2152.py`, `test_mina_welcome_polish_v2151.py`, `test_mina_theme_v2_1.py` |
| Calendar / voice | `test_mina_calendar_v27.py`, `test_mina_voice_calendar_v29.py`, `test_mina_voice_calendar_v291.py`, `test_mina_audio.py` |
| Family and shopping | `test_mina_family_hub_v2_4.py`, `test_mina_multi_store_v210.py`, `test_mina_list_removal_v211.py` |
| Routing / saved places | `test_mina_route_tools.py`, `test_mina_route_schedule_v2125.py`, `test_mina_route_geocode_v2123.py`, `test_mina_saved_places_pair_v2122.py` |
| Safety / conversation | `test_mina_write_guard.py`, `test_mina_conversation_state_v214.py`, `test_mina_cancel_lifecycle_v2141.py`, `test_mina_geocoding_consent_v2142.py` |
| Memory / reminders / multi-turn | `test_mina_v215.py` |
| Orchestration / reasoning | `test_mina_coordinator.py`, `test_mina_runtime.py`, `test_mina_tot_integrated.py`, `test_tot_critic.py`, `test_tot_llm_generator.py` |

This is an **inventory**, not a complete test pass report.

## 4. How to run tests locally

From the repository root (where `streamlit_app.py` and the `test_*.py` files currently live):

```bash
cd /path/to/MINA_GitHub
source .venv/bin/activate             # after creating and installing the environment
python -m unittest -q test_mina_welcome_tagline_v2154
```

For the verified offline subset:

```bash
python -m unittest -q \
  test_mina_welcome_tagline_v2154 \
  test_mina_welcome_teal_v2153 \
  test_mina_geocoding_consent_v2142 \
  test_mina_cancel_lifecycle_v2141
```

For the legacy offline baseline suite:

```bash
python run_offline_checks.py
```

**Caution:** `run_offline_checks.py` invokes a specific historical suite (`complexity_router.py`, `test_tot_critic.py`, `test_tot_llm_generator.py`, `test_tot_constraints_experiment9.py`, and `test_mina_tot_integrated.py`). It does **not** run every `test_*.py` file. The complete suite may need installed dependencies, additional fixtures, environment variables or excluded local data.

Do **not** assume that the following command is safe or self-contained until missing data fixtures and external service behavior are reviewed:

```bash
# Informational only; NOT yet approved as the release validation command:
# python -m unittest discover -p 'test_*.py'
```

Some tests reference `evaluation/scenarios.json`, which was **not** included in the lightweight audit ZIP. Consult the original project copy for a sanitized, publishable fixture before running or publishing those tests.

## 5. Targeted user acceptance testing (TEST-01–TEST-07)

**Source of truth:** private `MINA_Capstone_Evidence_Log_CONSOLIDATED_to_v2_15_4_2026-11-22.md`, addendum §§53–61, especially §§55–56; and `evidence/test_matrix_v2_14_2_to_v2_15_4.csv`. These were user-observed local Streamlit workflows on Mac, not a statistically representative benchmark. Statuses below are limited to each test's recorded acceptance criterion.

| ID | Version / workflow | Recorded outcome | Evidence | Boundary |
| --- | --- | --- | --- | --- |
| TEST-01 | v2.15 — standalone local reminder creation | **PASS (create only)** | User confirmation + patch documentation | No independently established list/done/delete lifecycle or background notifications; no selected S60–S66 screenshot |
| TEST-02 | v2.15 — opted-in pinned fact retrieved after restart | **PASS (specific fact)** | Private S64 / public Figure A5 | Literal match demonstrated; repeated chat snippets; no semantic-memory or encryption claim |
| TEST-03 | v2.15 — multi-turn shopping store clarification and Target proposal | **PASS (preview)** | Private S62 / public Figure A3 | Proposal with Confirm/Cancel, **not** a committed write |
| TEST-04 | v2.15 — dentist appointment date/time clarification and calendar proposal | **PASS (preview)** | Private S63 / public Figure A4 | Assumed 60-minute duration; no independently verified Google Calendar write |
| TEST-05 / REG-05 | v2.15 — saved pickup recovered after fresh Streamlit restart without re-saving Family Hub | **PASS (targeted)** | Private S65 / public Figure A6 | Earlier intermittent saved-state failure not root-caused; not all restarts guaranteed |
| TEST-06 | v2.15 — canceled shopping item absent from Target list | **PASS (app readback)** | Private S66 (upper) / public Figure A7 | Limited to the displayed Target list and this cancellation path |
| TEST-07 | v2.15 — canceled dentist event absent from calendar response | **PASS (app readback)** | Private S66 (lower) / public Figure A7 | Unrelated 4:00 PM local QA item remained; no independent Google Calendar UI audit |

**Acceptance summary:** 7 of 7 **selected scenarios** met their **specific** recorded criteria. This must not be interpreted as overall 100% system reliability, seven independently sampled tasks, complete write-side-effect verification, or full E2E coverage of all external services. TEST-06 and TEST-07 are follow-up readbacks of proposed/canceled actions.

### Historical route and consent evidence (not new v2.15.4 runs)

| Case | Historical version | Recorded result | Public figure | Limitation |
| --- | --- | --- | --- | --- |
| Route continuation with separate 12:30 PM response | v2.14 / v2.14.1 | PASS for modeled itinerary | A1 (private S60) | Travel, buffers, and slack are model estimates, not verified live traffic |
| Infeasible route refusal (`no_feasible_plan`) | Earlier route evaluation | PASS for modeled refusal | A2 (private S61, reused S44) | Reused historical evidence, not an independent new run |
| Public-geocoding consent survives restart (ON) | v2.14.2 | PASS for ON persistence | Private user report | OFF persistence and startup network silence not confirmed |

### Final interface freeze

v2.15.1–v2.15.4 were UI-only changes. The final v2.15.4 Welcome tagline is **“Plan your day, capture tasks, and make room for what truly matters.”** The user accepted the final UI. This is not an independent re-execution of all seven feature acceptance scenarios on v2.15.4.

### Public figure mapping

The **seven Appendix illustrations A1–A7 are seven selected screenshots, not TEST-01–TEST-07 one-to-one**. A1/A2 represent historical routing; A3→TEST-03, A4→TEST-04, A5→TEST-02, A6→TEST-05, A7→TEST-06/07. TEST-01 has no separate selected Appendix screenshot. See `docs/evaluation/MINA_Evaluation_Appendix_v2_15_4.md` after its privacy review and publication.

## 6. Release acceptance checklist

- [x] Identify final v2.15.4 entry point and version-specific tagline test.
- [x] Run and record the selected 23-test offline regression subset in an isolated audit environment.
- [ ] Inspect the complete dependency installation from a clean virtual environment.
- [ ] Restore only anonymized example fixtures required by tests; never publish tokens or private `local_data`.
- [ ] Run the agreed release regression suite from the GitHub-ready checkout and preserve actual output.
- [ ] Launch Streamlit from the GitHub-ready checkout and verify UI/required optional integrations.
- [x] Reconcile the seven user acceptance cases with the final private Evidence Log and curated Appendix (scope-qualified; publication of imagery remains subject to privacy review).
- [ ] Review every Git-tracked file for secrets and personal information before publishing.

## 7. Known limitations of the evidence

- Passing unit tests does not prove that remote routing, weather, Google Calendar or OpenAI services are reachable or configured.
- The lightweight audit archive is not by itself a complete runtime installation; it omits application-local files, evaluation fixtures and examples.
- No live browser session was executed as part of this document-generation pass.
- No complete `unittest`/`pytest` discovery pass is claimed here.

## 8. Evidence record format

For each meaningful release test, record:

```text
Test ID:
Feature / user scenario:
Version and code snapshot:
Environment (macOS/browser/Python):
Preconditions / sanitized test data:
Steps performed:
Expected result:
Actual result:
Status: PASS / FAIL / BLOCKED / NOT RUN
Evidence reference (sanitized screenshot, log, timestamp):
Issue / fix / retest link (if applicable):
```

**Related documents:** `RESULTS.md`, `DEVELOPMENT_HISTORY.md`, and the **private** consolidated Evidence Log (do not upload private log or 66-image archive to a public repository).
