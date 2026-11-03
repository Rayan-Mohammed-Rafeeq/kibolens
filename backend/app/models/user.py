import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, index=True, nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(256), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    incident_notification_min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="WARNING")
    recovery_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
