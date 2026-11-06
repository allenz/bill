"""Note: you can debug the live browser via `playwright-cli -s=e <command>`."""
import re

import edi_835_parser
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
    expect,
)

from custom_browser import get_wrapper, get_endpoint
from util import prepare, login, open_nav, PWD_STEP

# Billing > Payments page (menu item #PAYMENTS_BILLING opens paymentsListView.jsp)
PAYMENTS_URL_MARKER = "paymentsListView"
BILL_PATH = "Y:/allen/uploads/835-365204.txt"
# BILL_PATH = "d.txt"
# Payer name to look up in the Insurance Payment dialog (#insPmt) that
# F3 opens on the payments list view (case sensitive)
PAYER_NAME = "HPMG"


async def _payer_set(page):
    """Whether the #insPmt dialog's scope has a confirmed payer
    (_payerName non-empty)."""
    return await page.evaluate(
        """
        () => {
            const el = document.querySelector('#insPmt');
            if (!el) return false;
            const sc = angular.element(el).scope();
            return !!(sc && sc._payerName);
        }
        """)


async def _select_payer(page):
    """Open the Insurance Payment dialog (#insPmt) from the payments
    list view via F3 and select the payer in its nested "Insurance
    Lookup" panel (#insurance-lookup-modal).

    If the dialog is already open (e.g. from a previous run), reuse it
    instead of pressing F3 again. The panel is loaded via
    data-ng-include (insurance-modal.jsp), and that page's inline script
    auto-shows the modal when the included page arrives, so after F3 it
    may not be in the DOM yet - it is waited for (below) instead of
    checked once. A single check races the async fetch: the payer
    selection is silently skipped, then the panel arrives, auto-shows
    and its overlay intercepts every click on the dialog's fields. When
    the panel is missing or closed (a rerun of a dialog whose panel the
    app removed after an earlier confirmation) it is armed the way the
    dialog's "Sel" button (#insBtnSel) does - by calling the controller
    scope's lookUpInsurance() via evaluate. A pointer click on that
    button is not safe: it sits in #insPmt, which the in-flight panel's
    auto-show covers before the click's hit-test retries pass, so the
    click is intercepted by the very modal it was meant to open.

    Typing the payer name populates the panel's results dropdown (its
    own <ul>; several other .insuranceLookup dropdowns exist on the
    page but stay hidden). The first result must be clicked to register
    the selection (setClaimIns(), which also sets the dialog's
    _payerName for a fresh payment) before the panel's blue OK button
    (.btn-lblue) is pressed; OK then closes the panel, leaving #insPmt
    open.
    """
    if not await page.locator("#insPmt.in").count():
        await page.keyboard.press("F3")
        await page.locator("#insPmt.in").wait_for(
            state="visible", timeout=5_000)

    # A rerun with the payer already confirmed reuses the dialog as-is
    # (reopening the lookup would needlessly re-run the selection).
    if await _payer_set(page):
        return

    lookup = page.locator("#insurance-lookup-modal")
    if not (await lookup.count() and await lookup.is_visible()):
        # Not open: either F3's ng-include fetch of the panel is still
        # in flight, or a reused dialog removed/hidden it. Arm it the
        # way the dialog's "Sel" button (#insBtnSel) does, via the
        # controller scope - without a pointer click, which the
        # in-flight panel's auto-show would intercept (the button sits
        # in #insPmt, under the modal the fetch's inline script shows).
        armed = await page.evaluate(
            """
            () => {
                let sc = angular.element(
                    document.querySelector('#insPmt')).scope();
                while (sc && typeof sc.lookUpInsurance !== 'function')
                    sc = sc.$parent;
                if (!sc) return false;
                sc.lookUpInsurance();
                return true;
            }
            """)
        if not armed:
            raise RuntimeError("could not find the #insPmt controller "
                               "scope to open the insurance lookup")
    await lookup.wait_for(state="visible", timeout=30_000)

    # The lookup box duplicates the payments filter's id
    # (#insuranceList), so scope it to the lookup panel.
    ins_input = lookup.locator("input#insuranceList")
    await ins_input.wait_for(state="visible", timeout=15_000)
    await ins_input.click()
    # Replace any text left by a previous run
    await page.keyboard.press("Control+a")
    await page.keyboard.type(PAYER_NAME)

    # The panel's results dropdown; the other .insuranceLookup
    # dropdowns on the page (the payments filter's) stay hidden.
    results = lookup.locator(
        "ul.dropdown-menu.search-drop.fac_look.lookupDown.insuranceLookup")
    await results.wait_for(state="visible", timeout=30_000)
    # Click the first result to register the selection (the last <li>
    # is the Previous/Next pager, not a payer)
    await results.locator("li").first.click()

    # The panel's blue OK button (the only .btn-lblue in the panel; the
    # main dialog OK is #insurancePaymentBtn10) closes the panel.
    await lookup.locator(".btn-lblue").click()
    await lookup.wait_for(state="hidden", timeout=30_000)
    # Payer is now shown in the dialog header next to the "Sel" button
    # (`#insBtnSel`) which opens the lookup modal.
    if not await _payer_set(page):
        raise RuntimeError(
            f"the payer lookup closed without confirming a payer "
            f"(expected {PAYER_NAME!r})")


