"""LLM testing and health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.llm import get_llm_provider
from app.core.config import get_settings

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMHealthResponse(BaseModel):
    """LLM health check response."""

    provider: str
    model: str
    base_url: str
    available: bool


class LLMTestRequest(BaseModel):
    """LLM test generation request."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    system_prompt: str | None = Field(None, max_length=2000)
    temperature: float | None = Field(None, ge=0, le=1)


class LLMTestResponse(BaseModel):
    """LLM test generation response."""

    content: str
    metadata: dict


@router.get("/health", response_model=LLMHealthResponse)
async def llm_health_check():
    """Check LLM provider health status.
    
    Returns:
        LLMHealthResponse with provider availability
    """
    settings = get_settings()
    provider = get_llm_provider(settings)

    is_available = await provider.health_check()

    return LLMHealthResponse(
        provider=settings.llm_provider,
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        available=is_available,
    )


@router.post("/test", response_model=LLMTestResponse)
async def llm_test_generate(request: LLMTestRequest):
    """Test LLM text generation (development/testing only).
    
    Args:
        request: Test generation request with prompt
        
    Returns:
        LLMTestResponse with generated content
        
    Raises:
        HTTPException: If LLM generation fails
    """
    settings = get_settings()
    provider = get_llm_provider(settings)

    # Check provider is available
    if not await provider.health_check():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider {settings.llm_provider} is not available",
        )

    # Generate response
    response = await provider.generate(
        prompt=request.prompt,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        max_tokens=500,  # Limited for testing
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
