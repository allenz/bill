import psycopg2
from config import PG_DSN
# CAC=239,40%
# Chen Liangfan
conn = psycopg2.connect(PG_DSN)
cur = conn.cursor(name='audit')
q = ("SELECT l.mrn, l.name, l.result_date, l.result, p.yellow_note "
         "FROM lab l JOIN patient p ON p.mrn = l.mrn "
         "WHERE l.type = 1 AND NOT COALESCE(p.is_test, false) "
         "AND l.result IS NOT NULL AND l.result != '' AND l.name ILIKE '%CT CARD%' LIMIT 10")
cur.execute(q)
with open('tmp.txt', 'w') as f:
    for mrn, name, rdate, result, note in cur:
        # assert len(result) == 1
        f.write(f"{mrn} {rdate} {note}\n{result.replace('\\n', '\n')}\n\n")
