"""Main SQL code for updating the billing database."""

from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import pandas as pd
from pathlib import Path
import json
import os
from sqlmodel import Session, create_engine, SQLModel
import sqlalchemy as sa
import re
from urllib.parse import unquote_plus
from tqdm import tqdm
from typing import TypeVar

from ecw_session import ESession
from config import DATABASE_URL
from scrape_ecw import Client, CACHE, clean_interface_status, get_claim, get_claim_data, download_claims_overview, KNOWN_MISSING_PT, to_int, to_float
from claim_info import claim_info
from parse_claim import parse_claim
from models import ClaimCpt, Encounter, Lab, Patient, Pay, PayClaim, PayCpt
# from save_block import save_blocks

REPORT_DIR = Path('/srv/allen/ecw')

T = TypeVar("T", bound=SQLModel)


def upsert(session: Session, model_class: type[T], data: dict, key: str | tuple[str, ...] = 'id') -> T:
  """Sparse upsert of one object by `key` (a primary key column or tuple of
  them for a composite PK), returning the row.

  Only writes the columns the data actually carries; existing rows keep any
  columns the data does not set. Used for partial sources.

  Values must match the model column types: SQLAlchemy 2.0's batched
  INSERT...RETURNING matches rows back to parameter sets by exact value, so a
  str sent to an INTEGER column comes back as an int and the lookup fails
  with InvalidRequestError ("Can't match sentinel values").
  """
  # Fetch existing or initialize a blank instance
  pk = data.get(key) if isinstance(key, str) else tuple(data[k] for k in key)
  obj = session.get(model_class, pk) or model_class()
  for key, value in data.items():
    setattr(obj, key, value)
  session.add(obj)
  return obj


def iso_date(s: str) -> str:
  """Convert MM/DD/YYYY to YYYY-MM-DD."""
  if not s:
    return s
  try:
    return datetime.strptime(s, '%m/%d/%Y').strftime('%Y-%m-%d')
  except ValueError:
    return s


def date_range(from_date: str, to_date: str) -> list[str]:
  # Inclusive of from_date, exclusive of to_date (like range()).
  date = datetime.strptime(from_date, '%Y-%m-%d')
  dates = []
  while date < datetime.strptime(to_date, '%Y-%m-%d'):
    dates.append(date)
    date += timedelta(days=1)
  return [d.strftime('%Y-%m-%d') for d in dates]


# Right now we only update encounter/claim from the schedule list. Clearly we need another way...
# scrape_ecw.py download_claims_overview()
#   get_lookup_count(): POST getLookupCount.jsp
#     ecw_session.py make_claim_form()

def get_encounters(session, client, from_date: str, to_date: str) -> list[tuple[str, str]]:
  print('get_encounters()')
  # run _get_lookup_batch which writes enc_claim
  # download_claims_overview(client, from_date=from_date, to_date=to_date)

  mrn_claims = []
  rows = []
  dates = date_range(from_date, to_date)

  for date in tqdm(dates):
    schedule = client.get_doctors_schedule_list(date)
    for enc in schedule.find_all('encounter'):
      data = {
        'encounter': enc.encounterId.text,
        'date': enc.encDate.text,
        'mrn': to_int(enc.patientId.text),
        'visittype': enc.visitType.text,
        'reason': enc.reason.text,
        # 'dr': '' if enc.doctorName.text == "LING, JIE" else enc.doctorName.text,
      }

      # looks up in enc_claim
      # missing 216151, 218690
      if claim := get_claim(enc.encounterId.text):
        # if not data['claim']:
        #   breakpoint()
        data.update(get_claim_data(claim))
        mrn_claims.append((data['mrn'], data['claim']))
      rows.append(data)
  for row in rows:
    # model fields are int; get_claim() etc add str
    row['encounter'] = int(row['encounter'])
    if 'claim' in row:
      row['claim'] = int(row['claim'])
    upsert(session, Encounter, row, key='encounter')
  session.commit()

  for date in dates:
    mrn_claims += add_claim(session, client, date)
  return mrn_claims


