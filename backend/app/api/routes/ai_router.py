"""AI provider health and diagnostic endpoints.

Protected endpoint (requires authentication) exposing:
- Provider availability and circuit-breaker state
- Eligible models and priority lists
- Last success/failure categories
- Quota/rate-limit state
- Routing configuration

Never exposes API keys or sensitive credentials.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.ai.router.core import get_ai_router
from app.api.dependencies import require_session
from app.core.config import get_settings, Settings
from app.models.session import UserSession

router = APIRouter(prefix="/ai", tags=["ai-router"])

logger = logging.getLogger(__name__)


class AIHealthResponse(BaseModel):
    """AI router health summary (no secrets included)."""

    free_only_mode: bool
    allow_paid_models: bool
    max_model_attempts: int
    providers: dict


@router.get("/health", response_model=AIHealthResponse)
async def ai_router_health(
    session: UserSession = Depends(require_session),
    settings: Settings = Depends(get_settings),
):
    """Return AI router health status.

    Includes:
    - Provider availability and API reachability
    - Circuit-breaker state (open/closed/half-open)
    - Active free model lists
    - Quota/rate-limit state where known
    - Routing configuration

    Requires authentication. Never exposes API keys.
    """
    try:
        ai_router = await get_ai_router(settings)
        health = await ai_router.health_status()
        return AIHealthResponse(**health)
    except Exception as e:
        logger.exception("AI health check failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI health check failed",
        )


class LLMHealthResponse(BaseModel):
    """Legacy-compatible LLM health response (for backward compatibility)."""

    provider: str
    model: str
    base_url: str
    available: bool
    # Extended fields for cloud router
    routing_active: bool = False
    free_only: bool = True


class LLMTestRequest(BaseModel):
    """LLM test generation request."""

    prompt: str
    system_prompt: str | None = None
    temperature: float | None = None


class LLMTestResponse(BaseModel):
    """LLM test generation response."""

    content: str
    metadata: dict


@router.get("/llm/health", response_model=LLMHealthResponse, tags=["llm"])
async def llm_health_check(settings: Settings = Depends(get_settings)):
    """Check LLM / AI router health (backward-compatible endpoint).

    Returns provider availability.  When cloud routing is active, returns
    routing_active=True and the name of the first available provider.
    """
    from app.ai.llm.factory import get_llm_provider

    provider = get_llm_provider(settings)
    is_available = await provider.health_check()

    if settings.llm_provider.lower() == "cloud":
        return LLMHealthResponse(
            provider="cloud-router",
            model="gemini/openrouter-auto",
            base_url="https://generativelanguage.googleapis.com",
            available=is_available,
            routing_active=True,
            free_only=settings.ai_free_only,
        )

    return LLMHealthResponse(
        provider=settings.llm_provider,
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        available=is_available,
        routing_active=False,
        free_only=False,
    )


@router.post("/llm/test", response_model=LLMTestResponse, tags=["llm"])
async def llm_test_generate(
    request: LLMTestRequest,
    settings: Settings = Depends(get_settings),
):
    """Test LLM text generation (development/testing only).

    Routes through the cloud AI router when llm_provider=cloud.
    """
    from app.ai.llm.factory import get_llm_provider

    provider = get_llm_provider(settings)

    if not await provider.health_check():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider {settings.llm_provider!r} is not available",
        )

    response = await provider.generate(
        prompt=request.prompt,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        max_tokens=500,
    )

    if response.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM generation failed: {response.error}",
        )

    return LLMTestResponse(
        content=response.content,
        metadata=response.metadata,
    )
