"""
Lakebase connection — fresh connection per request (no pool).
Mints an OAuth token and connects directly, the exact pattern the
self-test proved works. No secrets in code.
"""
import os
from contextlib import contextmanager

import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
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
        conn.execute("SET search_path TO support")
        yield conn
        conn.commit()
    finally:
        conn.close()