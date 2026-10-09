"""
GET newLogin.jsp
- POST https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/login/authenticate/setAESKey?action=1043 usage=loginDataEncGCM

POST https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/login/authenticate/verifyUname with username and `_csrf`
- 302 GET https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/login/loginSuccess.jsp
- 302 GET https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/index.jsp
"""
from bs4 import BeautifulSoup
from js_crypto import JSCrypto
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import requests
import re
import shutil
import time
import urllib.parse
from datetime import datetime
import logging


HOST = "https://cabahcapp.ecwcloud.com"
URL_INDEX = HOST + "/mobiledoc/jsp/webemr/index.jsp"
# others: mycw62.ecwcloud.com to mycw179.ecwcloud.com, kschckebo, flgaheapp, nvfmheapp, eclinicalmsg2
# uses tomcat server and mysql
# sysadmin guide: https://www.bannerhealthnetwork.com/media/bae6719c-f848-41ff-890f-8ae5b4214e60

def make_claim_form(from_date: str, to_date: str, status: str = "EncClaims", mrn: str = "0"):
  # Let's assume missing claims is low. Get all other claims.
  # EncClaims = get claims with getLookupCount.
  # EncMissingClaims = get encounters without claims, need getLookupCount and getLookupBatch.
  # (useless) AllClaims = claims with outstanding balance with getClaimsList.
  return f'<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" S:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:xsd="http://www.w3.org/1999/XMLSchema" xmlns:xsi="http://www.w3.org/1999/XMLSchema-instance"><Body><m:NOOP xmlns:m="NOOP"><m:NOOP xmlns:m="NOOP"><lookup xsi:type="xsd:string"><EpisodesWithoutClaimsOption xsi:type="xsd:string">false</EpisodesWithoutClaimsOption><isMasterEpisodeSelected xsi:type="xsd:string">false</isMasterEpisodeSelected><ProviderIdList xsi:type="xsd:string">0</ProviderIdList><ClaimFilters xsi:type="xsd:string">31</ClaimFilters><AssignedTo xsi:type="xsd:string"></AssignedTo><AssignedToId xsi:type="xsd:int">0</AssignedToId><ClaimType xsi:type="xsd:string">-1</ClaimType><FromDate xsi:type="xsd:string">{from_date}</FromDate><ToDate xsi:type="xsd:string">{to_date}</ToDate><DateOption xsi:type="xsd:int">0</DateOption><pos xsi:type="xsd:string"></pos><isNewBuild xsi:type="xsd:string">yes</isNewBuild><DepartmentId xsi:type="xsd:string">0</DepartmentId><ClaimStatus xsi:type="xsd:string">{status}</ClaimStatus><RejStatus xsi:type="xsd:string"></RejStatus><StatusIndex xsi:type="xsd:int">0</StatusIndex><PatientId xsi:type="xsd:int">{mrn}</PatientId><InsGrp xsi:type="xsd:string"></InsGrp><InsuranceId xsi:type="xsd:int">0</InsuranceId><ExcludeFromCollection xsi:type="xsd:string">1</ExcludeFromCollection><SelfPay xsi:type="xsd:int">0</SelfPay><InsAddInsGroupId xsi:type="xsd:string"></InsAddInsGroupId><counter xsi:type="xsd:int">1</counter><MaxCount xsi:type="xsd:int">20</MaxCount><InvId xsi:type="xsd:string"></InvId><PrescriptionNumber xsi:type="xsd:string"></PrescriptionNumber><BalanceCondition xsi:type="xsd:string">&gt;</BalanceCondition><balance xsi:type="xsd:string">0.0</balance><CondAndOr xsi:type="xsd:string"></CondAndOr><Balance2 xsi:type="xsd:string"></Balance2><CondCompare2 xsi:type="xsd:string"></CondCompare2><PayorId xsi:type="xsd:string"></PayorId><ZeroChargeClaims xsi:type="xsd:int">1</ZeroChargeClaims><userid xsi:type="xsd:int">0</userid><DoNotRunQuery xsi:type="xsd:int">1</DoNotRunQuery><AdditionalCond2 xsi:type="xsd:int">0</AdditionalCond2><InsId2 xsi:type="xsd:string">0</InsId2><ProviderType xsi:type="xsd:int">0</ProviderType><EmployerFilterSel xsi:type="xsd:int">0</EmployerFilterSel></lookup></m:NOOP></m:NOOP></Body></S:Envelope>'

