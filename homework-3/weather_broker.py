"""
Open-Meteo adapter for the weather MCP server.

All HTTP calls and response parsing live here (mirrors alpaca_broker.py's
role). The MCP tool functions in weather_mcp_server.py stay thin and just
call these functions. Open-Meteo is free and needs no API key, so there is
no secret-management code here — unlike alpaca_broker.py's _secret() pattern.

APIs used (both keyless):
  - Geocoding: https://geocoding-api.open-meteo.com/v1/search  (city -> lat/lon)
  - Forecast:  https://api.open-meteo.com/v1/forecast          (current + daily)
"""

import requests

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 20

# Open-Meteo weather_code -> human-readable condition (WMO codes).
_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers", 85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _describe(code):
    """Map a WMO weather code to text; unknown codes fall back gracefully."""
    try:
        return _WEATHER_CODES.get(int(code), f"Unknown (code {code})")
    except (TypeError, ValueError):
        return "Unknown"


class LocationNotFound(Exception):
    """Raised when a city name can't be resolved to coordinates."""


def geocode(location: str) -> dict:
    """
    Resolve a city/place name to coordinates via Open-Meteo geocoding.
    Returns {name, latitude, longitude, country, timezone}.
    Raises LocationNotFound if there is no match.
    """
    location = (location or "").strip()
    if not location:
        raise LocationNotFound("Empty location")
    resp = requests.get(
        _GEOCODE_URL,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise LocationNotFound(f"Could not find a location named {location!r}")
    r = results[0]
    return {
        "name": r.get("name"),
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "country": r.get("country"),
        "timezone": r.get("timezone", "auto"),
    }


def get_current(location: str) -> dict:
    """
    Current conditions for a place name: temperature, humidity, wind, and a
    text condition. Geocodes first, then hits the forecast API's `current`.
    """
    loc = geocode(location)
    resp = requests.get(
        _FORECAST_URL,
        params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "current": "temperature_2m,relative_humidity_2m,"
                       "wind_speed_10m,weather_code,precipitation",
            "timezone": "auto",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    cur = resp.json().get("current", {}) or {}
    return {
        "location": loc["name"],
        "country": loc["country"],
        "temperature_c": cur.get("temperature_2m"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "wind_speed_kmh": cur.get("wind_speed_10m"),
        "precipitation_mm": cur.get("precipitation"),
        "conditions": _describe(cur.get("weather_code")),
        "observed_at": cur.get("time"),
    }


def get_daily_forecast(location: str, days: int = 3) -> dict:
    """
    Multi-day forecast for a place name. Returns a dict with the resolved
    location and a list of per-day dicts (date, high, low, precip chance,
    conditions). `days` is clamped to Open-Meteo's 1..16 range.
    """
    days = max(1, min(int(days), 16))
    loc = geocode(location)
    resp = requests.get(
        _FORECAST_URL,
        params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "daily": "temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max,weather_code",
            "forecast_days": days,
            "timezone": "auto",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {}) or {}

    # Open-Meteo returns parallel arrays; zip them into per-day dicts.
    dates = daily.get("time", []) or []
    highs = daily.get("temperature_2m_max", []) or []
    lows = daily.get("temperature_2m_min", []) or []
    precip = daily.get("precipitation_probability_max", []) or []
    codes = daily.get("weather_code", []) or []

    forecast = []
    for i in range(len(dates)):
        forecast.append({
            "date": dates[i],
            "high_c": highs[i] if i < len(highs) else None,
            "low_c": lows[i] if i < len(lows) else None,
            "precip_chance_pct": precip[i] if i < len(precip) else None,
            "conditions": _describe(codes[i]) if i < len(codes) else "Unknown",
        })
    return {"location": loc["name"], "country": loc["country"], "days": forecast}