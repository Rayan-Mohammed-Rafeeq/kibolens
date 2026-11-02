import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class EmailNotification(Base):
    """Durable idempotency and delivery status for incident email alerts."""

    __tablename__ = "email_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    provider_id: Mapped[str | None] = mapped_column(String(256))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("incident_id", "event_key", "recipient", name="uq_email_notification_event_recipient"),
        Index("ix_email_notifications_status", "status"),
    )
