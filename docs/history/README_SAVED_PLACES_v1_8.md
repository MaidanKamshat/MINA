# MINA v1.8 — Saved Places, 12-hour time windows and optional OSM hours lookup

**Status:** Local implementation and mock-based testing completed. Real HeiGIT + Saved Places and Overpass smoke tests must still be run by the user. This patch does **not** alter the 20 historical synthetic test cases or connect calendar/list/email writes.

## 1. New functionality

- User-controlled JSON `Saved Places` stores **12-hour AM/PM** weekly opening hours and school pickup windows. Internally the Critic converts them to minute offsets; JSON and displayed plans use AM/PM.
- School pickup window, e.g. **3:15 PM–3:30 PM**, is a **constraint**, not just a RAG note. Early arrival waits; pickup **including its duration** must finish by the window end.
- Grocery/library openings and closings similarly bound the whole visit, including waiting if early.
- For school, `school_days` lists applicable weekdays and `date_overrides` can record exceptions. For stores/library, `date_overrides` takes precedence over ordinary weekday hours. Missing or explicitly closed dates fail closed.
- In normal/live planning **without** `--saved-places`, old behavior is unchanged. `--start-time` and `--library-open` can now accept AM/PM; older 24-hour CLI flags continue to work for existing demos.
- `mina_osm_hours.py` performs a **single, user-triggered, exact-name** read-only lookup of an `opening_hours` tag in OpenStreetMap via Overpass. Returned data are marked **unverified** and **never inserted directly into Critic/Saved Places**. This avoids treating community-edited hours or holiday exceptions as confirmed.

## 2. Install on the Mac

**Use the directory where your latest v1.7.1 program actually runs.** Based on your prior `LOCAL MAP` path it is probably `~/Desktop/CMU/labs/capstone/MINA_Day1_baseline`, not `~/Documents/MINA_Day1_baseline`.

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
pwd
cp mina_planning.py mina_planning_before_v1_8.py
cp mina_live_planning.py mina_live_planning_before_v1_8.py
cp run_mina_v1.py run_mina_v1_before_v1_8.py
unzip -o ~/Downloads/MINA_v1_8_Saved_Places_Time_Windows_patch.zip -d .
grep -qxF 'saved_places.json' .gitignore || printf '\nsaved_places.json\n' >> .gitignore
```

No `.env` or existing real API keys are included in this patch. Keep all private locations and actual family routines in `saved_places.json` (Git-ignored), not the public demo file.

## 3. Tests

```bash
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_8
```

Assistant-side results: **134/134 unit tests PASS**, **20/20 offline structural scenarios PASS**. These are mock/local tests, not proof of stable live API performance.

## 4. Live planning demonstration with 3:15–3:30 PM pickup window

The shipped `examples/demo_saved_places_v1_8.json` is **fictional demonstration data**. It intentionally includes only public/placeholder locations; the hours are not real verified venue opening hours.

```bash
python run_mina_v1.py --live-tools --live-plan \
  --mode deterministic --no-rag \
  --origin=-78.85030,35.73260 \
  --task-location library=-78.80320,35.77210 \
  --task-location groceries=-78.78080,35.79150 \
  --task-location school_pickup=-78.83010,35.75220 \
  --start-time '10:00 AM' \
  --saved-places examples/demo_saved_places_v1_8.json \
  --plan-date 2026-11-20 \
  --duration library=15 \
  --duration groceries=60 \
  --duration school_pickup=10 \
  --travel-buffer 10 \
  --map-output evaluation/maps/live_plan_demo_v1_8.html \
  'For the demo, plan returning library books, buying groceries, and picking up a child before 4:30 PM. The library opens at noon, and grocery shopping takes at least 60 minutes.'
```

Expected status if provider routes fit: `STATUS: provisional_live_route_plan | ROUTE: complex`. The pickup service start should not precede **3:15 PM**, and the 10-minute task should finish at or before **3:30 PM**. A `no_feasible_plan` on a truly infeasible set of road estimates/constraints is correct; no guarantees.

Open map after a successful plan:

```bash
open evaluation/maps/live_plan_demo_v1_8.html
```

Repeat with `--mode llm` after deterministic succeeds. **Do not rerun the 20-case live benchmark just to chase 100%; the core v1.4 dataset is unchanged.**

## 5. Customize your *private* Saved Places JSON

To start from the demo schema:

```bash
cp examples/demo_saved_places_v1_8.json saved_places.json
open -e saved_places.json
```

Change fictional labels and times to **user-confirmed** information. Do **not** commit `saved_places.json`, real home/school addresses, or private calendars to GitHub. Source should be `user_provided` when it is not fictional. A different day may have different opening hours, and holidays are **not** automatically verified.

Example of the critical school record:

```json
{
  "source": "user_provided",
  "school_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "time_window": {"start": "3:15 PM", "end": "3:30 PM"},
  "date_overrides": {"2026-11-26": null}
}
```

`null` overrides represent no confirmed service on that date. The file schema currently allows **one continuous opening interval per day**; split shifts and overnight hours are intentionally not supported. Actual school pickup availability and dates must be confirmed independently.

## 6. Optional OpenStreetMap hours discovery — NOT auto-applied

Requires only public, expressly supplied venue name and coordinates. It is **one-off**, not a polling service:

```bash
python mina_osm_hours.py --name 'EXACT OSM VENUE NAME' --longitude -78.80 --latitude 35.77
```

If a single exact-name match has an `opening_hours` tag, MINA shows the **raw OpenStreetMap notation** (typically `Mo-Fr 09:00-18:00`) and a link to the specific OpenStreetMap object. This is **source syntax**, not the format of your personal JSON. Check it against the venue's official schedule, then enter the correct **AM/PM** times in `saved_places.json`. No automatic changes, no background scraping, no hidden fallback if Overpass is unavailable or returns ambiguous/missing data.

The public Overpass service may return 429/504 during load; usage is subject to the public operator's limits and is not suitable for production polling. For production, use a contracted provider or locally held verified schedules.

## 7. Known limitations

- Saved hours are **user-entered assumptions**, not external verification. School pickup may be unavailable even if the saved weekly window allows it (holidays, closures, policy changes).
- HeiGIT travel times exclude live traffic. Parking, queues, delay uncertainty and the value of buffers remain user decisions.
- 12-hour JSON fields are guaranteed for newly added Saved Places. Historical synthetic fixtures and internal Coordinator constraints retain HH:MM values as implementation internals to preserve old tests.
- Overpass is **discovery**, not automatic authoritative opening-hours integration. A fully automated venue hours workflow needs reliable entity matching, schedule parsing, exception handling, caching/rate limits and confirmed provenance.
- Existing CLI still requires explicit public location for each task. This feature stores **schedules**, not private coordinates.

References: https://wiki.openstreetmap.org/wiki/Key:opening_hours and https://wiki.openstreetmap.org/wiki/Overpass_API.