def add_patients(session, client, mrns: list[str] | None = None, refresh: bool = False):
  if not mrns:
    result = session.execute(sa.text('SELECT mrn FROM encounter WHERE mrn NOT IN (SELECT mrn FROM patient)'))
    mrns = [p for (p,) in result]
  pts = []
  for mrn in tqdm(set(mrns)):
    if int(mrn) in KNOWN_MISSING_PT:
      continue
    pt = client.search_patient(mrn)
    if not (pt.ControlNo or pt.id):
      print("missing pt", mrn) # like 90508
      continue
    data = {
      'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
      'mrn': to_int(pt.ControlNo.text if pt.ControlNo else pt.id.text),
      'sex': pt.Sex.text if pt.Sex else pt.sex.text,
      'name': pt.namewithsuffix.text if pt.namewithsuffix else pt.find('name').text,
      'dob': pt.dob.text,
      'ssn': pt.SSN.text if pt.SSN else '',
      'upPhone': pt.upPhone.text if pt.upPhone else '',
      'GrPhone': pt.GrPhone.text if pt.GrPhone else '',
      'email': pt.Email.text,
      'address': pt.address.text,
      'city': pt.city.text,
      'state': pt.state.text,
      'zipcode': pt.zipcode.text,
      'is_self_pay': pt.isSelfPayPatient.text == 'true',
    }
    # get_billing_claim_json(mrn, claim)
    xml = client.get_insurance_info(mrn, refresh=refresh)
    inses = list(xml.find_all('insurance'))
    if inses:
      ins = inses[0]
      data['insurance'] = ins.find('name').text
      data['member_id'] = ins.find('sbNo').text
      data['group_id'] = ins.find('gpNo').text
      data['insurance_id'] = to_int(ins.find('id').text)
      if len(inses) > 1:
        ins = inses[1]
        data['coinsurance'] = ins.find("name").text
        data['comember_id'] = ins.find('sbNo').text
        data['cogroup_id'] = ins.find('gpNo').text
        data['coinsurance_id'] = to_int(ins.find('id').text)
    pts.append(data)
  for pt in pts:
    upsert(session, Patient, pt, key='mrn')
  session.commit()


def _get_cpts(client, pay_id, claim):
  out = []
  data = client.payment_posting_medicare(pay_id, claim['payment_detail'])
  i = 0
  for s in re.findall(r"'[^']+FeeSchAllowedFee[^']+'", data):
    s = s.lstrip('<?xml+version="1.0"+encoding="ISO-8859-1"?>')
    xml = unquote_plus(s).strip("'")
    # with open(f'tmp_{i}.xml', 'w') as f:
    #   f.write(xml)
    i += 1
    xml = BeautifulSoup(xml, 'xml')
    for cpt in xml.find_all('cpt'):
      out.append({
        'payment_detail': str(claim['payment_detail']),
        'payment': int(pay_id),
        'claim': to_int(claim['claim']),
        'mrn': to_int(claim['mrn']),
        'cpt': cpt.code.text,  # ItemId is an id for the cpt code
        'name': cpt.find('name').text,
        'billed': to_float(cpt.BilledFee.text),
        'paid': to_float(cpt.paid.text),
        'adjustment': to_float(cpt.adjustment.text),
        'date': cpt.SDOS.text,
        # 'payer': pay['PayorName'],
        # 'allowed': cpt.allowed.text,
        # 'deduct': cpt.deduct.text,
        # 'enc': claim.encounterId.text,
      })
  return out


def _set_pay(session: Session, data: list[dict[str, str]], model_class: type[SQLModel]):
  """Delete existing rows for payment, then insert `data` as new rows.

  Used for pay_claim and pay_cpt that are fully refetched per payment.
  Does not commit.
  """
  # rows must match the model column types (int/float/str); see upsert()
  vals = list({row['payment'] for row in data if row['payment'] is not None})
  if vals:
    session.execute(sa.delete(model_class).where(getattr(model_class, 'payment').in_(vals)))
  for row in data:
    session.add(model_class(**row))


