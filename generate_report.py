import pandas as pd
import sqlalchemy as sa


def report_encounter(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
  claim_clause = f' AND claim={claim}' if claim else ''

  sql = '''
    SELECT encounter.id AS encounter, encounter.claim, encounter.date, patient.name, encounter.reason,
      encounter.dr, mrn, patient.insurance, insurance.ppo, insurance.party AS p, patient.coinsurance, encounter.visittype,
      encounter.assignee, encounter.task, encounter.notes, encounter.due_date
    FROM encounter
    -- mrn is the USING-merged column: patient.mrn on a match, encounter.mrn
    -- otherwise, so it is never NULL (the report table stores it as INTEGER)
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
    AND (encounter.type IS NULL OR encounter.type != 2) -- exclude reminders
    -- 'Reminder' and 'C reminder', incl. the new-format 'Chinese reminder (C reminder)' /
    -- 'Reminder (Reminder)'; NULL visittype is common on old rows and must not be excluded
    AND (encounter.visittype IS NULL OR encounter.visittype NOT ILIKE '%reminder%')
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


def generate_report(con, start_date: str, end_date: str, claim: str = '') -> pd.DataFrame:
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
  # money columns are PG numeric -> Decimal; coerce to float for pandas math
  for col in ('billed', 'paid', 'claim_balance', 'deduct'):
    C_df[col] = C_df[col].astype(float)
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
  pt_df['pt_paid'] = pt_df['pt_paid'].astype(float)

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
  # to_sql maps pandas int64/Int64 to BIGINT and float64 to DOUBLE PRECISION;
  # pin the int columns to 4-byte INTEGER (plenty for these ids) and the money
  # columns to numeric(12,2) for exact-decimal storage
  df.to_sql('report', con, index=False, dtype={
    'encounter': sa.Integer, 'claim': sa.Integer, 'mrn': sa.Integer, 'ppo': sa.Integer,
    'date': sa.Date, 'due_date': sa.Date,
    'billed': sa.Numeric(12, 2), 'paid': sa.Numeric(12, 2), 'deduct': sa.Numeric(12, 2),
    'claim_balance': sa.Numeric(12, 2), 'pt_paid': sa.Numeric(12, 2),
  })
  con.commit()

  # known_df = pd.read_csv('known_claim.csv')
  # known_claims = set(known_df.claim.tolist())
  # df = df[~df['claim'].isin(known_claims)]

  # with open('known_claim.txt') as f:
  #   known_claims = set(int(line.strip()) for line in f if line.strip())
  # df = pd.merge(df, known_df[known_df['claim']], how='outer', on='claim')
  # df['known'] = df['claim'].isin(known_claims)

  # GET /mobiledoc/jsp/webemr/webpm/claimFollowData.jsp?ClaimNo=47158&assignedToId=9246&startDate=11/11/2024&assignedTo=Eng,Landley&ptId=19996&showRightPanel=1&Type=0&claimScreenUId=1731340365176
  return df


  # df = df[(df.ppo == 1) & df.claim.notna() & (df.billed > 0)]
  # claims_info(con, df['claim'].tolist(), REPORT_DIR / 'claims_info.txt')
