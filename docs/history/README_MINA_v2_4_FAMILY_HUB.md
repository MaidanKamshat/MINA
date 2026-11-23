# MINA v2.4 — Local Family Hub + Map-in-Chat Routing Guard

**Scope:** Add local shopping lists, saved places, visit/appointment notes and read-only route-based store pairing suggestions to the existing MINA v2.2 landing UI / v2.3 backend. The core planning algorithm, OpenAI Coordinator, legacy 20-scenario dataset, and external write safety guard remain unchanged. **Not** a Google Calendar integration, external shopping-list integration or automatic appointment booking system.

## Why did the user get a synthetic plan without a map?

In the current Streamlit app, `Mode = Assistant` passes `live_tools=True` for weather/time, but does **not** pass a `live_plan` structure containing origin, exact task locations, durations, date and pickup/opening-hour assumptions. Thus the regular complex backend can legitimately return `synthetic_plan` using synthetic fixture travel times, and has no `map_report` to embed. A real-route plan (`provisional_live_route_plan`) is generated only in **Settings → Mode → Family planner**, when user reviews/confirm locations and time windows. In v2.4, a plain Assistant-mode request that clearly asks for a multi-errand route is intercepted with `needs_clarification` and an instruction to switch modes; **no synthetic schedule is disguised as a real itinerary**.

Route preview embeds the existing Leaflet/OSM HTML as an iframe **inside the MINA response in chat** for validated route reports, using Streamlit's HTML component. No image-generation API involved.

## New local Family Hub

In the sidebar open **Family Hub · Lists, places and visits**. It starts empty, without guessed locations or private data. User-entered information lives in `local_data/mina_family_hub.json`, created on first save and ignored by Git. Three independent lists:

- **Costco** — Costco shopping list
- **Target** — Target shopping list
- **Trader Joe's** — Trader Joe's shopping list

Use the sidebar form to add items, and checkboxes to mark purchased items. These are real local writes made by explicit user actions, **not external list/calendar writes**. A chat message such as **“Add milk to my Target shopping list”** creates a **pending local write** and displays **Confirm local list update / Cancel change**. It is not stored until the user confirms. Other writing commands are still processed by the existing safety guard and external writes remain unavailable.

User-facing times are **12-hour AM/PM** (e.g. `3:15 PM`). User can save the address and notes of each place in the sidebar (Costco, Target, Trader Joe's, Library, Dentist, Pediatrician). The JSON file and chat map previews are gitignored. **Do not paste medical/patient information into a public GitHub repository, screenshots, or demo logs.**

Save a **scheduled visit** for Library, Dentist or Pediatrician, with date, time, and a general label. This does not create a calendar event. The preconfigured preference pairs are:

- Library + Costco
- Dentist + Target
- Pediatrician + Trader Joe's

When a relevant saved visit is within the next 7 days and there are pending items for its paired store, the landing dashboard offers a **possible errand pairing** reminder, explicitly **not route-checked**. It is not a guaranteed nearby place.

### Real route-based suggestion

To get a real proximity check, add both saved addresses and schedule a visit, then check **“Allow HeiGIT to geocode saved addresses when I ask for nearby errands.”** Ask:

> What shopping can I combine with my dentist appointment?

The local Family Hub checks visits in the next 30 days and the store list. If the address is set and the user consented, it calls the existing **read-only HeiGIT** driving route tool. A recommendation appears **only if the retrieved driving estimate is at most 15 minutes** between the visit and store, and returns the pending store shopping items. The resulting Leaflet map is embedded in the response. If both addresses are missing, consent is absent, HeiGIT fails, or the trip exceeds 15 min, MINA says so rather than pretending proximity was checked. Distances are estimated without live traffic; store opening hours, appointment duration, parking and actual schedule feasibility are not verified.

If you want to see items without sharing saved addresses, ask:

> What's on my Target shopping list?

The answer is retrieved from the local file, not a cloud list service.

## Installation on Mac

Stop Streamlit with **Control+C** in the Terminal where it is running. Download the archive, then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_before_v2_4.py
unzip -o ~/Downloads/MINA_v2_4_Family_Hub_Pairings_patch.zip -d .
cat >> .gitignore <<'EOF'
local_data/
evaluation/maps/
.streamlit/secrets.toml
EOF
python -m unittest -v test_mina_family_hub_v2_4.py
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v2_4_family_hub
python -m streamlit run streamlit_app.py
```

**Note:** The ZIP intentionally does not overwrite your `.gitignore`, `.env`, original Saved Places or evaluation results. The `local_data/` folder is only created after saving private data. `.env` is already ignored in the baseline.

## Suggested smoke-test script

1. Open sidebar Family Hub → choose **Target** → add **Milk**. The pending item appears in Target only.
2. Voice/type **“What's on my Target shopping list?”**. See Milk from the local list.
3. Voice/type **“Add bread to my Target shopping list.”**. Confirm with the in-chat button; ensure item appears only after approval.
4. Save a **Dentist** location and **Target** store location with their exact PUBLIC-business addresses (do not include patient details). Save a **Dentist** visit for a date in the next 30 days, e.g. demo date Monday 2026-11-23 and time `3:15 PM`. Only enter actual addresses that you have checked, or your own public demo addresses.
5. Enable optional HeiGIT address lookup and ask **“What shopping can I combine with my dentist appointment?”**. If the real road time is at most 15 minutes, expect a local shopping-list suggestion and an embedded map. Otherwise a truthful refusal/explanation is correct.
6. In default **Assistant** mode, ask a clear three-errand planning prompt: MINA should respond with `needs_clarification` explaining how to turn on Family planner, **not synthetic times**.
7. Switch to **Family planner** with 3 demo tasks, demo Saved Places, weekday, and confirmed assumptions; re-run the old 3-errand request. When route data succeeds, expect `provisional_live_route_plan` and a map inline. Keep in mind that the three-task planning mode still takes explicit task location parameters; the Family Hub dentist/store pair suggestions are a separate read-only workflow in this MVP.
8. Confirm `Add a school event to my calendar` remains **blocked**. No external write action should occur.

## Offline evidence and limitations

- 208 Python unit tests passed on a reconstructed v2.3 project with the new files (18 new cases added in v2.4) — **not** a live browser or API test.
- Unchanged 20-case offline structural evaluation: **20/20 PASS**; synthetic fixtures with pre-labelled task extraction.
- The three new store lists are persistent **local JSON**, not connected to external shopping accounts.
- Real addresses are not provided in the repository and are not automatically validated as the correct business. User must choose and confirm them.
- Pairings are **suggestions only**, require an explicit saved visit and a nonempty list, and do not check whether the store is open or whether travel fits the appointment/pickup window. This is different from the existing strict three-task Planning Critic.
- The Streamlit browser and real HeiGIT/geocoding flow **must still be verified on the user's Mac**.
