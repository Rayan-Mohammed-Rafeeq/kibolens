import secrets
from datetime import datetime
from datetime import timezone as tz
from typing import Literal

UTC = tz.utc

from app.api.dependencies import CurrentUser, get_db
from app.core.config import get_settings
from app.monitoring.alerts import AlertDeduplicator
from app.monitoring.prometheus import PrometheusClient
from app.monitoring.docker_observer import DockerObserver
from app.monitoring.service import MonitoringService
from app.monitoring.vm_observer import VMObserver
from app.schemas.monitoring import (
    AlertmanagerWebhook,
    AlertWebhookResponse,
    ContainerStatus,
    InfrastructureSummary,
    MetricHistory,
    MonitoringStatus,
    VirtualMachineStatus,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from app.services.notifications import notify_incident
from app.models.incident import Incident

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])
alerts_router = APIRouter(prefix="/monitoring", tags=["monitoring"])
deduplicator = AlertDeduplicator()


def monitoring_service() -> MonitoringService:
    settings = get_settings()
    return MonitoringService(
        PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
        settings,
        DockerObserver(settings.docker_socket_path) if settings.docker_observer_enabled else None,
        VMObserver(settings.libvirt_uri) if settings.vm_observer_enabled else None,
    )


@router.get("/summary", response_model=InfrastructureSummary)
async def infrastructure_summary(_: CurrentUser) -> InfrastructureSummary:
    return await monitoring_service().summary()


@router.get("/metrics", response_model=InfrastructureSummary)
async def infrastructure_metrics(_: CurrentUser) -> InfrastructureSummary:
    return await monitoring_service().summary()


@router.get("/metrics/history", response_model=MetricHistory)
async def infrastructure_history(
    _: CurrentUser,
    metric: Literal[
        "cpu_utilization", "memory_utilization", "disk_utilization", "network_receive"
    ] = Query(),
    hours: int = Query(default=6, ge=1, le=24),
) -> MetricHistory:
    return await monitoring_service().history(metric, hours)


@router.get("/containers", response_model=list[ContainerStatus])
async def infrastructure_containers(_: CurrentUser) -> list[ContainerStatus]:
    return await monitoring_service().containers()


@router.get("/vms", response_model=list[VirtualMachineStatus])
async def infrastructure_vms(_: CurrentUser):
    return await monitoring_service().vms()


@router.get("/monitoring-status", response_model=MonitoringStatus)
async def monitoring_status(_: CurrentUser) -> MonitoringStatus:
    available = await monitoring_service().client.ready()
    return MonitoringStatus(
        prometheus_available=available,
        checked_at=datetime.now(UTC),
        detail=None if available else "Prometheus is unavailable or not ready.",
    )


@alerts_router.post("/alerts", response_model=AlertWebhookResponse)
async def alertmanager_webhook(
    request: Request,
    payload: AlertmanagerWebhook,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AlertWebhookResponse:
    content_length = request.headers.get("content-length")
    try:
        too_large = content_length is not None and int(content_length) > 256_000
    except ValueError:
        too_large = True
    if too_large:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large."
        )
    configured_token = get_settings().alert_webhook_token
    token = configured_token.get_secret_value() if configured_token else ""
    expected_authorization = f"Bearer {token}"
    if (
        not token
        or authorization is None
        or not secrets.compare_digest(expected_authorization, authorization)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid alert webhook token."
        )
    
    # Process alerts and create/update incidents
    from app.services.incidents import IncidentService
    
    settings = get_settings()
    monitoring = monitoring_service()
    incident_service = IncidentService(db, monitoring)
    
    processed = 0
    request_fingerprints: set[str] = set()
    for alert in payload.alerts:
        # Correlation is durable in PostgreSQL; only duplicate entries inside
        # one webhook payload are discarded here.
        if alert.fingerprint not in request_fingerprints:
            request_fingerprints.add(alert.fingerprint)
            try:
                before = db.scalar(select(Incident).where(
                    and_(Incident.alert_fingerprint == alert.fingerprint, Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]))
                ))
                before_severity = before.severity if before else None
                incident = incident_service.process_alert(alert)
                await incident_service.collect_incident_evidence(incident)
                event_key = "resolved" if alert.status == "resolved" else (
                    f"severity-{incident.severity.lower()}" if before_severity and before_severity != incident.severity else "firing"
                )
                await notify_incident(db, incident, event_key, settings)
                processed += 1
            except Exception as e:
                # Log error but continue processing other alerts
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to process alert {alert.fingerprint}: {e}")
    
    db.commit()
    return AlertWebhookResponse(accepted=processed, deduplicated=len(payload.alerts) - processed)
