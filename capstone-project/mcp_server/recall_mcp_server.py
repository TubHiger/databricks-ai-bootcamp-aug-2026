"""
Recall Radar MCP server (FastMCP).

Exposes product-safety tools over MCP so a Databricks Agent Bricks agent can
call them:
    - search_recalls(query, top_k)          READ  (semantic search)
    - add_product(label, kind, name, brand) WRITE (register a watched product)
    - check_watchlist(label)                READ+WRITE (match products -> alerts)
    - list_alerts(label)                    READ  (show a watchlist's alerts)

Backed by openFDA recall data in Lakebase (see recall_broker.py). Tool
functions are thin; all DB + embedding logic lives in the broker. Query
embedding uses the Databricks-hosted gte-large-en endpoint (no local model),
so the app stays light.
"""
import logging
import os

from fastmcp import FastMCP

import recall_broker
from recall_broker import _SEVERITY  # noqa (kept for reference)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recall-radar-mcp")

mcp = FastMCP("recall-radar")


@mcp.tool
def search_recalls(query: str, top_k: int = 5) -> list[dict]:
    """
    Search FDA product recalls by meaning (semantic search).

    Args:
        query: What to search for, e.g. "undeclared peanuts in snack bars"
            or "salmonella in flour" or "Honda airbag".
        top_k: How many results to return (1-20; default 5).

    Returns:
        A list of recall dicts, each with recall_id, firm, classification,
        severity (High/Medium/Low), reason, product, and a similarity score.
        On failure, returns [{"error": "..."}].
    """
    try:
        return recall_broker.search_recalls(query, top_k)
    except Exception as e:
        logger.exception("search_recalls failed")
        return [{"error": f"Search failed: {e}"}]


@mcp.tool
def add_product(label: str, kind: str, name: str, brand: str = None) -> dict:
    """
    Add a product to a watchlist so it can be checked against recalls.
    No login required — the watchlist is identified by a label the user picks.

    Args:
        label: A watchlist name the user chooses, e.g. "my-kitchen" or a name.
        kind: One of "food", "drug", "device", or "vehicle".
        name: The product name, e.g. "peanut butter" or "Civic".
        brand: Optional brand/maker, e.g. "Jif" or "Honda".

    Returns:
        A dict confirming what was added, or {"error": "..."}.
    """
    try:
        if kind not in ("food", "drug", "device", "vehicle"):
            return {"error": "kind must be one of: food, drug, device, vehicle"}
        return recall_broker.add_product(label, kind, name, brand)
    except Exception as e:
        logger.exception("add_product failed")
        return {"error": f"Add failed: {e}"}


@mcp.tool
def check_watchlist(label: str) -> dict:
    """
    Check every product on a watchlist against FDA recalls. For each match,
    creates an alert with a severity (from the FDA recall classification) and a
    recommended action. This is the core "monitoring" action.

    Args:
        label: The watchlist name to check.

    Returns:
        A dict with alerts_created and the list of alerts (product, matched
        recall, severity, match_confidence, recommended_action), or {"error"}.
    """
    try:
        return recall_broker.check_watchlist(label)
    except Exception as e:
        logger.exception("check_watchlist failed")
        return {"error": f"Check failed: {e}"}


@mcp.tool
def list_alerts(label: str) -> dict:
    """
    List all alerts previously created for a watchlist.

    Args:
        label: The watchlist name.

    Returns:
        A dict with the watchlist's alerts (severity, firm, reason, action,
        status), or {"error": "..."}.
    """
    try:
        return recall_broker.list_alerts(label)
    except Exception as e:
        logger.exception("list_alerts failed")
        return {"error": f"List failed: {e}"}


if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)