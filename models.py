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
