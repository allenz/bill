"""SQLModel tables for the billing database (see config.py)."""
import uuid
# Without alias, Encounter date: date field type would resolve to the field and
# not datetime.date.
from datetime import date as Date, datetime

import sqlalchemy as sa
from sqlmodel import Field, Session, SQLModel


class Patient(SQLModel, table=True):
    """One patient, from the  plus insurance info.

    Mostly added by db.py add_patients() which calls search_patient (ECW
    patient search).
    """
    mrn: int = Field(primary_key=True)  # ControlNo, falls back to pt.id
    name: str | None = None
    previous_name: str | None = None  # <PreviousName>
    dob: Date | None = None
    sex: str | None = None
    is_self_pay: bool | None = None
    active: bool | None = None  # search_patient <Status>: 0 = active, 1 = inactive
    deceased: bool | None = None  # search_patient <Deceased>
    is_test: bool | None = None  # test/template patient, hand-maintained (the API has no reliable flag)
    insurance: str | None = None
    member_id: str | None = None
    group_id: str | None = None
    coinsurance: str | None = None
    comember_id: str | None = None
    cogroup_id: str | None = None
    insurance_id: int | None = None
    coinsurance_id: int | None = None
    ssn: str | None = None
    up_phone: str | None = None  # home phone, ECW <upPhone>
    gr_phone: str | None = None  # ECW <GrPhone>
    email: str | None = None
    address: str | None = None
    address2: str | None = None  # <address2>, unit/apartment
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    cell_phone: str | None = None  # <mobileno>, when it differs from up_phone
    preferred_name: str | None = None  # <formatedPrefName>, falls back to <preferredName>
    external_mrn: str | None = None  # search_patient <MedicalRecNo>, "External MRN: "
    updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    # when this patient's encounters were last fetched via db.py patient_encounters()
    encounter_updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))

    # from fetch_patient_note (yellow sticky), not search_patient.
    # Never NULL: an empty sticky is ''.
    yellow_note: str = ''
    yellow_updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))


class Encounter(SQLModel, table=True):
    """One patient visit, from the ECW schedule feed.

    To lookup by claim, go to Claims and enter claim number. This calls
    getClaimsList() and get_billing_claim_json(). The latter calls
    billingClaim.jsp and getBillingClaimDetails.jsp. The UI also calls
    getInsuranceData.jsp (not implemented in client) and claimFollowData().

    encounter has at most one claim.
    claim has multiple payment_details, and a payment_detail has multiple pay_cpt.
    Also a claim has multiple cpts, and a cpt has multiple pay_cpt.

    Rows are written by db.py process_schedule() and add_claim()
    """
    id: int = Field(primary_key=True)
    claim: int | None = None
    date: Date | None = None
    mrn: int
    # 1 current, 2 telemed, 5 virtual, 6 web, 7 ePrescription
    type: int | None = Field(default=None, sa_type=sa.SmallInteger)
    reason: str | None = None
    # telenc "Message" field from the right panel (printChartOptions.jsp),
    # set by db.py teleweb_details()
    message: str | None = None
    # telenc "Refills" field, shown in the right panel instead of Message
    # when the call resulted in prescription refills
    refills: str | None = None
    # telenc "Answered By" field from the right panel: the staff member
    # who took the call
    answered_by: str | None = None
    dr: str | None = None
    visittype: str | None = None

    # set by db.py add_claim()
    billed: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    paid: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    balance: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))

    # editable fields in billing report, owned by app.py
    due_date: Date | None = None
    assignee: str | None = None
    task: str | None = None
    notes: str | None = None

    # New columns from the ECW doctor schedule API
    appt_start: str | None = None  # e.g. 06:00
    appt_end: str | None = None
    # appointment status (pStatus) FIN/CHK/CANC/Switch/N-S/R-S/N-A
    status: str | None = None
    is_billable: int | None = None  # billableVisitStatus
    claim_required: int | None = None
    # 1 eligible, 3 ineligible, 5 not verified, 7 self pay
    eligibility_status: int | None = None
    general_notes: str | None = None  # apptCard.generalNotes, staff per-appointment notes
    note: str | None = None  # dashboard progress note SOAP envelope XML, db.py progress_notes()
    # when the dashboard progress note was last saved to note by db.py progress_notes()
    note_updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    new_pt: bool | None = None  # newPt, new patient flag
    updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))


