#!/usr/bin/env python3
"""Parse the 835 payment file and print a summary of its transactions."""

from edi_835_parser import parse

PATH = "../../allen/uploads/835-358212_1.txt"

txs = parse(PATH)

print("Claims:      ", txs.count_claims())
print("Patients:    ", txs.count_patients())
print("Total paid:  ", txs.sum_payments())
# print(txs.to_dataframe().to_string(index=False))
