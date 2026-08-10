# Databricks notebook source
# MAGIC %pip install -q pg8000 requests "databricks-sdk>=0.89.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import pg8000.native
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ENDPOINT_NAME = "projects/recall-db/branches/production/endpoints/primary"
PGHOST = "ep-wild-violet-d86rvqjx.database.us-east-2.cloud.databricks.com"
PGUSER = w.current_user.me().user_name
PGDATABASE = "databricks_postgres"

def get_conn():
    token = w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME).token
    return pg8000.native.Connection(
        user=PGUSER, password=token, host=PGHOST,
        database=PGDATABASE, port=5432, ssl_context=True,
    )

con = get_conn()
print("recalls rows:", con.run("SELECT count(*) FROM recalls")[0][0])
con.close()

# COMMAND ----------

# ===== Spark ingest: openFDA food recalls -> Lakebase =====
import requests
import json as _json
import time
from pyspark.sql import functions as F


def fetch_with_retries(url, params, attempts=3, base_delay=1.0):
    """GET with retry/backoff on transient 429/5xx errors."""
    for i in range(attempts):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"transient {resp.status_code}")
            resp.raise_for_status()
            return resp
        except Exception as e:
            if i == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** i))   # 1s, 2s, 4s


# 1. Fetch live FDA food recalls from openFDA (keyless, with retries)
resp = fetch_with_retries(
    "https://api.fda.gov/food/enforcement.json",
    {"limit": 100},
)
results = resp.json().get("results", [])
print(f"Fetched {len(results)} FDA food recalls")

# 2. Load into a Spark DataFrame and normalize with Spark transformations
df = spark.createDataFrame([_json.dumps(r) for r in results], "string").toDF("raw_json")

parsed = (
    df.select(F.from_json(F.col("raw_json"),
        "recall_number STRING, recalling_firm STRING, product_description STRING, "
        "reason_for_recall STRING, classification STRING, status STRING, report_date STRING"
    ).alias("r"), F.col("raw_json"))
    .select(
        F.concat(F.lit("fda_food_"), F.col("r.recall_number")).alias("recall_id"),
        F.lit("fda_food").alias("source"),
        F.col("r.recalling_firm").alias("firm"),
        F.col("r.product_description").alias("product_description"),
        F.col("r.reason_for_recall").alias("reason"),
        F.col("r.classification").alias("classification"),
        F.col("r.status").alias("status"),
        F.col("r.report_date").alias("report_date"),
        F.col("raw_json"),
    )
    .filter(F.col("recall_id").isNotNull() & (F.col("recall_id") != "fda_food_"))
)

rows = parsed.collect()
print(f"Normalized {len(rows)} recall rows via Spark")

# 3. Write to Lakebase via pg8000 (ON CONFLICT dedups on re-run)
con = get_conn()
inserted = 0
for row in rows:
    con.run(
        """
        INSERT INTO recalls
            (recall_id, source, firm, product_description, reason,
             classification, status, report_date, raw, synced_at)
        VALUES (:rid, :src, :firm, :pd, :reason, :cls, :status, :rd,
                CAST(:raw AS jsonb), now())
        ON CONFLICT (recall_id) DO NOTHING
        """,
        rid=row["recall_id"], src=row["source"], firm=row["firm"],
        pd=row["product_description"], reason=row["reason"],
        cls=row["classification"], status=row["status"], rd=row["report_date"],
        raw=row["raw_json"],
    )
    inserted += 1
con.close()
print(f"Wrote {inserted} recalls to Lakebase")

# COMMAND ----------

# ===== Embed recalls with Databricks-hosted gte-large-en (1024-dim) =====
EMBED_ENDPOINT = "databricks-gte-large-en"

def embed_text(text):
    resp = w.serving_endpoints.query(name=EMBED_ENDPOINT, input=text)
    return resp.data[0].embedding

def recall_text(firm, product, reason):
    return " — ".join([p for p in [firm, product, reason] if p])

# Read recalls that don't yet have an embedding
con = get_conn()
recalls = con.run("""
    SELECT r.recall_id, r.firm, r.product_description, r.reason
    FROM recalls r
    WHERE NOT EXISTS (
        SELECT 1 FROM recall_embeddings e WHERE e.recall_id = r.recall_id
    )
""")
con.close()
print(f"Recalls to embed: {len(recalls)}")

con = get_conn()
written = 0
for recall_id, firm, product, reason in recalls:
    text = recall_text(firm, product, reason)[:2000]
    vec = embed_text(text)
    vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
    con.run("""
        INSERT INTO recall_embeddings
            (id, recall_id, chunk_index, chunk_text, embedding, model_name, created_at)
        VALUES (:id, :rid, 0, :ct, CAST(:emb AS vector), :model, now())
        ON CONFLICT (id) DO NOTHING
    """, id=f"{recall_id}_0", rid=recall_id, ct=text, emb=vec_literal, model=EMBED_ENDPOINT)
    written += 1
    if written % 25 == 0:
        print(f"  embedded {written}...")
con.close()
print(f"Wrote {written} embeddings (dim 1024)")

# COMMAND ----------

# ===== Quick check: semantic search over the embedded recalls =====
def search_recalls(query, top_k=5):
    qvec = embed_text(query)
    vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
    con = get_conn()
    rows = con.run("""
        SELECT r.firm, r.classification, r.reason,
               1 - (e.embedding <=> CAST(:qv AS vector)) AS similarity
        FROM recall_embeddings e
        JOIN recalls r ON r.recall_id = e.recall_id
        ORDER BY e.embedding <=> CAST(:qv AS vector)
        LIMIT :k
    """, qv=vec_literal, k=top_k)
    con.close()
    return rows

print("=== peanut allergen ===")
for firm, cls, reason, sim in search_recalls("peanut allergy undeclared nuts"):
    print(f"{sim:.3f} [{cls}] {firm}: {(reason or '')[:70]}")
