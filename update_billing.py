from datetime import date, timedelta
import sqlite3

from ecw_session import ESession
from scrape_ecw import Client, DIR
from db import update_all, report


if __name__ == "__main__":
  con = sqlite3.connect(DIR / "billing.sqlite3")
  with ESession() as esession:
    client = Client(esession)
    update_all(con, client)
    from_date = '2026-01-01'
    to_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    report(con, client, from_date, to_date, refresh=False)#, claim='49631')