class Lab(SQLModel, table=True):
    """One lab or imaging report, from the ECW labs list view.

    client.labs(date) POSTs labs/requestHandler.jsp  (JellyBean list view).
    More detail per report: client.lab_report(lab_id, enc_id, mrn), client.lab_results_json(lab_id), client.lab_request_json(lab_id).

    Rows are upserted by add_labs()/update_lab_result() in db.py.
    """
    id: int = Field(primary_key=True)  # ReportId

    # (itemName, value, units, range, flag, paramNotes)
    # Writer: db.py update_lab_result(lab_id), from client.lab_results_json(lab_id).
    # LabDataDetailJSONArray has one entry per report, including prior results for the same item on earlier encounters.
    result: str | None = None  # JSON string

    itemid: int | None = None  # lab type eg CMP
    encounter_id: int | None = None
    patientname: str | None = None
    mrn: int | None = None  # patient MRN
    name: str | None = None  # lab item name (e.g. "CMP"), not the patient name
    date: Date | None = None  # order date
    coll_date: Date | None = None
    coll_time: str | None = None
    result_date: Date | None = None
    from_lab_id: int | None = None
    interface_status: str | None = None  # e.g. "Received-LabCorp OG", "Manually Reconciled - SimonMed Rad Bi"
    status: int | None = None  # 0 outstanding, 1 reviewed
    type: int | None = None  # 0 for labs, 1 for imaging
    encounter_type: int | None = Field(default=None, sa_type=sa.SmallInteger)  # 1 for current, 5 for virtual
    priority: int | None = Field(default=None, sa_type=sa.SmallInteger)  # 1 for urgent


class Pay(SQLModel, table=True):
    """One payment row from Billing > Payments (getPayment.jsp).

    pay can have any number of pay_claim rows, possibly for different patients.
    Can have 0 pay_claim rows, e.g. pay 19922, an insurance Non PayClaim Data.
    Multiple pay_claim rows, e.g. patient payment 16622.
    Writer: db.py add_payments()
    """
    __tablename__ = "pay"
    payment: int = Field(primary_key=True)
    # date we record the payment, different from checkDate
    posted_date: Date | None = None
    paid: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    payor_id: int | None = Field(default=None, sa_type=sa.Integer)
    payor_name: str | None = None
    payor_type: int | None = Field(default=None, sa_type=sa.SmallInteger)  # 1 for insurance payments, 2 for patient
    posted_by: str | None = None
    era_detail: str | None = None
    payment_type: str | None = None
    deleted: bool | None = None
    created: datetime | None = Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )


class PayClaim(SQLModel, table=True):
    """One payment detail row, "Claims Paid" for a pay entry.

    A single claim payment can have multiple payment_detail.
    Patient payments do not have any payment detail.
    Rows are upserted by add_payments() in db.py from client.get_claims()
    (getPaymentDetails.jsp for insurance payments, receivePayments.jsp for
    patient payments).

    Columns are nullable.
    """
    __tablename__ = "pay_claim"
    __table_args__ = (
        sa.UniqueConstraint("payment", "claim", "payment_detail"),
        sa.Index("ix_pay", "payment"),
        sa.Index("idx_payclaim_paymentdetail", "payment_detail"),
    )

    # Surrogate key: patient payments have claim and payment_detail NULL, and
    # PostgreSQL (unlike SQLite) does not allow NULLs in a primary key. Rows
    # are deleted and re-inserted per payment by db.py _set_pay(); the
    # (payment, claim, payment_detail) tuple stays unique via the constraint
    # below (as in SQLite, NULLs are distinct, so a payment can have several
    # claim-less details).
    id: int = Field(default=None, sa_column=sa.Column("id", sa.Integer, sa.Identity(always=True), primary_key=True))
    payment: int | None = None
    claim: int | None = None
    payment_detail: int | None = Field(default=None, sa_type=sa.Integer)
    posted_date: Date | None = None
    paid: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))  # amount for this payment_detail, not the total payment
    payor_id: int | None = Field(default=None, sa_type=sa.Integer)
    payor_name: str | None = None
    payor_type: int | None = Field(default=None, sa_type=sa.SmallInteger)
    posted_by: str | None = None
    era_detail: str | None = None
    date: Date | None = None
    encounter: int | None = None
    mrn: int | None = None
    allowed: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    adjustment: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    deduct: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))  # per-claim deductible, repeated per payment_detail
    msg_code: str | None = None
    payment_type: str | None = None
    name: str | None = None
    created: datetime | None = Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )


