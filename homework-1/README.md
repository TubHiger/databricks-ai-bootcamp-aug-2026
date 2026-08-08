# Lakebase-Powered AI Support App

A small internal support-ticket application built as a **Databricks App**,
backed by **Lakebase** (managed Postgres). Users can create support tickets,
read and add messages on them, and change a ticket's status — all persisted
in Lakebase, not in memory.

Built for Day 1 of the Databricks AI Bootcamp.

## What it does

- **View all tickets** with status, priority, and creator
- **Open a ticket** to read its message thread
- **Create a ticket** (title, author, priority)
- **Add a message** to an existing ticket
- **Update a ticket's status** (open → in progress → resolved)

Every read and write goes to Lakebase over an authenticated Postgres
connection.

### Bonus features implemented

- Ticket **priority** (low / medium / high)
- **Filter** the ticket list by status
- **Input validation** with friendly inline error messages
- **Statistics** bar (counts by status)
- **Styled UI** (clean custom CSS, status pills)

## Architecture

```
Browser ──HTTP──> Databricks App (Flask)
                       │
                       │  psycopg  (SSL)
                       ▼
                  Lakebase Postgres  ── tickets, ticket_messages
```

The app authenticates to Lakebase as its own **service principal**. On each
request it mints a short-lived OAuth database credential via the Databricks
SDK and uses it as the Postgres password, so no long-lived secret is ever
stored.

## Data model

```
tickets
  ticket_id     BIGSERIAL PK
  title         TEXT
  status        TEXT  CHECK (open | in_progress | resolved)
  priority      TEXT  CHECK (low | medium | high)
  created_by    TEXT
  created_at    TIMESTAMPTZ

ticket_messages
  message_id    BIGSERIAL PK
  ticket_id     BIGINT  FK -> tickets(ticket_id) ON DELETE CASCADE
  message_text  TEXT
  author        TEXT
  created_at    TIMESTAMPTZ
```

See [`schema.sql`](./schema.sql) for the full DDL and sample data.

## Project layout

```
.
├── app.py             # Flask routes for all five operations
├── db.py              # Lakebase connection + OAuth token minting
├── requirements.txt   # Python dependencies
├── app.yaml           # Databricks App start command + ENDPOINT_NAME
├── schema.sql         # Schema + seed data
└── templates/
    ├── index.html     # Ticket list, stats, create form, filter
    └── detail.html    # One ticket: messages, add message, update status
```

## Running it

This app is designed to run as a Databricks App with a Lakebase project
attached as a resource. High level:

1. Create a Lakebase project (Postgres 17) and run `schema.sql` in its SQL
   editor.
2. Create a Databricks App (Flask template) and attach the Lakebase database
   as a resource.
3. Create a Postgres role for the app's service principal and grant it access
   to the `support` schema.
4. Set `ENDPOINT_NAME` in `app.yaml` to your compute's resource name
   (`projects/<project>/branches/<branch>/endpoints/<endpoint>`).
5. Deploy from the source folder.

Connection details (`PGHOST`, `PGUSER`, `PGDATABASE`, `PGPORT`, `PGSSLMODE`)
are injected automatically by Databricks when the Lakebase resource is
attached — the app reads them from the environment.

## Security

No passwords, tokens, connection strings, or other secrets are committed to
this repo. The app obtains database credentials at runtime from the Databricks
environment (injected connection variables + short-lived OAuth tokens). The
only identifier in config is the Lakebase endpoint **resource path**, which is
not a secret. See [`.gitignore`](./.gitignore) for excluded patterns.

## Reflection

The hardest part was authenticating the app's service principal to Lakebase:
the token-minting call needed the exact endpoint resource path and the correct
SDK method, which took a few deploy-and-read-the-logs cycles to get right.
Lakebase differs from a traditional analytics table in that it's an OLTP
Postgres database built for many small, low-latency reads and writes with real
transactional consistency and foreign keys — unlike a columnar Delta table
optimized for large scans. The next feature I'd add is delete-with-confirmation
plus ticket assignment, so tickets could be routed to specific agents.
