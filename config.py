from dotenv import load_dotenv
import os
from datetime import date as Date, datetime
from pathlib import Path

load_dotenv(".env")

DIR = Path('/srv/allen/ecw')

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


def parse_date(s) -> Date | None:
    """Scraped date text -> date for the DATE columns.

    None/'' -> None; accepts ISO (YYYY-MM-DD) and US (MM/DD/YYYY) text.
    Unparseable values are warned and stored as NULL.
    """
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    warn(f'parse_date: unparseable date {s!r}')
    return None


def warn(msg: str):
    """Append a timestamped warning to WARN_LOG."""
    with (DIR / 'warn.log').open('a') as f:
        f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n')

