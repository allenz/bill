"""Hourly refresh of the To-be-reviewed labs tab (db.unreviewed_labs),
which also refreshes the yellow sticky of tab patients whose stored
note is over a day old (or was never fetched).

Slim copy of update_billing.py: no full update_all, no report. Cron fires
on the hour, 7am-11pm PT only; the job sleeps a random 1-55 minutes first
so it never hits ECW exactly on the hour. The window check below also
guards against a manual run during the 12am-7am quiet hours (pass
--force to override).

Usage: python hourly_labs.py [DATE]  (DATE = MM/DD/YYYY, default today)
"""
import sys
from datetime import datetime

from config import DATABASE_URL
from db import unreviewed_labs
from ecw_session import ESession
from ecw_client import Client
from sqlmodel import Session, create_engine

QUIET_HOURS = range(0, 7)  # 12am-7am PT


def main():
  if datetime.now().hour in QUIET_HOURS and '--force' not in sys.argv:
    print(f'hourly_labs: {datetime.now():%Y-%m-%d %H:%M} is in the 12am-7am window, skipping')
    return
  date = next((a for a in sys.argv[1:] if not a.startswith('--')), '')
  engine = create_engine(DATABASE_URL)
  session = Session(engine)
  with ESession() as esession:
    client = Client(esession)
    unreviewed_labs(session, client, date)


if __name__ == '__main__':
  main()
