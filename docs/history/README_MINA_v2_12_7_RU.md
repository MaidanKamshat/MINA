# MINA v2.12.7 — Route Map Legend Rendering Fix

Requires the existing working **v2.12.6** installation. This fixes only the stale text **“Public demo locations reconnected”** within the HTML map preview when the route trace confirms user-saved Family Hub points. It does **not** change route geometry, ETA calculations, arrival-window guard, saved places, private home pin, maps APIs, weather, calendar, or lists.

## Why

The previous Python string replacement did not catch legends inserted by the map's JavaScript after initial HTML was rendered. The v2.12.7 helper retains the initial replacement, then also watches **text nodes in the map preview** for the obsolete string and replaces just that text. If the route's provenance has not been confirmed, the renderer does **not** inject this correction.

## Installation (Terminal on Mac)

Stop Streamlit with **Control+C**. Download the ZIP, then:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_Day1_baseline
source .venv/bin/activate
cp streamlit_app.py streamlit_app_backup_v2126.py
cp mina_route_schedule_v2125.py mina_route_schedule_v2125_backup_v2126.py
unzip -o ~/Downloads/MINA_v2_12_7_Map_Legend_Fix.zip -d .
python -m unittest -q test_mina_route_legend_v2127.py test_mina_route_timeline_v2126.py test_mina_route_schedule_v2125.py
python -m streamlit run streamlit_app.py
```

Refresh the browser and submit the same route-planning request again. The saved map header should say **Route locations from Family Hub** rather than **Public demo locations reconnected**.

## Validation

- 19/19 focused local Python tests pass (caption helper, timetable, and schedule guard).
- `py_compile` and JavaScript syntax check pass.
- No real user-device browser/render test was available during development. If the map still shows the old label, capture the map preview HTML under `evaluation/maps/mina_chat_map_*.html` (remove personal addresses/pins before sharing) so that its exact DOM markup can be diagnosed.
- Distances, times, opening hours, and school pickup are **provisional** and not independently verified. This fix does **not** integrate pickup time windows into the underlying Planner/Critic.
