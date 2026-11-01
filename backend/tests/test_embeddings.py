"""Tests for embedding service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.embeddings import EmbeddingService, EMBEDDING_DIMENSIONS, get_embedding_service
from app.core.config import Settings


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        ollama_base_url="http://localhost:11434",
        ollama_timeout_seconds=30,
    )


@pytest.fixture
def embedding_service(settings):
    """Create embedding service instance."""
    return EmbeddingService(settings, model="all-minilm")


@pytest.mark.asyncio
async def test_embedding_service_dimension():
    """Test embedding dimension property."""
    settings = Settings()
    service = EmbeddingService(settings, model="all-minilm")
    assert service.dimension == 384
    
    service = EmbeddingService(settings, model="nomic-embed-text")
    assert service.dimension == 768
    
    service = EmbeddingService(settings, model="mxbai-embed-large")
    assert service.dimension == 1024


@pytest.mark.asyncio
async def test_embed_text_success(embedding_service):
    """Test successful text embedding."""
    mock_embedding = [0.1] * 384
    
    with patch.object(embedding_service._client, "embeddings", new_callable=AsyncMock) as mock_embeddings:
        mock_embeddings.return_value = {"embedding": mock_embedding}
        
        result = await embedding_service.embed_text("test text")
        
        assert result == mock_embedding
        mock_embeddings.assert_called_once_with(
            model="all-minilm",
            prompt="test text",
        )


@pytest.mark.asyncio
async def test_embed_text_empty_response(embedding_service):
    """Test embedding with empty response."""
    with patch.object(embedding_service._client, "embeddings", new_callable=AsyncMock) as mock_embeddings:
        mock_embeddings.return_value = {"embedding": []}
        
        with pytest.raises(ValueError, match="Empty embedding"):
            await embedding_service.embed_text("test text")


@pytest.mark.asyncio
async def test_embed_text_error(embedding_service):
    """Test embedding with error."""
    with patch.object(embedding_service._client, "embeddings", new_callable=AsyncMock) as mock_embeddings:
        mock_embeddings.side_effect = Exception("Ollama connection failed")
        
        with pytest.raises(Exception, match="Ollama connection failed"):
            await embedding_service.embed_text("test text")


@pytest.mark.asyncio
async def test_embed_batch_success(embedding_service):
    """Test batch embedding."""
    mock_embedding_1 = [0.1] * 384
    mock_embedding_2 = [0.2] * 384
    
    with patch.object(embedding_service._client, "embeddings", new_callable=AsyncMock) as mock_embeddings:
        mock_embeddings.side_effect = [
            {"embedding": mock_embedding_1},
            {"embedding": mock_embedding_2},
        ]
        
        texts = ["first text", "second text"]
        results = await embedding_service.embed_batch(texts)
        
        assert len(results) == 2
        assert results[0] == mock_embedding_1
        assert results[1] == mock_embedding_2
        assert mock_embeddings.call_count == 2


@pytest.mark.asyncio
async def test_health_check_success(embedding_service):
    """Test health check when model is available."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "all-minilm:latest"},
            {"name": "llama3.2:3b"},
        ]
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        result = await embedding_service.health_check()
        
        assert result is True


@pytest.mark.asyncio
async def test_health_check_model_not_found(embedding_service):
    """Test health check when model is not installed."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3.2:3b"},
            {"name": "qwen2.5:1.5b"},
        ]
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        result = await embedding_service.health_check()
        
        assert result is False


@pytest.mark.asyncio
async def test_health_check_connection_error(embedding_service):
    """Test health check with connection error."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client
        
        result = await embedding_service.health_check()
        
        assert result is False


def test_get_embedding_service_factory(settings):
    """Test embedding service factory function."""
    service = get_embedding_service(settings, model="nomic-embed-text")
    
    assert isinstance(service, EmbeddingService)
    assert service.model == "nomic-embed-text"
    assert service.dimension == 768
