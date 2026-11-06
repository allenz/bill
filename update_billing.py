from datetime import date, timedelta

from ecw_session import ESession
from scrape_ecw import Client
from sqlmodel import Session, create_engine
from db import update_all, report
from config import DATABASE_URL


if __name__ == "__main__":
  engine = create_engine(DATABASE_URL)
  session = Session(engine)
  con = engine.connect()
  with ESession() as esession:
    client = Client(esession)
    update_all(session, client)
    from_date = '2026-01-01'
    to_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    report(con, session, client, from_date, to_date, refresh=False)#, claim='49631')
