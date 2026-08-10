# Databricks notebook source
# MAGIC %pip install -q pg8000 sentence-transformers "databricks-sdk>=0.89.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import pg8000.native
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ENDPOINT_NAME = "projects/weather-db/branches/production/endpoints/primary"

PGHOST = "ep-wandering-rice-d8kumok8.database.us-east-2.cloud.databricks.com"
PGUSER = w.current_user.me().user_name
PGDATABASE = "databricks_postgres"

def get_conn():
    token = w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME).token
    return pg8000.native.Connection(
        user=PGUSER, password=token, host=PGHOST,
        database=PGDATABASE, port=5432, ssl_context=True,
    )

con = get_conn()
rows = con.run("SELECT count(*) FROM weather_documents")
print("weather_documents rows:", rows[0][0])
con.close()

# COMMAND ----------

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# 1. Read documents that don't have embeddings yet
con = get_conn()
docs = con.run("""
    SELECT d.id, d.location, d.headline, d.narrative_text
    FROM weather_documents d
    WHERE NOT EXISTS (
        SELECT 1 FROM weather_embeddings e WHERE e.document_id = d.id
    )
""")
con.close()
print(f"Documents to embed: {len(docs)}")

# 2. Chunk long narratives with a sliding window
def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    for start in range(0, len(text), size - overlap):
        piece = text[start:start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
    return chunks

# Build (document_id, chunk_index, chunk_text) rows
chunk_rows = []
for doc_id, location, headline, narrative in docs:
    for i, piece in enumerate(chunk_text(narrative)):
        chunk_rows.append((doc_id, i, piece))

print(f"Total chunks to embed: {len(chunk_rows)}")

# 3. Load the model once and embed all chunks in batches
print(f"Loading {EMBEDDING_MODEL_NAME} ...")
model = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder="/tmp/hf_cache")

texts = [c[2] for c in chunk_rows]
vectors = model.encode(texts, batch_size=32, show_progress_bar=True) if texts else []
print(f"Computed {len(vectors)} embeddings, each dim={len(vectors[0]) if len(vectors) else 'NA'}")

# COMMAND ----------

from datetime import datetime

# Build the rows to insert: id, document_id, chunk_index, chunk_text, embedding, model_name
insert_rows = []
for (doc_id, chunk_index, chunk_text_val), vec in zip(chunk_rows, vectors):
    emb_id = f"{doc_id}_{chunk_index}"
    # pgvector accepts a string like '[0.1,0.2,...]' cast to ::vector
    vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
    insert_rows.append((emb_id, doc_id, chunk_index, chunk_text_val, vec_literal))

print(f"Writing {len(insert_rows)} embeddings...")

con = get_conn()
inserted = 0
for emb_id, doc_id, chunk_index, chunk_text_val, vec_literal in insert_rows:
    con.run(
        """
        INSERT INTO weather_embeddings
            (id, document_id, chunk_index, chunk_text, embedding, model_name, created_at)
        VALUES
            (:id, :doc_id, :ci, :ct, CAST(:emb AS vector), :model, now())
        ON CONFLICT (id) DO NOTHING
        """,
        id=emb_id,
        doc_id=doc_id,
        ci=chunk_index,
        ct=chunk_text_val,
        emb=vec_literal,
        model="sentence-transformers/all-MiniLM-L6-v2",
    )
    inserted += 1

con.close()
print(f"Done. Inserted/attempted {inserted} rows.")

# COMMAND ----------

from sentence_transformers import SentenceTransformer
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", cache_folder="/tmp/hf_cache")

def weather_search(query, top_k=5):
    top_k = max(1, min(int(top_k), 20))
    qvec = model.encode(query).tolist()
    vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
    con = get_conn()
    rows = con.run(
        """
        SELECT d.location, d.headline, e.chunk_text,
               1 - (e.embedding <=> CAST(:qv AS vector)) AS similarity
        FROM weather_embeddings e
        JOIN weather_documents d ON d.id = e.document_id
        ORDER BY e.embedding <=> CAST(:qv AS vector)
        LIMIT :k
        """,
        qv=vec_literal, k=top_k,
    )
    con.close()
    return [{"location": r[0], "headline": r[1],
             "chunk_text": (r[2] or "")[:120], "similarity": round(float(r[3]), 4)} for r in rows]

print("=== flash flood risk near rivers ===")
for h in weather_search("flash flood risk near rivers", 5):
    print(f"{h['similarity']:.3f}  {h['headline']}  ({h['location']})")
    print(f"        {h['chunk_text']}")

print("\n=== dangerous extreme heat ===")
for h in weather_search("dangerous extreme heat", 3):
    print(f"{h['similarity']:.3f}  {h['headline']}  ({h['location']})")

# COMMAND ----------

import requests
from databricks.sdk import WorkspaceClient

APP_URL = "https://weather-app-7474645680347061.aws.databricksapps.com"
APP_NAME = "weather-app"
WORKSPACE_URL = "https://dbc-26d9dc86-13f3.cloud.databricks.com"

w = WorkspaceClient()
app_client_id = w.apps.get(APP_NAME).oauth2_app_client_id
notebook_token = (
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
)
resp = requests.post(
    f"{WORKSPACE_URL}/oidc/v1/token",
    data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": notebook_token,
        "subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "all-apis",
        "audience": app_client_id,
    },
)
headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

# Embed the query with the SAME model, then POST the vector to the app
qvec = model.encode("flash flood risk near rivers").tolist()
r = requests.post(f"{APP_URL}/api/weather/search", headers=headers,
                  json={"query_vector": qvec, "top_k": 5})
print(r.status_code)
import json
print(json.dumps(r.json(), indent=2))