async def _fill_payment_fields(page, total):
    """Fill the Insurance Payment modal's Amount and Type fields.

    The #insPmt modal stays open after the payer lookup is confirmed.
    The Amount field (#insPaymentAmount) holds a 0.00 default, which is
    replaced with the total from the 835 file. The Type select
    (#insurancePaymentselect1) defaults to Cash; one Tab from the
    Amount field focuses it and five Down arrows walk the selection to
    "Non Payment Data" (the last option, which the browser stops at, so
    re-runs are a no-op).
    """
    amount = page.locator("#insPmt #insPaymentAmount")
    await amount.wait_for(state="visible", timeout=30_000)
    lookup = page.locator("#insurance-lookup-modal")
    if await lookup.count() and await lookup.is_visible():
        # The lookup panel would intercept the click below (its included
        # script can auto-show it again); re-run the (idempotent) payer
        # selection to confirm the payer and close it.
        await _select_payer(page)
    await amount.click()
    # Replace the 0.00 default
    await page.keyboard.press("Control+a")
    await page.keyboard.type(f"{total:.2f}")
    print(f"Entered amount {total:.2f} into the payments modal.")

    # One Tab from the Amount field focuses the Type select; five Down
    # arrows walk Cash to the last option, "Non Payment Data".
    await page.keyboard.press("Tab")
    type_sel = page.locator("#insPmt select#insurancePaymentselect1")
    for _ in range(5):
        await page.keyboard.press("ArrowDown")
    if await type_sel.input_value() != "Non Payment Data":
        # Arrow keys can wrap in some browsers; select it directly
        await type_sel.select_option(value="Non Payment Data")
    print('Set payment type to "Non Payment Data".')


# The open "Payment Posting" dialog shows the claim's CPT Payments table
# (#CPTDataTable), one row per service line: Service Dt, POS, Units, Code,
# Billed, FS Allowed, Balance, then the row's inputs Allowed,
# #paymentPostingMedicareIpt1..7ngR<n> are Allowed, Deduct, CoIns, CoPay,
# Paid, Adjust, Withheld (n = row index; the 8th input is a message-code
# box). Filling Allowed makes the app recompute Adjust (Billed - Allowed)
# on its own, so only Allowed and Paid are entered here.
CPT_COL = {"Service Dt": 0, "Units": 2, "Code": 3, "Billed": 4}
ALLOWED_INPUT_PREFIX = "paymentPostingMedicareIpt1ng"
COINS_INPUT_PREFIX = "paymentPostingMedicareIpt3ng"
COPAY_INPUT_PREFIX = "paymentPostingMedicareIpt4ng"
PAID_INPUT_PREFIX = "paymentPostingMedicareIpt5ng"
ADJUST_INPUT_PREFIX = "paymentPostingMedicareIpt6ng"
# #pmtPosting-finAdj-table rows (the claim-level write-offs F9 adds):
# Ipt10 = date, Ipt11 = code (e.g. CAS 234), Ipt12 = amount
FINADJ_AMT_INPUT_PREFIX = "paymentPostingMedicareIpt12ng"


def patient_adjustment(service_loop, reason_code):
    """Total of the line's CAS (service adjustment) amounts with the given
    X12 reason code: '3' = Co-payment Amount, '2' = Coinsurance Amount,
    '1' = Deductible Amount."""
    return sum(adj.amount for adj in service_loop.adjustments
               if adj.reason_code.code == reason_code)


def payer_adjustment(service_loop):
    """Payer-side write-off for the line: the CAS amounts in the CO
    (contractual, e.g. CO-45 fee schedule) and OA (other/overpayment,
    e.g. denials) groups. Unlike Billed - Paid - CoIns - CoPay this also
    covers denied lines and is unaffected by deductible (PR-1) or other
    patient-responsibility codes."""
    return sum(adj.amount for adj in service_loop.adjustments
               if adj.group_code.code in ('CO', 'OA'))


async def _patient_payments(page):
    """Total of the case's patient payments: the rows of the Payment(s)
    table on the payments list view (div.col-sm-3.bppleft >
    table#pmtPoting-payment-table; columns Paid, Date, Pmt No, Payer)
    whose Payer is "Patient". 0.0 when the table is not on the page."""
    table = page.locator("div.col-sm-3.bppleft table#pmtPoting-payment-table")
    if not await table.count():
        return 0.0
    return await table.evaluate(
        "t => [...t.rows].reduce((sum, r) =>"
        " r.cells[3] && r.cells[3].textContent.trim() === 'Patient'"
        " ? sum + parseFloat(r.cells[0].textContent) : sum, 0)")


