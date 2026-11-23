# MINA — Development History

**Project:** MINA — My Intelligent Navigation Assistant
**Capstone:** Carnegie Mellon University, Agentic AI
**Final local prototype:** v2.15.4 (feature-frozen November 22, 2026)
**Document scope:** An evidence-grounded summary of the incremental development of the local application. This is *not* a reconstruction of Git commits, nor a claim that each patch ZIP was a standalone application.

## 1. Development approach

MINA was built iteratively. New ZIP packages commonly updated a **working Streamlit project in place**. Some archives were partial patches that expected modules, CSS, configuration, and local user data from an earlier installed build. Therefore, v2.15.4 describes the **final integrated local application state**, while the separately distributed `MINA_v2_15_4_Welcome_Tagline_Copy.zip` is a **UI-only incremental patch** over v2.15.3.

Development evidence is maintained separately from the executable code:

- **Version READMEs:** release intent, changes, known defects, installation prerequisites, and sometimes offline checks.
- **Consolidated private Evidence Log:** observed Mac/browser behavior, defects, fixes, selected user acceptance checks, and screenshot references.
- **Evaluation Appendix:** curated, privacy-reviewed figures illustrating selected evaluation scenarios. Appendix figures A1–A7 are **not** one-to-one identifiers for acceptance TEST 1–7.

The original series of ZIP files remains a separate historical archive. Do not replace the final source with all archived implementations merged together.

## 2. Development timeline

| Phase / version | Documented engineering change | Evidence boundary |
|---|---|---|
| **Day 1–2 and Blocks 2–4** | Baseline, structured state and Coordinator, Planner → Critic → Controller, synthetic-case evaluation, optional sanitized audit logging. | Early development and offline/evaluation documentation, not proof of final real-world performance. |
| **v1.3–v1.4** | Bounded Coordinator repair and independent write-action safety guard. | Safety logic added; independent external actions were not thereby proven. |
| **v1.5–v1.8** | Opt-in read-only time/weather, driving-route and map integration, live route planning and constraint scoping, saved places and time-window handling. | Live routes and external information required configuration, provider availability, and grounded inputs. |
| **v1.9–v2.2** | Streamlit voice-first UI; unified chat/voice; theme and landing/dashboard iteration, including weather and today's plan. | UI milestones did not imply autonomous write integrations. |
| **v2.3–v2.4** | Separated read-only errand planning from write-action intent; introduced local Family Hub, shopping lists, saved places, and guarded route-based store pairing. | v2.3 identified an erroneous approval-required response for a read-only plan. v2.4 was not external shopping-list/calendar booking. |
| **v2.5–v2.6** | Auto Mode, voice shopping, local appointment notes and reminders, visible settings, complete list readbacks, family follow-ups. | Reminders at this stage were part of local MVP workflows, not evidence of background push notifications. |
| **v2.7–v2.9.1** | Calendar notes, optional Google Calendar integration, Settings/Welcome UX fixes, voice-to-calendar routing and a duration parsing repair. | v2.9.1 fixed a reproducible parsing/test regression; not every Calendar API action was comprehensively verified. |
| **v2.10–v2.11** | Corrected multi-store voice shopping segmentation; added guarded, preview-before-write, single-item shopping-list removal. | Earlier misrouting and removal failure are documented in version READMEs. No unconfirmed writes should be inferred from screenshots. |
| **v2.12–v2.12.4** | Addressed spoken multi-stop route parsing and dispatch, Saved Places/date compatibility, consent-based geocoding, private location pins. | Several updates were targeted hotfixes over an existing local installation, not standalone ZIPs. |
| **v2.12.5–v2.12.7** | Added pickup-window validation, coherent proposed timelines, and correction of stale map legend text. | No claim of live traffic prediction or a fully dynamic itinerary optimizer. |
| **v2.13–v2.13.1** | Time-window-aware Planner → Critic → Controller; follow-up intent and read-only calendar-routing reliability improvements. | Mac evidence includes feasible and infeasible route cases and controller abstention; **v2.13.2 was not installed**. |
| **v2.14–v2.14.1** | Session-scoped route slot filling, continuation after missing departure time, natural-language cancellation and task-switch lifecycle fixes. | Selected Mac acceptance/regression cases are recorded; not a guarantee across all session reconnections. |
| **v2.14.2** | Persisted explicit public-geocoding permission as a local boolean, initially OFF and revocable. | User confirmed that ON persisted after restart; OFF/restart and proof of no network calls at startup were not established. |
| **v2.15** | Standalone local reminders, opt-in local SQLite text history/pinned facts, selected multi-turn shopping/calendar slot filling. | Seven selected Mac acceptance checks are recorded as PASS within their narrow criteria. See §3. |
| **v2.15.1–v2.15.4** | Final Welcome Page refinements: typography/popovers, restored teal accent, Safari-compatible teal initials, and final tagline. | **UI-only changes**, with no documented new backend capability. Final interface accepted and feature work frozen. |

