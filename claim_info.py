"""Pull info from db needed to call insurance about a claim."""
from datetime import date

import psycopg2

from config import PG_DSN

DATA = """
Hee, June, T	55652
Chiu, Chih He	55654
"""


def claim_info(con, claim: str) -> dict[str, str]:
	"""con is a psycopg2 connection to the billing db; claim is a claim number.

	The claim is passed as a bound parameter (encounter.claim is INTEGER).
	"""
	sql = '''SELECT
		encounter.date, encounter.billed, patient.name, patient.dob, patient.ssn, patient.zipcode AS zip,
		patient.insurance, insurance.phone,
		CASE WHEN party = '1P' THEN 1003187766 ELSE 1609263961 END AS npi,
		CASE WHEN party = '1P' THEN 473725906 ELSE 943168453 END AS tax_id,
		patient.member_id, patient.group_id, patient.coinsurance
	FROM encounter
	LEFT JOIN patient USING (mrn)
	LEFT JOIN insurance
	ON TRIM(BOTH '- ' FROM
		CASE
		WHEN TRIM(patient.insurance) LIKE '%%Health Care-Brown and Toland'
			THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Care-Brown and Toland'))
		WHEN TRIM(patient.insurance) LIKE '%%Brown and Toland'
			THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Brown and Toland'))
		WHEN TRIM(patient.insurance) LIKE '%%Health Care'
			THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Care'))
		WHEN TRIM(patient.insurance) LIKE '%%Health Plan'
			THEN SUBSTR(TRIM(patient.insurance), 1, LENGTH(TRIM(patient.insurance)) - LENGTH('Health Plan'))
		ELSE TRIM(patient.insurance)
	END
	) = insurance.insurance
	WHERE claim = %(claim)s
	'''
	cur = con.cursor()
	cur.execute(sql, {'claim': int(claim)})
	row = cur.fetchone()
	if row is None:
		return {}

	D = {}
	D['DOS'], D['billed'], D['name'], D['dob'], D['ssn'], D['zip'], D['insurance'], D['phone'], D['npi'], D['tax_id'], D['member_id'], D['group_id'], D['coinsurance'] = row
	if isinstance(D['DOS'], date):
		# encounter.date is a PG date column; keep the old ISO text everywhere it is shown
		D['DOS'] = D['DOS'].isoformat()
	if isinstance(D['dob'], date):
		# patient.dob is a PG date column; keep the old ISO text everywhere it is shown
		D['dob'] = D['dob'].isoformat()
	del D['coinsurance']

	# reorder keys
	D2 = {}
	order = ['phone','DOS','billed','member_id','name','dob','npi','tax_id','insurance','group_id','ssn','zip']
	for k in order:
		D2[k] = D[k]
	D = D2
	if not D['ssn']:
		del D['ssn']

	if D['insurance'] == 'Imperial Health Holdings Co Mso  Inc. Of':
		D['insurance_company_address'] = 'PO BOX 60007'
	if D['insurance'] == 'Blue Card Program':
		D['plan_code'] = "I don't have it"
	return D


"""
11/13/24	Chen, Ju	48677					HBV-1st/pickup	Meritain Health	1	3P	
11/14/24	Hoang, Clement	48711					polio 1st/pickup	Aetna	1	3P	
11/14/24	Cai, Yanyi	48718					flu shot	Aetna	1	3P	
"""

def claims_info(con, claims: list[str], out: str = 'claims_info.txt'):
	res = []
	for claim in claims:
		# if  (info['phone'] and info['member_id']):
			# mrn = get_mrn(con, claim)
			# add_patients(session, client, [mrn], refresh=True)
		info = claim_info(con, claim)
		for key, value in info.items():
			res.append(f'{key}: {value}')
		res.append('Notes:\n')

	if len(claims) <= 3:
		print('\n'.join(res))

	with open(out, 'w') as f:
		f.write('\n'.join(res))


if __name__ == "__main__":
	claims = []
	for row in DATA.strip().split('\n'):
		r = row.split('\t')
		claims.append(r[-1])

	con = psycopg2.connect(PG_DSN)
	claims_info(con, claims)
	con.close()
