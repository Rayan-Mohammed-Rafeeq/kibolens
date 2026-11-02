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

# Global Qdrant service instance
_qdrant_service = None
_docker_task: asyncio.Task | None = None
logger = logging.getLogger(__name__)


async def _observe_lab_failures(settings) -> None:
    """Poll retained Docker state and correlate lab failures with incidents."""
    observer = DockerObserver(settings.docker_socket_path)
    active: set[str] = set()
    event_cursor = time.time() - 15
    while True:
        try:
            now = time.time()
            lifecycle_events = await observer.events_since(event_cursor, now)
            event_cursor = now
            lab_containers = await observer.lab_containers()
            failures = [item for item in lab_containers if item["status"] == "UNHEALTHY" or (
                item["status"] == "STOPPED" and item.get("exit_code", 0) != 0
            ) or (item.get("restart_count") or 0) > 0]
            known_ids = {item.get("id", "").lstrip("/").removeprefix("docker/") for item in lab_containers}
            for event in lifecycle_events:
                event_id = (event.get("id") or "").lstrip("/").removeprefix("docker/")
                if event.get("status") in {"die", "kill", "health_status: unhealthy"} and event_id and event_id not in known_ids:
                    failures.append({
                        "id": event_id,
                        "name": event.get("name") or event_id[:12],
                        "status": "STOPPED" if event.get("status") != "health_status: unhealthy" else "UNHEALTHY",
                        "restart_count": 0,
                        "exit_code": int(event.get("exit_code") or 1),
                        "last_observation": None,
                        "image": None,
                        "labels": event.get("labels", {}),
                        "logs": f"Docker lifecycle event: {event.get('status')}",
                    })
            current = {item["id"] for item in failures}
            db = SessionLocal()
            try:
                service = IncidentService(
                    db,
                    MonitoringService(
                        PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
                        settings,
                        observer,
                    ),
                )
                for item in failures:
                    fingerprint = f"docker:{item['id']}:failure"
                    if item["id"] not in active:
                        alert = AlertmanagerAlert(
                            status="firing",
                            fingerprint=fingerprint,
                            labels={
                                "alertname": "DockerLabFailure",
                                "severity": "warning",
                                "service": item["name"],
                                "kibolens_lab": "true",
                            },
                            annotations={
                                "summary": f"Failure Lab scenario failed: {item['name']}",
                                "description": item.get("logs") or "Docker reported a lab failure.",
                            },
                        )
                        incident = service.process_alert(alert)
                        service.capture_evidence(
                            incident.id, "CONTAINER_STATE", source="docker",
                            resource_identifier=item["name"],
                            metadata={
                                key: value for key, value in item.items()
                                if key != "last_observation"
                            },
                        )
                        db.commit()
                for container_id in active - current:
                    recovered = next((item for item in lab_containers if item["id"] == container_id), None)
                    if recovered and recovered["status"] == "RUNNING":
                        alert = AlertmanagerAlert(
                            status="resolved", fingerprint=f"docker:{container_id}:failure",
                            labels={"alertname": "DockerLabFailure", "severity": "warning", "service": recovered["name"], "kibolens_lab": "true"},
                            annotations={"summary": f"Failure Lab scenario recovered: {recovered['name']}"},
                        )
                        service.process_alert(alert)
                        db.commit()
                active = current
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
        _docker_task = asyncio.create_task(_observe_lab_failures(settings))

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
