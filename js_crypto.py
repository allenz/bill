"""Implement client-side Javascript encryption to talk with ECW servers."""

from base64 import b64encode, b64decode
from hashlib import sha256, md5, sha1
import numpy as np
import uuid
import random
from typing import Any

try:
  from Cryptodome.Cipher import AES
  from Cryptodome.PublicKey import RSA
  from Cryptodome.Util.number import bytes_to_long, long_to_bytes
except Exception:
  print("Please run: pip install pycryptodome")
  raise


class JSCrypto:
  def __init__(self, session, make_headers, rsa_key: str|None=None, serialized: str|dict[str, Any]=None):
    """
    session: a requests.Session object. We use its post() method to send data
      to the ECW server with the correct session cookies.
    make_headers: function we can call to get ECW headers
    rsa_key: the ECW public key, which we use to share our generated session
      AES keys to the server. All other data is encrypted using AES, which is
      faster than using RSA.
    serialized: JSCrypto object to restore
    """
    self.session = session
    self.make_headers = make_headers
    if serialized:
      self.rsa_key = RSA.import_key(serialized["rsa_key"])
      self.keys = serialized["keys"]
      self.ip = serialized["ip"]
    else:
      BEGIN = b'-----BEGIN PUBLIC KEY-----\n'
      END = b'\n-----END PUBLIC KEY-----'
      self.rsa_key = RSA.import_key(BEGIN + rsa_key.encode('ascii') + END)
      self.keys: dict[str, str] = {}
      self.ip = f'{uuid.uuid4()}.local'
    self.cip = sha256(self.ip.encode('ascii')).hexdigest()

  def serialize(self) -> dict[str, Any]:
    return {
      "rsa_key": self.rsa_key.export_key().decode('utf8'),
      "keys": self.keys,
      "ip": self.ip,
    }

  def _rsa_encrypt(self, text: str) -> str:
    """Encrypt text with the server RSA public key."""
    pad = 256 - len(text) - 3
    ps = bytes(list(np.random.randint(1, 256, pad)))
    em = b'\x00\x02' + ps + b'\x00' + text.encode('ascii')
    cipher = long_to_bytes(self.rsa_key._encrypt(bytes_to_long(em)))
    return b64encode(cipher).decode('utf8')

  def genkey(self, usage, referer, csrf):
    """Generate a session AES key and share it with the ECW server.

    We make a different AES key for each usage. The ECW getCryptoAesKey()
    function generates 8 random bytes which are converted to 16 hex digits,
    and the digits are directly interpreted as the AES key bytes.
    """
    if usage == "loginDataEncGCM":
      key = b64encode(random.randbytes(32)).decode('ascii')
      iv = b64encode(random.randbytes(12)).decode('ascii')
    else:
      key = np.random.bytes(8).hex()
      # print(self._rsa_encrypt(key))
      # previous used
      iv = np.random.bytes(8).hex()
    self.keys[usage] = key, iv
    # self.keys[usage] = key
    url = "https://cabahcapp.ecwcloud.com/mobiledoc/jsp/webemr/login/authenticate/setAESKey?action=1043"
    data = {
      "encKeyValue": self._rsa_encrypt(key),
      # "encIv": self._rsa_encrypt(iv),
      "isNewAlgo": "yes",
      "usage": usage,
    }
    typ = 'json' if usage == 'loginDataEnc' else 'any'
    headers = self.make_headers(
      post=True, json=False, csrf=csrf, referer=referer, accept='*/*'
    )
    r = self.session.post(url, data=data, headers=headers)
    assert r.text == "success", r.text

  def __call__(self, text: str, usage: str = 'loginDataEncGCM', pwd = False):
    """Encrypt data with our session AES key."""
    if pwd:
      text = md5(text.encode('ascii')).hexdigest()
      text = sha1(text.encode('ascii')).hexdigest()
    key, iv = self.keys[usage]
    if usage == "loginDataEncGCM":
      # GCM (Galois/Counter Mode) is a stream-based mode that provides both encryption and authentication
      key = b64decode(key.encode('ascii'))
      iv = b64decode(iv.encode('ascii'))
      cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
      ciphertext, tag = cipher.encrypt_and_digest(text.encode('ascii'))
      combined = iv + ciphertext + tag
      return b64encode(combined).decode('ascii')
    else:
      e = len(text) % 16
      text += " " * (16 - e) if e else ""
      cipher = AES.new(key.encode('ascii'), AES.MODE_CBC, iv.encode('ascii'))
      return b64encode(cipher.encrypt(text.encode('ascii')))

# please ignore
def unused_rsa_decrypt(ciphertext: str) -> bytes:
  cipher = b64decode(ciphertext)
  em = long_to_bytes(key._decrypt(bytes_to_long(cipher)))
  text = em.split(b'\x00')[-1]

def unused_rsa_genkey():
  key = RSA.generate(2048)
  with open('private.pem','wb') as f:
    f.write(key.export_key())
  with open('public.pem', 'wb') as f:
    f.write(key.public_key().export_key())
