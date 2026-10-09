# Has SQL code for the billing database. No other files should have billing SQL.
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import logging
import pandas as pd
from pathlib import Path
import sqlite3
import json
import os
import py7zr
from sqlmodel import Session, create_engine
import re
import requests
from urllib.parse import unquote_plus
from tqdm import tqdm
import xlsxwriter
# from msoffcrypto.format.ooxml import OOXMLFile

from ecw_session import ESession
from config import DIR, DB_PATH
from scrape_ecw import Client, CACHE, clean_interface_status, get_claim, get_claim_data, download_claims_overview, KNOWN_MISSING_PT, to_int
from claim_info import claim_info
from parse_claim import parse_claim
from save_block import save_block

REPORT_DIR = Path('/srv/allen/ecw')


def clear(con, table: str, index: str, vals: str):
  con.execute(f"DELETE FROM {table} WHERE {index} IN ({','.join(set(vals))})")
  con.commit()


def upsert(con, data: list[dict[str, str]], table: str, index='', delay=0):
  if index:
    data = list(data)
    clear(con, table, index, [row[index] for row in data])
  for row in tqdm(data, delay=delay):
    upsert_one(con, row, table)


def upsert_one(con, row: dict[str, str], table: str):
  if table == 'PayClaim':
    assert 'created' not in row
    row['created'] = datetime.now().strftime("%Y-%m-%d %H:%M")
  # Missing columns get replaced with NULLs
  q = f"REPLACE INTO {table} ({','.join(row)}) VALUES ({','.join(['?']*len(row))})"
  con.execute(q, tuple(row.values()))
  con.commit()


def true_upsert(con, table: str, data: dict, save_empty: bool = True):
  """Insert or update a single row, touching only the columns in data.

  Unlike upsert_one() (REPLACE INTO), columns not in data keep their existing
  value (e.g. Lab.result, set by update_lab_result()).

  save_empty: save None/"" values in data
  """
  keys = [k for k, v in data.items() if save_empty or (v is not None and v != "")]
  if not keys:
    return
  q = (f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))}) "
       f"ON CONFLICT DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in keys)}")
  con.execute(q, [data[k] for k in keys])
  con.commit()


def iso_date(s: str) -> str:
  """Convert MM/DD/YYYY to YYYY-MM-DD. Empty and unparseable values pass through."""
  if not s:
    return s
  try:
    return datetime.strptime(s, '%m/%d/%Y').strftime('%Y-%m-%d')
  except ValueError:
    return s


def date_range(from_date: str, to_date: str) -> list[str]:
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

def get_encounters(con, client, from_date: str, to_date: str) -> list[tuple[str, str]]:
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
        'mrn': enc.patientId.text,
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
  upsert(con, rows, 'encounter')

  for date in dates:
    mrn_claims += add_claim(con, client, date)
  return mrn_claims


def add_patients(con, client, mrns: list[str] | None = None, refresh: bool = False):
  # con.execute('''CREATE TABLE IF NOT EXISTS patient (mrn TEXT NOT NULL PRIMARY KEY, name TEXT, dob TEXT, sex TEXT, self_pay TEXT)''')
  if not mrns:
    result = con.execute('SELECT mrn FROM Encounter WHERE mrn NOT IN (SELECT mrn FROM Patient)')
    mrns = [p for (p,) in result]
  # result = con.execute('SELECT mrn FROM patient WHERE insurance IS NULL')
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
      'mrn': pt.ControlNo.text if pt.ControlNo else pt.id.text,
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
      'isSelfPayPatient': pt.isSelfPayPatient.text,
    }
    # get_billing_claim_json(mrn, claim)
    xml = client.get_insurance_info(mrn, refresh=refresh)
    inses = list(xml.find_all('insurance'))
    if inses:
      ins = inses[0]
      data['insurance'] = ins.find('name').text
      data['member_id'] = ins.find('sbNo').text
      data['group_id'] = ins.find('gpNo').text
      data['insurance_id'] = ins.find('id').text
      if len(inses) > 1:
        ins = inses[1]
        data['coinsurance'] = ins.find("name").text
        data['comember_id'] = ins.find('sbNo').text
        data['cogroup_id'] = ins.find('gpNo').text
        data['coinsurance_id'] = ins.find('id').text
    pts.append(data)
  upsert(con, pts, 'Patient')


