"""
Weather Intelligence app — NWS alerts -> Lakebase -> pgvector semantic search.
Endpoints:
  POST /api/weather/sync    harvest active NWS alerts into weather_documents
  POST /api/weather/search  semantic search over weather_embeddings (vector in)
  GET  /api/healthz         health check
The app stays lightweight (no embedding model): callers embed the query with
all-MiniLM-L6-v2 and POST the 384-dim vector. Keeps memory low for Free Edition.
"""
import json as _json
import logging
import re

from flask import Flask, jsonify, request

from db import get_conn
from weather_client import WeatherClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-app")

app = Flask(__name__)

_STATE_RE = re.compile(r"^[A-Z]{2}$")


@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok"})


# ----------------------------------------------------------------------------
# Retrieve: POST /api/weather/search
# ----------------------------------------------------------------------------

@app.route("/api/weather/search", methods=["POST"])
def weather_search():
    """
    Semantic search over weather_embeddings.
    Body: {"query_vector": [384 floats], "top_k": 5}
    The caller embeds the query text with all-MiniLM-L6-v2 (same model as
    ingestion) and passes the 384-dim vector. No model loaded in the app.
    """
    body = request.json if request.is_json else {}
    qvec = body.get("query_vector")
    if not qvec or not isinstance(qvec, list) or len(qvec) != 384:
        return jsonify({"error": "Provide 'query_vector' as a 384-float list."}), 400

    try:
        top_k = int(body.get("top_k", 5))
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 20))

    vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weather_embeddings")
            if cur.fetchone()[0] == 0:
                return jsonify({"results": [], "note": "No embeddings yet."})
            cur.execute(
                """
                SELECT d.location, d.headline, e.chunk_text,
                       1 - (e.embedding <=> %s::vector) AS similarity
                FROM weather_embeddings e
                JOIN weather_documents d ON d.id = e.document_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_literal, vec_literal, top_k),
            )
            rows = cur.fetchall()

    results = [
        {"location": r[0], "headline": r[1], "chunk_text": r[2],
         "similarity": round(float(r[3]), 4)}
        for r in rows
    ]
    return jsonify({"top_k": top_k, "results": results})


# ----------------------------------------------------------------------------
# Harvest: POST /api/weather/sync
# ----------------------------------------------------------------------------

def _parse_state(location: str):
    """'TX', 'Austin, TX', or 'austin tx' -> 'TX'. Alerts query by state."""
    if not isinstance(location, str):
        return None
    loc = location.strip().upper()
    if _STATE_RE.match(loc):
        return loc
    tail = re.split(r"[,\s]+", loc)[-1] if loc else ""
    return tail if _STATE_RE.match(tail) else None


def _upsert_weather_docs(docs):
    """Upsert normalized weather documents into weather_documents."""
    if not docs:
        return 0
    count = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for d in docs:
                cur.execute(
                    """
                    INSERT INTO weather_documents (
                        id, location, source_type, headline,
                        narrative_text, issued_at, payload, synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE
                        SET location = EXCLUDED.location,
                            source_type = EXCLUDED.source_type,
                            headline = EXCLUDED.headline,
                            narrative_text = EXCLUDED.narrative_text,
                            issued_at = EXCLUDED.issued_at,
                            payload = EXCLUDED.payload,
                            synced_at = EXCLUDED.synced_at
                    """,
                    (
                        d["id"], d["location"], d["source_type"], d.get("headline"),
                        d["narrative_text"], d.get("issued_at"),
                        _json.dumps(d["payload"]),
                    ),
                )
                count += 1
        conn.commit()
    return count


@app.route("/api/weather/sync", methods=["POST"])
def weather_sync():
    """
    Harvest active NWS alerts for the given locations into weather_documents.
    Body: {"locations": ["Chicago, IL", "TX"], "limit": 50}
    """
    body = request.json if request.is_json else {}
    locations = body.get("locations") or []
    limit = int(body.get("limit", 50))

    states = []
    for loc in locations:
        st = _parse_state(loc)
        if st and st not in states:
            states.append(st)

    if not states:
        return jsonify({"error": "No valid US state codes found in 'locations'."}), 400

    client = WeatherClient()
    all_docs = []
    for st in states:
        try:
            all_docs.extend(client.get_active_alerts(st, limit=limit))
        except Exception as exc:
            logger.warning("Failed to fetch alerts for %s: %s", st, exc)
            continue

    synced = _upsert_weather_docs(all_docs)
    return jsonify({"synced": synced, "states": states})


@app.errorhandler(Exception)
def handle_exception(err):
    logger.exception("Unhandled exception")
    code = getattr(err, "code", 500)
    if not isinstance(code, int):
        code = 500
    return jsonify({"error": str(err)}), code


if __name__ == "__main__":
    import os
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", 8000))
    app.run(host=host, port=port)