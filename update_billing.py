from datetime import date, timedelta

from config import DATABASE_URL
from db import update_all
from ecw_session import ESession
from generate_report import generate_report
from ecw_client import Client
from sqlmodel import Session, create_engine


if __name__ == "__main__":
  engine = create_engine(DATABASE_URL)
  session = Session(engine)
  con = engine.connect()
  with ESession() as esession:
    client = Client(esession)
    update_all(session, client)
    from_date = '2026-01-01'
    to_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    generate_report(con, from_date, to_date)#, claim='49631')
    # if refresh:
    #   mrns = df[df.ppo == 1].mrn.unique().tolist()
    #   add_patients(session, client, mrns, refresh=refresh)
    #   generate_report(start_date, end_date, claim)
