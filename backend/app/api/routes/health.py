from datetime import datetime
from datetime import timezone as tz

UTC = tz.utc

from app.core.config import get_settings
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import database_is_available
from fastapi import APIRouter, Response, status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, timestamp=datetime.now(UTC))


@router.get("/ready", response_model=ReadinessResponse)
def readiness_check(response: Response) -> ReadinessResponse:
    available = database_is_available()
    if not available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if available else "not_ready",
        database="available" if available else "unavailable",
    )


@router.get("/metrics", include_in_schema=False)
def application_metrics() -> Response:
    """Small internal Prometheus endpoint for backend availability."""
    return Response(
        content="# HELP kibolens_backend_up Backend process availability.\n"
        "# TYPE kibolens_backend_up gauge\n"
        "kibolens_backend_up 1\n",
        media_type="text/plain; version=0.0.4",
    )