async def _find_cpt_row(rows, count, used, service_loop):
    """Find the CPT table row of a service line, matching Service Dt,
    Units, Code and Billed against the table cells. Returns (row index,
    mismatch descriptions); the index is None when no unused row has the
    service's code, and the descriptions are non-empty when the matched
    row's cells differ from the 835 values."""
    service = service_loop.service
    expected = {
        "Service Dt": (service_loop.service_date.date.strftime("%m/%d/%Y")
                       if service_loop.service_date else None),
        "Units": f"{service.billed_units:.2f}",
        "Code": service.code,
        "Billed": f"{service.charge_amount:.2f}",
    }
    fallback = None
    for i in range(count):
        if i in used:
            continue
        cells = {name: (await rows.nth(i).locator("td").nth(col).inner_text()).strip()
                 for name, col in CPT_COL.items()}
        if cells["Code"] != expected["Code"]:
            continue
        diffs = [f"{name}: table {cells[name]} vs 835 {expected[name]}"
                 for name in expected
                 if expected[name] is not None and cells[name] != expected[name]]
        if not diffs:
            return i, []
        if fallback is None:  # keep the first code match as a fallback
            fallback = (i, diffs)
    if fallback is not None:
        return fallback
    return None, [f"no table row with code {expected['Code']}"]

async def _find_adj_row(line_rows, count, used, service):
    """Index of the Adjustment Posting dialog's service row for an 835
    line, matched by Code (preferring a row whose Units cell agrees,
    falling back to the first unused code match); None when no unused
    row has the code. The Balance cell cannot be used for matching: it
    reflects the live, already-adjusted line balance."""
    fallback = None
    for i in range(count):
        if i in used:
            continue
        code = (await line_rows.nth(i).locator("td").nth(2).inner_text()).strip()
        if code != service.code:
            continue
        units = (await line_rows.nth(i).locator("td").nth(1).inner_text()).strip()
        if units == f"{service.billed_units:.2f}":
            return i
        if fallback is None:
            fallback = i
    return fallback


