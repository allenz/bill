# Webapp

app.py
- /ws/report
  - REPORT_WEBSOCKETS (live websocket connections) and REPORT_VIEWERS (list of viewers)
  - JSON messages to every connected tab:
    - {"type": "online", "viewers": ["alice", "alice", "bob"]} on every join/leave
    - {"type": "cell_update", "encounter", "field", "value"}
      after /api/update saves an edit
- /api/claim_info?claim=N
  - JSON from claim_info.claim_info() for one claim number
- /api/lab_result?id=N
  - Lab.result JSON for one lab report id
- GET /lab: templates/lab.html
  - the type column shows "lab" (stored 0) or "im" (stored 1)
  - unreviewed rows (status 0) are bold
  - rows with a non-empty result show a "view" link in the result column
    that pops up the result details (fetches /api/lab_result;
    click again, the x, or Esc closes it)

/report -> report.py
- open ws(s)://host/ws/report and updates the badge on every online message
  - shows Online: (disconnected)
- on cell_update, refresh every input for that encounter+field
  (skips the focused input and inputs that already hold the value)
- clicking a claim number opens a bottom pane with the claim details
  (fetches /api/claim_info; click again, the x, or Esc closes it)

# Data update

## db.py
Only file that touches the database billing.sqlite3.

Write helpers:
- upsert(): DELETE + REPLACE INTO per row. Missing columns are set to NULL.
- true_upsert(): INSERT ... ON CONFLICT DO UPDATE for one row. Only the given columns are written, so other columns (e.g. Lab.result) keep their existing value.

update_all()
- get_encounters(): update **Encounter** for a date range.
  - client.download_claims_overview()
  - client.get_doctors_schedule_list(date range): basic encounter data.
  - client.get_claim(encounter): full claim xml.
  - add_claim(date): calls getClaimsList() to get submitted claims.
- get_ins_payments(): get the latest payment IDs
  - TODO make incremental by saving the previous checked payments.
- SELECT new payments up to the highest payment
- add_payments(pay_ids)
  - client.get_pay(): update **Pay** from getPayment.jsp
  - client.get_claims(): update **PayClaim**
    - getPaymentDetails.jsp for insurance payments, receivePayments.jsp for patient payments
  - `_get_cpts(pay_id, claim)`: update **PayCpt**
    - POST /mobiledoc/jsp/webemr/webpm/paymentPostingMedicare.jsp
  - TODO update encounter.claim from PayClaim.claim?
- add_patients(): update **Patient**
  - SELECT new mrn from encounter
- add_labs(date): update **Lab** from client.labs(date), row by row via true_upsert()
  - one-off, not part of update_all(); called from __main__ with a specific date
  - preserves Lab.result, which the list view does not include
- update_lab_result(lab_id): set **Lab**.result from client.lab_results_json(lab_id)
  - one-off, called from __main__ with a specific lab id
  - the JSON's LabDataDetailJSONArray also contains prior results for the same
    lab item on earlier encounters; every report id it contains is updated if in Lab
- some payments have no PayCpt rows at all (copay, no claim)
- Note: PayClaim has 60 rows where mrn = payorId due to `_get_pt_claims()` 'mrn': pay['payorId']
- Patient payments are often recorded at claim level, not cpt level (no PayCpt row).

## scrape_ecw.py
payment_posting_medicare(payment, paymentDetail)
- paymentDetail is the primary key for caching
- if not cached, we query server
- fill_payment_posting_medicare(payment)
  - get_pay(payment) -> dict pay
    - get_payment(pay) wraps getPayment.jsp: **Pay**
  - get_claims(pay): **Payment**
    - `_get_ins_claims(pay)`
      - payment_details(payment) wraps getPaymentDetails.jsp
    - `_get_pt_claims(pay)`
      - receivePayments_json(payment) wraps receivePayments.jsp: html

download_claims_overview()
- get_lookup_count(): return encounter ids by date range.
- `_get_lookup_batch()`: get claim data for encounter ids and date range.
  - caches enc_claim(encounter) -> claim xml, supporting get_claim().
    - Don't know any direct API to look up this mapping.
  - not directly cached.
  - returns data which can directly update **Encounter** (encounter, claim, paid), not currently used.

