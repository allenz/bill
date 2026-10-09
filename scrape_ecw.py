"""Download patient data from ECW."""
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from tqdm import tqdm
from urllib.parse import unquote_plus, quote
import json
from lxml.etree import fromstring

from ecw_session import ESession, get_csrf, make_claim_form
from store import cache, DIR, CACHE
from lab_post import lab_post, LAB_SUFFIXES, clean_interface_status


KNOWN_MISSING_PT = [19712,19653,19555,19483,19878,19607,19639,19509,19596,19715,19634,19844,19676,19597,19641,19655,19547,19621,19872,19622,19658,19526,19569,19583,19699,19654,19796,19511,19568,19819,19880,19723,19685,19486,19660,19501,19630,19519,19679,19849,19841,19859,19638,19717,19517,19719,19495,19875,19651,19589,19804,19640,19502,19810,19664,19488,19822,19698,19559,19542,19524,19726,19743,19504,19684,19711,19716,19574,19562,19828,19575,19682,19500,15080,19677]

# note claimstatus can also be EncMissingClaims
# BalanceCondition defaults to &gt;
CLAIM_CONFIG = '<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><m:NOOP xmlns:m="NOOP"><lookup xsi:type="xsd:string"><EpisodesWithoutClaimsOption xsi:type="xsd:string">false</EpisodesWithoutClaimsOption><isMasterEpisodeSelected xsi:type="xsd:string">false</isMasterEpisodeSelected><ProviderIdList xsi:type="xsd:string">0</ProviderIdList><ClaimFilters xsi:type="xsd:string">31</ClaimFilters><AssignedTo xsi:type="xsd:string"></AssignedTo><AssignedToId xsi:type="xsd:int">0</AssignedToId><ClaimType xsi:type="xsd:string">-1</ClaimType><FromDate xsi:type="xsd:string">XDATE</FromDate><ToDate xsi:type="xsd:string">XDATE</ToDate><DateOption xsi:type="xsd:int">XOPTION</DateOption><pos xsi:type="xsd:string"></pos><isNewBuild xsi:type="xsd:string">yes</isNewBuild><DepartmentId xsi:type="xsd:string">0</DepartmentId><ClaimStatus xsi:type="xsd:string">AllClaims</ClaimStatus><RejStatus xsi:type="xsd:string"></RejStatus><StatusIndex xsi:type="xsd:int">0</StatusIndex><PatientId xsi:type="xsd:int">0</PatientId><InsGrp xsi:type="xsd:string"></InsGrp><InsuranceId xsi:type="xsd:int">0</InsuranceId><ExcludeFromCollection xsi:type="xsd:string">1</ExcludeFromCollection><SelfPay xsi:type="xsd:int">0</SelfPay><InsAddInsGroupId xsi:type="xsd:string"></InsAddInsGroupId><counter xsi:type="xsd:int">1</counter><MaxCount xsi:type="xsd:int">100</MaxCount><InvId xsi:type="xsd:string"></InvId><PrescriptionNumber xsi:type="xsd:string"></PrescriptionNumber><BalanceCondition xsi:type="xsd:string"></BalanceCondition><balance xsi:type="xsd:string">0.0</balance><CondAndOr xsi:type="xsd:string"></CondAndOr><Balance2 xsi:type="xsd:string"></Balance2><CondCompare2 xsi:type="xsd:string"></CondCompare2><PayorId xsi:type="xsd:string"></PayorId><ZeroChargeClaims xsi:type="xsd:int">1</ZeroChargeClaims><userid xsi:type="xsd:int">0</userid><DoNotRunQuery xsi:type="xsd:int">1</DoNotRunQuery><AdditionalCond2 xsi:type="xsd:int">0</AdditionalCond2><InsId2 xsi:type="xsd:string">0</InsId2><ProviderType xsi:type="xsd:int">0</ProviderType><EmployerFilterSel xsi:type="xsd:int">0</EmployerFilterSel></lookup></m:NOOP></m:NOOP></Body></S:Envelope>'
CLAIM_CONFIG = quote(CLAIM_CONFIG).replace('/', '%2F')
CLAIM_CONFIG = 'SortBy=Service%20Date&FormData=' + CLAIM_CONFIG


