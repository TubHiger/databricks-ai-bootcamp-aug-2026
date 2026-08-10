# Weather-Prediction MCP Server + Agent Bricks Agent

A custom **MCP (Model Context Protocol) server** exposing weather-forecast
tools, wired to a **Databricks Agent Bricks agent** that answers natural-
language weather questions. Built for Day 3 of the Databricks AI Bootcamp,
following the `databricks-lakebase-app-day-3` Alpaca MCP pattern.

```
Agent Bricks agent  ──MCP tool calls──>  weather MCP server (Databricks App)  ──REST──>  Open-Meteo
 (AI Playground)                          FastMCP, streamable HTTP                        (no API key)
```

## Weather API + auth

**Open-Meteo** (https://open-meteo.com) — free, **no signup, no API key**,
~10,000 calls/day. Two keyless endpoints are used:
- **Geocoding** (`geocoding-api.open-meteo.com/v1/search`) — resolves a city
  name to latitude/longitude.
- **Forecast** (`api.open-meteo.com/v1/forecast`) — current conditions and
  daily forecast.

Because Open-Meteo needs no credentials, there are **no Databricks secrets**
in this project — nothing to store or commit. (The Day-3 reference used
Alpaca API keys via `_secret()`; that layer is intentionally removed here.)

## Tools exposed

All three are defined with `@mcp.tool` in `weather_mcp_server.py`; each is a
thin wrapper that calls `weather_broker.py` and returns a clean dict.

| Tool | Purpose |
|------|---------|
| `get_current_weather(location)` | Current temp, humidity, wind, conditions for a city. |
| `get_forecast(location, days=3)` | Multi-day forecast: daily high/low, precipitation chance, conditions. |
| `predict_umbrella_needed(location, date=None)` | **Derived recommendation**, not a passthrough. |

**The prediction tool applies its own logic** (documented in its docstring),
based on the forecast's precipitation probability:
- `>= 60%` → **"yes"** (umbrella strongly recommended)
- `>= 30%` → **"maybe"** (carry one just in case)
- otherwise → **"no"**

It returns the chance, the decision, and a human-readable reason.

## Architecture / files

```
homework-3/
└── mcp_server/
    ├── weather_mcp_server.py   # FastMCP server; 3 @mcp.tool functions (thin)
    ├── weather_broker.py       # Open-Meteo adapter: all HTTP + parsing
    ├── requirements.txt        # fastmcp, requests, databricks-sdk
    └── app.yaml                # runs weather_mcp_server.py
```

- **Thin tools / fat broker.** No `requests` calls live inside the `@mcp.tool`
  functions — all HTTP and response parsing is in `weather_broker.py`, mirroring
  the reference's `alpaca_broker.py` split.
- **Error handling.** The broker raises `LocationNotFound` for unresolvable
  cities; each tool catches it and returns `{"error": "..."}` rather than a
  stack trace, so the agent can respond sensibly (e.g. ask the user to clarify).
- **Transport.** `mcp.run(transport="http", ...)` serves streamable HTTP on
  `/mcp` — the transport Databricks' MCP gateway expects.

## Setup / deploy

1. **Deploy the MCP server as a Databricks App.** Create a Custom app whose
   name **starts with `mcp-`** (e.g. `mcp-weather-forecast`) — the `mcp-`
   prefix is required for the app to appear in the AI Playground. Point the
   deployment at the `mcp_server/` folder. No resources or secrets needed.
   The MCP endpoint is `https://<app-url>/mcp`.

2. **Wire it to an agent in the AI Playground.**
   AI Playground → **Tools → Add Tool → MCP Servers → Custom MCP Server** →
   select `mcp-weather-forecast` → Save. The Playground handles OAuth to the
   app automatically.

3. **Add the system prompt** (see `system_prompt.txt`) and chat with the agent.

## Agent system prompt

The agent's system prompt (full text in `system_prompt.txt`) maps question
types to tools and sets guardrails: answer only from tool data, never invent
weather, and on a tool error tell the user the location couldn't be found
rather than guessing.

## Demonstration

Three natural-language questions, each triggering the right tool (screenshots
in `screenshots/`):

1. *"What's the weather like in Chicago right now?"* → `get_current_weather` →
   returned 22°C, 90% humidity, overcast (live Open-Meteo data).
2. *"Will it rain in Austin this weekend?"* → `get_forecast`.
3. *"Do I need an umbrella in Seattle tomorrow?"* → `predict_umbrella_needed`
   → yes/maybe/no with the precipitation-based reason.

## Notes / limitations

- **Free Edition:** the AI Gateway "MCP Service" registration path (and PAT-
  based auth to app-hosted MCP servers) is limited on Free Edition. The working
  path is the **AI Playground custom MCP server** flow above, which handles
  OAuth automatically. App-hosted MCP servers require OAuth — personal access
  tokens are not supported for them.
- **Alerts / stretch tools** (severe-weather alerts via NWS, multi-city
  comparison, historical lookup) are natural next additions; `weather_broker.py`
  is structured so new tools are thin to add.
