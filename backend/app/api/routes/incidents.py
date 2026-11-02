import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import status as http_status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

from app.api.dependencies import CsrfSession, CurrentUser, get_db
from app.ai.cloud_embeddings import CloudEmbeddingService
from app.ai.investigator import get_investigator
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
    IncidentInvestigationResponse,
)
from app.schemas.conversation import MessageCreate
from app.services import conversations
from app.services.documents import DocumentService
from app.services.qdrant import get_qdrant_service
from app.services.incidents import IncidentService
from app.core.config import get_settings

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = logging.getLogger(__name__)


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
    try:
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
    except SQLAlchemyError as exc:
        logger.exception("Incident list query failed")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Incident storage is unavailable. Verify the database and run migrations.",
        ) from exc
    except ValidationError as exc:
        logger.exception("Incident list response serialization failed")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Incident data could not be serialized. Check the incident schema and stored values.",
        ) from exc


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


@router.post("/{incident_id}/investigate", response_model=IncidentInvestigationResponse)
async def investigate_incident(
    incident_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    _: CsrfSession,
    db: Session = Depends(get_db),
    service: IncidentService = Depends(get_incident_service),
) -> IncidentInvestigationResponse:
    """Investigate an incident with its persisted timeline and evidence."""
    incident = service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    settings = get_settings()
    conversation = conversations.create_conversation(
        db, user.id, f"Investigation · {incident.incident_number}"
    )
    conversation.incident_id = incident.id
    conversations.add_user_message(db, conversation, payload.content)
    timeline = service.get_incident_timeline(incident.id)
    evidence = service.get_incident_evidence(incident.id)
    context = "\n".join([
        f"Incident: {incident.incident_number} | {incident.title} | severity={incident.severity} | status={incident.status}",
        incident.description,
        "Timeline:",
        *[f"{event.created_at.isoformat()} {event.event_type}: {event.description}" for event in timeline],
        "Evidence:",
        *[f"{item.evidence_type} {item.metric_name or item.resource_identifier or ''}: {item.evidence_metadata or item.metric_value}" for item in evidence],
    ])
    investigator = await get_investigator(
        settings=settings,
        document_service=DocumentService(get_qdrant_service(settings), CloudEmbeddingService(settings)),
        incident_service=service,
        prometheus_client=PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
        database=db,
    )
    result = await investigator.investigate(
        question=payload.content,
        user_id=user.id,
        conversation_context=context,
        conversation_id=conversation.id,
    )
    assistant_content = result.get("findings") or f"Investigation could not be completed: {result.get('error', 'No provider response was available.')}"
    if result.get("findings") and result.get("data_sources"):
        assistant_content += "\n\n---\n**Sources consulted:** " + ", ".join(result["data_sources"])
    conversations.add_assistant_message(db, conversation, assistant_content)
    service.add_note(incident.id, f"AI investigation conversation created: {conversation.id}", source="ai")
    db.commit()
    return IncidentInvestigationResponse(**result, conversation_id=conversation.id)


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: UUID,
    update: IncidentStatusUpdate,
    _: CurrentUser,
    csrf: CsrfSession,
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
    csrf: CsrfSession,
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
    csrf: CsrfSession,
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