async def write_off(page, claim, residual):
    """Write the claim's patient-responsibility amounts (copay + coins)
    off to their CPT lines.

    Called at the end of _fill_claim_cpt_table() - only when the
    patient-responsibility residual (copay + coins minus the patient
    payments already posted on the case) is > $0 and < $1 - with the
    claim's Payment Posting dialog open. F9 appends a claim-level
    write-off row to #pmtPosting-finAdj-table (code CAS: 234, amount =
    the remaining balance, which after the CPT table is filled equals
    the residual). Alt+P ("Post CPT") then opens the Adjustment
    Posting dialog (#adjustmentPosting); its service rows (Service Dt,
    Units, Code, Description, read-only Balance, editable Amount input
    #adjustmentPostingIpt1ngR<n>) render a moment after the dialog
    shell opens, so they are waited for before being matched to the
    835 lines by Code and filled with each line's copay (CAS reason
    3) + coins (reason 2), capped line by line so the written-off
    total never exceeds the residual, and OK allocates the write-off
    line by line.
    """
    # Distribute the residual across the lines in claim order, capping
    # each line at its natural copay + coins, so the write-off never
    # exceeds the residual (the part of the copay + coins not already
    # covered by patient payments posted on the case).
    remaining = residual
    lines = []
    for loop in claim.services:
        natural = (patient_adjustment(loop, "2")
                   + patient_adjustment(loop, "3"))
        amount = max(0.0, min(natural, remaining))
        lines.append((loop, amount))
        remaining -= amount
    total = sum(amount for _, amount in lines)
    if not total:
        print(f"Claim {claim.claim.marker}: no copay/coins left to "
              f"write off.")
        return

    # F9 appends the write-off row; skip it when a previous run already
    # added one. The row's first column is the amount posted to CPT
    # (0 = not yet allocated).
    modal = page.locator("div.modal.in:has(#pmtPosting-finAdj-table)")
    rows = modal.locator("#pmtPosting-finAdj-table tbody tr")
    if not await rows.count():
        await page.keyboard.press("F9")
        try:
            await rows.first.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeoutError:
            print(f"Claim {claim.claim.marker}: "
                  f"F9 did not add a write-off row.")
            return
        print(f"Claim {claim.claim.marker}: F9 added the write-off row "
              f"({total:.2f}).")
    else:
        posted = (await rows.first.locator("td").first.inner_text()).strip()
        if posted not in ("", "0", "0.0", "0.00"):
            print(f"Claim {claim.claim.marker}: write-off already posted "
                  f"to CPT ({posted}); skipping.")
            return

    # Alt+P ("Post CPT") opens the Adjustment Posting dialog
    await page.keyboard.down("Alt")
    await page.keyboard.press("p")
    await page.keyboard.up("Alt")
    dlg = page.locator("#adjustmentPosting.in")
    await dlg.wait_for(state="visible", timeout=30_000)

    # The service rows carry the Amount inputs (the dialog's patient-
    # header and column-header rows do not); like the CPT table's rows
    # they render a moment after the dialog shell becomes visible, so
    # wait for them before matching (matching early misses rows and
    # skips amounts, which then fails the total check below).
    line_rows = dlg.locator("tbody tr:has(input[id^='adjustmentPostingIpt'])")
    try:
        await line_rows.first.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeoutError:
        print(f"Claim {claim.claim.marker}: the Adjustment Posting "
              f"dialog has no service rows; nothing to write off")
        return
    count = await line_rows.count()
    used = set()
    for loop, amount in lines:
        if not amount:
            continue
        service = loop.service
        i = await _find_adj_row(line_rows, count, used, service)
        if i is None:
            print(f"WARNING: claim {claim.claim.marker} {service.code}: no "
                  f"Adjustment Posting row with the code; skipped {amount:.2f}")
            continue
        used.add(i)
        amt_input = line_rows.nth(i).locator("input")
        await amt_input.fill(f"{amount:.2f}")
        # The app recomputes the column Total on blur
        await amt_input.evaluate("el => el.blur()")
        print(f"Claim {claim.claim.marker} {service.code}: wrote off "
              f"{amount:.2f} (copay/coins)")

    # OK is only accepted when the column Total equals the dialog's
    # adjustment amount (the F9 write-off)
    header = " ".join((await dlg.inner_text()).split())
    m = re.search(r"Adjustment Amount:\s*\$\s*([\d,]+(?:\.\d+)?)", header)
    if not m:
        raise RuntimeError(f"could not read the adjustment amount from the "
                           f"Adjustment Posting dialog: {header[:200]!r}")
    adj_amount = m.group(1).replace(",", "")
    total_el = dlg.locator("strong").last
    shown = ""
    for _ in range(20):
        shown = await total_el.inner_text()
        if (shown.replace("$", "").replace(",", "").strip()
                == f"{float(adj_amount):.2f}"):
            break
        await page.wait_for_timeout(500)
    else:
        raise RuntimeError(f"claim {claim.claim.marker}: Adjustment Posting "
                           f"total {shown!r} != adjustment amount {adj_amount}")

    await dlg.locator("button:visible", has_text="OK").click()
    await dlg.wait_for(state="hidden", timeout=30_000)
    print(f"Claim {claim.claim.marker}: write-off of {total:.2f} posted "
          f"to CPT (total {shown.strip()}).")


async def _remove_stale_write_offs(page, claim):
    """Delete leftover claim-level write-off rows in
    #pmtPosting-finAdj-table for the full billed amount.

    An interrupted run that pressed F9 before the CPT table was filled
    leaves such a row behind (the write-off amount is then the claim's
    full balance, i.e. its billed amount). Left in place, write_off()
    would reuse it instead of adding a fresh row at the small residual
    balance. Clicking the row's .remove-bin span raises the app's
    "delete adjustment" bootbox; Yes removes the row.
    """
    billed_total = sum(loop.service.charge_amount for loop in claim.services)
    copay_total = sum(patient_adjustment(loop, '3') for loop in claim.services)
    rows = page.locator(
        "div.modal.in:has(#pmtPosting-finAdj-table) "
        "#pmtPosting-finAdj-table tbody tr")
    while True:
        stale = None
        amount = None
        for i in range(await rows.count()):
            row = rows.nth(i)
            amt = row.locator(f"input[id^='{FINADJ_AMT_INPUT_PREFIX}']")
            if not await amt.count():
                # locked/closed rows have no inputs and no delete bin
                continue
            value = (await amt.input_value()).strip()
            if not value:
                continue
            try:
                amount = float(value)
            except ValueError:
                continue
            if abs(amount - billed_total - copay_total) <= 0.005:
                stale = row
                break
        if stale is None:
            return
        await stale.locator(".remove-bin").click()
        confirm = page.locator(
            "div.bootbox.in:has-text('delete adjustment')")
        await confirm.wait_for(state="visible", timeout=10_000)
        await _click_bootbox_yes(confirm)
        await confirm.wait_for(state="hidden", timeout=10_000)
        print(f"Claim {claim.claim.marker}: deleted the leftover write-off "
              f"for the full billed amount ({amount:.2f})")


