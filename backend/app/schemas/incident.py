from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from app.schemas.documents import InvestigationResponse

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


class IncidentResponse(BaseModel):
    id: UUID
    incident_number: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    source: str
    alert_fingerprint: str | None
    affected_host: str | None
    affected_service: str | None
    first_detected_at: datetime
    last_observed_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    logical_fingerprint: str | None = None

    class Config:
        from_attributes = True


class IncidentListResponse(BaseModel):
    incidents: list[IncidentResponse]
    total: int
    page: int
    page_size: int


class IncidentEventResponse(BaseModel):
    id: UUID
    incident_id: UUID
    event_type: EventType
    description: str
    previous_status: IncidentStatus | None
    new_status: IncidentStatus | None
    source: str
    event_metadata: dict | None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceRecordResponse(BaseModel):
    id: UUID
    incident_id: UUID
    evidence_type: EvidenceType
    source: str
    resource_identifier: str | None
    metric_name: str | None
    metric_value: float | None
    unit: str | None
    observed_at: datetime | None
    collected_at: datetime
    evidence_metadata: dict | None

    class Config:
        from_attributes = True


class IncidentDetailResponse(BaseModel):
    incident: IncidentResponse
    events: list[IncidentEventResponse]
    evidence: list[EvidenceRecordResponse]


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus = Field(
        ..., description="New status for the incident (must follow transition policy)"
    )
    note: str | None = Field(None, max_length=2000, description="Optional status change note")


class IncidentSeverityUpdate(BaseModel):
    severity: IncidentSeverity = Field(..., description="New severity level")
    note: str | None = Field(None, max_length=2000, description="Optional severity change note")


class IncidentNote(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000, description="Note content")


class IncidentSummary(BaseModel):
    total_active: int
    critical_count: int
    high_count: int
    warning_count: int
    info_count: int
    recently_resolved_count: int
    oldest_unresolved: IncidentResponse | None
    latest_incidents: list[IncidentResponse]


class IncidentInvestigationResponse(InvestigationResponse):
    conversation_id: UUID
