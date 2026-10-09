import pathlib
import re
import pickle
from urllib.parse import unquote_plus, quote_plus
import json
from tqdm import tqdm

from store import Store

DIR = pathlib.Path.home() / 'Downloads'
TEMPLATE = pathlib.Path.home() / 'Desktop/ecw/payment_posting_medicare.html'

FN_NAME = "paymentPostingMedicareInit("
RE_DOB = r"<p>DOB <strong>(\d{2}/\d{2}/\d{4})</strong>"
RE_SEX = r"<p>Sex <strong>(M|F|)</strong></p>"
RE_NAME = r'<strong class="fnt14 blue_txt">([^<>]+)</strong></p>'


def encode(data, write_template=False, check=True):
  pay = {}

  pre_arg, rest = data.split(FN_NAME, maxsplit=1)
  args, post_call = rest.split(')', maxsplit=1)
  (
    pay['payment'], pay['mrn'], pay['posting'], z1,
    pay['paymentDetail'], pay['unk1'], t1, t2, z3, name_enc, e1, payor_enc,
    z4, z5, e2, x1, x2, xml1_enc, xml_enc, *const
  ) = args.split(',')
  # see 71 for an example of backslashes
  pay['name'] = unquote_plus(name_enc[1:-1]).replace(r'\-', '-')
  pay['payor'] = unquote_plus(payor_enc[1:-1])
  pay['dob'] = re.search(RE_DOB, post_call).group(1)
  pay['sex'] = re.search(RE_SEX, post_call).group(1)
  pay['name_short'] = re.search(RE_NAME, post_call).group(1)

  # xml
  xml1 = unquote_plus(xml1_enc[1:-1])
  prefix1, xml1 = xml1.split('<return>', maxsplit=1)
  xml1, postfix1 = xml1.split('</return>', maxsplit=1)
  pay['xml1'] = xml1

  xml = unquote_plus(xml_enc[1:-1])
  prefix, xml = xml.split('<return>', maxsplit=1)
  xml, postfix = xml.split('</return>', maxsplit=1)
  pay['xml'] = xml
  assert prefix1 == prefix
  assert postfix1 == postfix

  if write_template:
    post_call = post_call.replace(pay['posting'], '@posting@')
    post_call = post_call.replace(pay['dob'], '@dob@')
    # example of a difference: PP9
    post_call = post_call.replace(pay['name_short'], '@name_short@')
    post_call = re.sub(RE_SEX, f"<p>Sex <strong>@sex@</strong></p>", post_call, count=1)

    parts = [
      pre_arg.replace(pay['posting'], '@posting@'),
      FN_NAME,
      "@payment@,@mrn@,@posting@,0,",
      "@paymentDetail@,@unk1@, true,true,0,'@name_enc2@','','@payor_enc@',",
      f"0,0,'',{x1},{x2},",
      f"'{quote_plus(f'{prefix}<return>')}@xml1_enc@{quote_plus(f'</return>{postfix}')}',",
      f"'{quote_plus(f'{prefix}<return>')}@xml_enc@{quote_plus(f'</return>{postfix}')}',",
      f"{','.join(const)})",
      post_call
    ]
    with TEMPLATE.open('w') as f:
      f.write(''.join(parts))

  if check:
    def quote(s):
      return quote_plus(s).replace('%2A', '*')

    subs = pay.copy()
    subs['name_enc'] = quote(pay['name'])
    subs['name_enc2'] = quote(pay['name']).replace('-', r'\-')
    subs['payor_enc'] = quote(pay['payor'])
    subs['xml_enc'] = quote(pay['xml'])
    subs['xml1_enc'] = quote(pay['xml1'])

    with TEMPLATE.open() as f:
      template = f.read()
    for k, v in subs.items():
      template = template.replace(f'@{k}@', v)

    if template != data:
      for i, (a, b) in enumerate(zip(template, data)):
        if a != b:
          print('data loss at ', i)
          print('original', data[i-20:i+30])
          print('decoded ', template[i-20:i+30])
          assert False
  return json.dumps(pay)


store = Store(pathlib.Path.home() / 'Desktop/ecw/pm.sqlite3')
out = Store(pathlib.Path.home() / 'Desktop/ecw/pm2.sqlite3')
for i in tqdm(range(1, 85332)):
  row = store.get('payment_posting_medicare', i)
  if row:
    store.con.execute(store.INSERT_Q, ('payment_posting_medicare', i, encode(row)))
  store.con.commit()

# posting = 71
# path = pathlib.Path.home() / 'Desktop/ecw/payment_posting_medicare' / f'{posting}.html'
# with path.open() as f:
#   data = f.read()
# # encode(data, write_template=True)
# # encode(data)
