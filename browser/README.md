# ecw

`automate.py` automates medical clinic tasks via playwright.

You can use `playwright-cli -s=e <command>` for developing.

automate.py connects and drives an already-running eCW browser session.

Functions:

`_login(page)`: fills the username and password and waits for the login pages to go away.

`lab()`: opens the Labs jellybean via the `Ctrl+Shift+L` keybind, falling back to clicking the "L" nav link.

Favorites
- Open left nav: click star (`#jellybean-panelLink5`) or hamburger (`#jellybean-panelLink4`) at top left
- Star opens Favorites (`#jcarousel3`) and hamburger opens menu (`#jcarousel2`). Can click `#next-fav` to switch between the two.

Payments
- Click "Payments" in Favorites
- Press `F3` to open `#insPmt` dialog to open a nested `#insurance-lookup-modal` panel
- Select Payer
  - Type `hpmg` into `#insurance-lookup-modal input#insuranceList`
  - Click first result in the dropdown.
  - Click panel's `.btn-lblue` OK button to confirm, which closes the lookup modal
- Fill Payment Fields
  - Enter total amount in `#insPaymentAmount`
  - select "Non Payment Data": press `Tab` once and `Down` arrow 5 times
- Once the payment is posted, open its Payment Advisory (button on bottom left), add the 835 claim via the Claim ID box + Enter, and open the claim's Payment Posting dialog. Its CPT Payments table is `#CPTDataTable`, one row per service line: Service Dt, POS, Units, Code, Billed, FS Allowed, Balance, then the row's inputs Allowed, Deduct, CoIns, CoPay, Paid, Adjust, Withheld, Code.
- Write Off: in the Payment Posting dialog's Financial Adjustments section, `F9` ("Write Off $X") appends a claim-level adjustment row to `#pmtPosting-finAdj-table` (today's date, code `CAS: 234`, amount = the full remaining balance; inputs `paymentPostingMedicareIpt10/11/12ngR0` = date/code/amount) and disables the button once the balance is covered. `Alt+P` ("Post CPT") opens the Adjustment Posting dialog (`#adjustmentPosting`) to allocate the write-off to service lines: only the Amount column is editable (`#adjustmentPostingIpt1ngR<n>`, n = row index), Balance is read-only, and the column Total recomputes on blur; OK allocates it and the finAdj row's first column then shows the posted amount.

`write_off(page, claim)` (called at the end of `_fill_claim_cpt_table()`, with the claim's Payment Posting dialog open)
- Writes the lines' patient-responsibility amounts off to the CPT lines: `F9` adds a write-off row (CAS: 234, amount = the remaining balance, which after the CPT table is filled equals the copay + coins total; skipped when a row already exists or is already posted), then `Alt+P` opens the Adjustment Posting dialog
- Each of the dialog's service rows (Service Dt, Units, Code, Description, read-only Balance, Amount input `#adjustmentPostingIpt1ngR<n>`) is matched to an 835 line by Code and filled with that line's copay (CAS reason 3) + coins (reason 2); the column Total must equal the dialog's Adjustment Amount, then OK allocates the write-off line by line
- Skipped unless the claim's copay + coins total is > $0 and < $1; the Payment Posting dialog is left open for review/saving
- When a claim is posted (`F3`), a balance of >= $1 is noted in the dialog's Billing Notes and the "The balance is …" bootbox is answered Yes; otherwise the run waits for the recomputed Net Balance to reach 0.00 before posting
- A negative Net Balance (the case's patient payments exceed the claim's copay + coins total, e.g. an unneeded patient payment) is posted as usual: the run skips the 0.00 Net Balance wait and answers the "The balance is …" bootbox Yes if F3 raises it

`fill_claims()` (the `payment` subcommand; run with the claim's CPT table open)
- For each service line of the first 835 claim, match the table row by (Service Dt, Units, Code, Billed) and warn on mismatch (falls back to the first row with the same code); warn if no row has the code
- Fill Allowed = the 835 B6 amount in the row's `#paymentPostingMedicareIpt1ngR<n>` input (skipped when the service has no B6 amount, e.g. OA-246 denied lines), and Paid = the SVC paid amount in `#paymentPostingMedicareIpt5ngR<n>` (n = row index)
- Filling Allowed makes the app recompute Adjust (Billed - Allowed) on its own; Adjust is never typed
- The dialog is left open for review/saving. To reset the screen: click Close (F11), if asked "Do you want to save" click No (alt N)

`patient(patient_name="Zhu, Lingyu")`
- Open patient-lookup modal via "Action" jellybean panel link (`#jellybean-panelLink65`)
- Fill `#searchText` with the patient name (search by "Name" is automatic)
- Wait for a result row in `#patient-lookup-screen .tablebody`
- Click patient name in the top result row (the span with the `Launch Patient Hub` tooltip) to launch the Patient Hub
- Wait for `.modal-title` starting with `Patient Hub`
- Closes a leftover `#patient-lookup-screen` modal or an already-open Patient Hub (`#patient-hub`/`#patient_hub` with the `in` class) first so reruns are idempotent.

## commands

- `python automate.py [payment]` - no subcommand defaults to `payment` (fill the open claim's CPT table from the 835 file, then, when the lines' copay + coins total is under $1, write it off via F9 / Post CPT)
- `python automate.py login` - log in to the portal
- `python automate.py lab` - open the Labs page
- `python automate.py patient [name]` - launch the Patient Hub for a patient

## playwright tips

- eCW uses the same `id` on the base page and inside dialogs (eg `#insuranceList`), and the page matches first. Scope selectors to the dialog container.
- Open modals: `div.modal.in`
- Closing a dialog may remove it from the DOM entirely.
- URL might not reflect the actual screen. It's a SPA where URL only updates sometimes.
- `playwright-cli snapshot` reassigns `ref=eNNN` on every call, so diffing two snapshots shows reference churn rather than real changes.
