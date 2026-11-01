"""Tests for LLM service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from app.ai.llm import get_llm_provider
from app.ai.llm.base import LLMResponse
from app.ai.llm.ollama import OllamaProvider
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
async def test_ollama_chat_parameters_structure(test_settings: Settings):
    """Test that AsyncClient.chat() receives correct parameter structure.
    
    Regression test for: temperature must be passed through options dict,
    not as top-level kwarg.
    """
    provider = OllamaProvider(test_settings)
    
    # Mock the AsyncClient.chat method
    mock_response = {
        "message": {"role": "assistant", "content": "Test response"},
        "prompt_eval_count": 10,
        "eval_count": 20,
    }
    
    with patch.object(provider._client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        
        await provider.generate(
            prompt="Test prompt",
            system_prompt="Test system",
            temperature=0.7,
            max_tokens=100,
        )
        
        # Verify chat was called exactly once
        assert mock_chat.call_count == 1
        
        # Extract the actual call arguments
        call_args = mock_chat.call_args
        
        # Verify positional args (should be none)
        assert len(call_args.args) == 0
        
        # Verify keyword arguments structure
        kwargs = call_args.kwargs
        
        # Model should be passed as top-level kwarg
        assert kwargs["model"] == "llama3.2:3b"
        
        # Messages should be a list of dicts
        assert "messages" in kwargs
        assert isinstance(kwargs["messages"], list)
        assert len(kwargs["messages"]) == 2
        assert kwargs["messages"][0] == {"role": "system", "content": "Test system"}
        assert kwargs["messages"][1] == {"role": "user", "content": "Test prompt"}
        
        # Options should be a dict containing temperature, num_predict, etc.
        assert "options" in kwargs
        assert isinstance(kwargs["options"], dict)
        assert kwargs["options"]["temperature"] == 0.7
        assert kwargs["options"]["num_predict"] == 100
        assert kwargs["options"]["num_thread"] == 2
        assert kwargs["options"]["num_ctx"] == 2048
        
        # Temperature should NOT be a top-level kwarg
        assert "temperature" not in kwargs
        assert "num_predict" not in kwargs


@pytest.mark.asyncio
async def test_ollama_chat_json_format_parameters(test_settings: Settings):
    """Test that structured generation passes format='json' correctly."""
    provider = OllamaProvider(test_settings)
    
    mock_response = {
        "message": {
            "role": "assistant",
            "content": '{"summary": "test", "severity": "low", "confidence": 0.8}'
        },
        "prompt_eval_count": 15,
        "eval_count": 25,
    }
    
    with patch.object(provider._client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        
        await provider.generate_structured(
            prompt="Analyze this",
            response_model=MockAnalysisResult,
            temperature=0.5,
        )
        
        # Verify chat was called
        assert mock_chat.call_count == 1
        
        kwargs = mock_chat.call_args.kwargs
        
        # Format should be passed as top-level kwarg
        assert kwargs["format"] == "json"
        
        # Temperature should still be in options, not top-level
        assert "options" in kwargs
        assert kwargs["options"]["temperature"] == 0.5
        assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_ollama_connection_error_handling(test_settings: Settings):
    """Test graceful handling of Ollama connection failures."""
    provider = OllamaProvider(test_settings)
    
    # Mock chat to raise a connection error
    with patch.object(provider._client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = ConnectionError("Failed to connect to Ollama")
        
        response = await provider.generate(prompt="Test")
        
        # Should return error response, not raise
        assert response.error is not None
        assert "Failed to connect to Ollama" in response.error
        assert response.content == ""
        assert response.metadata["provider"] == "ollama"


@pytest.mark.asyncio
async def test_ollama_model_error_handling(test_settings: Settings):
    """Test graceful handling of model-specific errors."""
    provider = OllamaProvider(test_settings)
    
    # Mock chat to raise a model error
    with patch.object(provider._client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = ValueError("Model not found")
        
        response = await provider.generate(prompt="Test")
        
        # Should return error response
        assert response.error is not None
        assert "Model not found" in response.error


@pytest.mark.asyncio
async def test_ollama_default_temperature_used(test_settings: Settings):
    """Test that default temperature is used when not specified."""
    provider = OllamaProvider(test_settings)
    
    mock_response = {
        "message": {"role": "assistant", "content": "Response"},
        "prompt_eval_count": 10,
        "eval_count": 20,
    }
    
    with patch.object(provider._client, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        
        # Call without specifying temperature
        await provider.generate(prompt="Test")
        
        kwargs = mock_chat.call_args.kwargs
        
        # Should use default temperature from settings (0.1)
        assert kwargs["options"]["temperature"] == 0.1


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

