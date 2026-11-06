"""SQLModel tables for the billing database (PostgreSQL, `web` schema)."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, Session, SQLModel


class Patient(SQLModel, table=True):
    """One patient, from the ECW patient search (search_patient) plus insurance info.

    Most columns added by db.py add_patients().
    """
    mrn: int = Field(primary_key=True)  # ControlNo, falls back to pt.id
    name: str | None = None
    dob: str | None = None
    sex: str | None = None
    is_self_pay: bool | None = None
    insurance: str | None = None
    member_id: str | None = None
    group_id: str | None = None
    coinsurance: str | None = None
    comember_id: str | None = None
    cogroup_id: str | None = None
    insurance_id: int | None = None
    coinsurance_id: int | None = None
    ssn: str | None = None
    upPhone: str | None = None
    GrPhone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None

    # not provided in search_patient
    yellow_note: str | None = None
    yellow_updated: str | None = None
    cell_phone: str | None = None
    preferred_name: str | None = None

    updated: str | None = None


class Encounter(SQLModel, table=True):
    """One patient visit, from the ECW schedule feed.

    To lookup by claim, go to Claims and enter claim number. This calls
    getClaimsList() and get_billing_claim_json(). The latter calls
    billingClaim.jsp and getBillingClaimDetails.jsp. The UI also calls
    getInsuranceData.jsp (not implemented in client) and claimFollowData().

    encounter has at most one claim.
    claim has multiple payment_details, and a payment_detail has multiple pay_cpt.
    Also a claim has multiple cpts, and a cpt has multiple pay_cpt.

    Rows are written by get_encounters()/add_claim() in db.py. get_encounters()
    does a sparse true_upsert (only schedule/claim cols are sent, so other
    columns of an existing row are kept); add_claim() upserts the claim cols
    (inserts new rows for encounters not in the schedule).
    Columns map from the schedule JSON:
    encounterId -> encounter, patId -> mrn, start/apptCard.dateTime -> date
    (date part only; date is YYYY-MM-DD and used in BETWEEN/MAX),
    reason/visitReason -> reason, doctorName/provider -> dr, visitId ->
    visittype (NOT apptCard.visitType, the display label),
    generalNotes -> notes, pStatus/visitStatus -> status, POS -> pos.
    billed/paid/balance/due_date/assignee come from the claim feed, not the
    schedule.
    """
    encounter: int = Field(primary_key=True)
    claim: int | None = None
    date: str | None = None
    mrn: int
    type: str | None = None
    reason: str | None = None
    dr: str | None = None
    visittype: str | None = None
    billed: str | None = None
    paid: str | None = None
    balance: str | None = None
    due_date: str | None = None
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
    updated: str | None = None


class Lab(SQLModel, table=True):
    """One lab or imaging report, from the ECW labs list view.

    client.labs(date) POSTs labs/requestHandler.jsp (JellyBean list view).
    More detail per report: client.lab_report(lab_id, enc_id, mrn), client.lab_results_json(lab_id), client.lab_request_json(lab_id).

    Rows are upserted by add_labs()/update_lab_result() in db.py.
    id is the ReportId.
    type is 0 for labs and 1 for imaging; status is 0 = unreviewed,
    1 = reviewed. result is a JSON string set by update_lab_result().
    """
    id: int = Field(primary_key=True)  # ReportId

    # (itemName, value, units, range, flag, paramNotes)
    # Writer: db.py update_lab_result(lab_id), from client.lab_results_json(lab_id).
    # LabDataDetailJSONArray has one entry per report, including prior results for the same item on earlier encounters.
    result: str | None = None

    itemid: int | None = None  # lab type eg CMP
    encounter_id: int | None = None
    patientname: str | None = None
    patient_id: int | None = None  # patient MRN, same as patient.mrn
    name: str | None = None  # lab item name (e.g. "CMP"), not the patient name
    date: str | None = None  # order date
    coll_date: str | None = None
    coll_time: str | None = None
    result_date: str | None = None
    from_lab_id: int | None = None
    interface_status: str | None = None  # e.g. "Received-LabCorp OG", "Manually Reconciled - SimonMed Rad Bi"
    status: int | None = None  # 0 outstanding, 1 reviewed
    type: int | None = None  # 0 for labs, 1 for imaging
    encounter_type: str | None = None
    priority: str | None = None


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
    posted_date: str | None = None
    paid: float | None = None
    payor_id: str | None = None
    payor_name: str | None = None
    payor_type: str | None = None  # 1 for insurance payments, 2 for patient
    posted_by: str | None = None
    era_detail: str | None = None
    payment_type: str | None = None
    deleted: bool | None = None
    created: str | None = Field(
        default=None,
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
    payment_detail: str | None = None
    posted_date: str | None = None
    paid: float | None = None  # amount for this payment_detail, not the total payment
    payor_id: str | None = None
    payor_name: str | None = None
    payor_type: str | None = None
    posted_by: str | None = None
    era_detail: str | None = None
    date: str | None = None
    encounter: int | None = None
    mrn: int | None = None
    allowed: float | None = None
    adjustment: float | None = None
    deduct: float | None = None  # per-claim deductible, repeated per payment_detail
    msg_code: str | None = None
    payment_type: str | None = None
    name: str | None = None
    created: str | None = Field(
        default=None,
        # SQLite stored CURRENT_TIMESTAMP as UTC text; keep the same format.
        sa_column_kwargs={"server_default": sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")},
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
    payment_detail: str = Field(primary_key=True)
    cpt: str = Field(primary_key=True)
    mrn: int | None = None
    name: str
    billed: float | None = None
    paid: float | None = None
    adjustment: float | None = None
    date: str | None = None
    created: str | None = Field(
        default=None,
        # Matches the old SQLite strftime('%Y-%m-%d %H:%M', 'now', 'localtime') default.
        sa_column_kwargs={"server_default": sa.text("to_char(now(), 'YYYY-MM-DD HH24:MI')")},
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
    billed: float
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
    """Block on calendar to prevent appointments."""
    # id autoincrements (SQLite rowid equivalent); the table is currently empty
    id: int = Field(default=None, sa_column=sa.Column("id", sa.Integer, sa.Identity(always=True), primary_key=True))
    start: datetime = Field(nullable=False)
    end: datetime = Field(nullable=False)
    title: str = Field(nullable=False)
    comments: str = Field(nullable=False)
    encounter_count: int = Field(nullable=False)


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
