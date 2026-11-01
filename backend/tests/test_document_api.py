"""Tests for document API endpoints."""

import pytest
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

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
async def test_upload_document_requires_auth(client):
    """Test document upload requires authentication."""
    files = {"file": ("test.txt", BytesIO(b"test content"), "text/plain")}
    response = client.post("/api/v1/documents/upload", files=files)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_upload_document_success(client, database, create_test_session):
    """Test successful document upload."""
    user, token = create_test_session()
    
    mock_result = {
        "document_id": str(uuid4()),
        "filename": "test.txt",
        "chunks": 1,
        "characters": 12,
        "uploaded_at": "2024-01-01T00:00:00",
    }
    
    with patch("app.api.routes.documents.DocumentService") as mock_service_class:
        mock_service = AsyncMock()
        mock_service.ingest_document.return_value = mock_result
        mock_service_class.return_value = mock_service
        
        files = {"file": ("test.txt", BytesIO(b"test content"), "text/plain")}
        response = client.post(
            "/api/v1/documents/upload",
            files=files,
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["filename"] == "test.txt"
    assert data["chunks"] == 1


@pytest.mark.asyncio
async def test_list_documents_requires_auth(client):
    """Test listing documents requires authentication."""
    response = client.get("/api/v1/documents/list")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_list_documents_success(client, database, create_test_session):
    """Test successful document listing."""
    user, token = create_test_session()
    
    mock_documents = [
        {
            "document_id": str(uuid4()),
            "filename": "test1.pdf",
            "file_type": ".pdf",
            "file_size": 1024,
            "uploaded_at": "2024-01-01T00:00:00",
            "total_chunks": 5,
        }
    ]
    
    with patch("app.api.routes.documents.DocumentService") as mock_service_class:
        mock_service = AsyncMock()
        mock_service.list_documents.return_value = mock_documents
        mock_service_class.return_value = mock_service
        
        response = client.get(
            "/api/v1/documents/list",
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "test1.pdf"


@pytest.mark.asyncio
async def test_delete_document_requires_auth(client):
    """Test document deletion requires authentication."""
    response = client.delete("/api/v1/documents/doc-123")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_delete_document_success(client, database, create_test_session):
    """Test successful document deletion."""
    user, token = create_test_session()
    
    document_id = str(uuid4())
    
    with patch("app.api.routes.documents.DocumentService") as mock_service_class:
        mock_service = AsyncMock()
        mock_service.delete_document.return_value = True
        mock_service_class.return_value = mock_service
        
        response = client.delete(
            f"/api/v1/documents/{document_id}",
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["document_id"] == document_id


@pytest.mark.asyncio
async def test_search_documents_requires_auth(client):
    """Test document search requires authentication."""
    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test"},
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_search_documents_success(client, database, create_test_session):
    """Test successful document search."""
    user, token = create_test_session()
    
    mock_results = [
        {
            "text": "Relevant content",
            "score": 0.95,
            "document_id": str(uuid4()),
            "filename": "test.pdf",
            "chunk_index": 0,
            "file_type": ".pdf",
        }
    ]
    
    with patch("app.api.routes.documents.DocumentService") as mock_service_class:
        mock_service = AsyncMock()
        mock_service.search_documents.return_value = mock_results
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/api/v1/documents/search",
            json={"query": "test query", "limit": 5},
            cookies={"kibolens_session": token},
        )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["query"] == "test query"
    assert len(data["results"]) == 1
    assert data["results"][0]["score"] == 0.95
