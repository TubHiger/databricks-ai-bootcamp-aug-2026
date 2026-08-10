"""
Recall Radar broker — all Lakebase queries + query embedding.
The MCP tools in recall_mcp_server.py stay thin and call these functions.

Query embedding uses the Databricks-hosted gte-large-en endpoint (1024-dim),
matching how the recalls were embedded — so NO local embedding model runs in
the app (avoids the PyTorch memory limit on Databricks Apps).
"""
import os
import time
import pg8000.native
from databricks.sdk import WorkspaceClient

def _with_retries(fn, attempts=3, base_delay=1.0):
    """Call fn(), retrying on transient errors with exponential backoff."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            # retry on rate-limit / server errors; give up on the last attempt
            msg = str(e).lower()
            transient = any(s in msg for s in ("429", "500", "502", "503", "504", "timeout", "temporarily"))
            if i == attempts - 1 or not transient:
                raise
            time.sleep(base_delay * (2 ** i))   # 1s, 2s, 4s
    raise last

_w = WorkspaceClient()

ENDPOINT_NAME = os.environ.get(
    "ENDPOINT_NAME", "projects/recall-db/branches/production/endpoints/primary"
)
PGHOST = os.environ["PGHOST"]
PGUSER = os.environ["PGUSER"]
PGDATABASE = os.environ.get("PGDATABASE", "databricks_postgres")
EMBED_ENDPOINT = os.environ.get("EMBED_ENDPOINT", "databricks-gte-large-en")

# FDA classification -> severity + default action
_SEVERITY = {
    "Class I":  ("High",   "Class I recall (most serious). Stop using immediately and contact the firm / seek guidance."),
    "Class II": ("Medium", "Class II recall. Review the recall details and consider discontinuing use."),
    "Class III":("Low",    "Class III recall (least serious). Be aware; risk is limited."),
}


def _conn():
    token = _w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME).token
    return pg8000.native.Connection(
        user=PGUSER, password=token, host=PGHOST,
        database=PGDATABASE, port=5432, ssl_context=True,
    )


def _embed(text: str):
    resp = _with_retries(lambda: _w.serving_endpoints.query(name=EMBED_ENDPOINT, input=text))
    return resp.data[0].embedding


def _severity_for(classification):
    return _SEVERITY.get(classification, ("Unknown", "Review the recall details."))


def search_recalls(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over recalls via pgvector cosine similarity."""
    vec = _embed(query)
    lit = "[" + ",".join(str(float(x)) for x in vec) + "]"
    con = _conn()
    rows = con.run(
        """
        SELECT r.recall_id, r.firm, r.classification, r.reason,
               r.product_description,
               1 - (e.embedding <=> CAST(:qv AS vector)) AS similarity
        FROM recall_embeddings e
        JOIN recalls r ON r.recall_id = e.recall_id
        ORDER BY e.embedding <=> CAST(:qv AS vector)
        LIMIT :k
        """,
        qv=lit, k=max(1, min(int(top_k), 20)),
    )
    con.close()
    out = []
    for rid, firm, cls, reason, product, sim in rows:
        sev, _ = _severity_for(cls)
        out.append({
            "recall_id": rid, "firm": firm, "classification": cls,
            "severity": sev, "reason": reason, "product": product,
            "similarity": round(float(sim), 4),
        })
    return out


def get_or_create_watchlist(label: str) -> int:
    con = _conn()
    con.run("INSERT INTO watchlists (label) VALUES (:l) ON CONFLICT (label) DO NOTHING",
            l=label)
    rows = con.run("SELECT watchlist_id FROM watchlists WHERE label = :l", l=label)
    con.close()
    return rows[0][0]


def add_product(label: str, kind: str, name: str, brand: str = None) -> dict:
    wl = get_or_create_watchlist(label)
    con = _conn()
    con.run(
        """INSERT INTO watched_products (watchlist_id, kind, name, brand)
           VALUES (:w, :k, :n, :b)""",
        w=wl, k=kind, n=name, b=brand,
    )
    con.close()
    return {"watchlist": label, "added": {"kind": kind, "name": name, "brand": brand}}


def check_watchlist(label: str) -> dict:
    """Match each watched product against recalls; write alerts for hits."""
    wl = get_or_create_watchlist(label)
    con = _conn()
    products = con.run(
        "SELECT kind, name, brand FROM watched_products WHERE watchlist_id = :w", w=wl)
    con.close()
    if not products:
        return {"watchlist": label, "message": "No products on this watchlist yet.", "alerts": []}

    alerts = []
    for kind, name, brand in products:
        query = " ".join([p for p in [brand, name, kind] if p])
        matches = search_recalls(query, top_k=1)
        if not matches:
            continue
        m = matches[0]
        # Only alert on a reasonable semantic match
        if m["similarity"] < 0.68:
            continue
        sev, action = _severity_for(m["classification"])
        con = _conn()
        con.run(
            """INSERT INTO alerts
               (watchlist_id, recall_id, severity, match_confidence, recommended_action, status)
               VALUES (:w, :rid, :sev, :conf, :act, 'new')""",
            w=wl, rid=m["recall_id"], sev=sev, conf=m["similarity"], act=action,
        )
        con.close()
        alerts.append({
            "product": name, "matched_recall": m["firm"], "reason": m["reason"],
            "severity": sev, "match_confidence": m["similarity"],
            "recommended_action": action,
        })
    return {"watchlist": label, "alerts_created": len(alerts), "alerts": alerts}


def list_alerts(label: str) -> dict:
    wl = get_or_create_watchlist(label)
    con = _conn()
    rows = con.run(
        """SELECT a.severity, a.match_confidence, a.recommended_action,
                  r.firm, r.reason, a.status
           FROM alerts a JOIN recalls r ON r.recall_id = a.recall_id
           WHERE a.watchlist_id = :w
           ORDER BY a.created_at DESC""",
        w=wl,
    )
    con.close()
    return {"watchlist": label, "alerts": [
        {"severity": s, "match_confidence": round(float(c), 4), "action": act,
         "firm": firm, "reason": reason, "status": st}
        for s, c, act, firm, reason, st in rows
    ]}
