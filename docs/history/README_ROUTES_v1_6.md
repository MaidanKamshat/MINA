# MINA v1.6 — HeiGIT / openrouteservice driving routes + local map

**Status:** 88/88 offline unit tests and 20/20 unchanged core offline structural cases passed on the assistant-side reconstructed v1.5 code. **Real HeiGIT calls on the user's Mac are not yet tested.**

## Scope

- Extends the opt-in `--live-tools` mode from v1.5; default synthetic benchmark remains unchanged.
- Uses HeiGIT **new** API URLs: `api.heigit.org/pelias/v1/search` and `api.heigit.org/openrouteservice/v2/directions/driving-car/geojson`.
- Gives estimates for **2–5 explicitly supplied stops**, with stop order preserved, per-leg distance/time, and total estimated driving time.
- Can generate a local **Leaflet + OpenStreetMap HTML map** with route geometry. A browser connection is required to load map libraries and tiles. Observe public tile usage limits/attribution.
- Requires a **free Standard HeiGIT key**. Never paste the key into chat or use it directly as a CLI argument.
- Does NOT use real-time traffic, calendar availability, verified hours, parking time, private-location inference, route optimization, or confirmed arrival times.
- Does NOT yet feed live route durations into the complex Planner/Critic/Controller branch. That is a separate, safe next step; **complex planning remains synthetic** even with `--live-tools`.
- Cannot modify calendar, lists or emails. Write guard executes before any route lookup.

## 1. Install safely

Download `MINA_v1_6_Routes_Map_patch.zip` to `~/Downloads`. Open Terminal:

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
cp mina_runtime.py mina_runtime_v1_5_backup.py
cp run_mina_v1.py run_mina_v1_v1_5_backup.py
cp .gitignore .gitignore_before_v1_6
unzip -o ~/Downloads/MINA_v1_6_Routes_Map_patch.zip -d .
grep -qxF "evaluation/maps/" .gitignore || printf "\nevaluation/maps/\n" >> .gitignore
```

`.env`, family notes, `evaluation/results/`, and historical CSV/JSON are unchanged.

## 2. Local tests, no network or API key

```bash
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_6
```

Expected `88 tests ... OK`, `20/20 structural PASS` on the same dataset. The 20-case offline result does not prove routing works in real life.

## 3. Free API key (do not share)

Create a **free Standard key** at https://account.heigit.org/ (linked from https://api.heigit.org/). Open the existing project `.env` in a text editor:

```bash
open -e .env
```

Add a new line, leaving your OpenAI key untouched:

```text
HEIGIT_API_KEY=PASTE_YOUR_OWN_KEY_HERE
```

Save the file. Do not paste this line with a real key into chat, screenshots, a public repository or command history. The existing `.gitignore` excludes `.env`. **No charge is required for the free Standard plan, but usage limits apply.** Check current limits on the HeiGIT account dashboard.

## 4. First real-route smoke test, using approximate public city-center coordinates

This avoids ambiguous geocoding in the very first test. Route coordinates use **longitude,latitude** order. These are approximate demonstration points, not precise street entrances.

```bash
python run_mina_v1.py --live-tools --no-rag \
  --origin=-78.8503,35.7326 \
  --destination=-78.7808,35.7915 \
  "Show driving directions between these two public demo locations."
```

When successful, expect `STATUS: simple_response`, `live_route` in TRACE, route length and time, and a `LOCAL MAP:` path. To open the generated local HTML map:

```bash
open evaluation/maps/latest_route_preview.html
```

The route map should display the path on OpenStreetMap with endpoint markers. The HTML file contains exact coordinates and must stay local (`evaluation/maps/` is added to `.gitignore` during installation).

## 5. Three stops (two legs)

```bash
python run_mina_v1.py --live-tools --no-rag \
  --origin=-78.8503,35.7326 \
  --via=-78.8032,35.7721 \
  --destination=-78.7808,35.7915 \
  "Show driving directions with an intermediate stop."
```

You should see two leg estimates and the total. This **does not optimize the stop order**; route visits points exactly as you passed them.

## 6. Public place names / addresses, after coordinate test

```bash
python run_mina_v1.py --live-tools --no-rag \
  --origin "Apex Town Hall, Apex, NC, USA" \
  --destination "Cary Arts Center, Cary, NC, USA" \
  "Show driving directions between these public places."
```

If Pelias returns multiple plausible matches or low confidence, MINA intentionally returns `needs_clarification`. Verify the route's displayed labels and coordinates. For exact private addresses, avoid sharing results, HTML, or logs with others.

## 7. Failure handling, safe operation

- No `HEIGIT_API_KEY` => `needs_clarification` and no request.
- API outage/timeout/malformed directions => `tool_unavailable` and **no invented travel time**.
- Ambiguous geocoding => `needs_clarification`, not guessed coordinates.
- Missing origin/destination => `needs_clarification`.
- Write command => `approval_required` before any route calls.
- Output includes source and UTC retrieval timestamp, and explicitly disclaims real-time traffic, parking, stops, and arrival guarantees.
- Simple Time & Weather still work; old synthetic evaluation continues unchanged without `--live-tools`.

## Revert safely to v1.5

```bash
cd ~/Documents/MINA_Day1_baseline
cp mina_runtime_v1_5_backup.py mina_runtime.py
cp run_mina_v1_v1_5_backup.py run_mina_v1.py
```

Optional new route modules can remain. Nothing should overwrite prior evaluation result files.

## Evidence policy

Report 88/88 and 20/20 as **assistant-side mocked/offline verification**, not as a successful live HeiGIT API integration. Only mark `Routes live smoke test PASS` after a successful user-run Terminal command. Capture status, number of route legs, the source of time estimates, and whether HTML map opened. Do not include private addresses or keys in submission artifacts.

Official links: https://api.heigit.org/ · https://playground.heigit.org/ · https://www.openstreetmap.org/copyright · https://leafletjs.com/.
