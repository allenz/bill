import json
from lxml.etree import ElementTree, fromstring
import pandas as pd


Row = dict[str, float | str]

def _resolve(row: Row, cpt, icds: list[tuple[str, str]]) -> None:
  # cpt is an element
  """Add ICD1, ICD2, etc columns by looking up CPT ids in the icds table."""
  for n in range(1, 5):
    i = cpt.find(f'ICD{n}').text
    if not i:
      row[f'ICD{n}'] = None
      row[f'desc{n}'] = None
      return
    i = int(i)
    if i >= len(icds):
      row[f'ICD{n}'] = i
      row[f'desc{n}'] = 'invalid'
    else:
      row[f'ICD{n}'], row[f'desc{n}'] = icds[i]


def parse_claim(claim: int, data: str) -> tuple[list[Row], list[Row]]:
  data = json.loads(data)

  root = fromstring(data["GET_BALREFADJSICDCPT"].encode('utf8'))
  # with open('tmp.xml', 'wb') as f:
  #   f.write(ElementTree.tostring(root))
  root = root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body/return')
  payments = []
  for p in root.find('Payments/data'):
    row = {
      'payment': p.find('PaymentId').text,
      'postedDate': p.find('Date').text,
      'paid': p.find('Amount').text,
      'payorId': p.find('payorId').text,
      'payorType': p.find('payorType').text,
      'paymentType': p.find('paymentType').text,
      'ERADetail': p.find('ERADetailId').text,
      'paymentDetail': p.find('PmtDetailId').text,
      'claim': p.find('invoiceid').text,
      'adjustment': p.find('adjustment').text,
      'deduct': p.find('deduct').text,
      # missing: service date, payorName, postedBy, encounter, mrn, MsgCode
    }
    payments.append(row)
  # print([c.tag for c in root])
  # Payments, Balances, ClaimAdjustments, status, refunds, CPTS, ICDS, insurances, ErrorCodes, PatientInfo, VoidClaim
  # Payments has payorId, Date, ERADetailId, Amount, payorType, etc.
  # insurances has Id, InsName, SubscriberNo

  icds = [None]
  for code in root.find('ICDS/invoice/ICDCodes'):
    icds.append((code.find("code").text, code.find("name").text))

  claim_cpts = []
  for cpt in root.find('CPTS/invoice/cpt'):
    # also sdos
    # print([c for c in cpt_code])
    row = {
      "claim": claim,
      "cpt": cpt.find("code").text,
      "name": cpt.find("name").text,
      "billed": float(cpt.find('BilledFee').text),
      'mod1': cpt.find('mod1').text,
      'mod2': cpt.find('mod2').text,
      'mod3': cpt.find('mod3').text,
      'mod4': cpt.find('mod4').text,
      "units": int(cpt.find("units").text),
    }
    _resolve(row, cpt, icds)
    claim_cpts.append(row)
  return claim_cpts, payments

# with open('sample_data.json') as f:
#   parse_claim(29, f.read()) # mrn 13975
# return pd.DataFrame(cpt_data)
# GET_CODEDESC, GET_PAYREJSTATUS

# print(df)


def scrape_claims():
  client = Client()
  res = set(con.execute("SELECT mrn, claim FROM encounter"))
  done = CACHE.con.execute("SELECT name FROM cache WHERE method = 'get_billing_claim_json'")
  done = set(tuple(a.split('-')) for (a,) in done)
  for (mrn, claim) in tqdm(res - done):
    client.get_billing_claim_json(mrn, claim)
  con.close()
