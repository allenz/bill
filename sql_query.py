#!/usr/bin/env python3
"""Run a SQL query against the billing database and print the result.

Usage:
  sql_query.py "SELECT mrn, name FROM patient LIMIT 5"
  sql_query.py < query.sql        # multi-line queries from stdin
  echo "SELECT 1" | sql_query.py

Queries are run against the PostgreSQL cluster in config.py (PG_DSN).
Rows are printed as an aligned table. If the query has no result set
(INSERT/UPDATE/etc.), the row count is printed instead.
"""
import sys

import psycopg2
from config import PG_DSN


def fmt(value):
  if value is None:
    return 'NULL'
  if isinstance(value, (list, tuple)):
    return str(list(value))
  if isinstance(value, dict):
    return str({k: fmt(v) for k, v in value.items()})
  return str(value)


def print_table(columns, rows):
  cells = [[fmt(v) for v in row] for row in rows]
  widths = [max(len(c), *(len(r[i]) for r in cells)) if cells else len(c)
            for i, c in enumerate(columns)]
  line = '  '.join(c.ljust(w) for c, w in zip(columns, widths))
  print(line)
  print('  '.join('-' * w for w in widths))
  for row in cells:
    print('  '.join(v.ljust(w) for v, w in zip(row, widths)))
  print(f'{len(rows)} row(s)')


def main(query: str):
  conn = psycopg2.connect(PG_DSN)
  try:
    with conn.cursor() as cur:
      cur.execute(query)
      if cur.description:
        print_table([d.name for d in cur.description], cur.fetchall())
      else:
        conn.commit()
        print(f'{cur.rowcount} row(s) affected')
  finally:
    conn.close()


if __name__ == "__main__":
  query = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
  query = query.strip()
  if not query:
    sys.exit('usage: sql_query.py <query>   (or pipe the query via stdin)')
  main(query)
