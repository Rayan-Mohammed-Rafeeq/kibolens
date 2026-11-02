"""AI investigation API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.cloud_embeddings import CloudEmbeddingService
from app.ai.investigator import get_investigator
from app.api.dependencies import require_session
from app.core.config import get_settings, Settings
from app.models.session import UserSession
from app.monitoring.prometheus import PrometheusClient
from app.schemas.documents import InvestigationRequest, InvestigationResponse
from app.services.documents import DocumentService
from app.services.qdrant import get_qdrant_service

router = APIRouter(prefix="/investigate", tags=["investigation"])

logger = logging.getLogger(__name__)


@router.post("", response_model=InvestigationResponse)
async def investigate_issue(
    request: InvestigationRequest,
    session: UserSession = Depends(require_session),
    settings: Settings = Depends(get_settings),
):
    """Run AI investigation for an infrastructure question.

    Gathers context from incidents, metrics, and documents, then uses
    the cloud AI router (Gemini → OpenRouter, free-only) to generate
    evidence-based findings and recommendations.

    Returns:
        InvestigationResponse with findings, evidence, and routing metadata
    """
    try:
        # Initialize services
        qdrant_service = get_qdrant_service(settings)
        embedding_service = CloudEmbeddingService(settings)
        document_service = DocumentService(qdrant_service, embedding_service)

        # Initialize Prometheus client
        prometheus_client = PrometheusClient(
            base_url=settings.prometheus_url,
            timeout_seconds=settings.prometheus_timeout_seconds,
        )

        # Create investigator (uses cloud router by default, or Ollama if configured)
        investigator = await get_investigator(
            settings=settings,
            document_service=document_service,
            incident_service=None,  # TODO: Add incident context with proper DB session
            prometheus_client=prometheus_client,
        )

        # Run investigation
        result = await investigator.investigate(
            question=request.question,
            user_id=session.user_id,
        )

        return InvestigationResponse(**result)

    except Exception as e:
        logger.exception("Investigation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {str(e)}",
        )
