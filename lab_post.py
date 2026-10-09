import json
from datetime import datetime, timedelta


# lab name suffix in InterfaceStatus per fromLabId, stripped when saving labs
LAB_SUFFIXES = {
  '1': '-Quest Diagnostics',
  '2': '-SimonMed Rad Bi',
  '3': '-LabCorp OG',
}

def clean_interface_status(status: str, from_lab_id: str) -> str:
  """Strip the lab name suffix from InterfaceStatus (e.g. 'Received -Quest
  Diagnostics' -> 'Received') and rtrim the result. The dash separator may be
  absent ('Received-LabCorp OG') or surrounded by spaces
  ('Manually Reconciled - Quest Diagnostics')."""
  if not status:
    return status
  if suffix := LAB_SUFFIXES.get(from_lab_id):
    # longest tail first, so ' - Quest Diagnostics' wins over '-Quest Diagnostics'
    for tail in (' - ' + suffix[1:], ' ' + suffix, suffix):
      if status.endswith(tail):
        status = status[:-len(tail)]
        break
  return status.rstrip()

# tabOnId is the tab we want to go to.
# nType is what is sent if that tab was active before the click.
TABS = {
  "Outstanding": (0, 10),
  "To be reviewed": (1, 27),
  "Reviewed": (2, 32),
  "Future": (3, 12),
  "By patient": (4, 41),
  "All": (5, 11),
  "Cancelled": (6, 51),
}

