-- ============================================================
-- Recall Radar — Lakebase schema (Postgres + pgvector)
-- Run in the recall-db Lakebase SQL editor.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Recalls harvested from openFDA (Spark ingest writes here)
CREATE TABLE IF NOT EXISTS recalls (
    recall_id           TEXT PRIMARY KEY,   -- source + recall_number (stable dedup key)
    source              TEXT NOT NULL CHECK (source IN ('fda_food','fda_drug','fda_device','nhtsa')),
    firm                TEXT,
    product_description TEXT,
    reason              TEXT,
    classification      TEXT,               -- FDA Class I/II/III = severity
    status              TEXT,
    report_date         TEXT,
    raw                 JSONB NOT NULL,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recalls_source ON recalls(source);
CREATE INDEX IF NOT EXISTS idx_recalls_class  ON recalls(classification);

-- Embeddings over recall text (gte-large-en = 1024-dim)
CREATE TABLE IF NOT EXISTS recall_embeddings (
    id          TEXT PRIMARY KEY,           -- recall_id + '_' + chunk_index
    recall_id   TEXT NOT NULL REFERENCES recalls(recall_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   VECTOR(1024) NOT NULL,
    model_name  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recall_emb_vec
    ON recall_embeddings USING hnsw (embedding vector_cosine_ops);

-- Watchlists (no login; a label the user picks)
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id  BIGSERIAL PRIMARY KEY,
    label         TEXT UNIQUE NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watched_products (
    product_id    BIGSERIAL PRIMARY KEY,
    watchlist_id  BIGINT NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('food','drug','device','vehicle')),
    name          TEXT NOT NULL,
    brand         TEXT,
    model         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_watched_products_wl ON watched_products(watchlist_id);

-- Alerts the agent writes (severity + recommended action)
CREATE TABLE IF NOT EXISTS alerts (
    alert_id            BIGSERIAL PRIMARY KEY,
    watchlist_id        BIGINT NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    recall_id           TEXT NOT NULL REFERENCES recalls(recall_id) ON DELETE CASCADE,
    severity            TEXT,
    match_confidence    REAL,
    recommended_action  TEXT,
    status              TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','dismissed','acted')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_wl ON alerts(watchlist_id);

-- ---- Grant each Databricks App's service principal access ----
-- Run once per app (MCP server + dashboard), replacing <APP_CLIENT_ID>:
-- CREATE EXTENSION IF NOT EXISTS databricks_auth;
-- SELECT databricks_create_role('<APP_CLIENT_ID>', 'service_principal');
-- GRANT USAGE ON SCHEMA public TO "<APP_CLIENT_ID>";
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "<APP_CLIENT_ID>";
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<APP_CLIENT_ID>";
