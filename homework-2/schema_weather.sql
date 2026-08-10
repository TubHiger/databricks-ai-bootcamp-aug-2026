-- ============================================================
-- Weather Intelligence — Lakebase schema (Postgres + pgvector)
-- Run in the weather-db Lakebase SQL editor, database databricks_postgres.
-- ============================================================

-- pgvector extension (enables the vector type + <=> operators)
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Raw weather documents ----------
CREATE TABLE IF NOT EXISTS weather_documents (
    id             TEXT PRIMARY KEY,          -- stable dedup key (NWS alert id, or forecast hash)
    location       TEXT NOT NULL,             -- "Chicago, IL" / areaDesc / "lat,lon"
    source_type    TEXT NOT NULL,             -- 'alert' or 'forecast'
    headline       TEXT,                      -- e.g. "Flash Flood Warning"
    narrative_text TEXT NOT NULL,             -- free-text body that gets embedded
    issued_at      TIMESTAMPTZ,               -- when the alert/forecast was issued
    payload        JSONB NOT NULL,            -- raw API response, for provenance
    synced_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_weather_documents_location
    ON weather_documents (location);
CREATE INDEX IF NOT EXISTS idx_weather_documents_source_type
    ON weather_documents (source_type);

-- ---------- Weather embeddings (pgvector) ----------
CREATE TABLE IF NOT EXISTS weather_embeddings (
    id           TEXT PRIMARY KEY,            -- document_id + '_' + chunk_index
    document_id  TEXT NOT NULL REFERENCES weather_documents(id) ON DELETE CASCADE,
    chunk_index  INT  NOT NULL,
    chunk_text   TEXT NOT NULL,
    embedding    VECTOR(384) NOT NULL,        -- all-MiniLM-L6-v2 = 384 dims
    model_name   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for fast cosine-similarity retrieval (the <=> operator)
CREATE INDEX IF NOT EXISTS idx_weather_embeddings_embedding
    ON weather_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- ---------- Grant the app's service principal access ----------
-- Replace <APP_CLIENT_ID> with the Databricks App's DATABRICKS_CLIENT_ID.
--
-- CREATE EXTENSION IF NOT EXISTS databricks_auth;
-- SELECT databricks_create_role('<APP_CLIENT_ID>', 'service_principal');
-- GRANT USAGE ON SCHEMA public TO "<APP_CLIENT_ID>";
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "<APP_CLIENT_ID>";
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<APP_CLIENT_ID>";