def add_payments(session, client, pay_ids) -> list[tuple[str, str]]:
  print('add_payments()')
  pays = []
  payments = []
  cpts = []
  mrn_claims = []
  for pay_id in tqdm(pay_ids):
    pay_id = str(pay_id)
    pay = client.get_pay(pay_id)
    pays.append(pay)

    claims = client.get_claims(pay)
    if not claims:
      pays.append(pay)
    for claim in claims:
      payments.append(claim)
      # if not claim['claim']:
      #   breakpoint()
      mrn_claims.append((claim['mrn'], claim['claim']))
      cpts += _get_cpts(client, pay_id, claim)

  # unneeded: update NULL encounter.claim
  # for e, c in zip(payments.encounter, payments.claim):
  #   res = con.execute('SELECT claim FROM encounter WHERE encounter={e} AND claim IS NOT NULL AND claim != {c}')
  #   assert not res, f"Conflict in enc {e}: old {res}, new {c}"
  #   con.execute(f'UPDATE encounter SET claim={c} WHERE encounter={c}')
  # con.commit()
  for p in pays:
    # model fields are int/float/bool; the scraped values are str
    p['payment'] = int(p['payment'])
    p['paid'] = float(p['paid']) if p['paid'] else None
    p['deleted'] = bool(int(p['deleted'])) if p['deleted'] not in (None, '') else None
    upsert(session, Pay, p, key='payment')
  session.commit()
  _set_pay(session, payments, PayClaim)
  _set_pay(session, cpts, PayCpt)
  session.commit()
  return mrn_claims


def add_claim_cpt(session: Session, client, mrn_claims: list[tuple[str, str]], refresh=False):
  claim_cpts = []
  payments = []
  for mrn, claim in tqdm(mrn_claims):
    # if not claim:
    #   breakpoint()
    data = client.get_billing_claim_json(mrn, claim, refresh=refresh)
    c, p = parse_claim(int(claim), data)
    claim_cpts += c
    payments += p
  # composite PK (claim, cpt)
  for row in claim_cpts:
    upsert(session, ClaimCpt, row, key=('claim', 'cpt'))
  # update payments without claim. this is rare.
  # raw SQL since we're changing the PK.
  q = sa.text("UPDATE pay_claim SET claim = :claim, payment_detail = :payment_detail, adjustment = :adjustment, deduct = :deduct WHERE payment = :payment AND claim IS NULL")
  q_args = [{'claim': r['claim'], 'payment_detail': r['payment_detail'], 'adjustment': r['adjustment'], 'deduct': r['deduct'], 'payment': r['payment']} for r in payments]
  if payments:
    session.execute(q, q_args)
  session.commit()
  # TODO we should rerun this automatically from the report.
  print(f'add_claim_cpt: updated {len(claim_cpts)}')


def add_labs(session: Session, client, date: str):
  """Labs list view (Reviewed tab). One row per lab report. id is the ReportId.

  type is 0 for labs and 1 for imaging.
  """
  from_date = (datetime.strptime(date, '%m/%d/%Y') - timedelta(days=365)).strftime('%m/%d/%Y')
  rows = client.labs(date, date, tab="Reviewed")# + client.labs(from_date, date, tab="Reviewed")
  # TODO set status=1 for all labs with resultdate in the past year
  # rows = client.labs(date)
  for row in rows:
    row['date'] = iso_date(row['date'])
    row['coll_date'] = iso_date(row['coll_date'])
  print(f'add_labs: {len(rows)} labs on {date}')
  for row in rows:
    upsert(session, Lab, row)
  session.commit()


