import requests
from lxml import etree
from tqdm import tqdm

from scrape_ecw import Client, DIR

HEADERS = {
  'User-Agent': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; Trident/7.0; .NET4.0C; .NET4.0E; Tablet PC 2.0; Zoom 3.6.0; Zoom 3.6.0)'
}

INDEX = DIR / 'docs' / 'all.xml'

def list_docs(count=20):
  # TODO create incremental version which paginates and stops once we see a document that we've already saved.
  # count=10000 to get all
  URL = f'/mobiledoc/jsp/catalog/xml/fax/FaxInboxLogs.jsp?pagination=true&FtpInboxPath=mobiledoc/faxinbox&MaxCount={count}&Counter=0&AllFacilities=NO'
  with (DIR / 'docs' / 'docs.xml').open('wb') as f:
    r = client.post(URL, data='FormData=')
    f.write(r.content)

# with INDEX.open('rb') as f:
  # data = f.read()
  # root = fromstring(data)

def get_file(file, out):
  with (DIR / 'docs' / f'{out}.tif').open('wb') as f:
    URL = f'/mobiledoc/ecwimage?filename={file}&ftpusername=&filepath=mobiledoc/faxinbox&operation=download'
    r = client.post(URL, get=True)
    f.write(r.content)

client = Client()
(DIR / 'docs').mkdir(exist_ok=True)
root = etree.parse(INDEX).getroot()
rows = root[0].xpath('return/Rows')[0][1:]
# breakpoint()
rows = [row for row in rows if row.find('Logdatetime').text > '20241108']
for row in tqdm(rows):
  # date = row.find('Date').text
  file_id = row.find('ID').text
  logdatetime = row.find('Logdatetime').text
  file = row.find('File').text
  if logdatetime > '20241108':
    get_file(file, f'{logdatetime}_{file_id}')
