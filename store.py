from pathlib import Path
import sqlite3
import bs4
from bs4 import BeautifulSoup
from time import sleep
import zstandard as zstd

DIR = Path('/srv/allen/ecw')


class Store:
  INSERT_Q = 'REPLACE INTO cache(method, name, data) VALUES (?, ?, ?)'

  def __init__(self, path):
    self.con = sqlite3.connect(path)

  def get(self, method, name):
    q = f'SELECT data FROM cache WHERE method = "{method}" AND name = "{name}"'
    r = self.con.execute(q)
    data = list(r)
    return DECOMP.decompress(data[0][0]).decode() if data else None  # first row, first value

  def put(self, method, name, value):
    self.con.execute(self.INSERT_Q, (method, name, COMP.compress(value.encode('utf8'))))
    self.con.commit()


CACHE = Store(DIR / 'cache.sqlite')
with (DIR / 'dict').open('rb') as f:
  dict_data = zstd.ZstdCompressionDict(f.read())
  COMP = zstd.ZstdCompressor(dict_data=dict_data)
  DECOMP = zstd.ZstdDecompressor(dict_data=dict_data)


def cache(func):
  """Caches calls to func.

  Caching only looks at positional args. kwargs are passed through, so new
  kwargs will not cause a new function call unless the positional args are also
  new. The cache key joins args into a string with separator '-'.

  The cached function returns BeautifulSoup XML objects by default.

  Pass the refresh kwarg to invalidate the cache.
  """
  def wrapper(cls, *args, **kwargs) -> bs4.element.Tag:
    refresh = kwargs.pop('refresh', False)
    f = func.__name__
    is_xml = not (f.endswith('html') or f.endswith('json'))

    arg = '-'.join(str(a) for a in args)
    result = None if refresh else CACHE.get(f, arg)
    if result is None:
      result = func(cls, *args, **kwargs)
      CACHE.put(f, arg, result)
      print(f, arg)
      sleep(.5)
    return BeautifulSoup(result, 'xml') if is_xml else result
  return wrapper

"""
CREATE TABLE IF NOT EXISTS cache (
  method TEXT NOT NULL,
  name TEXT NOT NULL,
  data TEXT NOT NULL,
  date TEXT DEFAULT (strftime('%Y-%m-%d %H:%M', 'now', 'localtime')))
);
CREATE UNIQUE INDEX ix_cache ON cache(method, name);

INSERT INTO cache(method,name,data,date)
SELECT method, SUBSTR(name, 1, LENGTH(name)-5) AS name, data, date FROM cache
WHERE method = 'payment_posting_medicare' AND name LIKE '%.html';

DELETE FROM cache WHERE method = 'payment_posting_medicare' AND name LIKE '%.html';
"""
