from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.services.qdrant import get_qdrant_service
import asyncio
import logging
import time
from app.database.session import SessionLocal
from app.monitoring.docker_observer import DockerObserver
from app.monitoring.prometheus import PrometheusClient
from app.monitoring.service import MonitoringService
from app.services.incidents import IncidentService
from app.schemas.monitoring import AlertmanagerAlert
from app.models.incident import Incident
from sqlalchemy import select
from app.services.notifications import notify_incident

# Global Qdrant service instance
_qdrant_service = None
_docker_task: asyncio.Task | None = None
logger = logging.getLogger(__name__)


async def _observe_container_events(settings) -> None:
    """Correlate Docker lifecycle failures with the normal incident pipeline."""
    observer = DockerObserver(settings.docker_socket_path)
    event_cursor = time.time() - 15
    while True:
        try:
            now = time.time()
            lifecycle_events = await observer.events_since(event_cursor, now)
            event_cursor = now
            for event in lifecycle_events:
                event_id = (event.get("id") or "").lstrip("/").removeprefix("docker/")
                if not event_id:
                    continue
                event_status = event.get("status", "")
                labels = event.get("labels", {})
                is_lab = labels.get("kibolens.lab") == "true"
                exit_code = int(event.get("exit_code") or 0)
                failure = event_status in {"kill", "oom", "health_status: unhealthy"} or (event_status == "die" and exit_code != 0)
                recovery = event_status in {"start", "health_status: healthy"}
                if not failure and not recovery:
                    continue
                fingerprint = f"docker:{event_id}:health" if event_status.startswith("health_status") else f"docker:{event_id}:process"
                db = SessionLocal()
                try:
                    service = IncidentService(
                        db,
                        MonitoringService(
                            PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
                            settings,
                            observer,
                            None,
                        ),
                    )
                    if failure:
                        severity = "critical" if event_status in {"oom", "kill"} else "high"
                        alert = AlertmanagerAlert(
                            status="firing",
                            fingerprint=fingerprint,
                            labels={
                                "alertname": "DockerContainerFailure",
                                "severity": severity,
                                "service": event.get("name") or event_id[:12],
                                "kibolens_source": "docker",
                                "kibolens_lab": "true" if is_lab else "false",
                            },
                            annotations={
                                "summary": f"Docker container {event.get('name') or event_id[:12]} {event_status}",
                                "description": f"Docker lifecycle event {event_status}; exit_code={exit_code}.",
                            },
                        )
                        incident = service.process_alert(alert)
                        service.capture_evidence(
                            incident.id,
                            "CONTAINER_STATE",
                            source="docker",
                            resource_identifier=event.get("name") or event_id,
                            metadata={"event": event_status, "exit_code": exit_code, "labels": labels, "simulated": False},
                        )
                        await service.collect_incident_evidence(incident)
                        await notify_incident(db, incident, "firing", settings)
                        db.commit()
                    elif recovery:
                        existing = db.scalar(select(Incident).where(
                            Incident.alert_fingerprint == fingerprint,
                            Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]),
                        ))
                        if existing:
                            alert = AlertmanagerAlert(
                                status="resolved",
                                fingerprint=fingerprint,
                                labels={"alertname": "DockerContainerFailure", "severity": "warning", "service": event.get("name") or event_id, "kibolens_source": "docker", "kibolens_lab": "true" if is_lab else "false"},
                                annotations={"summary": f"Docker container {event.get('name') or event_id} recovered"},
                            )
                            resolved = service.process_alert(alert)
                            await notify_incident(db, resolved, "resolved", settings)
                            db.commit()
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Docker observer loop failed; retrying: %s", exc)
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global _qdrant_service

    # Startup: Initialize Qdrant service
    settings = get_settings()
    _qdrant_service = get_qdrant_service(settings)

    global _docker_task
    if settings.docker_observer_enabled:
        _docker_task = asyncio.create_task(_observe_container_events(settings))

    # Pre-warm the AI router singleton (validates configuration)
    if settings.llm_provider.lower() == "cloud":
        try:
            from app.ai.router.core import get_ai_router
            await get_ai_router(settings)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "AI router pre-warm failed (non-fatal): %s", exc
            )
    else:
        # Legacy Ollama path: validate embedding service configuration
        try:
            from app.ai.embeddings import get_embedding_service
            get_embedding_service(settings)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Ollama embedding service init failed (non-fatal): %s", exc
            )

    yield

    # Shutdown: Close Qdrant client
    if _qdrant_service:
        await _qdrant_service.close()
    if _docker_task:
        _docker_task.cancel()
        await asyncio.gather(_docker_task, return_exceptions=True)

    # Reset AI router singleton
    try:
        from app.ai.router.core import reset_ai_router
        reset_ai_router()
    except Exception:
        pass


def create_application() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_application()
