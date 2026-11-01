"""Qdrant vector database health and connectivity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_session
from app.core.config import get_settings, Settings
from app.services.qdrant import get_qdrant_service, QdrantService

router = APIRouter(prefix="/qdrant", tags=["qdrant"])


class QdrantHealthResponse(BaseModel):
    """Qdrant health check response."""

    url: str
    available: bool
    version: str | None = None


@router.get("/health", response_model=QdrantHealthResponse, dependencies=[Depends(require_session)])
async def qdrant_health_check():
    """Check Qdrant vector database health status.
    
    Requires authentication. Returns Qdrant connectivity status and version.
    
    Returns:
        QdrantHealthResponse with availability status
    """
    settings: Settings = get_settings()
    qdrant_service: QdrantService = get_qdrant_service(settings)

    try:
        # Check health
        is_available = await qdrant_service.health_check()
        
        # Get version if available
        version = None
        if is_available:
            version = await qdrant_service.get_version()

        return QdrantHealthResponse(
            url=settings.qdrant_url,
            available=is_available,
            version=version,
        )
    
    finally:
        # Clean up client connection
        await qdrant_service.close()
