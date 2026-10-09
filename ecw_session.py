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


class ESession:
  def __enter__(self):
    # No up-front validity check: post() detects an expired session and
    # calls login() on demand.
    self.s = requests.Session()
    if os.path.exists(SESSION_FILE):
      with open(SESSION_FILE) as f:
        data = json.load(f)
      for c in data["cookies"]:
        self.s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
      self.crypt = JSCrypto(self.s, make_headers, serialized=data["crypt"])
      self.csrf = data["csrf"]
    else:
      self.login()
    return self

  @staticmethod
  def _expired(r: requests.Response) -> bool:
    """True if the response means the session is no longer valid.

    A logged-out session is redirected to newLogin.jsp, which the server
    serves over plain HTTP (port 80). Following that redirect hangs, so
    requests go out with allow_redirects=False and the logout is detected
    here. Code-protected endpoints instead answer 403 with a 'not
    authorized' page, and some endpoints answer 200 with a 'Sorry session'
    apology.
    """
    if 300 <= r.status_code < 400 and 'newLogin' in r.headers.get('Location', ''):
      return True
    if r.status_code in (401, 403):
      return True
    return 'Sorry session' in r.text

  def _request(self, method: str, url: str, data, headers) -> requests.Response:
    """Request without following redirects so an expired session is detected
    (see _expired) instead of hanging on the plain-HTTP login page. Any other
    redirect is followed as before. A socket timeout guards against the WAF
    accepting but never answering a throttled request."""
    r = self.s.request(method, url, data=data, headers=headers, allow_redirects=False, timeout=90)
    if 300 <= r.status_code < 400 and not self._expired(r):
      r = self.s.request(method, url, data=data, headers=headers, allow_redirects=True, timeout=90)
    return r

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
    if is_captcha != "0":
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

  def post(self, url: str, data: dict | str = "", get: bool = False, code: bool = True, referer: str = ''):  # params: dict | None = None
    """if code, add rnd2 and pd. Logs in and retries once if the session expired."""
    if not code and get:
      r = self._request('GET', HOST + url, None, make_headers(referer=referer))
      if self._expired(r):
        logging.info('Session expired, logging in')
        self.login()
        r = self._request('GET', HOST + url, None, make_headers(referer=referer))
      assert r.status_code == 200
      return r
    assert not url.endswith('?')
    ts = f"&timestamp={int(datetime.now().timestamp()*1000)}"
    URL_APPEND = f"sessionDID=122&TrUserId=122&Device=webemr&ecwappprocessid=0{ts}&clientTimezone=America/Los_Angeles"
    url += ('&' if '?' in url else '?') + URL_APPEND
    if isinstance(data, dict):
      data = requests.models.RequestEncodingMixin._encode_params(data)
    if get:
      # only if ".jsp" in url
      gd = sha256(urllib.parse.unquote(url.split('?')[1]).replace('+', ' ').encode('ascii')).hexdigest()
      url = HOST + url + f"&gd={gd}"
      body = None
    else:
      pd = sha256(url.encode('ascii') + data.encode('ascii')).hexdigest()
      url = HOST + url + f"&pd={pd}"
      body = data

    def attempt() -> requests.Response:
      # headers are rebuilt per attempt so a retry after login uses the fresh csrf
      headers = make_headers(post=not get, cip=self.crypt.cip, csrf=self.csrf, referer=referer)
      return self._request('GET' if get else 'POST', url, body, headers)

    r = attempt()
    if self._expired(r):
      logging.info('Session expired, logging in and retrying')
      self.login()
      r = attempt()
    assert r.status_code == 200, r.text
    return r



if __name__ == "__main__":
  session = ESession()
  key = "MxuQCdC07l1ncZui9iTrJn4P1Q9H/DZoCo87igb3oB8="
  iv = "eydXw6e+pyWe7inW"
