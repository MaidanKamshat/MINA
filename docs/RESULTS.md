# MINA v2.15.4 — Evaluation Results and Limitations

**Project:** MINA — My Intelligent Navigation Assistant
**Status:** Final Integrated and Validated **Local Prototype** (not a production release)
**Evidence cutoff:** November 22, 2026
**Evidence discipline:** This is a sanitized, scope-qualified summary of user-reported Mac/browser tests and selected offline test execution. The private consolidated Evidence Log remains the detailed audit record and must not be published as-is.

## 1. Executive results

| Evidence stream | Observed outcome | Interpretation |
| --- | --- | --- |
| Seven targeted user acceptance scenarios (TEST-01–TEST-07) | **7/7 met their recorded criteria** on v2.15 | Selected workflows only; not statistical or comprehensive reliability |
| Selected offline regression tests | **23/23 passed** in the isolated code-audit environment, per recorded run in `TESTS.md` | Four test modules; not the full repository suite or user Mac |
| Route continuation and infeasibility handling | **PASS, historical evidence** from v2.14/v2.14.1 | Modeled schedule and refusal, not live-traffic verification |
| Persistent geocoding consent | **PASS for ON across restart**, v2.14.2 | OFF/restart and startup network traffic not checked |
| Final Welcome UI / tagline | **User accepted**, v2.15.4 | UI-only refinement, not backend validation |
| Clean installation from public repository | **PENDING** | No complete reproducibility claim until verified |

The **7/7** describes a selected acceptance set, **not** 100% accuracy, general agent reliability, or representative benchmark performance.

## 2. Targeted user acceptance cases

| ID | Target behavior | Result | Evidence and limitation |
| --- | --- | --- | --- |
| TEST-01 | Create a standalone local reminder | **PASS — creation only** | User confirmation and patch documentation; no selected screenshot for this case; listing, completion, deletion and background push not established |
| TEST-02 | Retrieve explicitly pinned synthetic fact after restart | **PASS — specific fact** | S64 / A5; literal retrieval with duplicate snippet noise; no universal semantic memory claim |
| TEST-03 | Ask for missing store and propose Target shopping item | **PASS — preview** | S62 / A3; approval gate shown, item not silently added |
| TEST-04 | Collect date/time and preview dentist appointment | **PASS — preview** | S63 / A4; assumed 60-minute duration; no independently verified Google write |
| TEST-05 / REG-05 | Recover saved pickup target after fresh restart | **PASS — targeted recovery** | S65 / A6; 3:15 PM recovered; prior intermittent failure root cause unresolved |
| TEST-06 | Read Target list after cancel | **PASS — app readback** | S66 / A7; proposed synthetic oatmeal absent; other stores and cancellation paths not audited |
| TEST-07 | Read calendar after cancel | **PASS — app readback** | S66 / A7; proposed 10 AM dentist event absent; unrelated 4 PM local QA item remained; Google UI not inspected |

**Test sequence:** v2.15 acceptance evidence is carried forward into the v2.15.4 final evaluation record, while v2.15.1–v2.15.4 contained UI-focused patches. Do not describe the seven backend scenarios as freshly executed on v2.15.4.

## 3. Historical routing observations

**Figure A1 (private S60):** A follow-up `12:30 PM` reply resumed route planning, with two candidate orders evaluated and a modeled schedule before a 3:15 PM pickup. Recorded 42-minute modeled slack and 15-minute per-leg buffers are estimates, not guarantees. Historical route evidence from v2.14/v2.14.1.

**Figure A2 (private S61, reused S44):** Infeasible 3:00 PM departure with 50 minutes of stops before a 3:15–3:30 PM pickup window was rejected as `no_feasible_plan`, rather than inventing an achievable route. This is a reused historical screenshot, **not** a new independent v2.15.4 test.

## 4. Evidence inventory and provenance

The curated **Appendix A** has seven figures (`A1`–`A7`) showing selected user-observed Streamlit states. They are **not one-to-one** with TEST-01–TEST-07. Figures A3–A7 support selected v2.15 tests; A1 and A2 support older routing cases. Private evidence images S60–S66 correspond to A1–A7 respectively, with A7 showing both cancellation readbacks. `TEST-01` has no selected appendix figure.

Recommended repository reference (publish only after each image is checked for household/school/location data): [`Evaluation Appendix`](evaluation/MINA_Evaluation_Appendix_v2_15_4.md). Original `A*_source.png`, private S01–S66 images, full private Evidence Log, personal maps and saved locations should remain outside the public repository unless explicitly sanitized and approved.

## 5. Known limitations and unresolved checks

| Area | Remaining limitation |
| --- | --- |
| Reminder lifecycle | Creation confirmed; list/done/delete and notifications when Streamlit is closed not verified |
| Local memory | Opt-in literal pinned-fact retrieval shown; duplicated history snippets and unencrypted local storage remain |
| Calendar | Preview and cancel readback demonstrated; no independent third-party UI confirmation of Google writes or deletions |
| Shopping | One Target cancellation readback; no audit across every store or input formulation |
| Family Hub state | Targeted fresh-session recovery passed; earlier intermittent bug cause not conclusively established |
| Routes | No live-traffic prediction, verified opening hours, or quantified real-world arrival reliability |
| Geocoding consent | ON persistence observed; OFF persistence, no startup network request and provider retention not validated |
| Email | Drafting coverage is partial; Gmail send not verified |
| Privacy/security | No full formal audit; credentials and personal local data must never be committed |
| Reproducibility | Clean installation and full release-suite execution still pending on GitHub checkout |

## 6. Metrics: measured vs targets

The project had future evaluation targets for unauthorized actions, modeled feasibility, deadline adherence and approval compliance. **Those targets are not measured aggregate outcomes**. No aggregate escalation precision/recall, representative success rate, uncertainty calibration or third-party side-effect audit was established in this release.

## 7. Final release interpretation

The collected evidence supports freezing **MINA v2.15.4 as a locally evaluated educational MVP** with demonstrated targeted behaviors, approval gates and explicit constraints. It does **not** establish production readiness or independently verified behavior of all external services. For test commands, environment and scope, see [`TESTS.md`](TESTS.md).

**Evidence sources (private, not for public upload):** `MINA_Capstone_Evidence_Log_CONSOLIDATED_to_v2_15_4_2026-11-22.md` and `evidence/test_matrix_v2_14_2_to_v2_15_4.csv`; public candidate: `MINA_Evaluation_Appendix_v2_15_4.md` and curated display figures (subject to image privacy review).