def get_rsa(html: str) -> str:
  """Extract the ECW RSA public key from the ECW login page."""
  return re.search(r"rsaPubKey='([\w/\+]+)'", html).group(1)

def get_csrf(html: str) -> str:
  """Extract the Cross-Site Request Forgery token from an ECW response HTML."""
  soup = BeautifulSoup(html, 'lxml')
  csrf = soup.find('meta', attrs={"name": "_csrf"})
  if not csrf:
    csrf = soup.find('input', attrs={"name": "_csrf"})
    assert csrf, html
    csrf = csrf["value"]
  else:
    csrf = csrf["content"]
  return csrf

def make_headers(post=False, json=True, csrf='', referer='', cip='', ext='', accept=''):
  """Make request headers to talk with the ECW server.

  Params

    accept: override accept header
  """
  headers = {
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Origin': 'https://cabahcapp.ecwcloud.com',
    'Upgrade-Insecure-Requests': '1',
    # Default for requesting a document
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
  }
  if json:
      headers['Accept'] = 'application/json, text/plain, */*'
      headers['isAjaxRequest'] = 'true'
  if post:
    headers.update({
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'Isajaxrequest': 'true',
      'Sec-Fetch-Dest': 'empty',
      'Sec-Fetch-Mode': 'cors',
    })
    if not json:
      # headers['Accept'] = 'application/json, text/plain, */*'
      # headers['isAjaxRequest'] = 'true'
    # else:
      headers['X-Requested-With'] = 'XMLHttpRequest'
  elif ext == "png":
    headers['Accept'] = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    headers['Sec-Fetch-Dest'] = 'image'
    headers['Sec-Fetch-Mode'] = 'no-cors'
  if accept:
    headers.update({'Accept': accept})
  if csrf:
    headers['X-CSRF-TOKEN'] = csrf
  headers['Referer'] = referer or URL_INDEX
  if cip:
    headers['Cip'] = cip
  return headers


SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")


