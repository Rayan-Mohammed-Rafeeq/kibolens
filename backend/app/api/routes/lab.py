"""Administrator-only Failure Lab controls."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CsrfSession, CurrentUser
from app.core.config import get_settings
from app.monitoring.docker_observer import DockerLabController
from app.api.dependencies import get_db
from app.models.incident import EvidenceRecord, Incident
from app.models.notification import EmailNotification
from app.services.incidents import IncidentService
from app.services.notifications import notify_incident
from app.monitoring.simulation import SCENARIO_BY_KEY, SIMULATION_SCENARIOS, make_alert

router = APIRouter(prefix="/infrastructure/lab", tags=["failure-lab"])


class LabStartRequest(BaseModel):
    physical: bool = False
    # Retained for old clients; configured owner delivery is now automatic.
    notify_account: bool = False
    healthy: bool = False


class LabScenarioResponse(BaseModel):
    key: str
    title: str
    severity: str
    resource: str
    description: str
    safe_synthetic: bool = True


def _delivery_summary(db: Session, incident: Incident | None) -> dict:
    if incident is None:
        return {"requested": False, "status": "not_started", "deliveries": []}
    deliveries = db.scalars(
        select(EmailNotification)
        .where(EmailNotification.incident_id == incident.id)
        .order_by(EmailNotification.created_at, EmailNotification.recipient)
    ).all()
    return {
        "requested": bool(deliveries),
        "status": (
            "failed" if any(item.status == "failed" for item in deliveries)
            else "pending" if any(item.status == "pending" for item in deliveries)
            else "accepted" if deliveries else "not_requested"
        ),
        "deliveries": [
            {
                "recipient": item.recipient,
                "status": item.status,
                "provider_id": item.provider_id,
                "detail": item.error,
                "attempts": item.attempts,
            }
            for item in deliveries
        ],
    }


def _evidence_summary(db: Session, incident: Incident) -> list[dict]:
    records = db.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.incident_id == incident.id)
        .order_by(EvidenceRecord.collected_at)
    ).all()
    return [
        {
            "type": record.evidence_type,
            "metric_name": record.metric_name,
            "value": float(record.metric_value) if record.metric_value is not None else None,
            "unit": record.unit,
            "observed_at": record.observed_at.isoformat() if record.observed_at else None,
            "metadata": record.evidence_metadata or {},
        }
        for record in records
    ]


@router.get("/scenarios", response_model=list[LabScenarioResponse])
async def lab_scenarios(user: CurrentUser) -> list[LabScenarioResponse]:
    _admin(user)
    return [LabScenarioResponse(key=item.key, title=item.title, severity=item.severity, resource=item.resource, description=item.description) for item in SIMULATION_SCENARIOS]


def _admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")


@router.get("")
async def lab_status(user: CurrentUser, db: Session = Depends(get_db)) -> list[dict]:
    _admin(user)
    containers = await DockerLabController(get_settings().docker_socket_path).lab_containers()
    incidents = db.scalars(
        select(Incident).where(Incident.source.in_(["simulation", "docker_lab"]), Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]))
    ).all()
    incident_by_scenario = {
        (incident.alert_fingerprint or "").removeprefix("simulation:").removeprefix("docker:lab:"): incident
        for incident in incidents
    }
    for container in containers:
        scenario_key = container.get("labels", {}).get("kibolens.lab.scenario")
        incident = incident_by_scenario.get(scenario_key or "")
        if incident:
            container["incident_id"] = str(incident.id)
            container["notification"] = _delivery_summary(db, incident)
            container["evidence"] = _evidence_summary(db, incident)
    for incident in incidents:
        containers.append({
            "id": str(incident.id),
            "name": incident.affected_service or incident.title,
            "status": "SIMULATED",
            "labels": {"kibolens.simulated": "true", "kibolens.scenario": (incident.alert_fingerprint or "").removeprefix("simulation:")},
            "exit_code": None,
            "logs": incident.description,
            "incident_id": str(incident.id),
            "notification": _delivery_summary(db, incident),
            "evidence": _evidence_summary(db, incident),
        })
    return containers


@router.post("/{scenario}/start")
async def start_lab(scenario: str, user: CurrentUser, csrf: CsrfSession, request: LabStartRequest | None = None, db: Session = Depends(get_db)) -> dict:
    _admin(user)
    request = request or LabStartRequest()
    synthetic = SCENARIO_BY_KEY.get(scenario) if not request or not request.physical else None
    if synthetic:
        service = IncidentService(db)
        incident = service.process_alert(make_alert(synthetic))
        evidence_type = (
            "HOST_METRIC"
            if synthetic.resource == "kibo-host"
            else "CONTAINER_STATE"
            if synthetic.key.startswith("container-")
            else "SYSTEM_EVENT"
        )
        observed_at = datetime.now(timezone.utc)
        service.capture_evidence(
            incident.id,
            evidence_type,
            source="simulation",
            resource_identifier=synthetic.resource,
            metric_name=synthetic.metric_name,
            metric_value=synthetic.metric_value,
            unit=synthetic.unit,
            observed_at=observed_at,
            metadata={
                "simulated": True,
                "scenario": synthetic.key,
                "threshold": synthetic.threshold,
                "logs": synthetic.logs,
                "source": "failure_lab",
                "is_simulated": True,
            },
        )
        service.capture_evidence(
            incident.id,
            "LOG_EXCERPT",
            source="simulation",
            resource_identifier=synthetic.resource,
            observed_at=observed_at,
            metadata={"simulated": True, "logs": synthetic.logs},
        )
        settings = get_settings()
        # Failure Lab incidents always use the configured owner list. This is
        # deliberately independent of the signed-in administrator and the old
        # client-side notify_account flag.
        results = await notify_incident(db, incident, "firing", settings)
        notification = {
            "requested": bool(settings.get_incident_notification_emails()),
            "recipients": settings.get_incident_notification_emails(),
            "status": results[0]["status"] if results else "not_configured",
            "detail": results[0].get("error") if results else None,
            "delivery_results": results,
        }
        db.commit()
        return {"name": synthetic.key, "status": "SIMULATED", "simulated": True, "incident_id": str(incident.id), "notification": notification}
    physical_map = {"container-crash": "crasher", "container-restart-loop": "restart-loop", "container-unhealthy": "unhealthy", "application-config-failure": "config-error"}
    scenario = physical_map.get(scenario, scenario) if request.physical else scenario
    try:
        result = await DockerLabController(get_settings().docker_socket_path).start(
            scenario, healthy=request.healthy, notify_account=True
        )
        return {**result, "notification": {"requested": True, "status": "pending"}}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{scenario}/stop")
async def stop_lab(scenario: str, user: CurrentUser, csrf: CsrfSession, db: Session = Depends(get_db)) -> dict[str, bool | str]:
    _admin(user)
    synthetic = SCENARIO_BY_KEY.get(scenario)
    if synthetic:
        service = IncidentService(db)
        incident = db.scalar(select(Incident).where(Incident.alert_fingerprint == f"simulation:{scenario}", Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"])))
        if incident:
            resolved = service.process_alert(make_alert(synthetic, status="resolved"))
            await notify_incident(db, resolved, "resolved", get_settings())
            db.commit()
        return {"stopped": bool(incident), "simulated": True}
    physical_map = {"container-crash": "crasher", "container-restart-loop": "restart-loop", "container-unhealthy": "unhealthy", "application-config-failure": "config-error"}
    try:
        return {"stopped": await DockerLabController(get_settings().docker_socket_path).stop(physical_map.get(scenario, scenario))}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/reset")
async def reset_lab(user: CurrentUser, csrf: CsrfSession, db: Session = Depends(get_db)) -> dict[str, int | str]:
    """Remove only containers explicitly labeled as KiboLens lab resources."""
    _admin(user)
    settings = get_settings()
    removed = await DockerLabController(settings.docker_socket_path).reset()
    service = IncidentService(db)
    closed = 0
    for incident in db.scalars(select(Incident).where(Incident.source.in_(["docker_lab", "simulation"]), Incident.status != "CLOSED")):
        if incident.status != "RESOLVED":
            incident.status = "RESOLVED"
            incident.resolved_at = incident.resolved_at or incident.last_observed_at
        service.close_incident(incident.id, note="Administrator reset of Failure Lab demo", source="admin")
        closed += 1
    db.commit()
    return {"status": "reset", "removed_containers": removed, "closed_incidents": closed}
