"""Main SQL code for updating the billing database.

generate_report.py makes a billing report.

Note: psycopg2 cursor.execute() returns None
"""

from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta, timezone
from time import sleep
import json
from sqlmodel import Session, create_engine, SQLModel
import sqlalchemy as sa
import re
from urllib.parse import unquote_plus
from tqdm import tqdm
from typing import TypeVar

from ecw_session import ESession
from config import DATABASE_URL, parse_date, warn
from ecw_client import Client, get_claim, get_claim_data, to_int, to_float
from parse_claim import parse_claim
from save_block import save_blocks
from check_schedule import check_schedule
from models import ClaimCpt, Encounter, Lab, Patient, Pay, PayClaim, PayCpt

T = TypeVar("T", bound=SQLModel)


def upsert(session: Session, model_class: type[T], data: dict, key: str | tuple[str, ...] = 'id') -> tuple[T, bool]:
  """Sparse upsert of one object by `key` (a primary key column or tuple of
  them for a composite PK), returning the row and whether it was newly
  created (False for a pre-existing row).

  Only writes the columns the data actually carries; existing rows keep any
  columns the data does not set. Used for partial sources.

  Values must match the model column types: SQLAlchemy 2.0's batched
  INSERT...RETURNING matches rows back to parameter sets by exact value, so a
  str sent to an INTEGER column comes back as an int and the lookup fails
  with InvalidRequestError ("Can't match sentinel values").
  """
  # Fetch existing or initialize a blank instance
  pk = data.get(key) if isinstance(key, str) else tuple(data[k] for k in key)
  obj = session.get(model_class, pk)
  created = obj is None
  if created:
    obj = model_class()
  for key, value in data.items():
    setattr(obj, key, value)
  session.add(obj)
  return obj, created


def date_range(from_date: str, to_date: str) -> list[str]:
  # Inclusive of from_date, exclusive of to_date (like range()).
  date = datetime.strptime(from_date, '%Y-%m-%d')
  dates = []
  while date < datetime.strptime(to_date, '%Y-%m-%d'):
    dates.append(date)
    date += timedelta(days=1)
  return [d.strftime('%Y-%m-%d') for d in dates]


def add_claim(session: Session, client, date: str, refresh: bool = False, date_option: str = '1') -> list[tuple[int, int]]:
  # By default we use claim date = recently created claims.
  xml = client.getClaimsList(date, date_option, refresh=refresh)
  claims = xml.find_all('claim')
  for c in claims:
    assert not c.DueDate.text, f"due date {c}"
    assert not c.AssignedTo.text, f"assignee {c}"
  rows = [{'mrn': to_int(c.PatientAccNo.text), 'claim': to_int(c.ClaimId.text), 'billed': to_float(c.amount.text), 'paid': to_float(c.payment.text), 'balance': to_float(c.balance.text), 'id': to_int(c.EncounterId.text)} for c in claims]
  assert len(rows) < 100  # query MAXCOUNT
  for r in rows:
    upsert(session, Encounter, r)
  session.commit()
  if not rows:  # no claims this date; executing with [] raises InvalidRequestError
    return []
  mrn_claims = [(r['mrn'], r['claim']) for r in rows]
  assert all(c != 0 for m, c in mrn_claims)
  add_claim_cpt(session, client, mrn_claims)
  return mrn_claims
  # for c in tqdm(claims):
    # row = {
    #   'id': c.EncounterId.text,
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


# Right now we only update encounter/claim from the schedule list. Clearly we need another way...
# ecw_client.py download_claims_overview()
#   get_lookup_count(): POST getLookupCount.jsp
#     ecw_session.py make_claim_form()