async def _fill_claim_cpt_table(page, claim):
    """Fill the Allowed, CoIns, CoPay, Paid, and Adjust inputs from
    claim.

    CoIns and CoPay are the CAS reason-code 2 (coinsurance) and 3
    (co-payment) amounts when the 835 reports them; lines without either
    keep the fields' 0.00 defaults.

    Finally, write_off() writes the lines' copay + coins off to the CPT
    lines via F9 and the Adjustment Posting dialog, but only when the
    residual is small (>$0 and <$1) and never more than the residual.

    Returns the patient-responsibility residual: the claim's copay +
    coins total minus the patient payments already posted on the case
    (see _patient_payments()); that is what stays on the balance when
    write_off() does not clear it (only residuals under $1 are written
    off). It is negative when the patient payments exceed the claim's
    copay + coins (the patient overpaid, e.g. an unneeded patient
    payment); fill_claims() then posts as usual (skipping the 0.00 Net
    Balance wait) and answers F3's balance confirm Yes.
    """
    modal = page.locator("div.modal.in:has(#CPTDataTable)")
    await modal.wait_for(state="visible", timeout=10_000)

    shown = re.search(r"Claim No\s*(\d+)", await modal.first.inner_text())
    if shown and shown.group(1) != claim.claim.marker:
        print(f"WARNING: dialog shows claim {shown.group(1)} but the 835 "
              f"claim is {claim.claim.marker}")

    # maybe warn if there is another payer in the payments table (see _patient_payments())

    table = modal.first.locator("#CPTDataTable")
    rows = table.locator("tbody tr")
    # The table element is in the DOM as soon as the modal shell loads;
    # its rows can arrive a moment later, so wait for them to avoid
    # matching services against an empty table (which would skip them
    # all with warnings).
    try:
        await rows.first.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeoutError:
        print(f"WARNING: claim {claim.claim.marker}: the CPT table has "
              f"no rows; all services will be skipped")
    count = await rows.count()
    used = set()
    for service_loop in claim.services:
        service = service_loop.service
        i, diffs = await _find_cpt_row(rows, count, used, service_loop)
        if i is None:
            print(f"WARNING: claim {claim.claim.marker}: {', '.join(diffs)}; "
                  f"skipped {service.code}")
            continue
        if diffs:
            print(f"WARNING: claim {claim.claim.marker} {service.code}: "
                  f"{', '.join(diffs)}")
        used.add(i)
        row = rows.nth(i)
        # Allowed is only posted for services the 835 reports a B6
        # (allowed - actual) amount for; denied lines (OA-246) are left at
        # their 0.00 default.
        if service_loop.allowed_amount is not None:
            allowed = row.locator(f"input[id^='{ALLOWED_INPUT_PREFIX}']")
            await allowed.fill(f"{service_loop.allowed_amount:.2f}")
        coinsurance = patient_adjustment(service_loop, '2')
        if coinsurance:
            coins_input = row.locator(f"input[id^='{COINS_INPUT_PREFIX}']")
            await coins_input.fill(f"{coinsurance:.2f}")
        copay = patient_adjustment(service_loop, '3')
        if copay:
            copay_input = row.locator(f"input[id^='{COPAY_INPUT_PREFIX}']")
            await copay_input.fill(f"{copay:.2f}")
        paid = row.locator(f"input[id^='{PAID_INPUT_PREFIX}']")
        await paid.fill(f"{service.paid_amount:.2f}")
        adjust = row.locator(f"input[id^='{ADJUST_INPUT_PREFIX}']")
        # The payer-side write-off (CO/OA CAS amounts, e.g. CO-45); for
        # lines the app recomputes it as Billed - Allowed.
        adjust_amount = payer_adjustment(service_loop)
        await adjust.fill(f"{adjust_amount:.2f}")
        print(f"Claim {claim.claim.marker} {service.code}: "
              f"Allowed={service_loop.allowed_amount}, "
              f"CoIns={coinsurance or 0.00}, CoPay={copay or 0.00}, "
              f"Paid={service.paid_amount}")

    # An interrupted run may have left a claim-level write-off row for
    # the full billed amount (F9 pressed before the CPT table was
    # filled); delete it so write_off() adds a fresh row at the
    # residual balance instead of reusing the stale one.
    await _remove_stale_write_offs(page, claim)

    # Write off the lines' copay + coins to the CPT lines via F9 + the
    # Adjustment Posting dialog, but only for a small residual total
    # (>$0 and <$1); larger patient responsibility stays on the balance
    copay_coins = sum(
        patient_adjustment(loop, "2") + patient_adjustment(loop, "3")
        for loop in claim.services)
    # Payments already posted as patient payments (Payment(s) table on
    # the list view) reduce the patient's remaining responsibility.
    residual = copay_coins - await _patient_payments(page)
    if 0 < residual < 1:
        await write_off(page, claim, residual)
    else:
        # Nudge the dialog to refresh itself (e.g. recompute the Net
        # Balance); without a focus change the app can keep a stale
        # value and the run stalls on the next wait.
        await page.keyboard.press("Tab")
    return residual