def _get_cpts(client, pay_id, claim):
  out = []
  data = client.payment_posting_medicare(pay_id, claim['paymentDetail'])
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
        'paymentDetail': claim['paymentDetail'],
        'payment': pay_id,
        'claim': claim['claim'],
        'mrn': claim['mrn'],
        'cpt': cpt.code.text,  # ItemId is an id for the cpt code
        'name': cpt.find('name').text,
        'billed': cpt.BilledFee.text,
        'paid': cpt.paid.text,
        'adjustment': cpt.adjustment.text,
        'date': cpt.SDOS.text,
        # 'payer': pay['PayorName'],
        # 'allowed': cpt.allowed.text,
        # 'deduct': cpt.deduct.text,
        # 'enc': claim.encounterId.text,
      })
  return out


def add_payments(con, client, pay_ids) -> list[tuple[str, str]]:
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

  # unneeded: update NULL Encounter.claim
  # for e, c in zip(payments.encounter, payments.claim):
  #   res = con.execute('SELECT claim FROM Encounter WHERE encounter={e} AND claim IS NOT NULL AND claim != {c}')
  #   assert not res, f"Conflict in enc {e}: old {res}, new {c}"
  #   con.execute(f'UPDATE encounter SET claim={c} WHERE encounter={c}')
  # con.commit()
  upsert(con, pays, 'Pay', 'payment')
  upsert(con, payments, 'PayClaim', 'payment')
  upsert(con, cpts, 'PayCpt', 'payment')
  return mrn_claims


def add_claim_cpt(con, client, mrn_claims: list[tuple[str, str]], refresh=False):
  claim_cpts = []
  payments = []
  for mrn, claim in tqdm(mrn_claims):
    # if not claim:
    #   breakpoint()
    data = client.get_billing_claim_json(mrn, claim, refresh=refresh)
    c, p = parse_claim(int(claim), data)
    claim_cpts += c
    payments += p
  upsert(con, claim_cpts, 'ClaimCpt')
  # TODO we should rerun this automatically from the report.
  print(f'add_claim_cpt: updated {len(claim_cpts)}')

  # update payments without claim. this is rare.
  q = "UPDATE PayClaim SET claim = ?, paymentDetail = ?, adjustment = ?, deduct = ? WHERE claim IS NULL AND payment = ?"
  rows = [(row['claim'], row['paymentDetail'], row['adjustment'], row['deduct'], row['payment']) for row in payments]
  con.executemany(q, rows)
  con.commit()


def add_labs(con, client, date: str):
  """Labs list view (Reviewed tab). One row per lab report. id is the ReportId.

  type is 0 for labs and 1 for imaging.
  """
  from_date = (datetime.strptime(date, '%m/%d/%Y') - timedelta(days=365)).strftime('%m/%d/%Y')
  rows = client.labs(date, date, tab="Reviewed")# + client.labs(from_date, date, tab="Reviewed")
  # TODO set status=1 for all labs with resultdate in the past year
  # rows = client.labs(date)
  for row in rows:
    row['date'] = iso_date(row['date'])
    row['collDate'] = iso_date(row['collDate'])
  print(f'add_labs: {len(rows)} labs on {date}')
  for row in rows:
    true_upsert(con, 'Lab', row)


def update_lab_result(con, client, lab_id: int, report_type: int = 0):
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
      # true upsert: the response also contains prior reports from earlier
      # encounters that are not in the Lab table yet. save_empty keeps empty
      # response fields from wiping values the list view already saved.
      true_upsert(con, 'Lab', {
        'id': int(lab['id']),
        'result': json.dumps(results),
        'name': detail['LabDataJSON']['name'],
        'itemid': to_int(detail['LabDataJSON']['itemId']),
        'patientname': detail['PatientDataJSON']['PatientName'].strip(),
        'patientId': detail['PatientDataJSON']['Id'],
        'date': lab['date'],
        'collDate': lab['collDate'],
        'collTime': lab['collTime'],
        'encounterId': to_int(lab['encounterId']),
        'fromLabId': to_int(lab['fromLabId']),
        'type': to_int(lab['type']),
        'status': to_int(lab['Status']),  # 0 = unreviewed, 1 = reviewed
      }, save_empty=False)
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
    cur = con.execute('UPDATE Lab SET result = ? WHERE id = ?', (json.dumps(results), lab_id))
  con.commit()


