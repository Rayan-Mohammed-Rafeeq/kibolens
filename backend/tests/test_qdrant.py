"""Tests for Qdrant vector database service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient as HttpxAsyncClient

from app.core.config import Settings
from app.models.user import User
from app.services.auth import bootstrap_administrator, create_session
from app.services.qdrant import QdrantService, get_qdrant_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def create_test_session(database: Session, user: User) -> tuple[str, str]:
    """Create authenticated session for testing."""
    from app.core.config import get_settings
    raw_token, csrf_token, _ = create_session(database, user, get_settings())
    return raw_token, csrf_token


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with Qdrant configuration."""
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        qdrant_url="http://localhost:6333",
        qdrant_timeout_seconds=10,
    )


@pytest.fixture
def qdrant_service(test_settings: Settings) -> QdrantService:
    """Create a Qdrant service instance for testing."""
    return get_qdrant_service(test_settings)


def test_qdrant_service_factory(test_settings: Settings):
    """Test Qdrant service factory creates service correctly."""
    service = get_qdrant_service(test_settings)

    assert service is not None
    assert service.url == "http://localhost:6333"
    assert service.timeout == 10
    assert service._client is not None


@pytest.mark.asyncio
async def test_qdrant_health_check_success(qdrant_service: QdrantService):
    """Test successful Qdrant health check."""
    # Mock the get_collections method
    with patch.object(qdrant_service._client, "get_collections", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()  # Return any object

        is_healthy = await qdrant_service.health_check()

        assert is_healthy is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_qdrant_health_check_connection_error(qdrant_service: QdrantService):
    """Test Qdrant health check handles connection errors gracefully."""
    with patch.object(qdrant_service._client, "get_collections", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = ConnectionError("Failed to connect")

        is_healthy = await qdrant_service.health_check()

        assert is_healthy is False


@pytest.mark.asyncio
async def test_qdrant_get_version_success(qdrant_service: QdrantService):
    """Test getting Qdrant version."""
    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "1.20.0", "title": "qdrant"}
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        version = await qdrant_service.get_version()

        assert version == "1.20.0"


@pytest.mark.asyncio
async def test_qdrant_get_version_error(qdrant_service: QdrantService):
    """Test getting version handles errors gracefully."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.side_effect = ConnectionError("Connection refused")
        mock_client_class.return_value = mock_client

        version = await qdrant_service.get_version()

        assert version is None


@pytest.mark.asyncio
async def test_qdrant_close(qdrant_service: QdrantService):
    """Test closing Qdrant client."""
    with patch.object(qdrant_service._client, "close", new_callable=AsyncMock) as mock_close:
        await qdrant_service.close()

        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_qdrant_close_error_handling(qdrant_service: QdrantService):
    """Test close handles errors gracefully."""
    with patch.object(qdrant_service._client, "close", new_callable=AsyncMock) as mock_close:
        mock_close.side_effect = Exception("Close failed")

        # Should not raise
        await qdrant_service.close()


def test_qdrant_health_endpoint_requires_auth(client: TestClient):
    """Test Qdrant health endpoint requires authentication."""
    response = client.get("/api/v1/qdrant/health")

    assert response.status_code == 401


def test_qdrant_health_endpoint_authenticated(client: TestClient, database: Session):
    """Test Qdrant health endpoint with authentication."""
    # Create authenticated user
    user = bootstrap_administrator(
        database, "admin", "admin@example.com", "test-password"
    )
    session_token, _ = create_test_session(database, user)

    # Mock the Qdrant service
    with patch("app.api.routes.qdrant.get_qdrant_service") as mock_get_service:
        mock_service = AsyncMock()
        mock_service.health_check.return_value = True
        mock_service.get_version.return_value = "1.20.0"
        mock_service.close = AsyncMock()
        mock_get_service.return_value = mock_service

        response = client.get(
            "/api/v1/qdrant/health",
            cookies={"kibolens_session": session_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://localhost:6333"
        assert data["available"] is True
        assert data["version"] == "1.20.0"

        # Verify close was called
        mock_service.close.assert_called_once()


def test_qdrant_health_endpoint_unavailable(client: TestClient, database: Session):
    """Test Qdrant health endpoint when service is unavailable."""
    # Create authenticated user
    user = bootstrap_administrator(
        database, "admin", "admin@example.com", "test-password"
    )
    session_token, _ = create_test_session(database, user)

    with patch("app.api.routes.qdrant.get_qdrant_service") as mock_get_service:
        mock_service = AsyncMock()
        mock_service.health_check.return_value = False
        mock_service.get_version.return_value = None
        mock_service.close = AsyncMock()
        mock_get_service.return_value = mock_service

        response = client.get(
            "/api/v1/qdrant/health",
            cookies={"kibolens_session": session_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["version"] is None
