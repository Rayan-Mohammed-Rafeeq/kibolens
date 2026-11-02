"""Administrator-only Failure Lab cleanup controls."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CsrfSession, CurrentUser
from app.core.config import get_settings
from app.monitoring.docker_observer import DockerLabController
from app.api.dependencies import get_db
from app.models.incident import Incident
from app.services.incidents import IncidentService
from app.services.notifications import notify_incident
from app.monitoring.simulation import SCENARIO_BY_KEY, SIMULATION_SCENARIOS, make_alert

router = APIRouter(prefix="/infrastructure/lab", tags=["failure-lab"])


class LabStartRequest(BaseModel):
    physical: bool = False
    notify_test_recipients: bool = False


class LabScenarioResponse(BaseModel):
    key: str
    title: str
    severity: str
    resource: str
    description: str
    safe_synthetic: bool = True


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
        select(Incident).where(Incident.source == "simulation", Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]))
    ).all()
    containers.extend({
        "id": str(incident.id),
        "name": incident.affected_service or incident.title,
        "status": "SIMULATED",
        "labels": {"kibolens.simulated": "true", "kibolens.scenario": (incident.alert_fingerprint or "").removeprefix("simulation:")},
        "exit_code": None,
        "logs": incident.description,
        "incident_id": str(incident.id),
    } for incident in incidents)
    return containers


@router.post("/{scenario}/start")
async def start_lab(scenario: str, user: CurrentUser, csrf: CsrfSession, request: LabStartRequest | None = None, db: Session = Depends(get_db)) -> dict:
    _admin(user)
    request = request or LabStartRequest()
    synthetic = SCENARIO_BY_KEY.get(scenario)
    if synthetic:
        service = IncidentService(db)
        incident = service.process_alert(make_alert(synthetic))
        service.capture_evidence(
            incident.id,
            "SYSTEM_EVENT",
            source="simulation",
            resource_identifier=synthetic.resource,
            metric_name=synthetic.metric_name,
            metric_value=synthetic.metric_value,
            unit=synthetic.unit,
            metadata={
                "simulated": True,
                "scenario": synthetic.key,
                "threshold": synthetic.threshold,
                "logs": synthetic.logs,
            },
        )
        service.capture_evidence(
            incident.id,
            "LOG_EXCERPT",
            source="simulation",
            resource_identifier=synthetic.resource,
            metadata={"simulated": True, "logs": synthetic.logs},
        )
        settings = get_settings()
        if request.notify_test_recipients:
            await notify_incident(db, incident, "firing", settings, sorted(settings.get_incident_test_recipient_emails()))
        db.commit()
        return {"name": synthetic.key, "status": "SIMULATED", "simulated": True, "incident_id": str(incident.id)}
    physical_map = {"container-crash": "crasher", "container-restart-loop": "restart-loop", "container-unhealthy": "unhealthy", "application-config-failure": "config-error"}
    scenario = physical_map.get(scenario, scenario) if request.physical else scenario
    try:
        return await DockerLabController(get_settings().docker_socket_path).start(scenario)
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
            await notify_incident(db, resolved, "resolved", get_settings(), sorted(get_settings().get_incident_test_recipient_emails()))
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