class Session:
  def __enter__(self):
    self.s = requests.Session()
    if os.path.exists(SESSION_FILE):
      with open(SESSION_FILE) as f:
        data = json.load(f)
      for c in data["cookies"]:
        self.s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
      self.crypt = JSCrypto(self.s, make_headers, serialized=data["crypt"])
      self.csrf = data["csrf"]
      if self.session_valid():
        logging.info("Existing session is valid, skipping login")
      else:
        self.login()
    else:
      self.login()
    return self

  def session_valid(self) -> bool:
    """Check if the loaded session is still valid on the server."""
    r = self.s.get(URL_INDEX, headers=make_headers(), allow_redirects=False)
    # A logged-out session is redirected to newLogin.jsp, which the server
    # serves over plain HTTP (port 80). Following that redirect hangs, so
    # detect the logout without following it.
    if 300 <= r.status_code < 400 and 'newLogin' in r.headers.get('Location', ''):
      logging.info('Session is logged out (index.jsp redirected to login page)')
      return False
    # A valid session loads index.jsp; an expired one redirects to newLogin.jsp.
    r = self.s.get(URL_INDEX, headers=make_headers())
    valid = "index.jsp" in r.url
    logging.debug(f"Session valid: {valid} (final url {r.url}, status {r.status_code})")
    return valid

  def __exit__(self, *_):
    cookies = [
        {"name": c.name, "value": c.value, "domain": c.domain,
         "path": c.path, "secure": c.secure}
        for c in self.s.cookies
    ]
    data = {
      "cookies": cookies,
      "crypt": self.crypt.serialize(),
      "csrf": self.csrf,
    }
    with open(SESSION_FILE, "w") as f:
      json.dump(data, f, indent=2)
    print(f"Session saved to {SESSION_FILE}")

  def login(self):
    URL_LOGIN = HOST + "/mobiledoc/jsp/webemr/login/newLogin.jsp"
    URL_PUBKEY = HOST + "/mobiledoc/jsp/webemr/login/authenticate/getRsaPublicKey"
    URL_CAPTCHA = HOST + "/mobiledoc/jsp/uadmin/simpleCaptcha.png?bogus={}"
    URL_LOGIN2 = HOST + "/mobiledoc/jsp/webemr/login/authenticate/verifyUname"
    URL_LOGIN2r = HOST + "/mobiledoc/jsp/webemr/login/authenticate/getPwdPage"
    URL_LOGIN3 = HOST + "/mobiledoc/jsp/webemr/login/authenticate/processLoginRequest"

    # response sets JSESSIONID, ApplicationGatewayAffinity, and ApplicationGatewayAffinityCORS cookies
    r = self.s.get(URL_LOGIN, headers=make_headers())
    csrf = get_csrf(r.text)
    logging.debug("pubkey")
    pub_r = self.s.get(URL_PUBKEY, headers=make_headers(accept='application/json'))
    pub = pub_r.json()['publicKey']

    logging.debug("genkey")
    self.crypt = crypt = JSCrypto(self.s, make_headers, rsa_key=pub)
    crypt.genkey('loginDataEncGCM', URL_LOGIN, csrf)
    # also requestEnc, perenc, fileTransfer

    logging.debug("Send username")
    data = {"username": crypt("lingj"), "password": "", "lParam": "", "aParam": "", "_csrf": csrf}
    r = self.s.post(URL_LOGIN2, data=data, headers=make_headers())
    soup = BeautifulSoup(r.text, 'lxml')
    csrf = soup.find('meta', attrs={"name": "_csrf"})["content"]
    is_captcha = soup.find('input', id='isCaptcha')['value']
    print(f'{is_captcha=}')
    # "captcha": captcha

    # get captcha
    # t = time.time_ns() // 1_000_000
    # print(URL_CAPTCHA.format(t))
    # print(make_headers(ext='png', referer=URL_LOGIN2r))
    # r = self.s.get(URL_CAPTCHA.format(t), headers=make_headers(ext='png'))
    # r.raise_for_status()
    # with open('/srv/allen/ecw/captcha.png', 'wb') as f:
    #   r.raw.decode_content = True
    #   shutil.copyfileobj(r.raw, f)
    # captcha = input("captcha")

    logging.debug("Login")
    now = datetime.now()
    data = {
      'action': '1013',
      'username': crypt("lingj"),
      'turnstileResponse': '',
      # hex_sha1(MD5(pass)) from validateForm() at
      # https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/login/newLoginStep2.jsp
      'password': crypt("99924fc424e59ab9629a88474ee95393ee30528c"),
      'selectModuleName': '',
      'lParam': crypt("10"), # password length
      'aParam': crypt("Y"), # contains numbers and non-numbers
      'chasip': crypt(crypt.ip),
      'guideParam': crypt("yes"), # checkPwdAgainstGuidelines
      'userPswdStrength': '3',
      'clientLoginTime': now.strftime(f'%Y-{now.month}-{now.day} %H:%M:%S'),
      'evaOnlyLogin': 'false',
      'pluginParam': '',
      '_csrf': csrf,
      # 'enableADAuth: ': '',
      # 'enableADAuthSSO': '',
      # 'isCaptcha': is_captcha,
    }
    r = self.s.post(URL_LOGIN3, data=data, headers=make_headers(referer=URL_LOGIN2r))
    if "Username or Password was incorrect" in r.text:
      with (DIR / 'error.html').open('w') as f:
        f.write(r.text)
      assert False
    self.csrf = get_csrf(r.text)
    # gets /mobiledoc/jsp/webemr/login/loginSuccess.jsp, which is empty
    # gets /mobiledoc/jsp/webemr/landing.html, which redirects to /mobiledoc/jsp/webemr/indexVB.jsp#/landing
    # https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/index.jsp#/mobiledoc/jsp/webemr/jellybean/officevisit/officeVisits.jsp
    # Top frame is mobiledoc/jsp/webemr/indexVB.jsp
    # /mobiledoc/jsp/catalog/xml/getEncounters.jsp?eDate=2024-04-01&doctorId=122&CompressXML=Yes is alphanumeric

    # /mobiledoc/jsp/catalog/CheckLabsWeb.jsp?tabOnId=1&labs=True&imgs=True&procs=True&electronic=True&inHouse=True&sendOut=True&pId=0&PtName=select%20patient&facilityId=0&loginUserId=122&sortBy=0&sortOrder=DESC&pageNo=1&rowsPerPage=18&LabItemId=0&LabName=&DIItemId=0&DIName=&FromDate=04/02/2023%2012:00%20AM&ToDate=04/01/2024%2012:00%20AM&assignedToIds=0&userId=0&ProcItemId=0&ProcName=&ShowOnlyHighPriority=False&future=False&showRevCC=False&outstanding=True&received=True&reviewed=True&approvalstatus=False&facType=0&callingForm=LabDIProc&strFilterByDate=0

  def post(self, url: str, data: dict | str = "", get: bool = False, code: bool = True, referer: str = ''):  # params: dict | None = None
    """if code, add rnd2 and pd."""
    if not code:
      if get:
        r = self.s.get(HOST + url, headers=make_headers(referer=referer))
        assert r.status_code == 200
        return r
    assert not url.endswith('?')
    ts = f"&timestamp={int(datetime.now().timestamp()*1000)}"
    ts = "&timestamp=1783917152978"
    # 3/9/26 &rnd2={random.random()} before ts not needed?
    URL_APPEND = f"sessionDID=122&TrUserId=122&Device=webemr&ecwappprocessid=0{ts}&clientTimezone=America/Los_Angeles"
    url += ('&' if '?' in url else '?') + URL_APPEND
    if isinstance(data, dict):
      data = requests.models.RequestEncodingMixin._encode_params(data)
    # https://cabahcapp.ecwcloud.com/mobiledoc/jsp/wro/pnt_2.js interceptor
    if get:
      headers = make_headers(cip=self.crypt.cip, csrf=self.csrf, referer=referer)
      # breakpoint()
      # only if ".jsp" in url
      gd = sha256(urllib.parse.unquote(url.split('?')[1]).replace('+', ' ').encode('ascii')).hexdigest()
      url += f"&gd={gd}"
      r = self.s.get(HOST + url, headers=headers)
    else:
      headers = make_headers(post=True, cip=self.crypt.cip, csrf=self.csrf, referer=referer)
      pd = sha256(url.encode('ascii') + data.encode('ascii')).hexdigest()
      r = self.s.post(HOST + url + f"&pd={pd}", data=data, headers=headers)
    assert r.status_code == 200, r.text
    return r