def update_lab_result(session: Session, client, lab_id: int, report_type: int = 0):
  """Set Lab.result from lab_results_json() for each report in the response.

  LabDataDetailJSONArray has one entry per report, including prior results for
  the same lab item on earlier encounters.
  """
  # TODO broken
  if report_type == 0:
    # Lab
    detail = json.loads(client.lab_results_json(lab_id, report_type))
    for lab in detail['LabDataDetailJSONArray']:
      results = [
        {k: res[k] for k in ('itemName', 'value', 'units', 'range', 'flag', 'paramNotes')}
        for res in lab['properties']['property']
        if res['value']
      ]
      # the response also contains prior reports from earlier encounters that are not in the Lab table yet.
      upsert(session, Lab, {
        'id': int(lab['id']),
        'result': json.dumps(results),
        'name': detail['LabDataJSON']['name'],
        'itemid': to_int(detail['LabDataJSON']['itemId']),
        'patientname': detail['PatientDataJSON']['PatientName'].strip(),
        'patient_id': to_int(detail['PatientDataJSON']['Id']),  # patient MRN
        'date': lab['date'],
        'coll_date': lab['collDate'],
        'coll_time': lab['collTime'],
        'encounter_id': to_int(lab['encounterId']),
        'from_lab_id': to_int(lab['fromLabId']),
        'type': to_int(lab['type']),
        'status': to_int(lab['Status']),  # 0 = unreviewed, 1 = reviewed
      })
    print(f'update_lab_result: {len(detail["LabDataDetailJSONArray"])} report(s) for {lab_id}')
  else:
    # Imaging
    assert report_type == 1
    data = json.loads(client.lab_request_json(lab_id))
    results = data["labResults"]
    assert len(results) == 1
    assert results[0]["ReportId"] == int(lab_id), f"{results[0]["ReportId"]} {lab_id}"
    res = results[0]["resultInfo"]["resultParams"]["resultParam"]
    assert len(res) == 1
    notes = res[0]["paramNote"]
    results = [{"notes": "\n".join(n["notes"] for n in notes)}]
    lab = session.get(Lab, lab_id)
    lab.result = json.dumps(results)
  session.commit()


def update_all(session, client: Client):
  # Get data from yesterday, since today might not have full data.
  today = date.today()
  yesterday = today - timedelta(days=1)
  from_date = session.execute(sa.text('SELECT MAX(date) FROM encounter')).scalar() or yesterday.strftime('%Y-%m-%d')
  # use the payments page to update CPTs
  mrn_claims = get_encounters(session, client, from_date, today.strftime('%Y-%m-%d'))

  # update db: if yesterday has no payments yet, try the day before, then two days before
  pay_ids = set()
  for offset in range(1, 4):
    d = (today - timedelta(days=offset)).strftime('%Y-%m-%d')
    payments = BeautifulSoup(client.get_ins_payments(from_date=d, to_date=d), 'xml')
    pay_ids = set(int(pay.paymentId.text) for pay in payments.find_all('payment'))
    if pay_ids:
      break
  if not pay_ids:
    print('no payments in last 3 days')
  else:
    pay_ids = [str(p) for p in range(1, max(pay_ids)+1)]

    q = f'''WITH X(payment) AS (VALUES ({"),(".join(pay_ids)}))
SELECT payment FROM X
WHERE payment NOT IN (SELECT payment FROM pay_claim)
'''
    pay_ids = [row[0] for row in session.execute(sa.text(q))]
    mrn_claims += add_payments(session, client, pay_ids)

  add_patients(session, client)
  add_claim_cpt(session, client, mrn_claims)


