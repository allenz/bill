"""Download patient data from ECW."""
import re
from html import unescape
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from tqdm import tqdm
from urllib.parse import unquote_plus, quote
import json
from lxml.etree import fromstring

from ecw_session import ESession, get_csrf, make_claim_form
from config import parse_date
from store import cache, DIR, CACHE
from lab_post import lab_post, LAB_SUFFIXES, clean_interface_status

# note claimstatus can also be EncMissingClaims
# BalanceCondition defaults to &gt;
CLAIM_CONFIG = '<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><m:NOOP xmlns:m="NOOP"><lookup xsi:type="xsd:string"><EpisodesWithoutClaimsOption xsi:type="xsd:string">false</EpisodesWithoutClaimsOption><isMasterEpisodeSelected xsi:type="xsd:string">false</isMasterEpisodeSelected><ProviderIdList xsi:type="xsd:string">0</ProviderIdList><ClaimFilters xsi:type="xsd:string">31</ClaimFilters><AssignedTo xsi:type="xsd:string"></AssignedTo><AssignedToId xsi:type="xsd:int">0</AssignedToId><ClaimType xsi:type="xsd:string">-1</ClaimType><FromDate xsi:type="xsd:string">XDATE</FromDate><ToDate xsi:type="xsd:string">XDATE</ToDate><DateOption xsi:type="xsd:int">XOPTION</DateOption><pos xsi:type="xsd:string"></pos><isNewBuild xsi:type="xsd:string">yes</isNewBuild><DepartmentId xsi:type="xsd:string">0</DepartmentId><ClaimStatus xsi:type="xsd:string">AllClaims</ClaimStatus><RejStatus xsi:type="xsd:string"></RejStatus><StatusIndex xsi:type="xsd:int">0</StatusIndex><PatientId xsi:type="xsd:int">0</PatientId><InsGrp xsi:type="xsd:string"></InsGrp><InsuranceId xsi:type="xsd:int">0</InsuranceId><ExcludeFromCollection xsi:type="xsd:string">1</ExcludeFromCollection><SelfPay xsi:type="xsd:int">0</SelfPay><InsAddInsGroupId xsi:type="xsd:string"></InsAddInsGroupId><counter xsi:type="xsd:int">1</counter><MaxCount xsi:type="xsd:int">100</MaxCount><InvId xsi:type="xsd:string"></InvId><PrescriptionNumber xsi:type="xsd:string"></PrescriptionNumber><BalanceCondition xsi:type="xsd:string"></BalanceCondition><balance xsi:type="xsd:string">0.0</balance><CondAndOr xsi:type="xsd:string"></CondAndOr><Balance2 xsi:type="xsd:string"></Balance2><CondCompare2 xsi:type="xsd:string"></CondCompare2><PayorId xsi:type="xsd:string"></PayorId><ZeroChargeClaims xsi:type="xsd:int">1</ZeroChargeClaims><userid xsi:type="xsd:int">0</userid><DoNotRunQuery xsi:type="xsd:int">1</DoNotRunQuery><AdditionalCond2 xsi:type="xsd:int">0</AdditionalCond2><InsId2 xsi:type="xsd:string">0</InsId2><ProviderType xsi:type="xsd:int">0</ProviderType><EmployerFilterSel xsi:type="xsd:int">0</EmployerFilterSel></lookup></m:NOOP></m:NOOP></Body></S:Envelope>'
CLAIM_CONFIG = quote(CLAIM_CONFIG).replace('/', '%2F')
CLAIM_CONFIG = 'SortBy=Service%20Date&FormData=' + CLAIM_CONFIG


def to_int(v):
  """Cast a scraped field to int for INT columns. None/'' (empty XML
  elements) pass through and are stored as NULL."""
  return None if v in (None, '') else int(v)


def to_float(v):
  """Cast a scraped field to float for NUMERIC columns. None/'' pass through
  as NULL."""
  return None if v in (None, '') else float(v)


def download_claims_overview(client, status: str = "EncClaims", from_date: str = '2024-03-01', to_date: str = '2024-04-01'):
  """Main way to update billing info. No CPT-level data."""
  date = datetime.strptime(from_date, '%Y-%m-%d')
  while date < datetime.strptime(to_date, '%Y-%m-%d'):
    date_s = date.strftime('%Y-%m-%d')
    count = client.get_lookup_count(status, date_s, refresh=True)
    encs = count.find('EncIds').text.strip('|').split('|')
    client._get_lookup_batch([e for e in encs if e], date_s, date_s)
    date += timedelta(days=1)

def get_claim_data(claim) -> dict[str, str]:
  return {
    # NetAdj is always empty
    'encounter': claim.EncounterId.text,
    'claim': claim.ClaimId.text,
    'paid': claim.NetPayment.text,  # payment includes adjustment.
    'billed': claim.amount.text,
    'balance': claim.balance.text,
  }

