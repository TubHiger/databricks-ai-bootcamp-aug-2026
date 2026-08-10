# Weather Intelligence — Unstructured Data → Lakebase Vector Search → REST API

A retrieval-augmented pipeline that harvests free-text weather alerts from the
National Weather Service, embeds them into a pgvector column in Lakebase, and
serves semantic search over them through a Flask REST API on Databricks Apps.

```
NWS API ──sync──> weather_documents ──embed──> weather_embeddings ──search──> POST /api/weather/search
(free text)       (raw docs)          (384-dim    (pgvector)         (cosine
                                       vectors)                        similarity)
```

## Data source and why

**National Weather Service API (api.weather.gov).** Chosen because it is free,
requires **no API key**, and returns rich unstructured narrative text — active
alerts include a full `description` and safety `instruction` (e.g. flash-flood
warnings with "turn around, don't drown" guidance). No auth plumbing means the
work stays focused on harvesting, embedding, and retrieval. This project uses
**active alerts** (`GET /alerts/active?area={STATE}`) as the single source; the
schema (`source_type`) is ready to add forecasts later.

## Schema decisions

Two tables in `databricks_postgres` (see `schema_weather.sql`):

- **`weather_documents`** — one row per harvested alert. `id` is the NWS alert
  id (stable, so re-sync upserts via `ON CONFLICT`). `narrative_text` combines
  the alert `description` + `instruction` — the text that gets embedded.
  `payload` (JSONB) keeps the raw API response for provenance.
- **`weather_embeddings`** — one row per text chunk. `embedding VECTOR(384)`
  matches the model output. Foreign key `document_id → weather_documents(id)
  ON DELETE CASCADE`. An **HNSW** index (`vector_cosine_ops`) accelerates the
  `<=>` cosine search.

**Chunking:** sliding window, `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100` characters.
Most NWS alerts are short (one chunk); longer flood warnings with instructions
split into a few overlapping chunks so context isn't lost at boundaries.

**Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` → **384 dims**,
matching the reference news pipeline so the same distance-operator conventions
apply.

## Pipeline: how to run it end-to-end

**1. Create tables** — run `schema_weather.sql` in the `weather-db` SQL editor,
then grant the app's service principal access (commented block at the bottom).

**2. Harvest** — `POST /api/weather/sync` with a list of US states:
```json
{"locations": ["TX", "CA", "FL", "OK"], "limit": 50}
```
Fetches active NWS alerts, normalizes them, upserts into `weather_documents`.

**3. Embed** — run `ingest_weather_embeddings` (Databricks notebook). It reads
unembedded rows, chunks them, embeds with all-MiniLM-L6-v2, and writes vectors
into `weather_embeddings` (idempotent via `ON CONFLICT DO NOTHING`).

**4. Search** — `POST /api/weather/search` with a pre-computed 384-dim query
vector:
```json
{"query_vector": [/* 384 floats */], "top_k": 5}
```
Runs the pgvector cosine search and returns the top matches with location,
headline, chunk_text, and a similarity score.

**Retrieval SQL (core of the endpoint):**
```sql
SELECT d.location, d.headline, e.chunk_text,
       1 - (e.embedding <=> %s::vector) AS similarity
FROM weather_embeddings e
JOIN weather_documents d ON d.id = e.document_id
ORDER BY e.embedding <=> %s::vector
LIMIT %s;
```

Example: a query of *"flash flood risk near rivers"* ranks the Nueces River
Flood Warnings highest, then coastal-flood advisories — semantic matches with
no keyword overlap.

## Files

| File | Purpose |
|------|---------|
| `weather_client.py` | NWS API client (no key; normalizes alerts to documents) |
| `app.py` | Flask app: `/api/weather/sync`, `/api/weather/search`, `/api/healthz` |
| `db.py` | Lakebase connection (OAuth token per request) for the app |
| `ingest_weather_embeddings` | Notebook: chunk + embed + write vectors |
| `schema_weather.sql` | DDL for both tables + HNSW index |

## Known limitations / what I'd improve

- **Query embedding happens outside the app.** The search endpoint takes a
  pre-computed `query_vector` rather than raw text. Loading
  sentence-transformers (PyTorch, ~2GB) inside the Databricks App exceeded
  **Free Edition** app memory and crashed on deploy, so embedding is done by
  the caller with the same model. On a paid tier the app could embed text
  directly. This is the one deviation from a "send text, get results" API.
- **psycopg2 → pg8000 in the notebook.** `psycopg2-binary` crashes the Python
  kernel on Databricks Serverless (SIGABRT 134, a native-extension conflict).
  The ingestion notebook uses **pg8000** (pure Python) instead — same approach
  the reference app documents. The Flask app uses psycopg (v3), which runs fine
  in the app runtime.
- **Alerts only.** Forecast discussions aren't harvested yet; `source_type` is
  in place to add them and filter retrieval by type.
- **No LLM summary layer.** A RAG summary over the top results (stretch goal)
  would be a natural next step.
