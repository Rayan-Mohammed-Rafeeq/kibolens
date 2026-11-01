"""Tests for LLM service layer."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from app.ai.llm import get_llm_provider
from app.ai.llm.base import LLMResponse
from app.core.config import Settings


class MockAnalysisResult(BaseModel):
    """Test Pydantic model for structured output."""

    summary: str = Field(description="Brief summary")
    severity: str = Field(description="Severity level: low, medium, high, critical")
    confidence: float = Field(description="Confidence score 0-1", ge=0, le=1)


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with Ollama configuration."""
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2:3b",
        llm_temperature=0.1,
        llm_max_tokens=500,
    )


@pytest.mark.asyncio
async def test_llm_provider_factory(test_settings: Settings):
    """Test LLM provider factory creates Ollama provider."""
    provider = get_llm_provider(test_settings)

    assert provider is not None
    assert provider.model == "llama3.2:3b"
    assert provider.base_url == "http://localhost:11434"


@pytest.mark.asyncio
async def test_llm_generate_text(test_settings: Settings):
    """Test unstructured text generation."""
    provider = get_llm_provider(test_settings)

    # Skip if Ollama not available
    if not await provider.health_check():
        pytest.skip("Ollama not available")

    response: LLMResponse[None] = await provider.generate(
        prompt="What is 2+2? Answer with only the number.",
        system_prompt="You are a helpful calculator.",
        temperature=0.0,
        max_tokens=50,
    )

    assert response.content, "Response should have content"
    assert response.structured_output is None
    assert response.error is None
    assert "4" in response.content

    # Check metadata
    assert response.metadata["provider"] == "ollama"
    assert response.metadata["model"] == "llama3.2:3b"
    assert "latency_seconds" in response.metadata


@pytest.mark.asyncio
async def test_llm_generate_structured(test_settings: Settings):
    """Test structured output generation with Pydantic model."""
    provider = get_llm_provider(test_settings)

    if not await provider.health_check():
        pytest.skip("Ollama not available")

    prompt = """Analyze this infrastructure alert:
    
Alert: High CPU usage on server web-01
Details: CPU utilization at 95% for 10 minutes
Impact: Response time degraded by 40%

Provide analysis."""

    response: LLMResponse[MockAnalysisResult] = await provider.generate_structured(
        prompt=prompt,
        response_model=MockAnalysisResult,
        system_prompt="You are an infrastructure monitoring expert.",
        temperature=0.1,
    )

    assert response.content, "Response should have raw content"
    assert response.error is None, f"Structured generation failed: {response.error}"

    # Verify structured output was parsed
    assert response.structured_output is not None, "Should parse structured output"
    assert isinstance(response.structured_output, MockAnalysisResult)
    assert response.structured_output.summary
    assert response.structured_output.severity in ["low", "medium", "high", "critical"]
    assert 0 <= response.structured_output.confidence <= 1

    # Check metadata
    assert response.metadata["provider"] == "ollama"
    assert response.metadata["format"] == "json"
    assert "latency_seconds" in response.metadata


@pytest.mark.asyncio
async def test_llm_health_check(test_settings: Settings):
    """Test LLM provider health check."""
    provider = get_llm_provider(test_settings)

    # This may pass or fail depending on whether Ollama is running
    # We just verify it returns a boolean
    is_healthy = await provider.health_check()
    assert isinstance(is_healthy, bool)


@pytest.mark.asyncio
async def test_llm_graceful_failure():
    """Test LLM handles unreachable provider gracefully."""
    bad_settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        llm_provider="ollama",
        ollama_base_url="http://invalid-host:9999",  # Valid port range
        ollama_model="llama3.2:3b",
        ollama_timeout_seconds=2,  # Short timeout
    )

    provider = get_llm_provider(bad_settings)

    # Health check should fail
    is_healthy = await provider.health_check()
    assert is_healthy is False

    # Generate should return error response, not raise
    response = await provider.generate(prompt="test")
    assert response.error is not None
    assert response.content == ""


def test_unsupported_provider():
    """Test factory raises error for unsupported provider."""
    bad_settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        llm_provider="invalid-provider",
    )

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider(bad_settings)
