"""SQLModel table for Twilio inbound webhook messages."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, Session, SQLModel


class Message(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_sid: str = Field(max_length=64, unique=True, index=True)
    account_sid: str = Field(max_length=64)
    is_outbound: bool | None = None
    from_number: str = Field(max_length=30, index=True)
    to_number: str = Field(max_length=30)
    body: str | None = None
    media_urls: list[str] | None = Field(default=None, sa_type=sa.JSON)
    status: str = Field(max_length=30)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_webhook(cls, data: dict[str, str]) -> "Message":
        """Build a Message from the form fields Twilio POSTs to the webhook.

        data contains Twilio's params: MessageSid, AccountSid, From, To,
        Body, Status, DateCreated, DateUpdated, plus NumMedia and
        MediaUrl0..N for MMS/WhatsApp attachments.
        """
        n_media = int(data.get("NumMedia", 0))
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
    id: int | None = Field(default=None, primary_key=True)
    start: datetime = Field(nullable=False)
    end: datetime = Field(nullable=False)
    title: str = Field(nullable=False)
    comments: str = Field(nullable=False)
    encounter_count: int = Field(nullable=False)


class Encounter(SQLModel, table=True):
    """One patient visit, from the ECW schedule feed.

    Rows are upserted by get_encounters()/add_claim() in db.py (REPLACE INTO,
    so a row missing a column NULLs it). Columns map from the schedule JSON:
    encounterId -> encounter, patId -> mrn, start/apptCard.dateTime -> date
    (date part only; date is YYYY-MM-DD and used in BETWEEN/MAX),
    reason/visitReason -> reason, doctorName/provider -> dr, visitId ->
    visittype (NOT apptCard.visitType, the display label),
    generalNotes -> notes, pStatus/visitStatus -> status, POS -> pos.
    billed/paid/balance/due_date/assignee come from the claim feed, not the
    schedule.
    """
    __tablename__ = "Encounter"

    encounter: int = Field(primary_key=True)
    claim: int | None = None
    date: str | None = None
    mrn: str
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
    appt_start: str | None = None
    appt_end: str | None = None
    status: str | None = None
    is_billable: int | None = None
    claim_required: int | None = None
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
    __tablename__ = "Lab"

    id: int = Field(primary_key=True)  # ReportId

    # (itemName, value, units, range, flag, paramNotes)
    # Writer: db.py update_lab_result(lab_id), from client.lab_results_json(lab_id).
    # LabDataDetailJSONArray has one entry per report, including prior results for the same item on earlier encounters.
    result: str | None = None

    itemid: int | None = None  # lab type eg CMP
    encounter_id: int | None = None
    patientname: str | None = None
    patient_id: str | None = None
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