if __name__ == "__main__":
  session = Session()
  key = "MxuQCdC07l1ncZui9iTrJn4P1Q9H/DZoCo87igb3oB8="
  iv = "eydXw6e+pyWe7inW"


"""

  @cache
  def hub(self, mrn: str):
    # includes <td align="right" width="22%" class="hubNormalText">&nbsp;&nbsp;Insurance:&nbsp;</TD> <TD title="Blue Card Program" class="hubNormalText"><b>Blue Card Program</b></td></tr>
    return self.post(f'/mobiledoc/jsp/catalog/patienthub.jsp?pid={mrn}&empiEnabled=0&EncCount=0&ApptCount=0&disableclicks=False&redirect=1', get=True).text

  @cache
  def get_patient_inquiry_detail(self, mrn: str) -> str:
    # Patient hub > account inquiry. This returns claims by date without the encounter id.
    # Includes ClaimId, BilledFee, Paid, Adjustment, WithHeld.

    # ins_paid = 0
    # adj = 0
    # for payment in claim.find_all('Payment'):
    #   assert payment.PayorType.text == '1', payment.PayorType.text
    #   ins_paid += Decimal(payment.paid.text)
    #   adj += Decimal(payment.Adjustment.text)
    #   'charge': claim.Charge.text,
    #   'PtBalance': claim.PtBalance.text,
    #   'InsBalance': claim.InsBalance.text,
    #   'billing_notes': claim.BillingNotes.text,
    data = f"PatientId={mrn}&FromDate=2012-01-01&ToDate={datetime.now().strftime('%Y-%m-%d')}&BalanceFilter='All'&Balance=Claim+Balance&Facility=0&FacilityGroup=0&InsFilter=Insurance&AssignTo=All&InsorGrpId=0&InsAllChked=1&NoOfStmts=0&ClmWoColl=0&CollCodes=&Practice=0&ShowVoid=0&CaseId=0&rows=100&page=1&fromScreen=patienthub&badDebt=0"
    return self.post('/mobiledoc/jsp/catalog/xml/edi/getPatientInquiryDetail.jsp', data).text

  def populate_pt_pic(self, mrn: str):
    return self.post('/mobiledoc/jsp/dashboard/PopulatePtPic.jsp', data=f'ptId={mrn}&picName={mrn}.jpg', code=False).text

  def get_gr_patients(self, mrn: str) -> str:
    # not useful, guarantor info
    r = self.post(f'/mobiledoc/jsp/uadmin/getGrPts.jsp?GrId={mrn}', get=True)

  def check_if_patient_has_alerts(self, mrn: str) -> str:
    # not useful. returns MuAlert, MUMissingFields, BillingAlert, GlobalAlert.
    r = self.post('/mobiledoc/jsp/webemr/billingalert/checkIfPatientHasAlerts.jsp', data={'patientId': str(mrn)})
    assert r.text, r.text
    return r.text

  def providers(self):
    url = '/mobiledoc/jsp/webemr/uadmin/requestHandler.jsp?requestFor=getUsers&requestJSON=%7B%22userList%22%3A%22All%22%2C%22searchBy%22%3A%22Name%22%2C%22searchText%22%3A%22%22%2C%22userId%22%3A%22122%22%2C%22pageNo%22%3A1%2C%22userType%22%3A5%2C%22rowsPerPage%22%3A%221000%22%2C%22sortDir%22%3A%22ASC%22%2C%22sortBy%22%3A%22fullname%22%7D'
    with open(DIR / 'providers.json', 'w') as f:
      f.write(self.session.post(url, get=True).text)

  def add_cpt_raw(con):
    # sql_write(con, '''CREATE TABLE IF NOT EXISTS pay_cpt (mrn TEXT, enc TEXT, claim TEXT, payment TEXT, paymentDetail TEXT, `date` TEXT, name TEXT, cpt TEXT, payer TEXT, billed TEXT, allowed TEXT, deduct TEXT, paid TEXT, adjustment TEXT, withheld TEXT)''')
    # sql_write(con, 'CREATE UNIQUE INDEX IF NOT EXISTS payment_cpt ON pay_cpt(paymentDetail, cpt, claim)')
    df = pd.read_csv(DIR / 'cpt.csv')
    del df['pt']
    del df['item']
    df.to_sql('pay_cpt', con, if_exists='append', index=False)

  def add_claims_raw(con):
    # add from enc_claim files
    sql_write(con, '''CREATE TABLE IF NOT EXISTS claim (claim TEXT NOT NULL PRIMARY KEY, encounter TEXT NOT NULL, mrn TEXT, `date` TEXT, visittype TEXT, amount TEXT, payment TEXT, balance TEXT)''')
    rows = []
    for file in (DIR / 'enc_claim').iterdir():
      data = read_claim(file)
      if file:
        rows.append(data)
    df = pd.DataFrame(rows)
    df.to_sql('claim', con, if_exists='append', index=False)

  def add_payments2(con):
    # this returns payments actually
    rows = []
    for file in (DIR / 'get_patient_inquiry_detail').iterdir():
      with open(file) as f:
        xml = BeautifulSoup(f.read(), 'xml')
        for claim in xml.find('claim'):
          if not claim.ClaimId:
            continue
          rows.append({
            'claim': claim.ClaimId.text,
            'encounter': claim.EncounterId.text,
            'mrn': claim.PatientId.text,
            'date': claim.ServiceDate.text,
            'visittype': claim.visittype.text,
            'amount': claim.amount.text,
            'payment': claim.payment.text,
            'balance': claim.balance.text,
          })
    df = pd.DataFrame(rows)
    df.to_sql('claim', con, if_exists='append', index=False)

  
  # df.drop_duplicates(subset=drop, keep='last', inplace=True, ignore_index=True)
  # df.to_sql(table, con, if_exists='append', index=False)

"""