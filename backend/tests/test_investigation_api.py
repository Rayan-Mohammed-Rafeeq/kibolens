"""Tests for investigation API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import status


@pytest.fixture
def create_test_session(database):
    """Helper to create authenticated session."""
    from app.models.user import User
    from app.services.auth import create_session
    from app.core.config import get_settings
    
    def _create(email: str = "test@example.com"):
        user = User(email=email, username="testuser", password_hash="dummy-hash")
        database.add(user)
        database.commit()
        
        token, csrf_token, _ = create_session(database, user, get_settings())
        return user, token
    
    return _create


@pytest.mark.asyncio
async def test_investigate_requires_auth(client):
    """Test investigation requires authentication."""
    response = client.post(
        "/api/v1/investigate",
        json={"question": "What is causing high CPU?"},
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_investigate_success(client, database, create_test_session):
    """Test successful investigation."""
    user, token = create_test_session()
    
    mock_result = {
        "question": "What is causing high CPU?",
        "findings": "Based on available evidence...",
        "evidence": {
            "metrics_data": "CPU Utilization: 85%",
        },
        "data_sources": ["Prometheus Metrics"],
        "error": None,
        "timestamp": "2024-01-01T00:00:00",
    }
    
    with patch("app.ai.investigator.AIInvestigator") as mock_investigator_class:
        mock_investigator = AsyncMock()
        mock_investigator.investigate.return_value = mock_result
        mock_investigator_class.return_value = mock_investigator
        
        response = client.post(
            "/api/v1/investigate",
            json={"question": "What is causing high CPU?"},
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["question"] == "What is causing high CPU?"
    assert data["findings"] is not None
    assert "Prometheus Metrics" in data["data_sources"]


@pytest.mark.asyncio
async def test_investigate_with_error(client, database, create_test_session):
    """Test investigation with error."""
    user, token = create_test_session()
    
    mock_result = {
        "question": "What is causing high CPU?",
        "findings": None,
        "evidence": {},
        "data_sources": [],
        "error": "Prometheus unavailable",
        "timestamp": "2024-01-01T00:00:00",
    }
    
    # Mock the get_investigator factory to return a mock investigator
    # This works for both cloud and ollama modes
    with patch("app.api.routes.investigation.get_investigator") as mock_get_investigator:
        mock_investigator = AsyncMock()
        mock_investigator.investigate.return_value = mock_result
        mock_get_investigator.return_value = mock_investigator
        
        response = client.post(
            "/api/v1/investigate",
            json={"question": "What is causing high CPU?"},
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["error"] == "Prometheus unavailable"
    assert data["findings"] is None