### Final v2.15.4 wording

> Plan your day, capture tasks, and make room for what truly matters.

The v2.15.4 patch README explicitly instructs installation **on top of v2.15.3** and describes only the copy change. The local working folder — not that final patch ZIP by itself — represents the complete installed prototype.

## 3. Selected final user acceptance evidence

Seven selected workflows were recorded for **v2.15 functionality**, followed by the UI-focused versions through v2.15.4:

| ID | Workflow | Recorded result | Scope of the claim |
|---|---|---|---|
| TEST 1 | Standalone reminder creation | PASS | Creation, not background delivery/list/done/delete lifecycle. |
| TEST 2 | Pinned memory fact retrieval after restart | PASS | Opt-in local literal retrieval, not general semantic or encrypted memory. |
| TEST 3 | Missing-store shopping request → store reply → preview | PASS | Selected slot-filling/preview, not immediate write or arbitrary conversations. |
| TEST 4 | Missing-date Calendar request → date reply → preview | PASS | Preview, **not** proof of a Google Calendar write. |
| TEST 5 | Saved pickup target recovered after fresh Streamlit restart | PASS | Targeted recovery; earlier intermittent root cause remains unresolved. |
| TEST 6 | Canceled shopping proposal absent from list readback | PASS | Visible readback of that cancellation, not universal transaction audit. |
| TEST 7 | Canceled Calendar proposal absent from application readback | PASS | App-returned readback; independent Google Calendar UI was not inspected. |

**Interpretation:** 7/7 selected workflows met their recorded acceptance criteria. This is not a reliability percentage for all possible requests. The Appendix's seven figures show *selected* evaluation evidence across multiple versions and do not map directly onto these seven test IDs.

## 4. Known limitations at feature freeze

- Independent Gmail sending and Calendar deletion were not verified/implemented as general-purpose actions.
- Standalone reminders were not proven to trigger background/push delivery when Streamlit is closed.
- Text memory was opt-in local storage; the evidence does not establish encryption, broad semantic recall, or a comprehensive privacy audit.
- Route planning depended on supplied constraints and public routing/geocoding services; no live traffic or externally verified opening-hours guarantee was established.
- Intermittent saved pickup-profile behavior had a successful targeted restart test, but the original intermittent cause was unresolved.
- A clean install and full E2E rerun of the **GitHub-packaged repository** remain separate release-validation tasks.

## 5. Why development stopped at v2.15.4

The capstone reached a scope-controlled local MVP with selected tested workflows and explicit limitations. The final patches concentrated on presentation rather than adding more features. The decision to freeze v2.15.4 protects the validated functional baseline while enabling documentation, security review, packaging, and reproducibility checks.

**Release label:** *MINA v2.15.4 — Final Integrated and Validated Local Prototype.*
**Not yet claimed:** production-ready release, independent public clean-install verification, comprehensive reliability certification.

## 6. Source traceability

The following **existing project records** underpin this chronology; they are named to make the history auditable without publishing private logs:

- `README_DAY1.md`, `README_DAY2.md`, `README_BLOCK2.md`, `README_BLOCK3.md`, `README_BLOCK4.md`
- `README_WRITE_SAFETY.md`, `README_TIME_WEATHER_v1_5.md`, `README_ROUTES_v1_6.md`, `README_LIVE_PLANNING_v1_7.md`, `README_SAVED_PLACES_v1_8.md`
- Versioned README files from `README_STREAMLIT_VOICE_v1_9.md` through `README_MINA_v2_15_4_RU.md` in the working-code archive
- Private `MINA_Capstone_Evidence_Log_CONSOLIDATED_to_v2_15_4_2026-11-22.md`, especially §§22–30, 47–49 and 53–60
- Public `MINA_Evaluation_Appendix_v2_15_4.md` and its figure manifest (after separate privacy review)

The private Evidence Log contains local scenarios and screenshots and **should not be uploaded wholesale to a public repository**. Historical claims should not be upgraded from *patch description* to *user-verified result* without a matching test record.

## 7. Repository preparation after code freeze

1. Preserve the original installed working folder and the backup.
2. Review the cleaned code package for secrets, personal data, and missing runtime assets.
3. Keep the existing Python import layout intact unless an explicitly tested refactor is required.
4. Add architecture, installation, run, tests, and results documentation.
5. Verify clean installation and selected regression/E2E paths **from the packaged repository**.
6. Publish the reviewed repository and a version tag only after those checks.

This document records **historical development**. For current behavior and the exact validation scope, consult [`TESTS.md`](TESTS.md) and [`RESULTS.md`](RESULTS.md).