def update_all(con, client: Client):
  today = date.today().strftime('%Y-%m-%d')
  tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
  from_date = con.execute('SELECT MAX(date) FROM Encounter').fetchone()[0] or today
  # use the payments page to update CPTs
  mrn_claims = get_encounters(con, client, from_date, tomorrow)

  # update db: if today has no payments yet, try yesterday, then the day before
  pay_ids = set()
  for offset in range(3):
    d = (date.today() - timedelta(days=offset)).strftime('%Y-%m-%d')
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
WHERE payment NOT IN (SELECT payment FROM PayClaim)
'''
    pay_ids = [row[0] for row in con.execute(q)]
    mrn_claims += add_payments(con, client, pay_ids)

  add_patients(con, client)
  add_claim_cpt(con, client, mrn_claims)


def report_encounter(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
  claim_clause = f' AND claim={claim}' if claim else ''

  sql = '''
    SELECT Encounter.encounter, Encounter.claim, Encounter.date, Patient.name, Encounter.reason,
      Encounter.dr, Patient.mrn, Patient.insurance, Insurance.ppo, Insurance.party AS P, Patient.coinsurance, Encounter.visittype,
      Encounter.assignee, Encounter.task, Encounter.notes, Encounter.due_date
    FROM Encounter
    LEFT JOIN Patient USING (mrn)
    LEFT JOIN Insurance
    ON TRIM(
      CASE
      WHEN TRIM(Patient.insurance) LIKE '%Health Care-Brown and Toland'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Care-Brown and Toland'))
      WHEN TRIM(Patient.insurance) LIKE '%Health Plan-Brown and Toland'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Plan-Brown and Toland'))
      WHEN TRIM(Patient.insurance) LIKE '%Health Plan Brown and Toland'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Plan Brown and Toland'))
      WHEN TRIM(Patient.insurance) LIKE '%-Brown and Toland'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('-Brown and Toland'))
      WHEN TRIM(Patient.insurance) LIKE '% Brown and Toland'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH(' Brown and Toland'))
      WHEN TRIM(Patient.insurance) LIKE '%Health Care'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Care'))
      WHEN TRIM(Patient.insurance) LIKE '%Health Plan'
        THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Plan'))
      ELSE TRIM(Patient.insurance)
    END, "- "
    ) = Insurance.insurance
    WHERE Encounter.mrn != "9128"
    AND Encounter.date BETWEEN '{start_date}' AND '{end_date}'
    {claim_clause}
    ORDER BY Encounter.claim;
  '''.format(start_date=start_date, end_date=end_date, claim_clause=claim_clause)
  return pd.read_sql(sql, con)


def report_claim_pay(con, claim: str = ''):
  """Get billed and paid for each (claim, cpt). Also add claim_balance and deduct (per-claim deductible from PayClaim) columns for the entire claim.

  Payments deleted in ECW (Pay.deleted = 1) are ignored, along with their
  PayClaim and PayCpt rows (a NULL deleted is not deleted).
  """
  # indexed tmp table needed to avoid full scans in SQLite
  q = '''
    DROP TABLE IF EXISTS Paid;
    CREATE TEMPORARY TABLE Paid AS
    SELECT pc.claim, pc.cpt, MAX(pc.name) AS name, SUM(pc.paid) AS paid
    FROM PayCpt pc
    WHERE NOT EXISTS (
      SELECT 1 FROM Pay p
      WHERE p.payment = pc.payment AND p.deleted = 1
    )
    GROUP BY pc.claim, pc.cpt;
    CREATE INDEX IF NOT EXISTS tmp_ix_p ON Paid(claim, cpt);
    DROP TABLE IF EXISTS Deduct;
    CREATE TEMPORARY TABLE Deduct AS
    SELECT pc.claim, SUM(pc.deduct) AS deduct
    FROM PayClaim pc
    WHERE NOT EXISTS (
      SELECT 1 FROM Pay p
      WHERE p.payment = pc.payment AND p.deleted = 1
    )
    AND pc.deduct > 0
    GROUP BY pc.claim;
    CREATE INDEX IF NOT EXISTS tmp_ix_d ON Deduct(claim);
  '''
  con.executescript(q)

  claim_clause = f' AND claim={claim}' if claim else ''

  sql = '''
    WITH C AS (
      SELECT
        COALESCE(ClaimCpt.claim, Paid.claim) AS claim,
        COALESCE(ClaimCpt.cpt, Paid.cpt) AS cpt,
        COALESCE(ClaimCpt.name, Paid.name) AS cpt_name,
        ClaimCpt.billed,
        Paid.paid,
        Deduct.deduct
      FROM ClaimCpt
      -- PayCpt often includes old cpt codes that have been deleted from ClaimCpt. It is ok for these to be unpaid.
      LEFT JOIN Paid USING (claim, cpt)
      -- note: deduct is per paymentDetail, so a claim-level deductible repeated on
      -- multiple details of the same claim will be double-counted by the SUM above
      LEFT JOIN Deduct USING (claim)
      WHERE (NOT deleted) AND COALESCE(ClaimCpt.cpt, Paid.cpt) NOT IN (
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
  df = pd.read_sql(sql, con)
  con.execute('DROP TABLE Paid;')
  con.execute('DROP TABLE Deduct;')
  return df


def get_report(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
  """
  Include items that were billed without being paid or paid without being
  billed, but make sure that these are still reported with the correct Patient
  information. Note that a naive outer join might add rows without Patient
  information.
  Also available: Encounter.visittype, SUM(PayCpt.adjustment) AS adjust
  Materializes the result in the db as the Report table.
  """
  # Get encounter and claim info
  encounter_df = report_encounter(con, start_date, end_date, claim)
  encounter_df['claim'] = encounter_df['claim'].astype('Int64')
  # keep ppo integer instead of float (NULLs from unmatched Insurance rows would otherwise make it REAL)
  encounter_df['ppo'] = encounter_df['ppo'].astype('Int64')
  C_df = report_claim_pay(con, claim)
  df = pd.merge(encounter_df, C_df, how='left', on='claim')
  df['paid'] = df['paid'].round(2)
  df['claim_balance'] = df['claim_balance'].round(2)
  df['deduct'] = df['deduct'].round(2)

  # Add pt_paid for paymentDetails without CPT codes.
  # Test per (payment, paymentDetail), not per payment: a payment can have some
  # details with CPT rows (credited at CPT level via the Paid CTE) and others
  # without (e.g. payment 7948, $100 on claim 11777). NOT EXISTS instead of
  # NOT IN, which returns no rows at all if the subquery contains NULLs.
  # Payments deleted in ECW (Pay.deleted = 1) and their PayClaim rows are
  # ignored.
  sql = '''
    SELECT pc.claim, SUM(pc.paid) AS pt_paid FROM PayClaim pc
    WHERE NOT EXISTS (
      SELECT 1 FROM PayCpt
      WHERE payment = pc.payment AND paymentDetail = pc.paymentDetail
    )
    AND NOT EXISTS (
      SELECT 1 FROM Pay p
      WHERE p.payment = pc.payment AND p.deleted = 1
    )
    AND pc.date > '{start_date}'
    AND pc.paid > 10
    GROUP BY pc.claim
  '''.format(start_date=start_date)
  pt_df = pd.read_sql(sql, con)

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
  df.sort_values(by=['date', 'P'], inplace=True)

  # materialize the report as a table in the db
  con.execute('DROP TABLE IF EXISTS Report')
  df.to_sql('Report', con, index=False)
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


def make_7z(files: list[str], archive=REPORT_DIR / 'tmp.7z'):
    with py7zr.SevenZipFile(archive, 'w', password='PR15mbsFrEhZcirQ') as archive:
        for file in files:
            archive.write(file, arcname=os.path.basename(file))


def report(con, client, start_date: str, end_date: str, claim: str = '', refresh: bool = True):
  if refresh:
    df = get_report(con, start_date, end_date, claim)
    mrns = df[df.ppo == 1].mrn.unique().tolist()
    add_patients(con, client, mrns, refresh=refresh)
  df = get_report(con, start_date, end_date, claim)
  # to_xlsx(df)

  # df.to_csv(REPORT_DIR / 'unpaid.csv')

  # df = df[(df.ppo == 1) & df.claim.notna() & (df.billed > 0)]
  # claims_info(con, df['claim'].tolist(), REPORT_DIR / 'claims_info.txt')

  if False:
    GURL = 'https://api.github.com/gists/cdbbacd6c0978e2c0b844813763d20c5'
    GEAD = {'Authorization': 'token GH_TOKEN'}
    make_7z([REPORT_DIR / 'unpaid.xlsx', REPORT_DIR / 'claim_info.txt'])
    with open(REPORT_DIR / 'tmp.7z', 'rb') as f:
      url = "https://litterbox.catbox.moe/resources/internals/api.php"
      r = requests.post(url, data={'reqtype': 'fileupload', 'time': '72h'}, files={'fileToUpload': f})
      # r = requests.post('https://file.io/?expires=3d', files={'file': f})  # doesn't work
    if r.status_code == 200:
      link = r.text
      print(f'{link=}')
      data = {"files": {"tmp.txt": {"content": link}}}
      r = requests.patch(GURL, headers=GEAD, data=json.dumps(data))
      print(f'Patch {r.status_code}')
    else:
      print(f'Upload failed {r.status_code}')


def to_xlsx(df):
  if False:
    fields = ['date', 'name', 'claim', 'mrn', 'cpt', 'cpt_name', 'billed', 'paid', 'deduct', 'pt_paid', 'reason', 'insurance', 'ppo', 'P', 'coinsurance']
  else:
    fields = ['date', 'name', 'claim', 'cpt', 'cpt_name', 'billed', 'paid', 'deduct', 'reason', 'insurance', 'ppo', 'P', 'coinsurance']
  df = df[fields].copy()

  df['claim'] = df.claim.astype(object).fillna('').astype(str)
  # fillna('') is invalid on nullable Int64 columns
  for col in df.columns:
    if df[col].dtype == 'Int64':
      df[col] = df[col].astype(object)
  df = df.fillna('')
  path = REPORT_DIR / 'unpaid.xlsx'
  with xlsxwriter.Workbook(path) as wb:
    gen_fmt = wb.add_format({'font_size': 12})
    bold_fmt = wb.add_format({'bold': True, 'font_size': 12})
    date_fmt = wb.add_format({'num_format': 'm/d/yy', 'font_size': 12})
    num_fmt = wb.add_format({'num_format': '#,###', 'font_size': 12})
    raw_fmt = wb.add_format({'num_format': '@', 'font_size': 12})
    ws = wb.add_worksheet()
    ws.write_row(0,0, df.columns, bold_fmt)
    for i, col in enumerate(df.columns):
      data = df[col]
      fmt = gen_fmt
      width = 15
      if col == 'date':
        fmt = date_fmt
        width = 8
        data = pd.to_datetime(data)
      elif col == 'name':
        width = 20
      elif col == 'cpt' or col == 'claim':
        width = 6
      elif col == 'visittype':
        width = 9
      elif col == 'dr':
        width = 5
      elif col == 'P':
        width = 2
      elif col == 'cpt_name':
        fmt = raw_fmt
        width = 38
      elif col in ['billed', 'paid', 'deduct', 'adjust', 'pt_paid']:
        fmt = num_fmt
        width = 7
      elif col in ['name', 'reason', 'insurance']:
        width = 30
      ws.write_column(1, i, data)
      ws.set_column(i, i, width, fmt)
  # with path.open('rb') as f, (REPORT_DIR / 'unpaid_enc.xlsx').open('wb') as o:
  #   OOXMLFile(f).encrypt('bluefirefly', o)
  print(REPORT_DIR)

def query(con):
  with open("medicare_schedule.sql") as f:
    q = f.read()
  data = list(con.execute(q))
  df = pd.DataFrame(data, columns=["cpt","name","amount","last_paid","count"])
  df.to_csv(DIR / "medicare_schedule.csv", index=False)


def add_claim(con, client, date: str, refresh: bool = False) -> list[tuple[str, str]]:
  xml = client.getClaimsList(date, '0', refresh=refresh)
  q = "UPDATE encounter SET mrn = ?, claim = ?, billed = ?, paid = ?, balance = ? WHERE encounter = ?"
  claims = xml.find_all('claim')
  for c in claims:
    assert not c.DueDate.text, f"due date {c}"
    assert not c.AssignedTo.text, f"assignee {c}"
  rows = [(c.PatientAccNo.text, c.ClaimId.text, c.amount.text, c.payment.text, c.balance.text, c.EncounterId.text) for c in claims]
  assert len(rows) < 100  # query MAXCOUNT
  con.executemany(q, rows)
  con.commit()
  mrn_claims = [(mrn, claim) for (mrn, claim, *_) in rows]
  assert all(c != 0 for m, c in mrn_claims)
  add_claim_cpt(con, client, mrn_claims)
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
  con = sqlite3.connect(DB_PATH)
  # engine = create_engine(f"sqlite:///{DB_PATH}")
  # with Session(engine) as s

  with ESession() as esession:
    client = Client(esession)
    # client = None
    # client.labs_page()
    add_labs(con, client, '10/17/2026')  # list of labs
    # update_lab_result(con, client, 371031, 1)
    # update_lab_result(con, client, 373666)
    # text = client.fetch_patient_note(12556)
    # client.save_patient_note(12556, text + " done")
    # data = client.getClaimsList('2024-12-07', '0')
