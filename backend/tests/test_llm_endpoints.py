"""Tests for LLM API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(scope="function")
async def test_llm_health_check(client: AsyncClient):
    """Test LLM health check endpoint."""
    response = client.get("/api/v1/llm/health")  # Sync call with AsyncClient

    assert response.status_code == 200
    data = response.json()

    assert "provider" in data
    assert "model" in data
    assert "base_url" in data
    assert "available" in data
    assert isinstance(data["available"], bool)

    # Should use Ollama by default
    assert data["provider"] == "ollama"
    assert "llama" in data["model"].lower()


@pytest.mark.asyncio(scope="function")
async def test_llm_test_generate_missing_ollama(client: AsyncClient):
    """Test LLM generation when Ollama is not running."""
    # First check health - if Ollama IS running, skip this test
    health_response = client.get("/api/v1/llm/health")
    health_data = health_response.json()

    if health_data["available"]:
        pytest.skip("Ollama is running - skipping unavailable test")

    # Try to generate when unavailable
    response = client.post(
        "/api/v1/llm/test",
        json={
            "prompt": "What is 2+2?",
            "system_prompt": "You are a calculator",
        },
    )

    assert response.status_code == 503
    data = response.json()
    assert "not available" in data["detail"].lower()


@pytest.mark.asyncio(scope="function")
async def test_llm_test_generate_success(client: AsyncClient):
    """Test successful LLM text generation."""
    # Check if Ollama is available
    health_response = client.get("/api/v1/llm/health")
    health_data = health_response.json()

    if not health_data["available"]:
        pytest.skip("Ollama not available for testing")

    # Test generation
    response = client.post(
        "/api/v1/llm/test",
        json={
            "prompt": "What is 2+2? Answer with only the number.",
            "system_prompt": "You are a helpful calculator.",
            "temperature": 0.0,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "content" in data
    assert "metadata" in data
    assert len(data["content"]) > 0

    # Should contain the answer 4
    assert "4" in data["content"]

    # Check metadata structure
    assert "provider" in data["metadata"]
    assert "model" in data["metadata"]
    assert "latency_seconds" in data["metadata"]


@pytest.mark.asyncio(scope="function")
async def test_llm_test_generate_validation(client: AsyncClient):
    """Test LLM test endpoint input validation."""
    # Empty prompt
    response = client.post(
        "/api/v1/llm/test",
        json={"prompt": ""},
    )
    assert response.status_code == 422

    # Prompt too long
    response = client.post(
        "/api/v1/llm/test",
        json={"prompt": "x" * 10000},
    )
    assert response.status_code == 422

    # Invalid temperature
    response = client.post(
        "/api/v1/llm/test",
        json={"prompt": "test", "temperature": 2.5},
    )
    assert response.status_code == 422


@pytest.mark.asyncio(scope="function")
async def test_llm_test_generate_with_custom_temperature(client: AsyncClient):
    """Test LLM generation with custom temperature."""
    health_response = client.get("/api/v1/llm/health")
    if not health_response.json()["available"]:
        pytest.skip("Ollama not available")

    response = client.post(
        "/api/v1/llm/test",
        json={
            "prompt": "Say 'hello' in one word.",
            "temperature": 0.8,  # Higher temperature
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["temperature"] == 0.8
