"""Administrator-only Failure Lab cleanup controls."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CsrfSession, CurrentUser
from app.core.config import get_settings
from app.monitoring.docker_observer import DockerLabController
from app.api.dependencies import get_db
from app.models.incident import Incident
from app.services.incidents import IncidentService

router = APIRouter(prefix="/infrastructure/lab", tags=["failure-lab"])


def _admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")


@router.get("")
async def lab_status(user: CurrentUser) -> list[dict]:
    _admin(user)
    return await DockerLabController(get_settings().docker_socket_path).lab_containers()


@router.post("/{scenario}/start")
async def start_lab(scenario: str, user: CurrentUser, csrf: CsrfSession) -> dict:
    _admin(user)
    try:
        return await DockerLabController(get_settings().docker_socket_path).start(scenario)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{scenario}/stop")
async def stop_lab(scenario: str, user: CurrentUser, csrf: CsrfSession) -> dict[str, bool]:
    _admin(user)
    try:
        return {"stopped": await DockerLabController(get_settings().docker_socket_path).stop(scenario)}
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
    for incident in db.scalars(select(Incident).where(Incident.source == "docker_lab", Incident.status != "CLOSED")):
        if incident.status != "RESOLVED":
            incident.status = "RESOLVED"
            incident.resolved_at = incident.resolved_at or incident.last_observed_at
        service.close_incident(incident.id, note="Administrator reset of Failure Lab demo", source="admin")
        closed += 1
    db.commit()
    return {"status": "reset", "removed_containers": removed, "closed_incidents": closed}