## ecw_session.py
Session is persisted in session.json (cookies, JS crypto state, csrf token).
- `Session.__enter__` loads the saved session and checks it with `session_valid()`; a valid session skips login, otherwise `login()` runs. `__exit__` saves the session back to session.json.
- Logout: a logged-out session answers GET index.jsp with a 302 whose Location is an *absolute* `http://` URL to login/newLogin.jsp (plain port 80, which times out from this network). Following that redirect hangs, so `session_valid()` first probes with `allow_redirects=False` and treats a redirect to newLogin.jsp as logged out without following it; `__enter__` then runs `login()`.
- `login()` walks the ECW login steps (RSA key exchange, verifyUname, processLoginRequest). It may demand a captcha (the `is_captcha` flag is printed; the captcha step is commented out and solved manually when needed).

# Data model

## Encounter
- An Encounter has at most one claim.
- A claim has multiple paymentDetails, and a paymentDetail has multiple PayCpt.
- Also a claim has multiple cpts, and a cpt has multiple PayCpt.
- New columns from the ECW doctor schedule API (see encounter.md):
  - appt_start / appt_end: appointment start and end time (e.g. '06:00')
  - status: appointment status (pStatus) FIN/CHK/CANC/Switch/N-S/R-S/N-A
  - is_billable: billableVisitStatus bool (not the `billed` dollar amount)
  - claim_required: claimRequired bool
  - eligibility_status: 1 eligible, 3 ineligible, 5 not verified, 7 self pay
  - updated: timestamp of last write

```sql
CREATE TABLE ClaimCpt (
  claim INTEGER NOT NULL,
  cpt TEXT NOT NULL,
  name TEXT NOT NULL,
  billed NUMERIC NOT NULL,
  mod1 INTEGER,
  mod2 INTEGER,
  mod3 INTEGER,
  mod4 INTEGER,
  icd1 TEXT,
  icd2 TEXT,
  icd3 TEXT,
  icd4 TEXT,
  desc1 TEXT,
  desc2 TEXT,
  desc3 TEXT,
  desc4 TEXT,
  units INTEGER,
  deleted BOOLEAN DEFAULT FALSE
)
CREATE UNIQUE INDEX claim_cpt_ix ON ClaimCpt (claim, cpt);
```

To lookup by claim, go to Claims and enter claim number. This calls getClaimsList() and get_billing_claim_json(). The latter calls billingClaim.jsp and getBillingClaimDetails.jsp. The UI also calls getInsuranceData.jsp (not implemented in client) and claimFollowData().

Encounters missing claims:
```sql
SELECT * FROM Encounter
WHERE COALESCE(claim, '') = ''
AND COALESCE(visittype, '') != 'Self Pay'
AND date >= '2024'
AND mrn != 9129
ORDER BY date
LIMIT 5;
```

Update old claims. This is a one-off since we now call add_claim() daily. 
```py
mrn_claims = []
  for date in tqdm(date_range('2024-12-01', '2025-01-01')):
    mrn_claims += add_claim(con, client, date)
  add_claim_cpt(con, client, mrn_claims)
```

## Pay
- Pay has one row per payment. Row in Billing > Payments.
  - Pay can have any number of PayClaims, possibly for different patients.
  - Can have 0 PayClaims, e.g. pay 19922, an insurance Non PayClaim Data.
  - Multiple PayClaims, e.g. patient payment 16622.
  - Writer: db.py add_payments()
- PayClaim: "Claims Paid" when clicking on a Pay entry.
  - PaymentDetail is a unique key.
  - (pay, claim) is not unique!
    - payment 79 has many rows with claim 36 in the ERA.
- PayCpt: "Post CPT" when clicking on a PayClaim entry.
  - Unclear if (paymentdetail, cpt) is unique.
- Goal: the sum of the paid column reflects the total paid.
  - But Pay.paid ≠ SUM(PayClaim.paid) on 789 payments

