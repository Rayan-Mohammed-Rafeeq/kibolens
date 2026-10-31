import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

# Use JSON for SQLite compatibility, JSONB for PostgreSQL
JSONType = JSON().with_variant(SQLITE_JSON(), "sqlite")

IncidentSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
IncidentStatus = Literal[
    "DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING", "RESOLVED", "CLOSED"
]
EventType = Literal[
    "INCIDENT_CREATED",
    "ALERT_RECEIVED",
    "ALERT_REPEATED",
    "STATUS_CHANGED",
    "SEVERITY_CHANGED",
    "EVIDENCE_CAPTURED",
    "INCIDENT_RESOLVED",
    "INCIDENT_REOPENED",
    "NOTE_ADDED",
    "INCIDENT_CLOSED",
]
EvidenceType = Literal[
    "HOST_METRIC",
    "CONTAINER_METRIC",
    "CONTAINER_STATE",
    "PROMETHEUS_ALERT",
    "SYSTEM_EVENT",
    "LOG_EXCERPT",
]


class Incident(Base):
    """
    Incident records represent infrastructure problems detected from monitoring alerts.

    Each incident has a unique human-readable reference (INC-000001, INC-000002, etc.)
    and tracks severity, status, affected resources, and lifecycle timestamps.

    State transitions follow a documented policy:
    DETECTED → INVESTIGATING → IDENTIFIED → RESOLVING → RESOLVED → CLOSED

    Reopening is permitted when a previously-resolved fingerprint fires again.
    """

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_number: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="alertmanager")
    alert_fingerprint: Mapped[str | None] = mapped_column(String(256), index=True)
    affected_host: Mapped[str | None] = mapped_column(String(256))
    affected_service: Mapped[str | None] = mapped_column(String(256), index=True)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL')", name="ck_incident_severity"
        ),
        CheckConstraint(
            "status IN ('DETECTED', 'INVESTIGATING', 'IDENTIFIED', 'RESOLVING', 'RESOLVED', 'CLOSED')",
            name="ck_incident_status",
        ),
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_fingerprint_status", "alert_fingerprint", "status"),
    )


class IncidentEvent(Base):
    """
    Append-only event timeline for each incident.

    Every important state transition creates an event record with before/after states,
    source attribution, and optional structured metadata.
    """

    __tablename__ = "incident_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    event_metadata: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('INCIDENT_CREATED', 'ALERT_RECEIVED', 'ALERT_REPEATED', "
            "'STATUS_CHANGED', 'SEVERITY_CHANGED', 'EVIDENCE_CAPTURED', 'INCIDENT_RESOLVED', "
            "'INCIDENT_REOPENED', 'NOTE_ADDED', 'INCIDENT_CLOSED')",
            name="ck_incident_event_type",
        ),
        Index("ix_incident_events_incident_created", "incident_id", "created_at"),
    )


class EvidenceRecord(Base):
    """
    Evidence captured during incident lifecycle.

    Records host metrics, container state, Prometheus alerts, and bounded log excerpts
    collected when alerts arrive or during investigation.
    """

    __tablename__ = "evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="prometheus")
    resource_identifier: Mapped[str | None] = mapped_column(String(256))
    metric_name: Mapped[str | None] = mapped_column(String(128))
    metric_value: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=6))
    unit: Mapped[str | None] = mapped_column(String(32))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evidence_metadata: Mapped[dict | None] = mapped_column(JSONType)

    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('HOST_METRIC', 'CONTAINER_METRIC', 'CONTAINER_STATE', "
            "'PROMETHEUS_ALERT', 'SYSTEM_EVENT', 'LOG_EXCERPT')",
            name="ck_evidence_type",
        ),
        Index("ix_evidence_records_incident_type", "incident_id", "evidence_type"),
    )


class IncidentSequence(Base):
    """
    Concurrency-safe incident reference number generator.

    Uses a single-row table with an integer sequence to generate INC-XXXXXX references.
    """

    __tablename__ = "incident_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
