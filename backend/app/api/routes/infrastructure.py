import secrets
from datetime import datetime
from datetime import timezone as tz
from typing import Literal

UTC = tz.utc

from app.api.dependencies import CurrentUser, get_db
from app.core.config import get_settings
from app.monitoring.alerts import AlertDeduplicator
from app.monitoring.prometheus import PrometheusClient
from app.monitoring.service import MonitoringService
from app.schemas.monitoring import (
    AlertmanagerWebhook,
    AlertWebhookResponse,
    ContainerStatus,
    InfrastructureSummary,
    MetricHistory,
    MonitoringStatus,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])
alerts_router = APIRouter(prefix="/monitoring", tags=["monitoring"])
deduplicator = AlertDeduplicator()


def monitoring_service() -> MonitoringService:
    settings = get_settings()
    return MonitoringService(
        PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds), settings
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
    for alert in payload.alerts:
        # Use deduplicator for idempotency within this request
        if deduplicator.accept(alert.fingerprint):
            try:
                incident_service.process_alert(alert)
                processed += 1
            except Exception as e:
                # Log error but continue processing other alerts
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to process alert {alert.fingerprint}: {e}")
    
    db.commit()
    return AlertWebhookResponse(accepted=processed, deduplicated=len(payload.alerts) - processed)