def process_schedule(session, client, from_date: str, to_date: str) -> list[tuple[str, str]]:
  print('process_schedule()')
  # run _get_lookup_batch which writes enc_claim
  # download_claims_overview(client, from_date=from_date, to_date=to_date)

  mrn_claims = []
  rows = []
  dates = date_range(from_date, to_date)

  for date in tqdm(dates):
    schedule = client.get_doctors_schedule_list(date)
    for enc in schedule.find_all('encounter'):
      data = {
        'id': enc.encounterId.text,
        'date': enc.encDate.text,
        'mrn': to_int(enc.patientId.text),
        'visittype': enc.visitType.text,
        'reason': enc.reason.text,
        # 'dr': '' if enc.doctorName.text == "LING, JIE" else enc.doctorName.text,
        'updated': datetime.now(timezone.utc),
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
    row['id'] = int(row['id'])
    if 'claim' in row:
      row['claim'] = int(row['claim'])
    upsert(session, Encounter, row)
  session.commit()

  for date in dates:
    mrn_claims += add_claim(session, client, date)
  return mrn_claims


def ingest_encounters(session, client, date: str) -> None:
  """Process 1-week Resource Scheduling into the encounter and block tables."""
  entries = json.loads(client.get_encounters_json(date))['encounters']
  encs, blocks = [], []
  for entry in entries:
      check_schedule(entry, date)
      (encs if 'encounterId' in entry else blocks).append(entry)
  now = datetime.now(timezone.utc)
  for e in encs:
      appt = e['apptCard']
      upsert(session, Encounter, {
          'id': to_int(e['encounterId']),
          'date': e['start'][:10],
          'mrn': to_int(e['patId']),
          'visittype': appt['visitType'],
          'reason': e['reason'],
          'dr': e['doctorName'],
          # 1 current, 2 other, 5 virtual, 7 ePrescription (same codes as lab.encounter_type)
          'type': to_int(e.get('encType')),
          'appt_start': e['start'][11:16],
          'appt_end': e['end'][11:16],
          'status': e['pStatus'],
          'is_billable': to_int(e['billableVisitStatus']),
          'claim_required': to_int(e['claimRequired']),
          'eligibility_status': to_int(e['eligibilityStatus']),
          'general_notes': e['generalNotes'] or None,
          'new_pt': e['newPt'] == '1',
          'updated': now,
      })
  session.commit()
  if blocks:
      save_blocks(blocks, session)


def add_patients(session, client, mrns: list[str] | None = None, refresh: bool = False):
  if not mrns:
    result = session.execute(sa.text('SELECT mrn FROM encounter WHERE mrn NOT IN (SELECT mrn FROM patient)'))
    mrns = [p for (p,) in result]
  pts = []
  for mrn in tqdm(set(mrns)):
    pt = client.search_patient(mrn, refresh=refresh)
    if not (pt.ControlNo or pt.id):
      print("missing pt", mrn) # like 90508
      continue
    name = pt.namewithsuffix.text if pt.namewithsuffix else pt.find('name').text
    # skipping fields
    # GivenToColl, AlertStatus, isPartiallyMerged, RegistryEnabled, VoiceEnabled: all 0
    # pcpName, UserType, LastApptDate, empPhone, suffix, merge flags
    # WebEnabled
    data = {
      'updated': datetime.now(timezone.utc),
      'mrn': to_int(pt.ControlNo.text if pt.ControlNo else pt.id.text),
      'sex': pt.Sex.text if pt.Sex else pt.sex.text,
      'name': name,
      'previous_name': pt.PreviousName.text if pt.PreviousName and pt.PreviousName.text else None,
      'active': pt.Status.text == '0' if pt.Status and pt.Status.text else None,
      'deceased': pt.Deceased.text == '1' if pt.Deceased and pt.Deceased.text else None,
      'dob': parse_date(pt.dob.text),
      'ssn': pt.SSN.text if pt.SSN else '',
      'up_phone': pt.upPhone.text if pt.upPhone else '',
      'gr_phone': pt.GrPhone.text if pt.GrPhone else '',
      'email': pt.Email.text,
      'address': pt.address.text,
      'address2': pt.address2.text if pt.address2 and pt.address2.text else None,
      'city': pt.city.text,
      'state': pt.state.text,
      'zipcode': pt.zipcode.text,
      'is_self_pay': pt.isSelfPayPatient.text == 'true',
      'cell_phone': pt.mobileno.text if pt.mobileno and pt.mobileno.text
                    and pt.mobileno.text != (pt.upPhone.text if pt.upPhone else '') else None,
      'preferred_name': pt.formatedPrefName.text if pt.formatedPrefName and pt.formatedPrefName.text
                        else pt.preferredName.text if pt.preferredName and pt.preferredName.text else None,
      'external_mrn': pt.MedicalRecNo.text if pt.MedicalRecNo and pt.MedicalRecNo.text else None,
    }
    # get_billing_claim_json(mrn, claim)
    # has plan names, subscriber relationship, COB, etc
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
  new = []
  for pt in pts:
    _, created = upsert(session, Patient, pt, key='mrn')
    if created:
      new.append(pt['mrn'])
  session.commit()
  # Fetch new patients' yellow stickies right away, so their /patient page
  # shows the sticky without waiting for a manual refresh or the backfill.
  for mrn in new:
    try:
      update_patient_note(session, client, mrn)
    except Exception as e:
      session.rollback()
      print(f'add_patients: sticky fetch failed mrn={mrn}: {e!r}')
    sleep(1)


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
        'payment_detail': claim['payment_detail'],
        'payment': int(pay_id),
        'claim': to_int(claim['claim']),
        'mrn': to_int(claim['mrn']),
        'cpt': cpt.code.text,  # ItemId is an id for the cpt code
        'name': cpt.find('name').text,
        'billed': to_float(cpt.BilledFee.text),
        'paid': to_float(cpt.paid.text),
        'adjustment': to_float(cpt.adjustment.text),
        'date': parse_date(cpt.SDOS.text),
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
  #   res = con.execute('SELECT claim FROM encounter WHERE id={e} AND claim IS NOT NULL AND claim != {c}')
  #   assert not res, f"Conflict in enc {e}: old {res}, new {c}"
  #   con.execute(f'UPDATE encounter SET claim={c} WHERE id={c}')
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


def patient_encounters(session: Session, client, mrn: int) -> list[int]:
  """Insert encounters for `mrn` that are missing from the encounter table.

  Source is get_pt_encounters() (getPtEncounters.jsp), which unlike the
  schedule feeds also includes virtual (type 5) and other non-office
  encounters and ePrescription transactions (type 7). Only rows missing
  from the table are inserted; existing rows are left untouched, so fields
  written by the schedule feeds (dr, appt times, pStatus) are preserved.
  """
  xml = client.get_pt_encounters(mrn)
  have = {row[0] for row in session.execute(
    sa.text('SELECT id FROM encounter WHERE mrn = :mrn'), {'mrn': mrn})}
  now = datetime.now(timezone.utc)
  added = []
  for row in xml.find_all('row'):
    enc_el = row.find('encounterID')
    if not enc_el:
      continue
    enc = to_int(enc_el.text)
    if enc is None or enc in have:
      continue
    def field(tag: str):
      el = row.find(tag)
      return el.text if el and el.text else None
    upsert(session, Encounter, {
      'id': enc,
      'mrn': mrn,
      'type': to_int(field('encType')),
      'visittype': field('visitType'),
      'reason': field('reason'),
      # same code space as schedule-feed pStatus, plus PEN
      'status': field('status'),
      'date': field('date'),
      'updated': now,
    })
    have.add(enc)
    added.append(enc)
  if added:
    print(f'patient_encounters: mrn {mrn}, added {len(added)} encounter(s)')
  # stamp when this patient's encounters were last fetched via get_pt_encounters
  upsert(session, Patient, {'mrn': mrn, 'encounter_updated': now}, key='mrn')
  session.commit()
  return added


def update_patient_note(session: Session, client, mrn: int) -> str:
  """Set Patient.yellow_note from fetch_patient_note() (the yellow sticky),
  stamping yellow_updated (and the row's updated). An empty sticky stores
  '' (yellow_note is never NULL)."""
  note = client.fetch_patient_note(mrn)
  upsert(session, Patient, {
    'mrn': mrn,
    'yellow_note': note,
    'yellow_updated': datetime.now(timezone.utc),
  }, key='mrn')
  session.commit()
  return note


def _rcp_fields(html: str) -> dict[str, str]:
  """Extract labeled fields from printChartOptions RCP HTML.

  The fields are label/value rows in the encounter table
  (td.rightPaneHeading), present for both telephone encounters
  (Message/Refills, Answered By, Date/Time) and office visits
  (Provider, Answered By, Date, Time, Assigned To, Reason, Message/Refills).
  The tel table shows 'Message' for a normal call and 'Refills' (the
  refilled medications) instead when the call resulted in refills.
  Returns {label: value} for rows with non-empty values.
  """
  soup = BeautifulSoup(html, 'html.parser')
  fields = {}
  for label in soup.find_all('td', class_='rightPaneHeading'):
    name = label.get_text(strip=True)
    value = label.find_next_sibling('td')
    text = ' '.join(value.get_text().split()) if value else ''
    if text:
      fields[name] = text
  return fields


def teleweb_details(session: Session, client, encounter: int, enc_type: int = 2):
  """Set Encounter.message, Encounter.answered_by, and Encounter.refills
  from the 'Message', 'Answered By', and 'Refills' fields of the
  encounter's right chart panel
  (client.print_chart_options_html, Enc tab of the patient modal).

  enc_type is the ECW code for printChartOptions: 1 office visit, 2 tel,
  7 ePrescription. The encounter row must already exist.
  """
  enc = session.get(Encounter, encounter)
  assert enc, f"encounter {encounter} not in encounter table"
  html = client.print_chart_options_html(encounter, enc_type=enc_type)
  fields = _rcp_fields(html)
  enc.message = fields.get('Message')
  enc.answered_by = fields.get('Answered By')
  enc.refills = fields.get('Refills') or fields.get('Refill')
  session.commit()


def progress_notes(session: Session, client, encounter: int, refresh: bool = False) -> str:
  """Set Encounter.note to the dashboard progress note, the SOAP envelope XML
  of client.progress_notes_raw(mrn, encounter) (demographics + Subjective /
  Objective / Assessment / Plan / Billing sections; see the client
  docstring), and stamp note_updated.

  The _raw suffix makes @cache return the unparsed string, so the note is
  stored exactly as fetched. A refresh re-fetches and re-caches first. The
  encounter row must already exist: the MRN comes from it.
  """
  enc = session.get(Encounter, encounter)
  assert enc, f"encounter {encounter} not in encounter table"
  enc.note = client.progress_notes_raw(enc.mrn, encounter, refresh=refresh)
  enc.note_updated = datetime.now(timezone.utc)
  session.commit()
  return enc.note


def unreviewed_labs(session: Session, client, date: str):
  """Labs list view (To be reviewed tab).

  Returns unreviewed labs in the year up to date. Runs update_lab_result() for
  each unreviewed lab to fill in its result. Marks everything else in that
  range as reviewed (status 1).
  """
  year_ago = datetime.strptime(date, '%m/%d/%Y') - timedelta(days=365)
  rows = client.labs(year_ago.strftime('%m/%d/%Y'), date, tab="To be reviewed")
  for row in rows:
    upsert(session, Lab, row)
  session.commit()
  # fetch result details for the unreviewed labs (type 0 = lab, 1 = imaging).
  # Committing the upserts above keeps them safe if a fetch below rolls back.
  # A failing fetch (e.g. a malformed imaging report) skips just that lab: it
  # keeps status 0, so it is retried by the next daily run and by
  # backfill_lab_results.py.
  for row in rows:
    if not row['id']:
      continue
    try:
      update_lab_result(session, client, int(row['id']), int(row['type'] or 0))
    except Exception as e:
      session.rollback()
      warn(f'unreviewed_labs: lab {row["id"]} (type {row["type"]}) failed: {e!r}')
  # labs with a result date that are not in the tab no longer need review.
  # result_date IS NOT NULL keeps out labs whose result has not been
  # received yet: they are not in the tab either, but they still need review.
  stmt = sa.update(Lab).values(status=1).where(Lab.status == 0, Lab.result_date.isnot(None))
  ids = [row['id'] for row in rows if row['id']]
  if ids:
    stmt = stmt.where(Lab.id.not_in(ids))
  res = session.execute(stmt)
  print(f'unreviewed_labs: {len(rows)} labs on {date}, {res.rowcount} marked reviewed')
  session.commit()


def add_labs(session: Session, client, date: str, backfill: bool = True):
  """Labs list view (Reviewed tab). One row per lab report. id is the ReportId.

  type is 0 for labs and 1 for imaging.
  """
  from_date = (datetime.strptime(date, '%m/%d/%Y') - timedelta(days=365)).strftime('%m/%d/%Y')
  rows = client.labs(date, date, tab="Reviewed")# + client.labs(from_date, date, tab="Reviewed")
  # rows = client.labs(date)
  print(f'add_labs: {len(rows)} labs on {date}')
  for row in rows:
    upsert(session, Lab, row)
  session.commit()
  if backfill:
    have = set()
    encs = {row['encounter_id'] for row in rows if row['encounter_id']}
    if encs:
      have = {r[0] for r in session.execute(
        sa.text('SELECT id FROM encounter WHERE id = ANY(:ids)'),
        {'ids': list(encs)})}
    missing = [row for row in rows if row['encounter_id'] and row['encounter_id'] not in have]
    for row in missing:
      warn(f"lab {date} missing mrn={row['mrn']} enc={row['encounter_id']}")
    for mrn in {row['mrn'] for row in missing if row['mrn']}:
      patient_encounters(session, client, int(mrn))


def add_patient_labs(session: Session, client, mrn: int | str):
  """Upserts the past year of labs (one year up to today) for the patient."""
  today = date.today()
  year_ago = today - timedelta(days=365)
  rows = client.labs(year_ago.strftime('%m/%d/%Y'), today.strftime('%m/%d/%Y'), tab = "By patient", patient=str(mrn))
  print(f'add_patient_labs {mrn}: {len(rows)} labs')
  for row in rows:
    upsert(session, Lab, row)
  session.commit()


def add_telweb_encounters(session: Session, client, date: str, date_filter_days: int = 1):
  """Telephone/Web encounters for `date` (All tab) from the JellyBean T list.

  These (type 2) are separate from the normal schedule list.
  Use date_filter_days=7 to get one week up to and including `date`.
  """
  rows = client.telweb_encounters(date, date_filter_days=date_filter_days)
  print(f'add_telweb_encounters: {len(rows)} encounters on {date}')
  now = datetime.now(timezone.utc)
  for e in rows:
    _, created = upsert(session, Encounter, {
      'id': e['encounter'],
      'date': parse_date(e['datetime'][:10]),
      'mrn': e['mrn'],
      'type': e['type'],
      'reason': e['reason'],
      'dr': e['dr'],
      # 24h, like the schedule feeds
      'appt_start': datetime.strptime(e['datetime'][11:], '%I:%M %p').strftime('%H:%M'),
      'updated': now,
    })
    if created:  # only new encounters need their message fetched
      teleweb_details(session, client, e['encounter'], enc_type=e['type'])
  session.commit()


def update_lab_result(session: Session, client, lab_id: int, report_type: int = 0, fresh: bool = False):
  """Set Lab.result from lab_results_json() for each report in the response.

  LabDataDetailJSONArray has one entry per report, including prior results for
  the same lab item on earlier encounters.
  fresh bypasses the cache read (refresh=True): the app's lazy per-view fetch
  must always see the interface's current state, since a result fetched
  earlier while unavailable would otherwise be cached as "no result" forever.
  """
  if report_type == 0:  # Lab
    detail = json.loads(client.lab_results_json(lab_id, report_type, refresh=fresh))
    if detail.get('status') == 'failed' or 'LabDataDetailJSONArray' not in detail:
      warn(f'update_lab_result: {lab_id} failed: {detail.get("reason") or detail}')
      return
    for lab in detail['LabDataDetailJSONArray']:
      # property is a single dict, not a list, when the lab has one result
      props = (lab.get('properties') or {}).get('property') or []
      if isinstance(props, dict):
        props = [props]
      results = [
        {k: res.get(k) for k in ('itemName', 'value', 'units', 'range', 'flag', 'paramNotes')}
        for res in props
        # value may be '' for notes-only results (e.g. O&P), so keep those too
        if isinstance(res, dict) and (res.get('value') or res.get('paramNotes'))
      ]
      upsert(session, Lab, {
        'id': int(lab['id']),
        'result': json.dumps(results),
        'name': detail['LabDataJSON']['name'],
        'itemid': to_int(detail['LabDataJSON']['itemId']),
        'patientname': detail['PatientDataJSON']['PatientName'].strip(),
        'mrn': to_int(detail['PatientDataJSON']['Id']),  # patient MRN
        'date': parse_date(lab['date']),
        'coll_date': parse_date(lab['collDate']),
        'coll_time': lab['collTime'],
        'encounter_id': to_int(lab['encounterId']),
        'from_lab_id': to_int(lab['fromLabId']),
        'type': to_int(lab['type']),
        'status': to_int(lab['Status']),  # 0 = unreviewed, 1 = reviewed
      })
    # print(f'update_lab_result: {len(detail["LabDataDetailJSONArray"])} report(s) for {lab_id}')
  else:  # Imaging
    assert report_type == 1
    data = json.loads(client.lab_request_json(lab_id, refresh=fresh))
    results = data["labResults"]
    assert len(results) == 1
    assert results[0]["ReportId"] == int(lab_id), f"{results[0]['ReportId']} {lab_id}"
    res = results[0]["resultInfo"]["resultParams"]["resultParam"]
    assert len(res) == 1
    notes = res[0]["paramNote"]
    results = [{"notes": "\n".join(n["notes"] for n in notes)}]
    lab = session.get(Lab, lab_id)
    lab.result = json.dumps(results)
  session.commit()


def update_all(session, client: Client):
  # run start: encounter rows upserted below are stamped updated=now, so
  # 'updated >= run_start' selects the rows this run touched
  run_start = datetime.now(timezone.utc)
  # Get data from yesterday, since today might not have full data.
  today = date.today()
  yesterday = today - timedelta(days=1)
  from_date = (session.execute(sa.text('SELECT MAX(date) FROM encounter')).scalar()
               or yesterday).isoformat()
  # use the payments page to update CPTs
  mrn_claims = process_schedule(session, client, from_date, today.strftime('%Y-%m-%d'))

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

  # telephone/web encounters for yesterday; the schedule feeds omit them.
  # Before add_patients() so any new MRNs get patient rows.
  add_telweb_encounters(session, client, yesterday.strftime('%m/%d/%Y'))

  # Resource Scheduling to get tomorrow's appointments
  ingest_encounters(session, client, today.strftime('%Y-%m-%d'))

  add_patients(session, client)
  add_claim_cpt(session, client, mrn_claims)

  # Fetch the dashboard progress note for office visit encounters this run
  # touched that never had one. The selection is the backfill's (type 1,
  # note_updated IS NULL) restricted to rows this run stamped, and the
  # response cache makes already-fetched notes free, so a truly new encounter
  # costs one API request. A failure is left note_updated NULL, so the next
  # run retries (and backfill_progress_notes.py picks the rest up).
  for (enc, mrn) in session.execute(sa.text(
      'SELECT id, mrn FROM encounter '
      'WHERE type = 1 AND note_updated IS NULL AND updated >= :run_start '
      'ORDER BY date DESC, id DESC'), {'run_start': run_start}):
    try:
      progress_notes(session, client, enc)
    except Exception as e:
      session.rollback()
      warn(f'update_all: progress_notes for enc={enc} (mrn={mrn}) failed: {e!r}')

  add_labs(session, client, yesterday.strftime('%m/%d/%Y'))
  # unreviewed labs from the To be reviewed tab
  unreviewed_labs(session, client, today.strftime('%m/%d/%Y'))


if __name__ == "__main__":
  engine = create_engine(DATABASE_URL)
  session = Session(engine)

  with ESession() as esession:
    client = Client(esession)
    # client = None
    # client.labs_page()
    # add_labs(session, client, '10/17/2026')  # list of labs
    add_patient_labs(session, client, 22545)
    # update_lab_result(session, client, 371031, report_type=1)
    # text = client.fetch_patient_note(12556)
    # client.save_patient_note(12556, text + " done")
    # data = client.getClaimsList('2024-12-07', '0')