def report_encounter(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
  claim_clause = f' AND claim={claim}' if claim else ''

  sql = '''
    SELECT encounter.encounter, encounter.claim, encounter.date, patient.name, encounter.reason,
      encounter.dr, patient.mrn, patient.insurance, insurance.ppo, insurance.party AS p, patient.coinsurance, encounter.visittype,
      encounter.assignee, encounter.task, encounter.notes, encounter.due_date
    FROM encounter
    LEFT JOIN patient USING (mrn)
    LEFT JOIN insurance
    ON TRIM(BOTH '- ' FROM
      CASE
      WHEN TRIM(patient.insurance) LIKE '%Health Care-Brown and Toland'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Care-Brown and Toland'))
      WHEN TRIM(patient.insurance) LIKE '%Health Plan-Brown and Toland'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Plan-Brown and Toland'))
      WHEN TRIM(patient.insurance) LIKE '%Health Plan Brown and Toland'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Plan Brown and Toland'))
      WHEN TRIM(patient.insurance) LIKE '%-Brown and Toland'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('-Brown and Toland'))
      WHEN TRIM(patient.insurance) LIKE '% Brown and Toland'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH(' Brown and Toland'))
      WHEN TRIM(patient.insurance) LIKE '%Health Care'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Care'))
      WHEN TRIM(patient.insurance) LIKE '%Health Plan'
        THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Plan'))
      ELSE TRIM(patient.insurance)
    END
    ) = insurance.insurance
    WHERE encounter.mrn != 9128
    AND encounter.date BETWEEN '{start_date}' AND '{end_date}'
    {claim_clause}
    ORDER BY encounter.claim
  '''.format(start_date=start_date, end_date=end_date, claim_clause=claim_clause)
  # sa.text so pandas uses the compiled-SQL path: a plain driver string makes
  # psycopg2 %-interpolate the statement, which breaks the literal % in LIKE.
  return pd.read_sql(sa.text(sql), con)


def report_claim_pay(con, claim: str = ''):
  """Get billed and paid for each (claim, cpt). Also add claim_balance and deduct (per-claim deductible from pay_claim) columns for the entire claim.

  Payments deleted in ECW (pay.deleted = 1) are ignored, along with their
  pay_claim and pay_cpt rows (a NULL deleted is not deleted).
  """
  con.execute(sa.text('DROP TABLE IF EXISTS paid;'))
  con.execute(sa.text('''
    CREATE TEMPORARY TABLE paid AS
    SELECT pc.claim, pc.cpt, MAX(pc.name) AS name, SUM(pc.paid) AS paid
    FROM pay_cpt pc
    WHERE NOT EXISTS (
      SELECT 1 FROM pay p
      WHERE p.payment = pc.payment AND p.deleted
    )
    GROUP BY pc.claim, pc.cpt;
  '''))
  con.execute(sa.text('CREATE INDEX IF NOT EXISTS tmp_ix_p ON paid(claim, cpt);'))
  con.execute(sa.text('DROP TABLE IF EXISTS deduct;'))
  con.execute(sa.text('''
    CREATE TEMPORARY TABLE deduct AS
    SELECT pc.claim, SUM(pc.deduct) AS deduct
    FROM pay_claim pc
    WHERE NOT EXISTS (
      SELECT 1 FROM pay p
      WHERE p.payment = pc.payment AND p.deleted
    )
    AND pc.deduct > 0
    GROUP BY pc.claim;
  '''))
  con.execute(sa.text('CREATE INDEX IF NOT EXISTS tmp_ix_d ON deduct(claim);'))

  claim_clause = f' AND claim={claim}' if claim else ''

  sql = '''
    WITH C AS (
      SELECT
        COALESCE(claim_cpt.claim, paid.claim) AS claim,
        COALESCE(claim_cpt.cpt, paid.cpt) AS cpt,
        COALESCE(claim_cpt.name, paid.name) AS cpt_name,
        claim_cpt.billed,
        paid.paid,
        deduct.deduct
      FROM claim_cpt
      -- pay_cpt often includes old cpt codes that have been deleted from claim_cpt. It is ok for these to be unpaid.
      LEFT JOIN paid USING (claim, cpt)
      -- note: deduct is per payment_detail, so a claim-level deductible repeated on
      -- multiple details of the same claim will be double-counted by the SUM above
      LEFT JOIN deduct USING (claim)
      WHERE (NOT deleted) AND COALESCE(claim_cpt.cpt, paid.cpt) NOT IN (
        'G0008', 'G0103', 'G0442', 'G0444', 'G0447', 'G2211', 'G8482','G8510', -- sometimes not paid, especially MPMG (capitation)
        'J3301',
        '91312', '91313', '99401', '99406', '99408', '99051', '99072', '93000',
        '46600',  -- anoscopy can be as low as 30
        '1101F','1004F','1101F','1111F','1125F','1126F','1157F','1158F','1159F','1160F','1170F',
        '2000F','2001F','2010F','2022F',
        '3008F','3014F','3015F','3017F','3044F','3051F','3060F','3061F','3066F',
        '3072F','3074F','3075F','3077F','3078F','3079F','3080F','3725F','4010F')
      {claim_clause}
    ),
    D AS (
      SELECT claim, SUM(billed) - (2 * SUM(paid)) AS claim_balance
      FROM C
      GROUP BY claim
    )
    SELECT * FROM C
    LEFT JOIN D USING (claim)
    ORDER BY claim;
  '''.format(claim_clause=claim_clause)
  df = pd.read_sql(sa.text(sql), con)
  con.execute(sa.text('DROP TABLE paid;'))
  con.execute(sa.text('DROP TABLE deduct;'))
  return df


def get_report(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
  """
  Include items that were billed without being paid or paid without being
  billed, but make sure that these are still reported with the correct patient
  information. Note that a naive outer join might add rows without patient
  information.
  Also available: encounter.visittype, SUM(pay_cpt.adjustment) AS adjust
  Materializes the result in the db as the report table.
  """
  # Get encounter and claim info
  encounter_df = report_encounter(con, start_date, end_date, claim)
  encounter_df['claim'] = encounter_df['claim'].astype('Int64')
  # keep ppo integer instead of float (NULLs from unmatched insurance rows would otherwise make it REAL)
  encounter_df['ppo'] = encounter_df['ppo'].astype('Int64')
  C_df = report_claim_pay(con, claim)
  df = pd.merge(encounter_df, C_df, how='left', on='claim')
  df['paid'] = df['paid'].round(2)
  df['claim_balance'] = df['claim_balance'].round(2)
  df['deduct'] = df['deduct'].round(2)

  # Add pt_paid for payment_details without CPT codes.
  # Test per (payment, payment_detail), not per payment: a payment can have some
  # details with CPT rows (credited at CPT level via the paid CTE) and others
  # without (e.g. payment 7948, $100 on claim 11777). NOT EXISTS instead of
  # NOT IN, which returns no rows at all if the subquery contains NULLs.
  # Payments deleted in ECW (pay.deleted = 1) and their pay_claim rows are
  # ignored.
  sql = '''
    SELECT pc.claim, SUM(pc.paid) AS pt_paid FROM pay_claim pc
    WHERE NOT EXISTS (
      SELECT 1 FROM pay_cpt
      WHERE payment = pc.payment AND payment_detail = pc.payment_detail
    )
    AND NOT EXISTS (
      SELECT 1 FROM pay p
      WHERE p.payment = pc.payment AND p.deleted
    )
    AND pc.date > '{start_date}'
    AND pc.paid > 10
    GROUP BY pc.claim
  '''.format(start_date=start_date)
  pt_df = pd.read_sql(sa.text(sql), con)

  df = pd.merge(df, pt_df, how='left', on='claim')

  self_pay = (df.reason == "Immigration") | (df.reason == "immigration") | (df.visittype == "Self Pay")
  valid = (
    # this CPT paid >100 or >50%
    (df.paid > 100) | (df.paid >= (df.billed * 0.5)) |
    # pt paid >50 or >50% balance for this entire claim
    (df.pt_paid > 50) | (df.pt_paid > (df.claim_balance * 0.5)) |
    # small cpt paid >10
    ((df.cpt == '95117') | (df.cpt == 'J3420') & (df.paid > 10)) |
    # imm_admin: paid >18
    (df.cpt.isin(['90471', '90472', '90686']) & (df.paid > 18)) |
    # capitation
    (df.insurance == "MPMG") | (df.insurance == "Imperial Health Holdings Co Mso  Inc. Of") |
    ((df.cpt == "99212") & (df.paid >= 40)) |  # office visit 2
    ((df.cpt == "99213") & (df.paid >= 70)) |  # office visit 3
    ((df.cpt == "90746") & (df.paid >= 70)) |  # hep B
    ((df.cpt == "90472") & (df.paid >= 19.49)) |  # additional immunization admin (Cigna)
    ((df.cpt == "96365") & (df.paid >= 95.5)) |  # THER/PROPH/DIAG IV INF, INIT (Cigna)
    ((df.cpt == "90713") & (df.paid >= 38)) |  # poliovirus
    ((df.cpt == "90656") & (df.paid >= 22)) |  # flu vaccine
    ((df.cpt == "69210") & (df.paid >= 62)) |  # ear wash
    ((df.cpt == "90746") & (df.paid >= 69)) |  # hep b
    # blue pays very little for immunization
    ((df.cpt == '9047') & (df.insurance == "blue of california") & (df.paid >= 10))
  )
  df = df[(df.cpt.isna() & (~self_pay)) | (~valid)]
  df.sort_values(by='billed', inplace=True, ascending=False)
  df.drop_duplicates(subset=['date', 'name', 'claim'], ignore_index=True, inplace=True)
  df.sort_values(by=['date', 'p'], inplace=True)

  # materialize the report as a table in the db
  con.execute(sa.text('DROP TABLE IF EXISTS report'))
  df.to_sql('report', con, index=False)
  con.commit()

  # known_df = pd.read_csv('known_claim.csv')
  # known_claims = set(known_df.claim.tolist())
  # df = df[~df['claim'].isin(known_claims)]

  # with open('known_claim.txt') as f:
  #   known_claims = set(int(line.strip()) for line in f if line.strip())
  # df = pd.merge(df, known_df[known_df['claim']], how='outer', on='claim')
  # df['known'] = df['claim'].isin(known_claims)

  # GET /mobiledoc/jsp/webemr/webpm/claimFollowData.jsp?ClaimNo=47158&assignedToId=9246&startDate=11/11/2024&assignedTo=Eng,Landley&ptId=19996&showRightPanel=1&Type=0&claimScreenUId=1731340365176
  return df.copy()


def report(con, session, client, start_date: str, end_date: str, claim: str = '', refresh: bool = True):
  if refresh:
    df = get_report(con, start_date, end_date, claim)
    mrns = df[df.ppo == 1].mrn.unique().tolist()
    add_patients(session, client, mrns, refresh=refresh)
  df = get_report(con, start_date, end_date, claim)

  # df = df[(df.ppo == 1) & df.claim.notna() & (df.billed > 0)]
  # claims_info(con, df['claim'].tolist(), REPORT_DIR / 'claims_info.txt')

def add_claim(session: Session, client, date: str, refresh: bool = False, date_option: str = '1') -> list[tuple[int, int]]:
  # By default we use claim date = recently created claims.
  xml = client.getClaimsList(date, date_option, refresh=refresh)
  claims = xml.find_all('claim')
  for c in claims:
    assert not c.DueDate.text, f"due date {c}"
    assert not c.AssignedTo.text, f"assignee {c}"
  rows = [{'mrn': to_int(c.PatientAccNo.text), 'claim': to_int(c.ClaimId.text), 'billed': c.amount.text, 'paid': c.payment.text, 'balance': c.balance.text, 'encounter': to_int(c.EncounterId.text)} for c in claims]
  assert len(rows) < 100  # query MAXCOUNT
  for r in rows:
    upsert(session, Encounter, r, key='encounter')
  session.commit()
  if not rows:  # no claims this date; executing with [] raises InvalidRequestError
    return []
  mrn_claims = [(r['mrn'], r['claim']) for r in rows]
  assert all(c != 0 for m, c in mrn_claims)
  add_claim_cpt(session, client, mrn_claims)
  return mrn_claims
  # for c in tqdm(claims):
    # row = {
    #   'encounter': c.EncounterId.text,
    #   'claim': c.ClaimId.text,
    #   'date': c.ServiceDate.text,
    #   'mrn': c.PatientAccNo.text,
    #   'type': c.''.text,
    #   'reason': c.''.text,
    #   'dr': c.''.text,
    #   'visittype': c.visittype.text,
    #   'billed': c.amount.text,
    #   'paid': c.payment.text,
    #   'balance': c.balance.text,
    #   'due_date': c.DueDate.text,
    #   'assignee': c.AssignedTo.text,
    # }
    # CACHE.put('enc_claim', enc, str(claim))
    # rows.append(get_claim_data(claim))
  # return rows


if __name__ == "__main__":
  engine = create_engine(DATABASE_URL)
  session = Session(engine)

  with ESession() as esession:
    client = Client(esession)
    # client = None
    # client.labs_page()
    add_labs(session, client, '10/17/2026')  # list of labs
    # update_lab_result(session, client, 371031, 1)
    # update_lab_result(session, client, 373666)
    # text = client.fetch_patient_note(12556)
    # client.save_patient_note(12556, text + " done")
    # data = client.getClaimsList('2024-12-07', '0')