class PayCpt(SQLModel, table=True):
    """One CPT row within a payment detail, "Post CPT" for a pay_claim entry.

    Rows are upserted by add_payments() -> _get_cpts() in db.py from
    paymentPostingMedicare.jsp. (payment_detail, cpt) is unique; created
    falls back to the DB default when the row omits it.
    """
    __tablename__ = "pay_cpt"
    __table_args__ = (
        sa.Index("ix_pay_cpt_payment", "payment", "cpt"),
    )

    # (payment_detail, cpt) is the unique key (unique index payment_cpt in the DB)
    payment_detail: int = Field(primary_key=True, sa_type=sa.Integer)
    cpt: str = Field(primary_key=True)
    mrn: int | None = None
    name: str
    billed: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    paid: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    adjustment: float | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    date: Date | None = None
    created: datetime | None = Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )
    claim: int | None = None
    payment: int | None = None


class ClaimCpt(SQLModel, table=True):
    """One CPT line billed on a claim, from the billing claim JSON.

    Rows are upserted by add_claim_cpt() in db.py (parse_claim of
    client.get_billing_claim_json()).
    """
    __tablename__ = "claim_cpt"

    # unique index claim_cpt_ix (claim, cpt) in the DB
    claim: int = Field(primary_key=True)
    cpt: str = Field(primary_key=True)
    name: str
    billed: float = Field(sa_type=sa.Numeric(12, 2))
    mod1: str | None = None  # modifier eg GY, WT
    mod2: str | None = None
    mod3: str | None = None
    mod4: str | None = None
    icd1: str | None = None
    icd2: str | None = None
    icd3: str | None = None
    icd4: str | None = None
    desc1: str | None = None
    desc2: str | None = None
    desc3: str | None = None
    desc4: str | None = None
    units: int | None = None
    # cpt lines removed from the claim. we exclude these from the report.
    deleted: bool = False


class Message(SQLModel, table=True):
    """Incoming text message."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_sid: str = Field(max_length=64, unique=True, index=True)  # alphanumeric
    account_sid: str = Field(max_length=64)  # alphanumeric
    is_outbound: bool | None = None
    from_number: str = Field(max_length=30, index=True)  # has leading plus
    to_number: str = Field(max_length=30)
    body: str | None = None
    media_urls: list[str] | None = Field(default=None, sa_type=sa.JSON)
    status: str = Field(max_length=30)
    # Stored in PostgreSQL as TIMESTAMPTZ (values are UTC).
    created_at: datetime = Field(sa_type=sa.DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=sa.DateTime(timezone=True))

    @classmethod
    def from_webhook(cls, data: dict[str, str]) -> "Message":
        """Build a Message from the form fields Twilio POSTs to the webhook."""
        n_media = int(data.get("NumMedia", 0))
        # MediaUrl0..N for MMS attachments
        media_urls = [data[f"MediaUrl{i}"] for i in range(n_media)] if n_media else None
        return cls(
            message_sid=data["MessageSid"],
            account_sid=data["AccountSid"],
            is_outbound=False,
            from_number=data["From"],
            to_number=data["To"],
            body=data.get("Body"),
            media_urls=media_urls,
            status=data.get("Status", "received"),
            created_at=datetime.fromisoformat(data["DateCreated"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["DateUpdated"].replace("Z", "+00:00")),
        )


class Block(SQLModel, table=True):
    """Block on calendar to prevent appointments.

    id is the ECW block id, parsed from the schedule JSON's "blk:<id>:<provider>".
    """
    id: int = Field(primary_key=True)
    start: datetime = Field(nullable=False)
    end: datetime = Field(nullable=False)
    title: str = Field(nullable=False)
    comments: str = Field(nullable=False)
    encounter_count: int = Field(nullable=False)

    # set by save_block.py
    updated: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))


class Insurance(SQLModel, table=True):
    """One insurance company, hand-maintained. Joined from the report and
    claim_info queries on the (trimmed) patient.insurance name."""
    insurance: str = Field(primary_key=True)
    phone: str | None = None
    party: str | None = None  # 1P or 3P
    ppo: int | None = None  # 1 for PPO plans, 0 otherwise
    comment: str | None = None


class Users(SQLModel, table=True):
    """Login for the web app (app.py /login, PBKDF2-SHA256)."""
    name: str = Field(primary_key=True)
    hash: str
    salt: str
