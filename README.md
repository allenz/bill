# Webapp

app.py
- /login
  - unauthenticated page visits redirect here with the page they came from
    as /login?next=/path?args; a successful login sends them back there
    (only local paths are honored, so a hand-crafted next can't redirect
    off-site), falling back to /report with no next (e.g. a direct visit)
- /ws/report
  - REPORT_WEBSOCKETS (live websocket connections) and REPORT_VIEWERS (list of viewers)
  - JSON messages to every connected tab:
    - {"type": "online", "viewers": ["alice", "alice", "bob"]} on every join/leave
    - {"type": "cell_update", "encounter", "field", "value"}
      after /api/update saves an edit
- /doc -> templates/doc.html, /ws/doc, POST /api/doc {"body": "..."}
  - the shared notepad: one row in the doc table (id = 1) that all logged-in
    users can edit. The page autosaves (debounced, retries on failure) and
    shows the last update age/author; the textarea is locked while the
    browser is offline
  - /ws/doc pushes {"type": "doc_update", "body", "updated_by"} to every
    connected tab after /api/doc saves, so the other open tabs update in
    place (a tab never clobbers text it is currently typing)
  - edits are assumed infrequent and from one user at a time: a save is a
    plain overwrite of the row, stamping updated/updated_by
- /api/claim_info?claim=N
  - JSON from claim_info.claim_info() for one claim number
- /api/lab_result?id=N
  - lab.result JSON for one lab report id
- POST /api/patient_note {"mrn": N}
  - refreshes the yellow sticky note (db.update_patient_note):
    re-fetches it from ECW and returns the new note plus the
    "Sticky updated ..." age/tooltip; the /patient page's refresh button
    updates the sticky and that line in place
- POST /api/patient_note_edit {"mrn": N, "original": "...", "new": "..."}
  - saves the /patient page's in-place sticky edit. original is the note
    the page loaded (a string, possibly empty; a NULL note has no editable
    sticky so the page never sends one); the server checks the sticky
    against ECW (source of truth) and writes to ECW only if it is still
    unchanged (409 otherwise), then re-fetches and stores the note
    (yellow_note, yellow_updated)
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

models.py: definitions for most tables

## db.py
Write helpers:
- upsert(): DELETE + REPLACE INTO per row. Missing columns are set to NULL.
- true_upsert(): sparse upsert of one row by id via a SQLModel Session (session.get + setattr). Only the given columns are written, so other columns (e.g. lab.result) keep their existing value.

update_all()
- process_schedule(): update **encounter** for a date range.
  - client.download_claims_overview()
  - client.get_doctors_schedule_list(date range): basic encounter data.
  - client.get_claim(encounter): full claim xml.
  - add_claim(date): calls getClaimsList() to get submitted claims.
- get_ins_payments(): get the latest payment IDs
  - TODO make incremental by saving the previous checked payments.
- SELECT new payments up to the highest payment
- add_payments(pay_ids)
  - client.get_pay(): update **pay** from getPayment.jsp
  - client.get_claims(): update **pay_claim**
    - getPaymentDetails.jsp for insurance payments, receivePayments.jsp for patient payments
  - `_get_cpts(pay_id, claim)`: update **pay_cpt**
    - POST /mobiledoc/jsp/webemr/webpm/paymentPostingMedicare.jsp
  - TODO update encounter.claim from pay_claim.claim?
- add_patients(): update **patient**
  - SELECT new mrn from encounter
- add_labs(date): update **lab** from client.labs(date), row by row via true_upsert()
  - one-off, not part of update_all(); called from __main__ with a specific date
  - preserves lab.result, which the list view does not include
- update_lab_result(lab_id): set **lab**.result from client.lab_results_json(lab_id)
  - one-off, called from __main__ with a specific lab id
  - the JSON's LabDataDetailJSONArray also contains prior results for the same
    lab item on earlier encounters; every report id it contains is updated if in lab
- some payments have no pay_cpt rows at all (copay, no claim)
- Note: pay_claim has 60 rows where mrn = payor_id due to `_get_pt_claims()` 'mrn': pay['payor_id']
- Patient payments are often recorded at claim level, not cpt level (no pay_cpt row).