```sql
CREATE TABLE IF NOT EXISTS Pay (
  payment INTEGER NOT NULL PRIMARY KEY,
  postedDate TEXT,  -- date we record the payment, different from checkDate
  paid NUMERIC,
  payorId TEXT,
  payorName TEXT,
  payorType TEXT,
  postedBy TEXT,
  ERADetail TEXT,
  paymentType TEXT,
  deleted BOOLEAN,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
```

maybe drop columns:
postedDate TEXT,
payorId TEXT,
payorName TEXT,
payorType TEXT,
postedBy TEXT,
ERADetail TEXT,
paymentType TEXT

```sql
CREATE TABLE IF NOT EXISTS PayClaim (
  paymentDetail TEXT,
  payment INTEGER NOT NULL,  -- not unique!
  claim INTEGER,
  ERADetail TEXT,
  postedDate TEXT,
  paid NUMERIC,  -- amount for the PaymentDetail, not the total PayClaim paid
  payorId TEXT,
  payorName TEXT,
  payorType TEXT,
  postedBy TEXT,
  date TEXT,
  encounter INTEGER,
  mrn INTEGER,
  allowed NUMERIC,
  adjustment NUMERIC,
  deduct NUMERIC,
  MsgCode TEXT,
  paymentType TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_pay ON PayClaim(payment);
```

```sql
CREATE TABLE IF NOT EXISTS PayCpt (
  "paymentDetail" TEXT NOT NULL,
  "mrn"   TEXT,
  "cpt"   TEXT NOT NULL,
  "name"  TEXT NOT NULL,
  "billed" NUMERIC,
  "paid" NUMERIC,
  "adjustment" NUMERIC,
  "date"  TEXT,
  claim INTEGER,
  payment INTEGER,
  "created" TEXT DEFAULT (strftime('%Y-%m-%d %H:%M', 'now', 'localtime'))
);

-- Is this truly unique?
CREATE UNIQUE INDEX payment_cpt ON PayCpt (paymentDetail, cpt);
CREATE INDEX ix_pay_cpt_payment ON PayCpt(payment, cpt);
```

**PayCpt**
CREATE UNIQUE INDEX payment_cpt ON PayCpt (paymentDetail, cpt);
CREATE INDEX PayCpt_ix ON PayCpt (claim, cpt);
CREATE INDEX ix_PayCpt_payment ON PayCpt(payment, cpt);

## Lab
- One row per lab report. id is the ReportId. Writer: db.py add_labs(date).
- Source: client.labs(date) POSTs labs/requestHandler.jsp (JellyBean list view, Reviewed tab) for a single date. One row per (item, patient), so an itemid can appear multiple times.
- name is the lab item name (e.g. "CMP"), not the patient name. Patient comes from Encounter.mrn via encounterId.
- InterfaceStatus e.g. "Received-LabCorp OG", "Manually Reconciled - SimonMed Rad Bi".
- status: 0 for outstanding (not reviewed), 1 for reviewed. Matches the list view tab the report appears under.
- type: 0 for labs, 1 for imaging (Type field from the list view).
- result: non-empty lab results as JSON (itemName, value, units, range, flag, paramNotes), one entry per result.
  - Writer: db.py update_lab_result(lab_id), from client.lab_results_json(lab_id).
  - LabDataDetailJSONArray has one entry per report, including prior results for the same item on earlier encounters.
- More detail per report: client.lab_report(lab_id, enc_id, mrn), client.lab_results_json(lab_id), client.lab_request_json(lab_id).

```sql
CREATE TABLE Lab (
  id TEXT NOT NULL PRIMARY KEY, -- ReportId
  itemid TEXT, -- lab type eg CMP
  encounterId TEXT,
  name TEXT,
  date TEXT, -- order date
  collDate TEXT,
  collTime TEXT,
  ResultDate TEXT,
  fromLabId TEXT,
  InterfaceStatus TEXT,
  result TEXT, -- non-empty lab results from lab_results_json()
  type TEXT, -- 0 for labs, 1 for imaging
  status TEXT -- 0 outstanding, 1 reviewed
);
```
