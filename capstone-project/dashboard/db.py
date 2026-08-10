"""Lakebase connection for the Recall Radar dashboard (psycopg v3)."""
import os
from contextlib import contextmanager

import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

ENDPOINT_NAME = os.environ.get(
    "ENDPOINT_NAME", "projects/recall-db/branches/production/endpoints/primary"
)
PGHOST = os.environ["PGHOST"]
PGUSER = os.environ["PGUSER"]
PGPORT = os.environ.get("PGPORT", "5432")
PGDATABASE = os.environ.get("PGDATABASE", "databricks_postgres")


@contextmanager
def get_conn():
    cred = w.postgres.generate_database_credential(endpoint=ENDPOINT_NAME)
    conn = psycopg.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE,
        user=PGUSER, password=cred.token, sslmode="require", connect_timeout=10,
    )
    try:
        yield conn
    finally:
        conn.close()