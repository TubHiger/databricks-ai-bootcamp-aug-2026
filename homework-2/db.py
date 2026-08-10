"""
Lakebase connection for the weather app — OAuth token per connection.
Same proven pattern as HW1; only the endpoint/project differs.
"""
import os
from contextlib import contextmanager

import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# weather-db's endpoint resource path. Override via env if needed.
ENDPOINT_NAME = os.environ.get(
    "ENDPOINT_NAME", "projects/weather-db/branches/production/endpoints/primary"
)
PGUSER = os.environ["PGUSER"]
PGHOST = os.environ["PGHOST"]
PGPORT = os.environ.get("PGPORT", "5432")
PGDATABASE = os.environ.get("PGDATABASE", "databricks_postgres")
PGSSLMODE = os.environ.get("PGSSLMODE", "require")


@contextmanager
def get_conn():
    cred = w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME)
    conn = psycopg.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE,
        user=PGUSER, password=cred.token, sslmode=PGSSLMODE,
        connect_timeout=10,
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()