class Client:
  def __init__(self, session: ESession, skip=False):
    self.session = session

  def post(self, *args, **kwargs):
    return self.session.post(*args, **kwargs)

  @cache
  def search_patient(self, mrn: str | int) -> str:
    """Query for a patient and return the full response html."""
    data = {
      'counter': '1',
      'AccountNo': str(mrn),
      'SearchBy': 'AccountNo',
      'enc': '0',
      'AddlSearchBy': '',
      'AddlSearchVal': '',
      'ShowLastApptDate': '1',  # needed to show some patients
      'StatusSearch': 'All',
      'MAXCOUNT': '18',
      'limitstart': '0',
      'limitrange': '18',
    }
    r = self.post('/mobiledoc/jsp/catalog/xml/getPatients.jsp', data)
    assert r.text, r.text
    assert "Sorry session" not in r.text, r.text
    return r.text

  @cache
  def get_insurance_info(self, mrn: str | int) -> str:
    return self.post(f'/mobiledoc/jsp/catalog/xml/getInsuranceInfo.jsp?patientId={mrn}&isPtDemo=true').text

  @cache
  def getClaimsList(self, date: str, date_option: str) -> str:
    # Use option 1 for claim date or 0 for service date.
    date_option = str(date_option)
    data = CLAIM_CONFIG.replace('XDATE', date).replace('XOPTION', date_option)
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getClaimsList.jsp', data).text

  @cache
  def get_doctors_schedule_list(self, date: str) -> str:
    """Practice > Office Visits. Can be logged, can include vbpd."""
    # Fields: patientId, encounterId, time, arrivedTime, depTime, sex, dob, age.text.rstrip(' Y')
    data = f"eDate={date}&doctorId=0&sortBy=time&facilityId=0&apptTime=0&checkinstatus=0&FacilityGrpId=0&maxCount=100&nCounter=0&DeptId=0&fromWeb=yes&fromAfterCare=officeVisit&tabId=3&toDate=&selectedChkShowASCvisits=false"
    return self.post("/mobiledoc/jsp/catalog/xml/getDoctorsScheduleList.jsp", data).text

  def get_encounters_json(self, date: str) -> str:
    """Resource Scheduling for Sunday through Saturday."""
    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    data = f"duration=15&dayView=7&providers=122&facilities=0&startDate={date}&endDate={end_date}&weekDay=1&doNotGetRecFacility=0&noWHoursForProv=0&deptId=0&userName=lingj&loadClipboard=1&loadTasks=0&moduleName=ResourceSchedule"
    # getDoctorsScheduleList.jsp (XML, Office Visits) answers this body with a literal `null`; the
    # Resource Scheduling page actually POSTs it to getEncountersJson.jsp, which returns the JSON.
    return self.post("/mobiledoc/jsp/webemr/scheduling/getEncountersJson.jsp", data).text

  def fetch_patient_note(self, mrn: int) -> str:
    """Yellow sticky. Used by db.update_patient_note (Patient.yellow_note)."""
    url = f"/mobiledoc/emr/patientDashboard/fetchPatientNote?fetchSecureNote=false&patientId={mrn}"
    xml = fromstring(self.post(url, get=True).content)
    notes = xml.xpath("//row/PtNotes/text()")
    # resultset is empty (no row) for patients with no sticky
    return notes[0] if notes else ''

  def save_patient_note(self, mrn: int, text: str) -> str:
    import xml.sax.saxutils

    url = f"/mobiledoc/jsp/dashboard/SaveStickyNotes.jsp"
    text = xml.sax.saxutils.escape(text)
    xml = f'<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><item xsi:type="xsd:string"><Notes xsi:type="xsd:string">{text}</Notes></item></m:NOOP></Body></S:Envelope>'
    data = {"patientId": mrn, "FormData": xml}
    return self.post(url, data=data).text

  def _get_assessment(self, encounter: int) -> str:
    """Part of encounter."""
    url = f"/mobiledoc/jsp/catalog/xml/getAssessment.jsp?Id={encounter}"
    return self.post(url, get=True).text

  def _top_panel(self, mrn: int, encounter: int) -> str:
    """Top panel notes (unused) loaded in progress notes. Large xml with patientobj=... line, xml-escaped json."""
    url = f"/mobiledoc/jsp/webemr/toppanel/topPanel.jsp?context=progressnotes&patientId={mrn}&encounterId={encounter}"
    return self.post(url, get=True).text

  def _patient_hub(self, mrn: int, encounter: int) -> str:
    """Called from an encounter. Returns picPath etc."""
    url = f"/mobiledoc/jsp/webemr/toppanel/patientHub/fetchPatientHub.jsp?pid={mrn}&encounterId={encounter}"
    return self.post(url).text

  def _img(self, mrn: int) -> str:
    """Get patient image path. Not used."""
    url = f"/mobiledoc/jsp/webemr/toppanel/getPatientPicImgPath.jsp?patientId={mrn}&picFileName={mrn}.jpg"
    return self.post(url, get=True).text

  @cache
  def progress_notes_raw(self, mrn: int, encounter: int) -> str:
    """Progress Notes (Physician's Dashboard) note data as the SOAP envelope
    XML, decoded from the ~200KB dashboard.jsp page. Everything else on that
    page is static scaffolding: the only per-patient bits outside the envelope
    are the patientId/encounterId echoed in a few init calls. The envelope's
    <return> has ~105 children: demographics (patient, DOB, phone, address,
    MrnNo), SectionTitle, and the clinical sections - Subjective (hpi,
    CurrentMeds, PastHistory, allergies, ros), Objective (vitals,
    examination), Assessment (ICDs), Plan (treatment notes per ICD,
    procedures, FollowUp), Billing Information. style=Bulleted is the
    display style. Returns the raw XML string; the _raw suffix makes @cache
    return it unparsed (no BeautifulSoup). The envelope is a JS string in the
    page, so decode html entities then JS escapes (\\n, \\" and \\/ which
    also hits <\\/).
    """
    url = (f'/mobiledoc/jsp/webemr/progressnotes/physiciansdashboard/dashboard.jsp'
           f'?isRoute=true&encounterId={encounter}&patientId={mrn}'
           f'&style=Bulleted&redirect=1&loaderId=patient_hub')
    page = self.post(url, get=True).text
    i = page.find('&lt;?xml version=')
    j = page.find('"); initPnController()')
    assert i >= 0 and j > i, (i, j, page[:200])
    s = unescape(page[i:j])
    bs = '\\'
    # JS string unescape; protect literal backslashes (\\) first
    s = (s.replace(bs + bs, '\x00')
           .replace(bs + 'n', '\n')
           .replace(bs + 't', '\t')
           .replace(bs + '"', '"')
           .replace(bs + '/', '/')
           .replace('\x00', bs))
    return s

  ################ BILLING ################
  @cache
  def get_lookup_count(self, status: str, date: str) -> str:
    # lookup ids by date
    data = {
      'SortBy': 'Service Date',
      'FormData': make_claim_form(date, date, status),
    }
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getLookupCount.jsp', data=data).text

  @cache
  def get_lookup_count_mrn(self, mrn: str = "0"):
    # lookup by pt
    data = {
      'SortBy': 'Service Date',
      'FormData': make_claim_form("2012-01-01", "2024-04-01", mrn=mrn),
    }
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getLookupCount.jsp', data=data).text

  def _get_lookup_batch(self, encs: list[str], from_date: str, to_date: str, skip_cache: bool = False, status: str = "EncClaims") -> list[dict[str, str]]:
    # given a batch of enc ids, save claim info for each enc id.
    # (DIR / 'enc_claim').mkdir(parents=True, exist_ok=True)
    # TODO get list of good encounters since cache lookup can be slow
    if not skip_cache:
      encs = [e for e in encs if CACHE.get('enc_claim', e)]
    if encs:
      data = {
        'EncIds': ','.join(encs) + ',',
        'SortBy': 'Service Date',
        'FormData': make_claim_form(from_date, to_date, status),
      }
      xml = self.post('/mobiledoc/jsp/catalog/xml/edi/getLookupBatch.jsp', data=data).text
      print('getLookupBatch', len(encs))
      # with open('tmp.json', 'w') as f:
      #   f.write(xml)
      sleep(0.4)
      rows = []
      claims = BeautifulSoup(xml, 'xml').find_all('claim')
      for claim in tqdm(claims):
        enc = claim.EncounterId.text
        assert enc
        CACHE.put('enc_claim', enc, str(claim))
        rows.append(get_claim_data(claim))
      return rows
      # for enc in set(encs) - set(claim.EncounterId.text for claim in claims):
      #   (DIR / 'enc_claim' / f'{enc}.xml').touch()

  @cache
  def get_pt_encounters(self, mrn: int):
    url = f'/mobiledoc/jsp/catalog/xml/getPtEncounters.jsp?PatientId={mrn}&FacilityId=0&LogView=true&ecwVisitStatusFlag=true&EncOptions=0&DelOptions=0&ProviderId=0&UnlockedEnc=0&CaseTypeId=0&CaseId=0'
    return self.post(url, get=True).text

  @cache
  def get_patient_inquiry_detail(self, mrn: int):
    # PmtId
    # return > claims > claim
    # no CPT-level data on unpaid claims
    url = '/mobiledoc/jsp/catalog/xml/edi/getPatientInquiryDetail.jsp'
    data = f"PatientId={mrn}&FromDate=2012-01-01&ToDate=2024-04-13&BalanceFilter='All'&Balance=Claim+Balance&Facility=0&FacilityGroup=0&InsFilter=Insurance&AssignTo=All&InsorGrpId=0&InsAllChked=1&NoOfStmts=0&ClmWoColl=0&CollCodes=&Practice=0&ShowVoid=0&CaseId=0&rows=100&page=1&fromScreen=patienthub&badDebt=0"
    return self.post(url, data=data).text

  @cache
  def get_claim_summary(self, claim: int) -> str:
    # Lists ICDs but doesn't give payments by ICD
    return self.post('/mobiledoc/jsp/catalog/xml/getClaimSummary.jsp', data=f'claimId={claim}&redirect=1').text

  def check_claim_for_enc(self, encounter: int) -> int:
    # map enc -> claim
    url = "/mobiledoc/jsp/catalog/xml/CheckClaimForEnc.jsp"
    return self.post(url, data=f"encounterId={encounter}")

  @cache
  def get_all_balances_for_patient(self, mrn: int) -> str:
    """PtBalance, Balance, InsBalance, UnPostedAmount, insAging."""
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getAllBalncesForPt.jsp', data=f'patientId={mrn}&origin=patientInquiryDetails&coll=0').text

  @cache
  def get_imm_labs_for_encounter(self, enc: int):
    return self.post('/mobiledoc/jsp/catalog/xml/GetImmLabsForEncounter.jsp?encounterId={enc}', get=True).text

  def get_ins_payments(self, from_date: str, to_date: str, count: int = 16) -> None:
    """Billing > Payments listing.
    No paymentDetailId, though we can follow up with getPaymentDetails.
    Normally clicking on a result pulls up /insurancePayment.
    Can specify LookupPmtId which will ignore date filters.
    """
    data = f'facilityId=0&fromDate={from_date}&toDate={to_date}&payorType=0&balFilterVal=0.0&balFilterCon=&LookupPmtId=0&maxCount={count}&nCounter=0&ptId=0&insId=0&insGroupId=0&insGroup=&insClassCode=&chkno=&Status=All%20Payments&PmtDateType=0&balanceType=0&RowSort=ASC&postedBy=&SortBy=Payment%20ID&BatchId=&practiceId=&PaymenttType=All&additionalFilters=&exceptionStatus=3'
    # file = DIR / f'get_ins_payments_{to_date}.xml'
    # if file.exists():
    #   with file.open() as f:
    #     return f.read()
    r = self.post('/mobiledoc/jsp/catalog/xml/getInsPayments.jsp', data)
    # with file.open('w') as f:
    #   f.write(r.text)
    return r.text

  @cache
  def get_payment(self, payment_id: str):
    """PayerName, amount, date, PostedDate, checkDate. Missing deleted?"""
    assert payment_id.isdigit(), payment_id
    return self.post(f'/mobiledoc/jsp/catalog/xml/edi/getPayment.jsp?paymentId={payment_id}').text

  @cache
  def payment_details(self, payment_id: str):
    """Lists the paymentDetails associated with the payment.
    One detail per claim paid. Empty XML content if there are no associated claims.
    Returns: patientId, patientName, PmtDetailId, encounterId, invoiceId, invoiceAmount, paid, allowed, deduct, adjustment, MsgCode, serviceDate, ClmBalance.
    """
    return self.post(f'/mobiledoc/jsp/catalog/xml/getPaymentDetails.jsp?paymentId={payment_id}').text

  @cache
  def receivePayments_json(self, payment_id: str):
    """Claim info for patient payments only. From inquiry detail then click on a patient payment."""
    data = self.post(f'/mobiledoc/jsp/webemr/webpm/receivePayments.jsp?paymentId={payment_id}&parentScreen=divPatientInquiryDetail', get=True).text
    m = re.search(r"initReceivePayment\('([^']+)'\)", data)
    assert m, data
    # remove percent encoding and \- (which is not valid json).
    j = unquote_plus(m.group(1)).replace('\\-', '-')
    j = json.loads(j)
    del j["jsonPmtTypeList"]
    j["jsonClaimList"] = json.loads(j["jsonClaimList"])
    return json.dumps(j, separators=(',', ':'))

  @cache
  def payment_advisory_html(self, payment_id: str = '25083'):
    url = '/mobiledoc/jsp/webemr/webpm/payments/paymentAdvisory.jsp'
    return self.post(url, data={'paymentId': payment_id}).text

  @cache
  def get_billing_claim_json(self, mrn: str, claim: str):
    """Claim view with claim CPTs. mrn is actually not needed."""
    # claim_html = self.post(f'/mobiledoc/jsp/webemr/webpm/billingClaim.jsp?claimId={claim}&modulefrom=AccountsLookup&encounterId=0&patientId={mrn}', get=True, ).text
    # 3/9/26: remove &_csrf={get_csrf(claim_html)}
    data = f'tableNames=edi_pos%2Cedi_tos%2Cedi_reltogr&InvId={claim}'
    # NetPayment, Payment (incl. adj), Balance incl. PtBalance. Also ICDCodes, cpt, insurance tables
    return self.post('/mobiledoc/jsp/webemr/webpm/getBillingClaimDetails.jsp', data=data).text

  def get_claim_status_list(self, claim: str):
    data = f'<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><lookup><counter xsi:type="xsd:int">1</counter><MAXCOUNT xsi:type="xsd:int">25</MAXCOUNT><FileId xsi:type="xsd:string">{claim}</FileId><IsFileIdSearch xsi:type="xsd:string">yes</IsFileIdSearch><SortBy xsi:type="xsd:string"></SortBy></lookup></m:NOOP></Body></S:Envelope>'
    return self.post('/jsp/edi/era/getClaimStatusList.jsp', data=data).text

  def get_pay(self, pay_id: str, refresh: bool = False) -> dict[str, str]:
    xml = self.get_payment(pay_id, refresh=refresh)
    return {
      'payment': pay_id,
      'posted_date': parse_date(xml.PostedDate.text),
      'paid': xml.amount.text,  # normally we save amount per claim
      'payor_id': to_int(xml.payerId.text),  # xml.payorId.text,
      'payor_name': xml.PayerName.text,  # xml.payor.text,
      'payor_type': to_int(xml.payerType.text),  # xml.payorType.text,
      'posted_by': xml.PostedByName.text,
      'era_detail': xml.EraTransactionNumber.text,
      'payment_type': xml.type.text,  # xml.PaymentType.text,
      'deleted': xml.DeleteFlag.text,
    }

  @cache
  def insurancePayment_json(self, payment_id: str) -> str:
    # Found from payment lookup.
    assert payment_id.isdigit(), payment_id
    data = self.post('/insurancePayment.jsp?parentScreen=payments&paymentId={payment_id}&pmtClosingId=0', get=True).text
    return json.dumps({
      # 'deleted': '<span class="errorLarge">Deleted</span>' in data,  # e.g. payment 19975
      # r'$scope._postedDateTime = "(\d\d/\d\d/\d{4} +\d{2}:\d{2} (A|P)M)";'
      'posted_date': re.search(r'$scope._paymentDate = "(\d\d/\d\d/\d{4})";', data).group(1),
      'paid': re.search(r'$scope._amount = "1274.15";', data).group(1),
      'payor_id': to_int(re.search(r'$scope.InsId = "(\d+)";', data).group(1)),
      'payor_name': re.search(r'var payerNameEncVal = "([^"]+)";', data).group(1),
      'payor_type': 1,
      'posted_by': re.search(r'$scope._postedByName = "([^"]+)";', data).group(1),
      'payment_type': re.search(r'$scope._selPmtType = "([^"]+)";', data).group(1),
      'era_detail': '',
    }, separators=(',', ':'))

  def _get_ins_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict[str, str]]:
    claims = self.payment_details(pay['payment'], refresh=refresh).find_all('claim')
    for claim in claims:
      if not claim.invoiceId.text:
        breakpoint()
    return [{
      'payment': int(pay['payment']),
      'paid': to_float(claim.paid.text),  # is this on the payment or payment_detail?
      'payment_detail': to_int(claim.PmtDetailId.text),  # int: INTEGER column and cache key
      'claim': to_int(claim.invoiceId.text),
      'date': parse_date(claim.serviceDate.text),
      'encounter': to_int(claim.encounterId.text),
      'mrn': to_int(claim.patientId.text),
      'name': claim.patientName.text,
      'allowed': to_float(claim.allowed.text),
      'adjustment': to_float(claim.adjustment.text),
      'deduct': to_float(claim.deduct.text),
      'msg_code': claim.MsgCode.text,  # looks like CLP02:19|CLP06:MB
    } for claim in claims]


  def _get_pt_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict[str, str]]:
    j = json.loads(self.receivePayments_json(pay['payment'], refresh=refresh))
    # Unused:
    # j['jsonPayment']['SOAP-ENV:Envelope']['SOAP-ENV:Body']['return']['PaymentData']
    # j['paymentId']
    # pay 33541, payment_detail 90960, enc 235936
    # pay 33542
    return [{
      'payment': int(pay['payment']),
      'paid': to_float(claim['payment']),
      'payment_detail': to_int(claim['pmtDetailId']),  # JSON may be str or int; INTEGER column and cache key
      'claim': to_int(claim['claimId']),
      'date': claim['serviceDate'],
      'encounter': to_int(claim['encId']),
      'mrn': to_int(pay['payor_id']),
      'name': claim['patientName'],
      'allowed': to_float(claim['payment']),
      'adjustment': 0.0,
      'deduct': 0.0,
      'msg_code': '',
    } for claim in j['jsonClaimList']]


  def get_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict]:
    if pay['payor_type'] == 1:  # Insurance payment
      return self._get_ins_claims(pay, refresh=refresh)
    assert pay['payor_type'] == 2  # Patient Payment
    return self._get_pt_claims(pay, refresh=refresh)


  def fill_payment_posting_medicare(self, payment: str, refresh: bool = False):
    # mrn: str, claim: str, payment: str, enc: str, name: str, era: str, parent_screen: str):
    # advisory = self.payment_advisory_html(payment)
    pay = self.get_pay(payment, refresh)
    for claim in self.get_claims(pay, refresh):
      # pmtdetailid, encounterid, invoiceid, patientid, patientname
      # invoiceId, invoiceAmount, paid, allowed, deduct, adjustment, MsgCode, serviceDate, ClmBalance
      url = f"/mobiledoc/jsp/webemr/webpm/paymentPostingMedicare.jsp?params=claimId={claim['claim']}&pmtDetailId={claim['payment_detail']}&encId={claim['encounter']}&paymentId={payment}&patientId={claim['mrn']}&patientName={claim['name'].strip().replace(' ','%20')}&EraTransactionNumber=&paymentLock=0&closingId=0&payerName={pay['payor_name']}&parentScreen="
      args = 'payment_posting_medicare', claim['payment_detail']
      result = None if refresh else CACHE.get(*args)
      if not result:
        data = self.post(url).text
        CACHE.put(*args, self.post(url).text)
        print(*args)
        sleep(.5)

  def payment_posting_medicare(self, payment: str, payment_detail: str, refresh: bool = False) -> str:
    # look up payment_detail in cache. call fill_payment_posting_medicare() if not found.
    data = None if refresh else CACHE.get('payment_posting_medicare', payment_detail)
    if data is None:
      self.fill_payment_posting_medicare(payment, refresh)
      data = CACHE.get('payment_posting_medicare', payment_detail)
      assert data is not None, f"PmtDetail {payment_detail} not found"
    return data

  @cache
  def receive_payments(self, payment: str):
    # payment 32057 -> claim 47849
    return self.get(f'/mobiledoc/jsp/webemr/webpm/receivePayments.jsp?paymentId={payment}&parentScreen=payments').text

  @cache
  def notes_log(self, claim: str):
    return self.get(f'/mobiledoc/jsp/webemr/webpm/viewClaimAssignedToLogs.jsp?InvId={claim}').text

  @cache
  def billing_log(self, claim: str):
    data = f'tabOnId=0&EntityType=1&EntityId={claim}&txtDateFrom=&txtDateTo=&PatientId=&sortBy=1&sortOrder=DESC&logType=0&AssignedToId=0&LogCategory=All&counter=0&maxCount=10'
    return self.post(f'/mobiledoc/jsp/webemr/webpm/claimBillingLogsReport.jsp', data=data).text

  @cache
  def claimFollowData(self, claim: str):
    claim_html = self.post(f'/mobiledoc/jsp/webemr/webpm/billingClaim.jsp?claimId={claim}&modulefrom=AccountsLookup&encounterId=0&patientId=19996', get=True).text
    uid = re.search(r"var claimScreenUId='(\d+)';", claim_html).group(1)
    print(uid)
    # data = f'tableNames=edi_pos%2Cedi_tos%2Cedi_reltogr&InvId={claim}&_csrf={get_csrf(claim_html)}'
    self.session.csrf = get_csrf(claim_html)
    return self.post(f'/mobiledoc/jsp/webemr/webpm/claimFollowData.jsp?ClaimNo={claim}&assignedToId=9246&startDate=11/11/2024&assignedTo=Eng,Landley&ptId=19996&showRightPanel=1&Type=0&claimScreenUId={uid}', get=True).text
    # return self.post(f'/mobiledoc/jsp/webemr/webpm/claimFollowData.jsp?ClaimNo={claim}&assignedToId=9246&startDate=11/11/2024&assignedTo=Eng,Landley&ptId=19996&showRightPanel=1&Type=0&claimScreenUId={uid}', get=True).text

  def labs_page(self):
    return self.post('/mobiledoc/jsp/webemr/jellybean/labs/JellyBeanL-Lab-DI-Procedure-ListView.jsp?isRoute=true&Type=all', get=True).text

  def labs(self, from_date: str, to_date: str, tab="To be reviewed", filterDateType=1, patient: str | None = None):
    # lab list table view. To be reviewed tab can be empty.
    # patient: account number; forces the By patient tab (lab_post).
    out = []
    page = 1
    total = None
    while True:
      data = lab_post(from_date=from_date, to_date=to_date, tab=tab, page=page, filterDateType=filterDateType, patient=patient)
      xml = self.post('/mobiledoc/jsp/webemr/jellybean/labs/requestHandler.jsp', data=data).content
      # .content to fix ValueError: Unicode strings with encoding declaration are not supported. Please use bytes input...
      # strip to fix XMLSyntaxError: XML declaration allowed only at the start of the document
      root = fromstring(xml.strip())
      page_labs = root.findall('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/labs/lab')
      for lab in page_labs:
        out.append({
          'id': to_int(lab.find('id').text),
          'itemid': to_int(lab.find('itemid').text),
          'encounter_id': to_int(lab.find('encounterId').text),
          'patientname': lab.find('patientname').text,
          'mrn': to_int(lab.find('patientId').text),
          'name': lab.find('name').text,
          'date': parse_date(lab.find('date').text),
          'coll_date': parse_date(lab.find('collDate').text),
          'coll_time': lab.find('collTime').text,
          'result_date': parse_date(lab.find('ResultDate').text),
          'from_lab_id': to_int(lab.find('fromLabId').text),
          'interface_status': clean_interface_status(lab.find('InterfaceStatus').text, lab.find('fromLabId').text),
          'status': to_int(lab.find('status').text),
          'type': to_int(lab.find('Type').text),
          'encounter_type': to_int(lab.find('EncounterType').text),
          'priority': to_int(lab.find('priority').text)
        })
      if total is None:
        total = int(root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/Total').text)
      if len(out) >= total:
        break
      assert page_labs
      page += 1
    if int(total) > len(out):
      print(f"labs({from_date}..{to_date}): {len(out)} of {int(total)}")
    return out

  def telweb_encounters(self, date: str, tab: int = 2, date_filter_days: int = 1):
    """Telephone/Web Encounters list view (JellyBean T). One row per encounter.

    date is MM/DD/YYYY. With date_filter_days=1 the query covers only `date`;
    with 3 or 7 it covers the days up to and including it.
    tab: 0 Open, 1 Addressed, 2 All (default), 3 All Open (All Dates), which
    ignores the date filter.
    """
    out = []
    page = 1
    total = None
    while True:
      url = ('/mobiledoc/jsp/webemr/jellybean/telephoneencounter/PatientDetails.jsp'
             f'?assignToGroupId=0&assignedToId=0&assignedToUserType=0&date={date}'
             f'&dateFilterDays={date_filter_days}&doctorId=0&facType=0&facilityId=0&facilityIds=0'
             f'&pageNo={page}&rowsPerPage=100&showDelegated=0&sortBy=1&sortOrder=DESC'
             f'&tabOnId={tab}&webPortalEnabled=1')
      # some GET endpoints get a CSP <meta> HTML line prepended to the XML
      content = self.post(url, get=True).content
      i = content.find(b'<?xml version')
      root = fromstring(content[i:] if i >= 0 else content.strip())
      encs = root.findall('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/encounters/encounter')
      for enc in encs:
        out.append({
          'encounter': to_int(enc.find('encounterId').text),
          'mrn': to_int(enc.find('patientId').text),
          'name': enc.find('name').text,
          'datetime': enc.find('datetime').text,  # MM/DD/YYYY h:MM AM
          'time': enc.find('time').text,
          'reason': enc.find('reason').text or None,
          'type': to_int(enc.find('encType').text),  # 2
          'dr': enc.find('doctorname').text or None,
          'assigned_to': enc.find('assignedTo').text,
          'web': enc.find('webEnabled').text == '1',  # web portal vs telephone
          'phone': enc.find('upPhone').text,
          'facility': enc.find('facilityName').text,
          'priority': to_int(enc.find('priority').text),
        })
      if total is None:
        total = int(root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/Total').text)
      if len(out) >= total:
        break
      assert encs
      page += 1
    if total > len(out):
      print(f"telweb_encounters({date}): {len(out)} of {total}")
    return out

  @cache
  def print_chart_options_html(self, encounter: int, enc_type: int = 2, visit_code_flag: str = ''):
    """Right Chart Panel (RCP) HTML for an encounter, as shown in the Enc tab
    of the patient modal.

    enc_type: 1 office visit, 2 tel, 5 lab, 7 ePrescription.
    Tel returns: Answered By, Date/Time, Reason, and Message.
    Office visit returns Provider, Answered By, Date, Time, Assigned To,
    Reason, Message (or Refills) and includes eg
    <td valign="top">Electronic signature of Provider: JIE LING , MD/PhD  on 11/11/2026 at 02:11 PM PST</td>.
    visit_code_flag only applies to office visits (1 = AV/double book).
    """
    url = ('/mobiledoc/jsp/catalog/xml/printChartOptions.jsp'
           f'?FormData=Default&isHtml=true&requestFrom=RCP&style=ModernII'
           f'&visitCodeFlag={visit_code_flag}&encounterID={encounter}&encType={enc_type}')
    return self.post(url, get=True).text

  def lab_report(self, lab_id: str='355969', enc_id: str='273291', mrn: str='17668'):
    # returns patientobj incl secure notes
    url = f'/mobiledoc/jsp/webemr/labs/report/LabReport.jsp?ReportId={lab_id}&EncounterId={enc_id}&patientId={mrn}&tabId=1&ccDoctorId=0&Type=0&rowIndex=6&context=LJELLY_BEAN_SCREEN'
    return self.post(url, get=True).text

  @cache
  def lab_results_json(self, lab_id: str='355969', report_type: int = 0):
    # 0 for lab and 1 for imaging
    url = f'/mobiledoc/jsp/webemr/labs/report/GetLabResultsJSON.jsp?ReportId={lab_id}&ReportType={report_type}&CCProviderId=0&loadAdditionalDetails=%7B%22reasons%22%3A0%2C%22results%22%3A0%2C%22specimenSource%22%3A0%2C%22specimenDescription%22%3A0%2C%22userFacility%22%3A0%7D'
    # LabDataJSON: ActualFasting, InterfaceStatus (eg Manually Reconciled - SimonMed Rad Bi)
    # Also LabDataDetailJSONArray, ReasonJSONArray, PatientDataJSON
    data = self.post(url, get=True).text
    return data

  @cache
  def lab_request_json(self, lab_id: str='352700'):
    # full details with lab notes eg fasting, lab address
    url = f'/mobiledoc/jsp/webemr/labs/LabsRequestHandler.jsp?sRequestFrom=PinkPaperScreen&sRequestType=getPinkPaperClip&viewAllReportCriteria=&reportId={lab_id}&callingform='
    return self.post(url).text

  def review_labs(self, lab_ids: list[int]) -> str:
    """JellyBeanL 'More Action > Mark as Reviewed'.
    lab_ids: comma-separated string or list of lab ids from the labs() listing;
    one table row can span several report ids (eg '374908,374912').
    Idempotent for already-reviewed labs.
    """
    lab_ids = ','.join(str(i) for i in lab_ids)
    content = self.post(f'/mobiledoc/jsp/catalog/xml/labs/setAllLabReviewed.jsp?context=LJELLYBEAN&strLabIds={lab_ids}', get=True).content
    # some GET endpoints get a CSP <meta> HTML block prepended to the XML
    i = max(content.find(b'<?xml version'), content.find(b'<SOAP-ENV:Envelope'))
    status = fromstring(content[i:]).find('.//status').text
    assert status == 'success', (lab_ids, content)
    return status

  def unreview_lab(self, lab_id: str | int, encounter_id: str | int, reason: str = '') -> str:
    """Results screen 'Options > Unreview'. Reverts a reviewed lab/DI/procedure
    to unreviewed and unlocks it for editing. reason: not prompted in the current UI, sent empty.
    Idempotent for already-unreviewed labs.
    """
    content = self.post(f'/mobiledoc/jsp/catalog/xml/unlockLabsDI.jsp?ReportId={lab_id}&unreviewReason={quote(reason)}&encounterId={encounter_id}', get=True).content
    # some GET endpoints get a CSP <meta> HTML block prepended to the XML
    i = max(content.find(b'<?xml version'), content.find(b'<SOAP-ENV:Envelope'))
    status = fromstring(content[i:]).find('.//status').text
    assert status == 'success', (lab_id, content)
    return status

  # /mobiledoc/jsp/webemr/security/getAuthToken?action=1021 returns a long b64 blob
  # /mobiledoc/jsp/webemr/rightpanel/getOverviewData.jsp?patientId=17668&context=LAB_RESULT_SCREEN&encounterId=273291&trigger=overviewjson&strFilter=0 problemList, etc
  # /mobiledoc/jsp/catalog/xml/getValuesForEnctrId.jsp?encounterId=273291&addPtDetails=true&noAccessSection=true encounter info

def get_claim(enc: str):
  if data := CACHE.get('enc_claim', enc):
    return BeautifulSoup(data, 'xml')
  # else:
  #   with open('missing.txt','w') as f:
  #     f.write(enc + '\n')

"""
POST https://cabahcapp.ecwcloud.com/mobiledoc/jsp/catalog/xml/encLookup.jsp?sessionDID=122&TrUserId=122
<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><lookup><ProviderId xsi:type="xsd:string">122</ProviderId><FromDate xsi:type="xsd:string">2025-06-10</FromDate><ToDate xsi:type="xsd:string">2025-06-10</ToDate><FromDOB xsi:type="xsd:string">1902-01-01</FromDOB><ToDOB xsi:type="xsd:string">2025-06-19</ToDOB><pos xsi:type="xsd:string"></pos><SortBy xsi:type="xsd:string">DOB</SortBy><counter xsi:type="xsd:int">1</counter><MaxCount xsi:type="xsd:int">10</MaxCount><ItemIdRx xsi:type="xsd:int">0</ItemIdRx><ItemIdICD xsi:type="xsd:int">0</ItemIdICD><ItemIdCPT xsi:type="xsd:int">0</ItemIdCPT><showuniquepats xsi:type="xsd:int">1</showuniquepats><VisitType xsi:type="xsd:string">ALL</VisitType><VisitStatus xsi:type="xsd:string">ALL</VisitStatus></lookup></m:NOOP></Body></S:Envelope>

Also has insurance:
GET https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/rightpanel/getOverviewData.jsp?patientId={mrn}
response["rpm"]["data"] gives xml blob with insurances
"""