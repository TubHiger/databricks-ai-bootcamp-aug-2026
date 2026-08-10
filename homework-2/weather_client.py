"""
Client for the National Weather Service API (api.weather.gov).

No API key is required — NWS only asks for a descriptive User-Agent header
identifying the application (their guidelines request contact info). Mirrors
the structure of massive_client.py: a session-based client with one method
per endpoint, returning normalized document dicts ready for Lakebase.
"""

import hashlib
import os
from typing import Any

import requests

_BASE_URL = os.environ.get("NWS_API_BASE_URL", "https://api.weather.gov")
# NWS asks for a User-Agent identifying your app + a contact. Override via env.
_USER_AGENT = os.environ.get(
    "NWS_USER_AGENT", "weather-intelligence-hw (contact: student@example.com)"
)
_DEFAULT_TIMEOUT = 30


class WeatherClient:
    """Thin wrapper around the NWS API. No auth key needed."""

    def __init__(self, base_url: str | None = None, timeout: int = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or _BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "weather-intelligence-hw (ezhunik@gmail.com)", "Accept": "application/geo+json"}
        )

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> Any:
        # Accept both "/alerts/active" paths and absolute URLs (NWS hands back
        # absolute forecast URLs from the /points lookup).
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}{path_or_url}"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---------- Alerts ----------

    def get_active_alerts(self, area: str, limit: int = 50) -> list[dict]:
        """
        Active weather alerts for a US state (2-letter code, e.g. "TX").
        Returns normalized document dicts ready to upsert into weather_documents.
        """
        data = self.get("/alerts/active", params={"area": area})
        features = data.get("features", [])[:limit]
        docs = []
        for feat in features:
            p = feat.get("properties", {}) or {}
            # The free-text body we embed: description + safety instruction.
            narrative = (p.get("description") or "").strip()
            instruction = (p.get("instruction") or "").strip()
            if instruction:
                narrative = f"{narrative}\n\nInstructions: {instruction}".strip()
            if not narrative:
                continue  # skip alerts with no usable text
            docs.append({
                "id": str(p.get("id") or feat.get("id")),
                "location": p.get("areaDesc") or area,
                "source_type": "alert",
                "headline": p.get("event") or p.get("headline"),
                "narrative_text": narrative,
                "issued_at": p.get("sent") or p.get("effective"),
                "payload": feat,
            })
        return docs

    # ---------- Forecasts ----------

    def _resolve_gridpoint_forecast_url(self, lat: float, lon: float) -> str | None:
        """Resolve a lat/lon to its NWS forecast URL via /points/{lat},{lon}."""
        data = self.get(f"/points/{lat},{lon}")
        return (data.get("properties") or {}).get("forecast")

    def get_forecast(self, lat: float, lon: float, location_label: str,
                     limit: int = 14) -> list[dict]:
        """
        Multi-period narrative forecast for a lat/lon. Each period's
        detailedForecast free text becomes one document.
        """
        forecast_url = self._resolve_gridpoint_forecast_url(lat, lon)
        if not forecast_url:
            return []
        data = self.get(forecast_url)
        periods = (data.get("properties") or {}).get("periods", [])[:limit]
        docs = []
        for period in periods:
            narrative = (period.get("detailedForecast") or "").strip()
            if not narrative:
                continue
            issued = (data.get("properties") or {}).get("updated")
            # Forecasts have no stable API id, so hash location + period name.
            raw_id = f"{location_label}|{period.get('name')}|{issued}"
            doc_id = "forecast_" + hashlib.sha1(raw_id.encode()).hexdigest()[:16]
            docs.append({
                "id": doc_id,
                "location": location_label,
                "source_type": "forecast",
                "headline": period.get("name"),  # e.g. "Tonight", "Saturday"
                "narrative_text": narrative,
                "issued_at": issued,
                "payload": period,
            })
        return docs