unreviewed_labs(date)
- The /lab "To be reviewed" tab refresh; not part of update_all().
  date defaults to today.
- Update **lab** from client.labs() over the year up to date: upserts the
  tab's rows, then fetches missing results per patient via
  update_patient_labs(unreviewed_only=True) (a failed patient is rolled
  back and warned, the rest continue).
- Refreshes the yellow sticky (update_patient_note) for the tab's
  patients whose note was last fetched over a day ago (yellow_updated
  older than 1 day, or never fetched), so /patient and /unreviewed show
  a current note next to the open labs; a failed patient is rolled back
  and warned, the rest continue.
- Labs with a result that are no longer in the tab are marked reviewed
  (status 1). result_date IS NOT NULL keeps out labs whose result has not
  arrived yet: those leave the tab too, but still need review.
- Records the tab's patient order (first-appearance order of each MRN,
  i.e. ECW's display order) on patient.unreviewed_order, which /unreviewed
  sorts by; a patient no longer in the tab (or an empty tab) drops its
  order.

claim_info.py: pull info from db needed to call insurance about a claim

## ecw_client.py
payment_posting_medicare(payment, payment_detail)
- payment_detail is the primary key for caching
- if not cached, we query server
- fill_payment_posting_medicare(payment)
  - get_pay(payment) -> dict pay
    - get_payment(pay) wraps getPayment.jsp: **pay**
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
  - returns data which can directly update **encounter** (encounter, claim, paid), not currently used.

## ecw_session.py
Session is persisted in session.json (cookies, JS crypto state, csrf token).
- `ESession.__enter__` loads the saved session (or logs in if there is none); no up-front validity check. `post()` detects an expired session and calls `login()` on demand, retrying the request once. `__exit__` saves the session back to session.json.
- Expired-session detection: requests go out with `allow_redirects=False`. A logged-out session answers with a 302 whose Location is an *absolute* `http://` URL to login/newLogin.jsp (plain port 80, which hangs from this network if followed); code-protected endpoints instead answer 403 with a 'not authorized' page, and some answer 200 with a 'Sorry session' apology. `_request()` also uses a socket timeout to guard against the WAF accepting but never answering a throttled request.
- `login()` is fully unattended (RSA key exchange, verifyUname, processLoginRequest), so cron jobs can re-login without a human; it may demand a captcha (the `is_captcha` flag is printed; the captcha step is commented out and solved manually when needed).

## Scheduled jobs
User crontab (server time is PT); output goes to /srv/allen/ecw/cron.log.
- `30 2 * * *` update_billing.py: full update_all() plus generate_report()
  over the 30 days up to today. flock -n /tmp/update_billing.lock.
- `0 7-23 * * *` hourly_labs.py: refreshes the To-be-reviewed labs tab
  (db.unreviewed_labs()) every hour, except the 12am-7am quiet window.
  Cron fires on the hour; the job first sleeps a random 1-55 minutes so it
  never hits ECW exactly on the hour. The script itself also refuses to run
  during 12am-7am unless invoked with --force, and
  flock -n /tmp/unreviewed_labs.lock skips an hour if the previous run is
  still going. Usage: `python hourly_labs.py [DATE]`, DATE = MM/DD/YYYY,
  default today (a slim copy of update_billing.py with only unreviewed_labs()).

# Data model

## encounter

Encounters missing claims:
```sql
SELECT * FROM encounter
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

## pay
- pay_claim: "Claims Paid" when clicking on a pay entry.
  - payment_detail is a unique key.
  - (pay, claim) is not unique!
    - payment 79 has many rows with claim 36 in the ERA.
- pay_cpt: "Post CPT" when clicking on a pay_claim entry.
  - (payment_detail, cpt) is not unique: a detail can bill the same cpt on
    multiple lines (e.g. 90471 IMMUNIZATION ADMIN once per vaccine). Rows
    carry a surrogate id and are deleted/re-inserted per payment.
- Goal: the sum of the paid column reflects the total paid.
  - But pay.paid ≠ SUM(pay_claim.paid) on 789 payments

maybe drop pay columns:
posted_date TEXT,
payor_id TEXT,
payor_name TEXT,
payor_type TEXT,
posted_by TEXT,
era_detail TEXT,
payment_type TEXT
