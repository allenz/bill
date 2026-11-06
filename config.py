from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

DIR = Path('/srv/allen/ecw')

# Legacy SQLite billing db, kept only for the one-off migrate_*.py scripts
# and as a cold backup after the PostgreSQL cutover.
DB_PATH = DIR / "billing.sqlite3"

# PostgreSQL (local cluster 18). All billing tables live in the `web` schema,
# which is first in the search_path of the `web` role.
# PG_HOST = "localhost"
PG_HOST = "100.109.64.20"
PG_PORT = 5432
PG_USER = "web"
PG_PASS = os.environ["PG_PASS"]
PG_DATABASE = "web"

# Sync SQLAlchemy URL (db.py, update_billing.py).
DATABASE_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
# Async SQLAlchemy URL (app.py).
DATABASE_URL_ASYNC = f"postgresql+asyncpg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
# Plain DSN for raw psycopg2 connections (claim_info.py).
PG_DSN = f"host={PG_HOST} port={PG_PORT} dbname={PG_DATABASE} user={PG_USER} password={PG_PASS}"
