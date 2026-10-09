from pathlib import Path
from xml.etree import ElementTree as ET
import pandas as pd
from decimal import Decimal

DIR = Path.home() / 'Desktop/ecw'
root = ET.parse(DIR / 'payments.xml')

def parse_payments():
  # Find all 'payment' elements within 'payments'
  payments = root.find('.//payments').findall('payment')

  df = pd.DataFrame([{
      "paymentLock": int(payment.find('paymentLock').text),
      "paymentId": int(payment.find('paymentId').text),
      "amount": Decimal(payment.find('amount').text),
      "checkNo": payment.find('checkNo').text,
      "ClosingId": int(payment.find('ClosingId').text),
      "checkDate": payment.find('checkDate').text,
      "PostedAmount": Decimal(payment.find('PostedAmount').text),
      "ProviderId": int(payment.find('ProviderId').text),
      "PostedDt": payment.find('PostedDt').text,
      "PaymentDt": payment.find('PaymentDt').text,
      "docUpdate_flag": payment.find('docUpdate_flag').text,
      "BatchId": payment.find('BatchId').text,
      "postedBy": payment.find('postedBy').text,
      "payorType": int(payment.find('payorType').text),
      "payorId": int(payment.find('payorId').text),
      "payor": payment.find('payor').text,
      "DocAttached": payment.find('DocAttached').text,
      "ERAPayments": int(payment.find('ERAPayments').text),
      "BatchName": payment.find('BatchName').text,
      "ParentPaymentId": int(payment.find('ParentPaymentId').text),
      "DeletePaymentCheck": int(payment.find('DeletePaymentCheck').text),
      "depositDate": payment.find('depositDate').text,
      "isCollectionPayment": int(payment.find('isCollectionPayment').text),
      "voidPayment": int(payment.find('voidPayment').text),
      "PaymentType": payment.find('PaymentType').text
    } for payment in payments
  ])

  # https://stackoverflow.com/questions/20209600/pandas-dataframe-remove-constant-column
  df.loc[:, (df != df.iloc[0]).any()]

  # Print the dataframe
  print(df.head())
  df.to_csv(DIR / 'payments.csv')

def reconcile_bank():
  from openpyxl import load_workbook, Workbook, utils
  wb = load_workbook('C:/Users/az/Dropbox/accounting/Ledger.xlsx', read_only=True)
  try:
    data = wb['Book'].values
    header = next(data)
    df = pd.DataFrame(data, columns=header)
  finally:
    wb.close()

  df = df[(df.Date > '2023-10-01') & (df.Account == 8127) & (df.Category == "400. Revenue from patients")]
  amounts = set(Decimal(x) for x in df.Amount if x > 0)

  payments = pd.read_csv(DIR / 'payments.csv')
  payments = payments[payments.PaymentType == "Check"]
  payments.reset_index(inplace=True)
  payments["conf"] = [v in amounts for v in payments.amount]
  payments.to_csv(DIR / 'payments_rec.csv')

# July to December
# Every visit should have a claim.
# Claim

# Office > Encounter > Patient Info > Billing Info

# print(df.head())

# ledger = pd.read_xlsx()

# df.read_csv(DIR / 'payments.csv')
