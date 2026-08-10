"""
Weather-forecast MCP server (FastMCP).

Exposes weather tools over MCP so a Databricks Agent Bricks agent can call
them like any other tool:
    - get_current_weather(location)
    - get_forecast(location, days)
    - predict_umbrella_needed(location, date)

Backed by Open-Meteo (see weather_broker.py) — free, no API key. Tool
functions are thin: all HTTP/parsing lives in the broker. Deploy this as
its own Databricks App using the app.yaml + FastMCP entrypoint pattern;
Agent Bricks registers the app's URL as an external MCP server.

Run locally:
    python weather_mcp_server.py
"""

import logging
import os

from fastmcp import FastMCP

import weather_broker
from weather_broker import LocationNotFound

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp-server")

mcp = FastMCP("weather-forecast")


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get current weather conditions for a location.

    Args:
        location: A city or place name, e.g. "Chicago" or "Austin, TX".

    Returns:
        A dict with location, country, temperature_c, humidity_pct,
        wind_speed_kmh, precipitation_mm, conditions (text), and observed_at.
        On an unresolvable location, returns {"error": "..."} instead of
        raising, so the agent can respond gracefully.
    """
    try:
        return weather_broker.get_current(location)
    except LocationNotFound as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("get_current_weather failed")
        return {"error": f"Weather lookup failed: {e}"}


@mcp.tool
def get_forecast(location: str, days: int = 3) -> dict:
    """
    Get a multi-day daily forecast for a location.

    Args:
        location: A city or place name, e.g. "Seattle".
        days: Number of days to forecast (1-16; default 3).

    Returns:
        A dict with location, country, and a "days" list. Each day has
        date, high_c, low_c, precip_chance_pct, and conditions (text).
        On an unresolvable location, returns {"error": "..."}.
    """
    try:
        return weather_broker.get_daily_forecast(location, days)
    except LocationNotFound as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("get_forecast failed")
        return {"error": f"Forecast lookup failed: {e}"}


@mcp.tool
def predict_umbrella_needed(location: str, date: str = None) -> dict:
    """
    Predict whether an umbrella is needed for a location on a given date,
    based on precipitation probability from the forecast.

    Decision logic (applied here, not by the raw API):
        - precip chance >= 60%  -> "yes" (umbrella strongly recommended)
        - precip chance >= 30%  -> "maybe" (carry one just in case)
        - otherwise             -> "no"

    Args:
        location: A city or place name, e.g. "London".
        date: Target date as YYYY-MM-DD. If omitted or not in the forecast
            window, the soonest forecast day is used.

    Returns:
        A dict with location, date, precip_chance_pct, umbrella ("yes" /
        "maybe" / "no"), and a human-readable reason. On an unresolvable
        location, returns {"error": "..."}.
    """
    try:
        # Look ahead far enough to likely include the requested date.
        fc = weather_broker.get_daily_forecast(location, days=16)
    except LocationNotFound as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("predict_umbrella_needed failed")
        return {"error": f"Prediction failed: {e}"}

    days = fc.get("days", [])
    if not days:
        return {"error": "No forecast data available for that location."}

    # Pick the requested date, or default to the first forecast day.
    chosen = None
    if date:
        for d in days:
            if d["date"] == date:
                chosen = d
                break
    if chosen is None:
        chosen = days[0]

    chance = chosen.get("precip_chance_pct")
    chance_val = chance if isinstance(chance, (int, float)) else 0

    if chance_val >= 60:
        umbrella, reason = "yes", (
            f"{chance_val}% chance of precipitation — bring an umbrella."
        )
    elif chance_val >= 30:
        umbrella, reason = "maybe", (
            f"{chance_val}% chance of precipitation — you may want to carry one."
        )
    else:
        umbrella, reason = "no", (
            f"Only {chance_val}% chance of precipitation — an umbrella is "
            "probably unnecessary."
        )

    return {
        "location": fc.get("location"),
        "date": chosen["date"],
        "precip_chance_pct": chance,
        "conditions": chosen.get("conditions"),
        "umbrella": umbrella,
        "reason": reason,
    }


if __name__ == "__main__":
    # Databricks Apps route external HTTP traffic to this port via app.yaml.
    # streamable-http ("http") is the transport Databricks' MCP gateway expects.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)