from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.monitoring.prometheus import PrometheusClient
from app.monitoring.service import MonitoringService
from app.schemas.incident import (
    EvidenceRecordResponse,
    IncidentDetailResponse,
    IncidentEventResponse,
    IncidentListResponse,
    IncidentNote,
    IncidentResponse,
    IncidentSeverity,
    IncidentSeverityUpdate,
    IncidentStatus,
    IncidentStatusUpdate,
    IncidentSummary,
)
from app.services.incidents import IncidentService
from app.core.config import get_settings

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_incident_service(db: Session = Depends(get_db)) -> IncidentService:
    """Create incident service with monitoring integration."""
    settings = get_settings()
    monitoring = MonitoringService(
        PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
        settings,
    )
    return IncidentService(db, monitoring)


@router.get("/summary", response_model=IncidentSummary)
async def get_incident_summary(
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> IncidentSummary:
    """Get incident summary statistics for dashboard."""
    summary_data = service.get_incident_summary()
    return IncidentSummary(**summary_data)


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    _: CurrentUser,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
    severity: IncidentSeverity | None = Query(default=None, description="Filter by severity"),
    status: IncidentStatus | None = Query(default=None, description="Filter by status"),
    affected_service: str | None = Query(
        default=None, max_length=256, description="Filter by affected service"
    ),
    search: str | None = Query(
        default=None, max_length=256, description="Search in number, title, description"
    ),
    service: IncidentService = Depends(get_incident_service),
) -> IncidentListResponse:
    """
    List incidents with filtering and pagination.

    Supports filtering by:
    - severity: INFO, WARNING, HIGH, CRITICAL
    - status: DETECTED, INVESTIGATING, IDENTIFIED, RESOLVING, RESOLVED, CLOSED
    - affected_service: exact match
    - search: fuzzy match against incident number, title, description
    """
    incidents, total = service.list_incidents(
        page=page,
        page_size=page_size,
        severity=severity,
        status=status,
        affected_service=affected_service,
        search=search,
    )

    return IncidentListResponse(
        incidents=[IncidentResponse.model_validate(inc) for inc in incidents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident_detail(
    incident_id: UUID,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> IncidentDetailResponse:
    """Get detailed incident information including timeline and evidence."""
    incident = service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    events = service.get_incident_timeline(incident_id)
    evidence = service.get_incident_evidence(incident_id)

    return IncidentDetailResponse(
        incident=IncidentResponse.model_validate(incident),
        events=[IncidentEventResponse.model_validate(e) for e in events],
        evidence=[EvidenceRecordResponse.model_validate(ev) for ev in evidence],
    )


@router.get("/{incident_id}/events", response_model=list[IncidentEventResponse])
async def get_incident_events(
    incident_id: UUID,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> list[IncidentEventResponse]:
    """Get incident event timeline."""
    incident = service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    events = service.get_incident_timeline(incident_id)
    return [IncidentEventResponse.model_validate(e) for e in events]


@router.get("/{incident_id}/evidence", response_model=list[EvidenceRecordResponse])
async def get_incident_evidence(
    incident_id: UUID,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> list[EvidenceRecordResponse]:
    """Get incident evidence records."""
    incident = service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    evidence = service.get_incident_evidence(incident_id)
    return [EvidenceRecordResponse.model_validate(ev) for ev in evidence]


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: UUID,
    update: IncidentStatusUpdate,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    """
    Update incident status.

    Validates state transitions according to policy:
    DETECTED → INVESTIGATING, RESOLVED
    INVESTIGATING → IDENTIFIED, DETECTED, RESOLVED
    IDENTIFIED → RESOLVING, INVESTIGATING, RESOLVED
    RESOLVING → RESOLVED, IDENTIFIED
    RESOLVED → CLOSED, INVESTIGATING (reopen)
    CLOSED → (terminal, no transitions)
    """
    try:
        incident = service.update_incident_status(
            incident_id=incident_id,
            new_status=update.status,
            note=update.note,
            source="user",
        )
        service.db.commit()
        return IncidentResponse.model_validate(incident)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{incident_id}/severity", response_model=IncidentResponse)
async def update_incident_severity(
    incident_id: UUID,
    update: IncidentSeverityUpdate,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    """Update incident severity level."""
    try:
        incident = service.update_incident_severity(
            incident_id=incident_id,
            new_severity=update.severity,
            note=update.note,
            source="user",
        )
        service.db.commit()
        return IncidentResponse.model_validate(incident)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{incident_id}/notes", response_model=IncidentEventResponse, status_code=status.HTTP_201_CREATED)
async def add_incident_note(
    incident_id: UUID,
    note: IncidentNote,
    _: CurrentUser,
    service: IncidentService = Depends(get_incident_service),
) -> IncidentEventResponse:
    """Add a note to incident timeline."""
    try:
        event = service.add_note(
            incident_id=incident_id,
            note=note.note,
            source="user",
        )
        service.db.commit()
        return IncidentEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
