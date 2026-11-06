# eCW client code

Payments list view (`paymentsListView.jsp`), the **Payment Advisory** modal, and the claim **Payment Posting** dialog.

## App architecture

- JSP endpoints
- All requests must use URL from global `makeURL()`, which adds required params
- **AngularJS 1.x + jQuery** on a single page. `window.angular` is global.
  Controllers expose everything on their element's scope; minified but
  readable sources can be dumped with `fn.toString()`.
- Angular
  - `angular.element(el).scope()` gives the scope bound to `el`
  - `scope.$parent` walks up
  - controller state (e.g. `paymentId`, `allClaimIds`, `getClaimIdsByPaymentId`) was found on the scope of `#pmtAdvisoryModal` (depth 0).
  - UI-Grid scope in `grid.appScope.ecwScope` (advisory controller), `grid.options.data` (full array), `grid.rows[].entity` (row data), `grid.columns[].name`. Not much in the actual grid element `#gridaccountlkup`.
- Visible tables: `document.querySelectorAll('table')` where `offsetParent !== null`
- Script files: search in `document.querySelectorAll('script[src]')`
  - Requires session; fetch in-page with XMLHttpRequest

   ```
   /mobiledoc/jsp/webemr/webpm/payments/js/paymentsLookupController.js
   /mobiledoc/jsp/webemr/webpm/payments/js/paymentAdvisoryController.js   ← the advisory
   /mobiledoc/jsp/webemr/webpm/js/claimProcessErrorService.js
   /mobiledoc/jsp/webemr/webpm/js/paymentPostingMedicare.js
   /mobiledoc/jsp/webemr/webpm/js/spectrum.js
   /mobiledoc/jsp/webemr/webpm/js/angular-spectrum-colorpicker.min.js
   ```

## 3. Payments screens (DOM structure, observed)

### Payments list view (`paymentsListView.jsp`)

- `table#paymentsList` - payment records: (checkbox/cells), **Payment ID**
  (e.g. `41208`), **Payment From** (payer or patient name), payment type
  (`Non Payment Data`), Date, Check/Deposit dates, **Amount**, Posted,
  Balance. Plus `#paymentsListViewTbl1..4` (filter/summary panels).
- `div.col-sm-3.bppleft table#pmtPoting-payment-table`: the case's
  Payment(s) table (Paid, Date, Pmt No, Payer)
  - rows with Payer `Patient` are the patient payments (`_patient_payments()` in `run_payment.py`)

### Payment Advisory modal

DOM chain (open state):

```
div.modal.fade.app-modal-window.bluetheme.advisory-mod.in     ← "in" = open
└─ .modal-dialog.ui-draggable
   └─ .modal-content
      └─ #pmtAdvisoryModal (ng-scope = advisory controller's $scope)
         ├─ #pmtAdvisory<timestamp>        (inner re-created per open)
         ├─ #PaymentAdvisory-frame<timestamp>  (empty "managed-iframe"; the grid is NOT in it)
         ├─ #paymentAdvisoryModalBody
         │   ├─ #paymentAdvisoryTbl1/Tbl2  header: Payer, Payment ID, ERA File ID,
         │   │                              Check Amount, Payment Date, Posted Amount,
         │   │                              Balance (strong[data-ng-bind="paymentId"] etc.)
         │   ├─ toolbar ("Claims Posted" section):
         │   │   Add Claims (F2) #addClaimId · Claim ID #txtClaimID · Go (F3) #goclickId
         │   │   · CPT claim box #paymentAdvisoryIpt10 · Post CPT (F4) #postcptId
         │   │   · Scan (F5) #paymentAdvisoryScanBtn · View ERA #paymentAdvisoryBtn3 (often hidden)
         │   │   · Delete #btndelID · Show Msg Codes #btnshowMsgCodeId · Filter #pibuttonprevidfilter
         │   └─ #gridaccountlkup           UI-Grid "Claims Posted"
         └─ #paymentAdvisoryBtn1 (× close)
```

Header values bind to `paymentId`, `payment.amount` (check amount),
`totalPaid` (posted amount), `payment.amount - totalPaid` (balance).

**The claims grid** (`#gridaccountlkup`, ui-grid, in the *parent* document -
not the iframe): columns `voidFlag, rowindex, reviewed("E"=exception),
invoiceId (Claim #), statusDesc, serviceDate, patientName, invoiceAmount
(Billed), allowed, deduct, coins, memberBalance, paid, adjustment,
withheld, MsgCode, ClmBalance, dirtyflag`. Row entity keys include
`PmtDetailId, encounterId, invoiceId, patientId, patientName, serviceDate,
invoiceAmount, allowed, deduct, coins, memberBalance, paid, adjustment,
withheld, MsgCode, ClmBalance, voidFlag, reviewed, ERACASPostedAsIs`.
`grid.options.data` holds the full list (client-side; the `page`
object `{currentPage, itemsPerPage, perPageCounts}` only drives paging).

