"""
Recall Radar dashboard — web UI over FDA recall data in Lakebase.
  /            : semantic recall search
  /watchlist   : save foods under a name and check them against current recalls
"""
import os
from flask import Flask, request, render_template, redirect, url_for

from databricks.sdk import WorkspaceClient
from db import get_conn

app = Flask(__name__)
w = WorkspaceClient()
EMBED_ENDPOINT = os.environ.get("EMBED_ENDPOINT", "databricks-gte-large-en")

_SEVERITY = {"Class I": "High", "Class II": "Medium", "Class III": "Low"}
_ACTION = {
    "Class I":  "Class I recall (most serious). Stop using immediately and contact the firm.",
    "Class II": "Class II recall. Review the recall details and consider discontinuing use.",
    "Class III": "Class III recall (least serious). Be aware; risk is limited.",
}

MATCH_FLOOR = 0.68   # hide weak/irrelevant matches below this similarity


def embed(text):
    resp = w.serving_endpoints.query(name=EMBED_ENDPOINT, input=text)
    return resp.data[0].embedding


def vector_search(text, top_k=10):
    vec = embed(text)
    lit = "[" + ",".join(str(float(x)) for x in vec) + "]"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.recall_id, r.firm, r.classification, r.reason,
                   r.product_description,
                   1 - (e.embedding <=> %s::vector) AS similarity
            FROM recall_embeddings e
            JOIN recalls r ON r.recall_id = e.recall_id
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (lit, lit, top_k),
        )
        return cur.fetchall()


def _get_or_create_watchlist(cur, label):
    cur.execute(
        "INSERT INTO watchlists (label) VALUES (%s) ON CONFLICT (label) DO NOTHING",
        (label,),
    )
    cur.execute("SELECT watchlist_id FROM watchlists WHERE label = %s", (label,))
    return cur.fetchone()[0]


def _known_labels():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT label FROM watchlists ORDER BY created_at DESC LIMIT 20")
        return [r[0] for r in cur.fetchall()]


@app.route("/", methods=["GET"])
def index():
    query = (request.args.get("q") or "").strip()
    results = []
    if query:
        for rid, firm, cls, reason, product, sim in vector_search(query, 10):
            if float(sim) < MATCH_FLOOR:
                continue
            results.append({
                "firm": firm, "classification": cls,
                "severity": _SEVERITY.get(cls, "Unknown"),
                "reason": reason, "product": product,
                "similarity": round(float(sim), 3),
            })
    return render_template("index.html", query=query, results=results)


@app.route("/watchlist", methods=["GET", "POST"])
def watchlist():
    label = (request.values.get("label") or "").strip()
    products, alerts = [], []

    # Add a product (POST), then redirect back to the watchlist view
    if request.method == "POST" and label:
        kind = request.form.get("kind", "food")
        name = (request.form.get("name") or "").strip()
        brand = (request.form.get("brand") or "").strip() or None
        if name:
            with get_conn() as conn, conn.cursor() as cur:
                wl = _get_or_create_watchlist(cur, label)
                cur.execute(
                    "INSERT INTO watched_products (watchlist_id, kind, name, brand) "
                    "VALUES (%s,%s,%s,%s)",
                    (wl, kind, name, brand),
                )
                conn.commit()
        return redirect(url_for("watchlist", label=label))

    # Show saved products + recall matches for the given label
    if label:
        with get_conn() as conn, conn.cursor() as cur:
            wl = _get_or_create_watchlist(cur, label)
            conn.commit()
            cur.execute(
                "SELECT kind, name, brand FROM watched_products "
                "WHERE watchlist_id = %s ORDER BY created_at",
                (wl,),
            )
            products = [{"kind": k, "name": n, "brand": b} for k, n, b in cur.fetchall()]

        for p in products:
            q = " ".join([x for x in [p["brand"], p["name"], p["kind"]] if x])
            rows = vector_search(q, 1)
            if not rows:
                continue
            rid, firm, cls, reason, product, sim = rows[0]
            if float(sim) < MATCH_FLOOR:
                continue
            alerts.append({
                "product": p["name"], "firm": firm,
                "severity": _SEVERITY.get(cls, "Unknown"),
                "classification": cls, "reason": reason,
                "action": _ACTION.get(cls, "Review the recall details."),
                "confidence": round(float(sim), 3),
            })

    return render_template(
        "watchlist.html",
        label=label, products=products, alerts=alerts,
        known_labels=_known_labels(),
    )


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))