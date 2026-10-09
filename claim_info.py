import sqlite3
from pathlib import Path

# DB_PATH is defined here (instead of importing scrape_ecw) so this module
# can be imported by the web app without pulling in the ECW cache/dict files.
# from db import get_mrn, add_patients

DB_PATH = Path('/srv/allen/ecw/billing.sqlite3')

DATA = """
Hee, June, T	55652
Chiu, Chih He	55654
"""


def claim_info(con, claim: str) -> dict[str, str]:
	sql = '''SELECT
		encounter.date, encounter.billed, Patient.name, Patient.dob, Patient.ssn, Patient.zipcode AS zip,
		Patient.insurance, Insurance.phone,
		CASE WHEN party = '1P' THEN 1003187766 ELSE 1609263961 END AS npi,
		CASE WHEN party = '1P' THEN 473725906 ELSE 943168453 END AS tax_id,
		Patient.member_id, Patient.group_id, Patient.coinsurance
	FROM encounter
	LEFT JOIN Patient USING (mrn)
	LEFT JOIN Insurance
	ON TRIM(
		CASE
		WHEN TRIM(Patient.insurance) LIKE '%Health Care-Brown and Toland'
			THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Care-Brown and Toland'))
		WHEN TRIM(Patient.insurance) LIKE '%Brown and Toland'
			THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Brown and Toland'))
		WHEN TRIM(Patient.insurance) LIKE '%Health Care'
			THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Care'))
		WHEN TRIM(Patient.insurance) LIKE '%Health Plan'
			THEN SUBSTR(TRIM(Patient.insurance), 1, LENGTH(TRIM(Patient.insurance)) - LENGTH('Health Plan'))
		ELSE TRIM(Patient.insurance)
	END, "- "
	) = Insurance.insurance
	WHERE claim = {claim};
	'''.format(claim=claim)

	rows = list(con.execute(sql))
	if not rows:
		return {}

	D = {}
	D['DOS'], D['billed'], D['name'], D['dob'], D['ssn'], D['zip'], D['insurance'], D['phone'], D['npi'], D['tax_id'], D['member_id'], D['group_id'], D['coinsurance'] = rows[0]
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


# client = Client()

# claims = [47989,47986,47948,47969,47951,47953,47918]


"""
11/13/24	Chen, Ju	48677					HBV-1st/pickup	Meritain Health	1	3P	
11/14/24	Hoang, Clement	48711					polio 1st/pickup	Aetna	1	3P	
11/14/24	Cai, Yanyi	48718					flu shot	Aetna	1	3P	
"""

# TODO due date, assigned to e.g. 


# TODO update patient info before phone call?

def claims_info(con, claims: list[str], out: str = 'claims_info.txt'):
	res = []
	for claim in claims:
		# if  (info['phone'] and info['member_id']):
			# mrn = get_mrn(con, claim)
			# add_patients(con, client, [mrn], refresh=True)
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

	con = sqlite3.connect(DB_PATH)
	claims_info(con, claims)