async def _click_bootbox_handler(box, handler):
    """Click a bootbox's Yes/No button by dispatching a click event on
    the button instead of aiming at its bounding box.

    Playwright's coordinate-based click() hangs on these bootboxes: the
    modal's own wrapper (or even <html>) intercepts pointer events at
    the button's position, so the actionability check never passes even
    though the button is visible. The app only needs a click event on
    the button, so dispatch it directly on the element.
    """
    btn = box.locator(f"button[data-bb-handler='{handler}']")
    await btn.wait_for(state="visible", timeout=30_000)
    await btn.dispatch_event("click")


async def _click_bootbox_yes(box):
    """Click a balance-confirm bootbox's Yes button."""
    await _click_bootbox_handler(box, "Yes")


async def _click_bootbox_no(box):
    """Click a bootbox's No button. Used for the Payment Posting
    dialog's "The changes have not been saved. Do you want to save?"
    prompt, where No discards the dialog's state and closes it."""
    await _click_bootbox_handler(box, "No")


async def _existing_claims(page):
    """Claim numbers already posted in the open Payment Advisory modal
    (#pmtAdvisoryModal inside its .modal.in wrapper), as a set of ints.

    The advisory's scope carries getClaimIdsByPaymentId(), which
    re-fetches the server's claim map for the advisory's payment
    (getPaymentDetails.jsp?paymentId=...&allclaimids=true; {claim id:
    [payment detail ids]}). The app's own "already posted in the
    current payment advisory" check is exactly this map, so it also
    covers claims posted by interrupted previous runs. Empty when the
    advisory is not open (a warning is printed then).
    """
    res = await page.evaluate(
        """
        () => {
            const el = document.querySelector('div.modal.in #pmtAdvisoryModal');
            if (!el) return {open: false, ids: []};
            const sc = angular.element(el).scope();
            if (!sc || typeof sc.getClaimIdsByPaymentId !== 'function')
                return {open: false, ids: []};
            sc.getClaimIdsByPaymentId();  // synchronous $.ajax re-fetch
            return {open: true, ids: Object.keys(sc.allClaimIds || {})};
        }
        """)
    if not res["open"]:
        print("WARNING: the Payment Advisory is not open; cannot tell "
              "which claims were already posted")
        return set()
    return {int(c) for c in res["ids"]}


async def _close_cpt_dialog(page, claim_marker, what):
    """Close the open Payment Posting dialog (#CPTDataTable) without
    saving it. The dialog's X button raises the "The changes have not
    been saved. Do you want to save?" bootbox; No discards the dialog's
    state and closes it. `what` describes what the dialog was (e.g.
    "a previous run left open (claim 62871)") for the log lines.
    """
    dlg = page.locator("div.modal.in:has(#CPTDataTable)")
    close_btn = dlg.first.locator(".modal-header > button.close")
    await close_btn.first.click()
    save_box = page.locator(
        "div.bootbox.in:has-text('have not been saved')")
    try:
        await save_box.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        print(f"Claim {claim_marker}: no save prompt after closing the "
              f"Payment Posting dialog {what}")
    else:
        await _click_bootbox_no(save_box)
        await save_box.wait_for(state="hidden", timeout=10_000)
    await dlg.wait_for(state="hidden", timeout=10_000)
    print(f"Claim {claim_marker}: closed the Payment Posting dialog "
          f"{what} without saving.")


def _claim_interest(raw, marker):
    """Interest posted on a claim (AMT*I), summed across the marker's CLP
    sections; None when none of them reports any. The parser keeps only a
    single AMT element per claim loop (the last one), so the amount is read
    from the raw file instead."""
    total = 0.0
    for m in re.finditer(r"CLP\*" + re.escape(marker) + r"\*", raw):
        nxt = re.search(r"CLP\*|LX\*|PLB\*|SE\*", raw[m.end():])
        section = raw[m.end():m.end() + nxt.start()] if nxt else raw[m.end():]
        for im in re.finditer(r"AMT\*I\*([0-9.]+)", section):
            total += float(im.group(1))
    return total or None