> Gotcha: ui-grid keeps an offscreen
> `.ui-grid-a11y-ariascreenreader-speakable` announcer div that holds the
> *last announced* row value (e.g. a claim number announced earlier). It
> leaks into `innerText` dumps and looks like a rendered row, but is not
> grid data.

**Controller state** (`grid.appScope.ecwScope` ≡ scope of
`#pmtAdvisoryModal`), observed keys: `paymentId`, `screenId`,
`parentScreen ("payments")`, `claimId`, `cptClaim`, `selectedClaimIndex`,
`isClaimsDirty`, `allClaimIds` (claim id → [pmt detail ids]), totals
(`totalBilled/Allowed/Deduct/Coins/Copay/Paid/Adjustment/Withheld/Balance`),
`page`, flags (`bClaimIdVisible`, `bViewERAVisible`, `bDisableGo`, …), and
the methods listed below.

## 4. Key controller logic (read from `paymentAdvisoryController.js`)

### Duplicate-posting check - the app's source of truth for "already posted"

```js
// called on load / before adds: sync $.ajax POST
//   /mobiledoc/jsp/catalog/xml/getPaymentDetails.jsp?paymentId=<id>&allclaimids=true
// -> $scope.allClaimIds = JSON.parse(response)   // {claimId: [pmtDetailIds]}
getClaimIdsByPaymentId = function () { $scope.allClaimIds = {}; /* sync $.ajax as above */ }

containItem = function (invId) {
  if ($scope.allClaimIds && $scope.allClaimIds.hasOwnProperty('' + invId + '')) {
    $scope.existingLastClaimId = invId;
    return true;
  }
  return false;
}

addClaim = function (claims, hasClaimBal) {
  $scope.getClaimIdsByPaymentId();              // fresh server fetch first
  for (...) {
    if (containItem(claims[ii].InvId)) {
      // native confirm():
      // "The payment for the claim number <id> is already posted in the
      //  current payment advisory.\nDo you want to post another payment
      //  for the same claim?\n\nOK - Post one more payment to the claim
      //  \nCancel  - Open existing posting"
      // !confirm -> loadExistingClaim=true (Cancel path) and skip the add
    }
    // else: build row {PmtDetailId:0, invoiceId, ...} and push to the grid
  }
}
```

### Per-claim "Go" path (Claim ID box + Enter)

```
#txtClaimID keypress 13 (Enter) → claimIdKeyPress → goClick()
  → validateInvoiceId / getNewInvId (recreated/void claims) / facility-perm check
  → goContinue()
      → sync POST /mobiledoc/jsp/catalog/xml/edi/getInvGenData.jsp?InvId=<id>
      → setInvGenData(result)
          → misc-revenue / practice-mismatch guards
          → $scope.addClaim(claimArray, true)   ← the duplicate check above
          → $scope.loadPostCpt()                ← opens the claim's Payment
                                                 ← Posting dialog (#CPTDataTable)
```

So **both** the bulk add (F2 / ERA import) and the per-claim Go path funnel
through `addClaim` → `allClaimIds`. Any automation that wants to know which
claims are "already posted in the current payment advisory" should read that
same map rather than re-deriving it from the grid (the grid can show a
filtered/stale view, and the a11y announcer is not data).

Other endpoints seen in the same file: `getnewInvoiceId.jsp?invoiceid=`,
`/modules/webemr/InvoiceCtrl/checkInvFacPerm/<invId>/<userId>` (GET),
`getPatientInfo.jsp?patientId=`, `getClaimForPrescriptionNumbers.jsp`,
`ValidateInvoiceId.jsp?invoiceid=`.

### Insurance Payment dialog (#insPmt) and its Insurance Lookup panel

paymentsListView.jsp inline script has the dialogue load handler
- fresh payment, empty payer -> open lookUpInsurance(); else focus #insPaymentAmount.
- button#insBtnSel also runs lookUpInsurance().
- lookUpInsurance() sets ng-include url to makeURL("/mobiledoc/jsp/webemr/webpm/payments/insurance-modal.jsp").
  - jsp panel markup contains the search box bound to `selectClaimIns`
  - jsp trailing script calls `.modal('show')`.
- Clicking a result in the panel's `insurance` directive fires its
setClaimIns() which sets scope InsId.
- Note that there is a HTTP fetch delay before #insurance-lookup-modal shows.
- Never open the panel with a pointer click on #insBtnSel: the button
  sits in #insPmt, which the in-flight panel's auto-show covers before
  the click's hit-test retries pass (Playwright reports the modal as
  "intercepting pointer events"). Call
  `angular.element('#insPmt').scope().lookUpInsurance()` via evaluate
  instead, then wait for #insurance-lookup-modal to be visible.
  Confirmed payer = that scope's `_payerName` (non-empty).
