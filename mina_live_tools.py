"""Opt-in, read-only Time and Open-Meteo weather tools for MINA.

No external writes, no private location inference, and no silent synthetic data fallback.
Uses Python's standard library only; all network reads have a bounded timeout.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_URL = "https://open-meteo.com/en/docs"
TIMEOUT_SECONDS = 6


class ToolUnavailable(Exception):
    """The tool cannot provide verified information; do not invent a result."""


class LocationRequired(Exception):
    """A location or time zone must be supplied explicitly."""


@dataclass(frozen=True)
class WeatherReport:
    city: str
    day: str
    date: str
    timezone: str
    low_f: float
    high_f: float
    rain_probability_pct: int
    condition: str
    retrieved_at: str
    source: str = SOURCE_URL


STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    56: "freezing drizzle", 57: "dense freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light rain showers",
    81: "rain showers", 82: "violent rain showers", 85: "light snow showers",
    86: "heavy snow showers", 95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


def _fetch_json(endpoint: str, params: dict, *, opener=None, timeout: float = TIMEOUT_SECONDS) -> dict:
    """GET JSON from a hardcoded HTTPS endpoint. Opener injection is for offline tests."""
    if endpoint not in (GEOCODING_URL, FORECAST_URL):
        raise ValueError("Unexpected endpoint")
    url = endpoint + "?" + urlencode(params)
    opener = opener or urlopen
    try:
        with opener(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, UnicodeError, ValueError) as exc:
        raise ToolUnavailable("Weather provider is currently unreachable or returned invalid data.") from exc
    if not isinstance(data, dict) or data.get("error"):
        raise ToolUnavailable("Weather provider returned an error or incomplete response.")
    return data


def _place_hint(place: str) -> tuple[str, str | None]:
    if not place or len(place) > 120 or any(c in place for c in "\n\r<>/\\"):
        raise LocationRequired("Please provide a city, e.g. 'Apex, NC'.")
    chunks = [x.strip() for x in place.split(",") if x.strip()]
    if not chunks or len(chunks) > 3:
        raise LocationRequired("Please provide a city and optionally a state/country.")
    city = chunks[0]
    if len(city) < 2:
        raise LocationRequired("Please provide the full city name.")
    region = chunks[1] if len(chunks) > 1 else None
    return city, STATES.get(region.upper(), region) if region else None


def resolve_city(place: str, *, opener=None) -> dict:
    """Geocode an explicitly supplied city; refuse ambiguous or mismatched results."""
    city, region = _place_hint(place)
    data = _fetch_json(GEOCODING_URL, {"name": city, "count": 10, "language": "en", "format": "json"}, opener=opener)
    candidates = data.get("results") or []
    if not isinstance(candidates, list):
        raise ToolUnavailable("Location lookup returned invalid results.")
    matching = [c for c in candidates if isinstance(c, dict) and str(c.get("name", "")).casefold() == city.casefold()]
    if region:
        matching = [c for c in matching if region.casefold() in {
            str(c.get("admin1", "")).casefold(), str(c.get("country", "")).casefold(),
            str(c.get("country_code", "")).casefold(),
        }]
    # Never select the first result if there may be multiple geographic matches.
    if len(matching) != 1:
        raise LocationRequired("Location could not be identified unambiguously. Specify 'City, State' or 'City, Country'.")
    result = matching[0]
    try:
        lat = float(result["latitude"])
        lon = float(result["longitude"])
        tz = str(result["timezone"])
        ZoneInfo(tz)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid coordinates")
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError) as exc:
        raise ToolUnavailable("Location provider returned invalid coordinates/timezone.") from exc
    return {"latitude": lat, "longitude": lon, "timezone": tz,
            "label": f"{result['name']}, {result.get('admin1') or result.get('country') or ''}".rstrip(", ")}


def get_weather_report(place: str, *, day: str = "today", opener=None, now: datetime | None = None) -> WeatherReport:
    if day not in {"today", "tomorrow"}:
        raise LocationRequired("Only today's and tomorrow's forecasts are supported in this MVP.")
    coords = resolve_city(place, opener=opener)
    data = _fetch_json(FORECAST_URL, {
        "latitude": coords["latitude"], "longitude": coords["longitude"],
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "temperature_unit": "fahrenheit", "timezone": coords["timezone"], "forecast_days": 3,
    }, opener=opener)
    try:
        current = now.astimezone(ZoneInfo(coords["timezone"])) if now else datetime.now(ZoneInfo(coords["timezone"]))
        wanted_date = (current.date() + timedelta(days=int(day == "tomorrow"))).isoformat()
        daily = data["daily"]
        idx = daily["time"].index(wanted_date)
        high = float(daily["temperature_2m_max"][idx])
        low = float(daily["temperature_2m_min"][idx])
        rain = float(daily["precipitation_probability_max"][idx])
        code = int(daily["weather_code"][idx])
        if not (math.isfinite(high) and math.isfinite(low) and math.isfinite(rain)):
            raise ValueError("Non-finite weather value")
        if not -150 <= low <= high <= 150 or not 0 <= rain <= 100 or code not in WEATHER_CODES:
            raise ValueError("Out-of-range weather")
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ToolUnavailable("A verified forecast for the requested day was not available.") from exc
    return WeatherReport(coords["label"], day, wanted_date, coords["timezone"], low, high,
                         round(rain), WEATHER_CODES[code], current.isoformat(timespec="seconds"))


def describe_weather(report: WeatherReport, *, clothing: bool = True) -> str:
    result = (f"Open-Meteo forecast for {report.city} on {report.date} ({report.day}, "
              f"{report.timezone}): {report.condition}; low {report.low_f:g}°F, "
              f"high {report.high_f:g}°F; maximum daily precipitation probability "
              f"{report.rain_probability_pct}%. ")
    if clothing:
        if report.high_f < 40:
            clothes = "For the children: warm coats, layers, and hats/gloves."
        elif report.high_f < 60:
            clothes = "For the children: layers and a jacket."
        elif report.high_f < 75:
            clothes = "For the children: light layers; consider a light jacket for the morning."
        else:
            clothes = "For the children: breathable clothes and comfortable shoes."
        if report.rain_probability_pct >= 50:
            clothes += " Pack a rain jacket or umbrella."
        result += clothes + " "
    return result + (f"Source: {report.source}. Checked: {report.retrieved_at}. "
                     "This is a forecast, not a guarantee or a severe-weather alert.")


def current_local_time(timezone_name: str | None = None, *, now: datetime | None = None) -> str:
    try:
        if timezone_name:
            zone = ZoneInfo(timezone_name)
            clock = now.astimezone(zone) if now else datetime.now(zone)
        else:
            clock = now.astimezone() if now else datetime.now().astimezone()
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise LocationRequired("Unknown time zone. Use an IANA name such as America/New_York.") from exc
    return (f"Current date and time: {clock.strftime('%A, %B %d, %Y, %I:%M %p')} "
            f"({timezone_name or clock.tzname()}; source: local system clock).")