def _print_claim_lines(claim, indent="    "):
    """One line per service of the claim, in the columns the CPT table
    posting fills: code, billed, paid, the payer-side adjustment (CO/OA
    CAS amounts), the copay (CAS PR-3) and the allowed amount (AMT*B6,
    '-' when the 835 reports none)."""
    for loop in claim.services:
        svc = loop.service
        code = f"{svc.code}:{svc.modifier}" if svc.modifier else svc.code
        allowed = (f"{loop.allowed_amount:.2f}"
                   if loop.allowed_amount is not None else "-")
        print(f"{indent}{code:<10} billed={svc.charge_amount:>10.2f} "
              f"paid={svc.paid_amount:>10.2f} "
              f"adjust={payer_adjustment(loop):>10.2f} "
              f"copay={patient_adjustment(loop, '3'):>8.2f} "
              f"allowed={allowed:>10}")


async def fill_claims(page):
    # Claims already posted in the advisory (e.g. by an interrupted
    # previous run) are skipped; the set is the advisory's server-side
    # claim map, the same source the app's own duplicate-posting check
    # uses
    existing_claims = await _existing_claims(page)
    if existing_claims:
        print(f"Already posted in the payment advisory: "
              f"{', '.join(map(str, sorted(existing_claims)))}")

    txs = edi_835_parser.parse(BILL_PATH)
    claims = txs.transaction_sets[0].claims
    with open(BILL_PATH, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    noted_interest = set()
    warned_duplicates = set()
    for i, claim in enumerate(claims):
        if int(claim.claim.marker) in existing_claims:
            continue
        # e.g. a reversal and a re-payment of the same claim
        duplicates = [c for c in claims
                      if c.claim.marker == claim.claim.marker]
        if (len(duplicates) > 1
                and claim.claim.marker not in warned_duplicates):
            warned_duplicates.add(claim.claim.marker)
            print(f"WARNING: claim {claim.claim.marker} appears "
                  f"{len(duplicates)} times in the payment; the service "
                  f"lines of each entry:")
            for j, dup in enumerate(duplicates, 1):
                print(f"  entry {j} (remitt ref {dup.claim.icn}, "
                      f"status {dup.claim.status.code} "
                      f"{dup.claim.status.description}):")
                _print_claim_lines(dup)
            breakpoint()
        # AMT*I (interest) is claim-level money. maybe manually add to a cpt payment (reducing adjustment accordingly).
        interest = _claim_interest(raw, claim.claim.marker)
        if interest and claim.claim.marker not in noted_interest:
            noted_interest.add(claim.claim.marker)
            print(f"Claim {claim.claim.marker}: the 835 reports "
                  f"{interest:.2f} of interest (AMT*I) on the claim")
            breakpoint()
        # A balance confirm bootbox left open by an interrupted previous
        # run (the browser session persists) would resolve the post-F3
        # locator to two elements; answer Yes so it closes and the
        # previous claim's posting completes. The Payment Posting dialog
        # it covers closes with it; wait for that so the claim number is
        # not typed while the app is still posting.
        leftover = page.locator("div.bootbox.in:has-text('The balance is')")
        while await leftover.count():
            box = leftover.first
            body = (await box.locator(".bootbox-body").inner_text()).strip()
            await _click_bootbox_yes(box)
            await box.wait_for(state="hidden", timeout=10_000)
            dlg = page.locator("div.modal.in:has(#CPTDataTable)")
            if await dlg.count():
                await dlg.wait_for(state="hidden", timeout=30_000)
            print(f"Claim {claim.claim.marker}: dismissed the balance "
                  f"confirm left open by a previous run: "
                  f"{body.splitlines()[0]}")

        # A Payment Posting dialog left open by an interrupted previous
        # run (the browser session persists) would otherwise be filled
        # with this claim's amounts (the claim-number check below only
        # warns), so close it and discard its state first; the claim
        # number is re-entered below for the correct claim. A dialog
        # that already shows this claim is kept open: the run resumes
        # filling it instead of re-entering the claim.
        dlg = page.locator("div.modal.in:has(#CPTDataTable)")
        if await dlg.count():
            shown = re.search(r"Claim No\s*(\d+)",
                              await dlg.first.inner_text())
            if not shown or shown.group(1) != claim.claim.marker:
                await _close_cpt_dialog(
                    page, claim.claim.marker,
                    f"a previous run left open "
                    f"(claim {shown.group(1) if shown else '?'})")

        # Enter claim to show CPT table modal
        await page.locator("#txtClaimID").fill(claim.claim.marker)
        await page.keyboard.press("Enter")
        residual = await _fill_claim_cpt_table(page, claim)

        if residual >= 1:
            # The claim keeps a >= $1 patient-responsibility balance;
            # note it in the dialog's Billing Notes field before F3,
            # which raises the balance bootbox that covers the dialog
            # and would block the field.
            notes = page.locator(
                "div.modal.in:has(#CPTDataTable) #txtaBillingNotesPostCpt")
            await notes.wait_for(state="visible", timeout=30_000)
            await notes.fill("Patient's copay")
            print(f"Claim {claim.claim.marker}: noted the remaining copay "
                  f"balance ({residual:.2f}) in the billing notes.")

        if -0.005 <= residual < 1:  # half-cent tolerance for float
            # The app is slow to recompute the dialog's Net Balance after
            # the CPT table is filled (and after write_off() above); F3
            # pressed against a stale value (e.g. $26.03) surfaces the
            # "The balance is ..." confirm and posts the claim with a
            # balance that should be 0. Wait for the recomputed Net
            # Balance to reach 0.00 first; expect() raises on timeout.
            # A negative residual (the case's patient payments exceed the
            # 835's copay + coins, e.g. an unneeded patient payment) keeps
            # the Net Balance negative, so it is not waited on here: F3 is
            # pressed as usual and its balance confirm answered Yes below.
            net_balance = page.locator(
                "div.modal.in:has(#CPTDataTable) "
                "strong[data-ng-bind='newBalance']")
            await expect(net_balance).to_have_text("0.00", timeout=30_000)

        await page.keyboard.press("F3")

        # The write-off above only clears copay + coins under $1, so any
        # non-zero residual balance (>= $1 of patient responsibility, or
        # negative when the case's patient payments exceed the 835's copay
        # + coins, e.g. an unneeded patient payment) makes F3 surface a
        # bootbox confirm ("The balance is <amt>. Do you want to continue
        # without changing 'Assign claim to' anyway?"); it is expected, so
        # answer Yes so the Payment Posting dialog proceeds and closes.
        if residual < -0.005 or residual >= 1:
            # .last targets the bootbox this F3 just raised (the stale
            # ones were dismissed before the claim was entered)
            balance = page.locator(
                "div.bootbox.in:has-text('The balance is')").last
            try:
                await balance.wait_for(state="visible", timeout=2_000)
            except PlaywrightTimeoutError:
                print(f"Claim {claim.claim.marker}: expected the balance "
                      f"confirm after F3 but none appeared")
            else:
                body = (await balance.locator(".bootbox-body")
                        .inner_text()).strip()
                await _click_bootbox_yes(balance)
                print(f"Claim {claim.claim.marker}: "
                      f"{body.splitlines()[0]}: answered Yes to continue.")

        # wait until modal is closed
        modal = page.locator("div.modal.in:has(#CPTDataTable)")
        await modal.wait_for(state="hidden", timeout=10_000)

    # Click OK button to close modal
    await page.keyboard.down("Alt")
    await page.keyboard.press("o")
    await page.keyboard.up("Alt")


async def payment():
    async with get_wrapper().use_async(async_playwright()) as p:
        browser = await p.chromium.connect(get_endpoint())
        page = browser.contexts[0].pages[0]
        await prepare(page)
        print(f"Current page: {page.url}")

        # Log in first if the session is not authenticated
        if "newLogin" in page.url or PWD_STEP in page.url:
            await login(page)

        if PAYMENTS_URL_MARKER in page.url:
            print("Already on the payments page.")
        else:
            # Click the star to open the left nav; it shows the Favorites
            # carousel (#jcarousel3), which carries the "Payments" favorite.
            await open_nav(page)

            fav_link = page.locator("#jcarousel3 a[title='Payments']")
            try:
                await fav_link.first.wait_for(state="visible", timeout=5_000)
                await fav_link.first.click()
            except PlaywrightTimeoutError:
                # "Payments" is not among the favorites: switch to the main
                # menu carousel (#jcarousel2) and use the Billing > Payments
                # item (#PAYMENTS_BILLING) instead, expanding the Billing
                # submenu first.
                main_carousel = page.locator("#jcarousel2")
                if "active" not in (await main_carousel.get_attribute("class") or ""):
                    await page.locator("#next-fav").click()
                    await page.wait_for_selector(
                        "#jcarousel2.active", state="visible", timeout=10_000)
                await page.locator("#Billing_menu").click()
                await page.locator("#PAYMENTS_BILLING").click()

            await page.wait_for_url(
                lambda url: PAYMENTS_URL_MARKER in url, timeout=60_000)
            print(f"On payments page. Current page: {page.url}")

        advisory = page.locator("div.modal.in:has(#pmtAdvisoryModal)")
        if not await advisory.count():
            # F3 opens the Insurance Payment modal (#insPmt) and confirms the
            # payer; the modal stays open afterwards, so the total from the
            # 835 file is typed into its Amount field and its Type is set to
            # Non Payment Data.
            await _select_payer(page)
            txs = edi_835_parser.parse(BILL_PATH)
            total = txs.sum_payments()
            await _fill_payment_fields(page, total)

            # open Payment Advisory (button on bottom left)
            # This will create a new payment record
            await page.keyboard.down("Alt")
            await page.keyboard.press("a")
            await page.keyboard.up("Alt")

        await fill_claims(page)
