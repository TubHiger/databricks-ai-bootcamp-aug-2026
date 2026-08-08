-- ============================================================
-- Lakebase schema for the AI Support App
-- Run in the Lakebase SQL editor against the databricks_postgres
-- database (connected as the project owner).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS support;
SET search_path TO support;

-- ---------- Tables ----------

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id    BIGSERIAL PRIMARY KEY,
    title        TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'in_progress', 'resolved')),
    priority     TEXT        NOT NULL DEFAULT 'medium'
                 CHECK (priority IN ('low', 'medium', 'high')),
    created_by   TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id   BIGSERIAL PRIMARY KEY,
    ticket_id    BIGINT      NOT NULL
                 REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    message_text TEXT        NOT NULL,
    author       TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_ticket
    ON ticket_messages(ticket_id);

-- ---------- Sample data ----------
-- 3 tickets, 2 messages each, 3 distinct statuses.

INSERT INTO tickets (title, status, priority, created_by) VALUES
    ('Cannot log in to dashboard',        'open',        'high',   'aika'),
    ('Export to CSV is missing columns',  'in_progress', 'medium', 'jordan'),
    ('Feature request: dark mode',        'resolved',    'low',    'sam');

INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'I get a 403 error right after entering my password.', 'aika'
  FROM tickets WHERE title = 'Cannot log in to dashboard';
INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'Thanks — can you confirm which browser you are using?', 'support'
  FROM tickets WHERE title = 'Cannot log in to dashboard';

INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'The region and signup_date columns are blank in the export.', 'jordan'
  FROM tickets WHERE title = 'Export to CSV is missing columns';
INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'Reproduced it. A fix is in progress for the next release.', 'support'
  FROM tickets WHERE title = 'Export to CSV is missing columns';

INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'Would love a dark theme for late-night work.', 'sam'
  FROM tickets WHERE title = 'Feature request: dark mode';
INSERT INTO ticket_messages (ticket_id, message_text, author)
SELECT ticket_id, 'Shipped in v2.4 — marking this resolved.', 'support'
  FROM tickets WHERE title = 'Feature request: dark mode';

-- ---------- Grant the app's service principal access ----------
-- Replace <APP_CLIENT_ID> with your app's DATABRICKS_CLIENT_ID.
-- (Requires the databricks_auth extension for OAuth roles.)
--
-- CREATE EXTENSION IF NOT EXISTS databricks_auth;
-- SELECT databricks_create_role('<APP_CLIENT_ID>', 'service_principal');
-- GRANT USAGE ON SCHEMA support TO "<APP_CLIENT_ID>";
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA support
--     TO "<APP_CLIENT_ID>";
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA support
--     TO "<APP_CLIENT_ID>";
