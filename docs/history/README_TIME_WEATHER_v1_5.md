# MINA v1.5 — opt-in Time + Open-Meteo Weather (read-only)

**Status:** patch prepared and checked offline; **real weather API connectivity on the user's Mac is not yet confirmed**.

**Baseline:** MINA v1.4, dataset v1.1 (20 existing synthetic scenarios). This patch adds real tools but deliberately does not change Coordinator, Critic, Controller, synthetic fixtures or existing evaluation data.

## Installation on Mac

The ZIP contains only the new/changed Python modules and this README. It does **not** include `.env`, API credentials, private logs or evaluation data.

```bash
cd ~/Documents/MINA_Day1_baseline
source .venv/bin/activate
cp mina_runtime.py mina_runtime_v1_4_backup.py
cp run_mina_v1.py run_mina_v1_v1_4_backup.py
unzip -o ~/Downloads/MINA_v1_5_Time_Weather_patch.zip -d .
```

## Offline tests (no network / OpenAI charges)

```bash
python -m unittest discover -p 'test_*.py'
python eval_mina.py --mode offline --output-prefix evaluation/results/offline_v1_5
```

In the assistant's reconstructed v1.4 environment: **70/70 unit tests PASS**, and **20/20 offline structural cases PASS**. The original 20-case dataset and default workflow are unchanged. These checks do **not** prove successful public-weather connectivity on macOS.

## Live read-only smoke tests (no OpenAI key required)

Time, with explicit timezone:

```bash
python run_mina_v1.py --live-tools --no-rag --timezone America/New_York "What time and date is it right now?"
```

Weather (the exact city is required; no automatic location inference):

```bash
python run_mina_v1.py --live-tools --no-rag --city "Apex, NC" "What's the weather forecast tomorrow, and what should the kids wear?"
```

Alternative:

```bash
python run_mina_v1.py --live-tools --no-rag --city "Apex, NC" "What's the weather today?"
```

Expected successful weather output has `STATUS: simple_response`, current local forecast date, temperature range in °F, precipitation probability, a clothing suggestion, explicit provider attribution and check timestamp. It must NOT say it has Google Maps/calendar or real-time traffic access.

When no city is supplied, `needs_clarification` is expected. If the API is unavailable, `tool_unavailable` is expected, with no made-up forecast. A city with several geographic matches also requires clarification. Some free Open-Meteo geocoding cities may have aliases that require a different city name; this is an experimental feature.

**Important:** The Open-Meteo public free endpoint is for non-commercial use and subject to rate limits/terms. No API key is required for this educational demo. Documentation: https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/geocoding-api.

## Architecture and boundaries

- `--live-tools` is an explicit opt-in switch. **Without it**, the original v1.4 runtime path is unchanged; the benchmark runner does not pass this switch.
- For unambiguous, **simple read-only** time and weather questions, a conservative deterministic fast path avoids LLM dependency. The existing independent write gate remains in place before any weather/tool access.
- All complex scheduling requests still use existing **SYNTHETIC** planning context. Real travel times/maps are **not** connected. A complex question mentioning the weather does not yet put live weather into the Planner/Critic.
- If a message includes explicit planning/action terms, the fast path defers to the existing Coordinator; it does not silently discard requested tasks.
- Weather uses two HTTPS GETs to Open-Meteo (geocoding and daily forecast), standard-library `urllib`, 6-second timeout for each request, explicit city, IANA provider timezone, date-key matching, bounded numeric validation and safe failure on missing data. No API key or secrets.
- Time uses `datetime` and `zoneinfo` based on the **machine's local clock** (not an independent authoritative network-time source). Supply `--timezone America/New_York` when timezone matters.
- Does **not** implement OpenAI function calling, multi-step ReAct, writable tools, voice, Google Calendar or routes. Live tool choice is deterministic in this patch; don't claim otherwise in the report.

## Evaluate separately

The existing 20 synthetic scenarios evaluate the **unchanged core baseline**. The new `test_mina_live_tools.py` unit suite uses mocked HTTP and deterministic clocks; it tests API failures, ambiguity, safety precedence, time zone correctness and live-tool isolation. A real weather connectivity test on the Mac is still required.

## Revert

```bash
cd ~/Documents/MINA_Day1_baseline
cp mina_runtime_v1_4_backup.py mina_runtime.py
cp run_mina_v1_v1_4_backup.py run_mina_v1.py
```

New `mina_live_tools.py`, `mina_live_routing.py`, and their tests can remain on disk; they are not imported by the reverted v1.4 runtime. Preserve all historical `evaluation/results` and `.env` files.