def to_int(v):
  """Cast a scraped field to int for the Lab INT columns. None/'' (empty XML
  elements) pass through and are stored as NULL."""
  return None if v in (None, '') else int(v)


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
  def search_patient(self, mrn: str) -> str:
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
  def get_insurance_info(self, mrn: str) -> str:
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
    """Resource Scheduling. Includes all C reminders."""
    end_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    data = f"duration=15&dayView=7&providers=122&facilities=0&startDate={date}&endDate={end_date}&weekDay=1&doNotGetRecFacility=0&noWHoursForProv=0&deptId=0&userName=lingj&loadClipboard=1&loadTasks=0&moduleName=ResourceSchedule"
    return self.post("/mobiledoc/jsp/catalog/xml/getDoctorsScheduleList.jsp", data).text

  def fetch_patient_note(self, patient: int) -> str:
    """Yellow sticky! Not used yet."""
    url = f"/mobiledoc/emr/patientDashboard/fetchPatientNote?fetchSecureNote=false&patientId={patient}"
    xml = fromstring(self.post(url, get=True).content)
    return xml.xpath("//row/PtNotes/text()")[0]

  def save_patient_note(self, patient: int, text: str) -> str:
    import xml.sax.saxutils

    url = f"/mobiledoc/jsp/dashboard/SaveStickyNotes.jsp"
    text = xml.sax.saxutils.escape(text)
    xml = f'<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><item xsi:type="xsd:string"><Notes xsi:type="xsd:string">{text}</Notes></item></m:NOOP></Body></S:Envelope>'
    data = {"patientId": patient, "FormData": xml}
    return self.post(url, data=data).text

  def _get_assessment(self, encounter: int) -> str:
    """Part of encounter."""
    url = f"/mobiledoc/jsp/catalog/xml/getAssessment.jsp?Id={encounter}"
    return self.post(url, get=True).text

  def _top_panel(self, patient: int, encounter: int) -> str:
    """Top panel notes (unused) loaded in progress notes. Large xml with patientobj=... line, xml-escaped json."""
    url = f"/mobiledoc/jsp/webemr/toppanel/topPanel.jsp?context=progressnotes&patientId={patient}&encounterId={encounter}"
    return self.post(url, get=True).text

  def _patient_hub(self, patient: int, encounter: int) -> str:
    """Called from an encounter. Returns picPath etc."""
    url = f"/mobiledoc/jsp/webemr/toppanel/patientHub/fetchPatientHub.jsp pid={patient}&encounterId={encounter}"
    return self.post(url).text

  def _img(self, patient: int) -> str:
    """Get patient image path. Not used."""
    url = f"/mobiledoc/jsp/webemr/toppanel/getPatientPicImgPath.jsp?patientId={patient}&picFileName={patient}.jpg"
    return self.post(url, get=True).text

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
  def get_pt_encounters(self, mrn):
    url = f'/mobiledoc/jsp/catalog/xml/getPtEncounters.jsp?PatientId={mrn}&FacilityId=0&LogView=true&ecwVisitStatusFlag=true&EncOptions=0&DelOptions=0&ProviderId=0&UnlockedEnc=0&CaseTypeId=0&CaseId=0'
    return self.get(url).text

  @cache
  def get_patient_inquiry_detail(self, mrn: str):
    # PmtId
    # return > claims > claim
    # no CPT-level data on unpaid claims
    url = '/mobiledoc/jsp/catalog/xml/edi/getPatientInquiryDetail.jsp'
    data = f"PatientId={mrn}&FromDate=2012-01-01&ToDate=2024-04-13&BalanceFilter='All'&Balance=Claim+Balance&Facility=0&FacilityGroup=0&InsFilter=Insurance&AssignTo=All&InsorGrpId=0&InsAllChked=1&NoOfStmts=0&ClmWoColl=0&CollCodes=&Practice=0&ShowVoid=0&CaseId=0&rows=100&page=1&fromScreen=patienthub&badDebt=0"
    return self.post(url, data=data).text

  @cache
  def get_claim_summary(self, claim: str) -> str:
    # Lists ICDs but doesn't give payments by ICD
    return self.post('/mobiledoc/jsp/catalog/xml/getClaimSummary.jsp', data=f'claimId={claim}&redirect=1').text

  def check_claim_for_enc(self, encounter: int) -> int:
    # go from enc -> claim
    url = "/mobiledoc/jsp/catalog/xml/CheckClaimForEnc.jsp"
    return self.post(url, data=f"encounterId={encounter}")

  @cache
  def get_all_balances_for_patient(self, mrn: str) -> str:
    """PtBalance, Balance, InsBalance, UnPostedAmount, insAging."""
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getAllBalncesForPt.jsp', data=f'patientId={mrn}&origin=patientInquiryDetails&coll=0').text

  @cache
  def get_imm_labs_for_encounter(self, enc: str):
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
      'postedDate': xml.PostedDate.text,
      'paid': xml.amount.text,  # normally we save amount per claim
      'payorId': xml.payerId.text,  # xml.payorId.text,
      'payorName': xml.PayerName.text,  # xml.payor.text,
      'payorType': xml.payerType.text,  # xml.payorType.text,
      'postedBy': xml.PostedByName.text,
      'ERADetail': xml.EraTransactionNumber.text,
      'paymentType': xml.type.text,  # xml.PaymentType.text,
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
      'postedDate': re.search(r'$scope._paymentDate = "(\d\d/\d\d/\d{4})";', data).group(1),
      'paid': re.search(r'$scope._amount = "1274.15";', data).group(1),
      'payorId': re.search(r'$scope.InsId = "(\d+)";', data).group(1),
      'payorName': re.search(r'var payerNameEncVal = "([^"]+)";', data).group(1),
      'payorType': 1,
      'postedBy': re.search(r'$scope._postedByName = "([^"]+)";', data).group(1),
      'paymentType': re.search(r'$scope._selPmtType = "([^"]+)";', data).group(1),
      'ERADetail': '',
    }, separators=(',', ':'))

  def _get_ins_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict[str, str]]:
    claims = self.payment_details(pay['payment'], refresh=refresh).find_all('claim')
    for claim in claims:
      if not claim.invoiceId.text:
        breakpoint()
    return [{
      'payment': pay['payment'],
      'paid': claim.paid.text,  # is this on the payment or paymentDetail?
      'paymentDetail': claim.PmtDetailId.text,
      'claim': claim.invoiceId.text,
      'date': claim.serviceDate.text,
      'encounter': claim.encounterId.text,
      'mrn': claim.patientId.text,
      'name': claim.patientName.text,
      'allowed': claim.allowed.text,
      'adjustment': claim.adjustment.text,
      'deduct': claim.deduct.text,
      'MsgCode': claim.MsgCode.text,  # looks like CLP02:19|CLP06:MB
    } for claim in claims]


  def _get_pt_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict[str, str]]:
    j = json.loads(self.receivePayments_json(pay['payment'], refresh=refresh))
    # Unused:
    # j['jsonPayment']['SOAP-ENV:Envelope']['SOAP-ENV:Body']['return']['PaymentData']
    # j['paymentId']
    # pay 33541, paymentDetail 90960, enc 235936
    # pay 33542
    return [{
      'payment': pay['payment'],
      'paid': claim['payment'],
      'paymentDetail': claim['pmtDetailId'],
      'claim': claim['claimId'],
      'date': claim['serviceDate'],
      'encounter': claim['encId'],
      'mrn': pay['payorId'],
      'name': claim['patientName'],
      'allowed': claim['payment'],
      'adjustment': 0,
      'deduct': 0,
      'MsgCode': '',
    } for claim in j['jsonClaimList']]


  def get_claims(self, pay: dict[str, str], refresh: bool = False) -> list[dict[str, str]]:
    if pay['payorType'] == '1':  # Insurance payment
      return self._get_ins_claims(pay, refresh=refresh)
    assert pay['payorType'] == '2'  # Patient Payment
    return self._get_pt_claims(pay, refresh=refresh)


  def fill_payment_posting_medicare(self, payment: str, refresh: bool = False):
    # mrn: str, claim: str, payment: str, enc: str, name: str, era: str, parent_screen: str):
    # advisory = self.payment_advisory_html(payment)
    pay = self.get_pay(payment, refresh)
    for claim in self.get_claims(pay, refresh):
      # pmtdetailid, encounterid, invoiceid, patientid, patientname
      # invoiceId, invoiceAmount, paid, allowed, deduct, adjustment, MsgCode, serviceDate, ClmBalance
      url = f"/mobiledoc/jsp/webemr/webpm/paymentPostingMedicare.jsp?params=claimId={claim['claim']}&pmtDetailId={claim['paymentDetail']}&encId={claim['encounter']}&paymentId={payment}&patientId={claim['mrn']}&patientName={claim['name'].strip().replace(' ','%20')}&EraTransactionNumber=&paymentLock=0&closingId=0&payerName={pay['payorName']}&parentScreen="
      args = 'payment_posting_medicare', claim['paymentDetail']
      result = None if refresh else CACHE.get(*args)
      if not result:
        data = self.post(url).text
        CACHE.put(*args, self.post(url).text)
        print(*args)
        sleep(.5)

  def payment_posting_medicare(self, payment: str, paymentDetail: str, refresh: bool = False) -> str:
    # look up paymentDetail in cache. call fill_payment_posting_medicare() if not found.
    data = None if refresh else CACHE.get('payment_posting_medicare', paymentDetail)
    if data is None:
      self.fill_payment_posting_medicare(payment, refresh)
      data = CACHE.get('payment_posting_medicare', paymentDetail)
      assert data is not None, f"PmtDetail {paymentDetail} not found"
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

  def labs(self, from_date: str, to_date: str, tab="To be reviewed", filterDateType=1):
    # lab list table view. To be reviewed tab can be empty.
    out = []
    page = 1
    total = None
    while True:
      data = lab_post(from_date=from_date, to_date=to_date, tab=tab, page=page, filterDateType=filterDateType)
      xml = self.post('/mobiledoc/jsp/webemr/jellybean/labs/requestHandler.jsp', data=data).content
      # .content to fix ValueError: Unicode strings with encoding declaration are not supported. Please use bytes input...
      # strip to fix XMLSyntaxError: XML declaration allowed only at the start of the document
      root = fromstring(xml.strip())
      page_labs = root.findall('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/labs/lab')
      for lab in page_labs:
        breakpoint()
        out.append({
          'id': to_int(lab.find('id').text),  # ReportId field
          'itemid': to_int(lab.find('itemid').text),  # lab item which can have multiple patients
          'encounterId': to_int(lab.find('encounterId').text),
          'patientname': lab.find('patientname').text,
          'patientId': lab.find('patientId').text,
          'name': lab.find('name').text,
          'date': lab.find('date').text,
          'collDate': lab.find('collDate').text,
          'collTime': lab.find('collTime').text,
          'ResultDate': lab.find('ResultDate').text,
          'fromLabId': to_int(lab.find('fromLabId').text),
          'InterfaceStatus': clean_interface_status(lab.find('InterfaceStatus').text, lab.find('fromLabId').text),
          'status': to_int(lab.find('status').text),
          'type': to_int(lab.find('Type').text),  # 0 for labs, 1 for imaging
          'encounterType': lab.find('EncounterType').text,  # 1 for current, 5 for virtual
          'priority': lab.find('priority').text
        })
      if total is None:
        total = int(root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body/return/Total').text)
      if len(out) >= total:
        break
      assert page_labs
      page += 1
    if int(total) > len(out):
      print(f"labs({date}): {len(out)} of {int(total)}")
    breakpoint()
    return out

  def lab_report(self, lab_id: str='355969', enc_id: str='273291', mrn: str='17668'):
    # returns patientobj incl secure notes
    url = f'/mobiledoc/jsp/webemr/labs/report/LabReport.jsp?ReportId={lab_id}&EncounterId={enc_id}&patientId={mrn}&tabId=1&ccDoctorId=0&Type=0&rowIndex=6&context=LJELLY_BEAN_SCREEN'
    return self.post(url, get=True).text

  def lab_results_json(self, lab_id: str='355969', report_type: int = 0):
    # 0 for lab and 1 for imaging
    url = f'/mobiledoc/jsp/webemr/labs/report/GetLabResultsJSON.jsp?ReportId={lab_id}&ReportType={report_type}&CCProviderId=0&loadAdditionalDetails=%7B%22reasons%22%3A0%2C%22results%22%3A0%2C%22specimenSource%22%3A0%2C%22specimenDescription%22%3A0%2C%22userFacility%22%3A0%7D'
    # LabDataJSON: ActualFasting, InterfaceStatus (eg Manually Reconciled - SimonMed Rad Bi)
    # Also LabDataDetailJSONArray, ReasonJSONArray, PatientDataJSON
    data = self.post(url, get=True).text
    return data

  def lab_request_json(self, lab_id: str='352700'):
    # full details with lab notes eg fasting, lab address
    url = f'/mobiledoc/jsp/webemr/labs/LabsRequestHandler.jsp?sRequestFrom=PinkPaperScreen&sRequestType=getPinkPaperClip&viewAllReportCriteria=&reportId={lab_id}&callingform='
    return self.post(url).text

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