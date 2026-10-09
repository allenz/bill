SELECT cpt, name, MAX(CAST(paid AS FLOAT)) AS pay, MAX(date) AS date, COUNT(*) AS count
FROM
  (SELECT pay_cpt.cpt, pay_cpt.name, SUM(pay_cpt.paid) AS paid, pay.date
  FROM pay_cpt
  LEFT JOIN pay USING (paymentDetail)
  WHERE pay.payorName = "Medicare"
  AND pay_cpt.claim != 10565 -- Overpaid
  GROUP BY pay_cpt.claim, pay_cpt.cpt)
INNER JOIN top_cpt USING (cpt)
GROUP BY cpt
HAVING MAX(CAST(paid AS FLOAT)) > 0
AND MAX(date) > "2022-01-01"
ORDER BY top_cpt.cpt_volume DESC;

-- Find overpaid claims
-- eCW first import on 4/7/2021
SELECT pay_cpt.cpt, pay_cpt.name, pay_cpt.claim, SUM(pay_cpt.paid) AS paid, pay.date
FROM pay_cpt
LEFT JOIN pay USING (paymentDetail)
WHERE pay.payorName = "Medicare" AND cpt = 99214
AND pay_cpt.claim NOT IN (10565, 42256, 37098, 37154, 37178, 38531, 43906, 11609, 11812) -- Overpaid
GROUP BY pay_cpt.claim, pay_cpt.cpt
HAVING SUM(pay_cpt.paid) > 200