def lab_post(from_date: str="07/12/2025", to_date: str="07/12/2026", tab: str = "All", filterDateType: int = 1):
  # filterDateType: 1 for result date, 0 for order date
  tab_id = TABS[tab][0]

  year_ago = from_date
  # pastOneYear value is 1 year before from_date on the To be reviewed tab
  # if tab == "To be reviewed":
  #   year_ago = (datetime.strptime(from_date, "%m/%d/%Y") - timedelta(days=365)).strftime("%m/%d/%Y")

  # serialize data inside a form variable
  data = {"cInHouse":True,"DIName":"","facilityid":"2","cImgs":True,"nonEPriorAuthOnly":False,"enableCCView":True,"cShowRevCC":False,"cSendOut":True,"assignToGroupId":0,"primaryServiceLocation":2,"noOfPages":0,"ePaFilterList":[{"name":"All","id":"1"},{"name":"Determination Pending","id":"2"},{"name":"Redirection","id":"3"},{"name":"Questionnaire Required","id":"4"},{"name":"Clinical Documentation Required","id":"5"},{"name":"Prior Auth Decision Pending","id":"6"},{"name":"Approved","id":"7"},{"name":"Denied","id":"8"},{"name":"Errors","id":"9"},{"name":"Prior Authorization Not Required","id":"10"}],"pageNo":1,"cHighpriority":False,"sortBy":"0","ePriorAuthOnly":False,"cLabs":True,"providerName":"All","selected":False,"DIId":0,"cOutstanding":True,"ShowUnReviewed":0,"dateFromOrig":from_date,"ProcedureId":0,"cFuture":False,"userFullName":"LING,JIE ","nId":0,"totalRows":0,"approvalFilter":False,"dateFrom":from_date,"allProvider":0,"nLabio":0,"LabId":0,"isRowsPerPageFilterExist":1,"selectedEPAStatus":"1","cProcs":True,"sortOrder":"DESC","allStaff":0,"enableDateRange":1,"callingForm":"","LabCompId":0,"facType":0,"isDefaultFilterDateTypeExists":True,"cReviewed":True,"dateRange":365,"ePARequestStatus":[{"code":"","iconName":"epa-determination-pending.svg","tooltipMessage":"Coverage Requirement Determination Pending","value":0},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Errors","value":1},{"code":"","iconName":"epa-determination-pending.svg","tooltipMessage":"Coverage Requirement Determination Pending","value":2},{"code":"","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":3},{"code":"","iconName":"epa-not-required.svg","tooltipMessage":"Prior Authorization Not Required","value":4},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Questionnaire Required","value":5},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Clinical Documentation Required","value":6},{"code":"","iconName":"epa-redirection.svg","tooltipMessage":"CRD Redirection","value":7},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Questionnaire Required","value":8},{"code":"Pending","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":9},{"code":"Pending","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":10},{"code":"Approved","iconName":"epa-approved.svg","tooltipMessage":"Prior Authorization Approved","value":11},{"code":"Denied","iconName":"epa-denied.svg","tooltipMessage":"Prior Authorization Denied","value":12},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Questionnaire Required","value":14},{"code":"Pending","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":15},{"code":"Call Payer","iconName":"epa-redirection.svg","tooltipMessage":"Redirection - Call Payer","value":17},{"code":"Cancelled","iconName":"epa-error.svg","tooltipMessage":"Cancelled By User","value":18},{"code":"Not Required","iconName":"epa-not-required.svg","tooltipMessage":"Prior Authorization Not Required","value":19},{"code":"Pending","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":20},{"code":"Pending","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":21},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Clinical Documentation Required","value":16},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Medical ePA has failed. Contact eClinicalWorks Support.","value":111},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Medical ePA has failed. Contact eClinicalWorks Support.","value":112},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Medical ePA has failed. Contact eClinicalWorks Support.","value":113},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Medical ePA has failed. Contact eClinicalWorks Support.","value":114},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Medical ePA has failed. Contact eClinicalWorks Support.","value":115},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Order Provider NPI/TIN is missing. To enter the provider NPI/TIN: Admin > Providers. Click the error icon to retrigger request for prior authorization.","value":211},{"code":"","iconName":"epa-error.svg","tooltipMessage":"Facility phone number is missing. To enter a default facility phone number: Menu > File > Facilities > Facility List. Click the error icon to retrigger request for prior authorization.","value":212},{"code":"","iconName":"epa-error.svg","tooltipMessage":"This order does not have an ICD code associated. Associate an ICD code to the order and then click the error icon to retrigger request for prior authorization.","value":213},{"code":"","iconName":"epa-error.svg","tooltipMessage":"This order does not have an CPT code associated. Associate a CPT code to the order and then click the error icon to retrigger request for prior authorization.","value":214},{"code":"","iconName":"epa-error.svg","tooltipMessage":"CPT code has been edited for this order. Click the error icon to retrigger request for prior authorization.","value":216},{"code":"","iconName":"epa-error.svg","tooltipMessage":"ICD code has been edited for this order. Click the error icon to retrigger request for prior authorization.","value":217},{"code":"","iconName":"epa-error.svg","tooltipMessage":"This order does not have an Service Type Code associated. Associate a Service Type Code  to the order and then click the error icon to retrigger request for prior authorization.","value":215},{"code":"","iconName":"epa-determination-pending.svg","tooltipMessage":"","value":107},{"code":"","iconName":"epa-not-required.svg","tooltipMessage":"Prior Authorization Not Required","value":101},{"code":"","iconName":"epa-payor-decision-pending.svg","tooltipMessage":"Prior Authorization Payer Decision Pending","value":102},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Questionnaire Required","value":103},{"code":"","iconName":"epa-docs-ques-required.svg","tooltipMessage":"Clinical Documentation Required","value":104},{"code":"","iconName":"epa-approved.svg","tooltipMessage":"Prior Authorization Approved","value":105},{"code":"","iconName":"epa-denied.svg","tooltipMessage":"Prior Authorization Denied","value":106}],"hideCancel":0,"cApprovalStatus":False,"isAutoFitEnableForJellyBean":1,"defaultViewAllReportBy":"By Patient (Unreviewed)","ProcedureName":"","cElectronic":True,"facilityName":"Bay Area Union Health Center","staffproviderName":"All","labCompanyDropdown":0,"cancelOrders":True,"nType1":-1,"patientid":0,"assignToGroupName":"","enableDateRangeOnToBeReviewedTab":0,"tabOnId":tab_id,"rowsPerPage":"100","interfaceStatus":True,"LabName":"","pastOneYear":year_ago,"dayDropdownOption":"0","providerid":"0","filterDateType":str(filterDateType),"dateTo":to_date,"cReceived":True,"staffproviderid":0,"TrUserId":122,"nType":27,"isGroupSelected":False,"groupId":0,"isAllProviderSelected":False,"isAllStaffSelected":False,"reloadData":"no","patientName":"","dayDropdown":"1","enableFilteringByOrderResultCollDate":1,"isCorrectionalEnable":False,"encodeHousingAreaFilter":"","encodeBlockFilter":""}
  return {"LJelly": json.dumps(data)}
