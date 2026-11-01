"""Tests for document service."""

import pytest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.documents import DocumentService, DocumentMetadata


@pytest.fixture
def mock_qdrant_service():
    """Create mock Qdrant service."""
    mock = MagicMock()
    mock.client = AsyncMock()
    return mock


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service."""
    mock = MagicMock()
    mock.dimension = 384
    mock.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock.embed_batch = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])
    return mock


@pytest.fixture
def document_service(mock_qdrant_service, mock_embedding_service):
    """Create document service instance."""
    return DocumentService(mock_qdrant_service, mock_embedding_service)


def test_validate_file_success(document_service):
    """Test successful file validation."""
    is_valid, error = document_service.validate_file("test.pdf", 1024 * 1024)  # 1MB
    assert is_valid is True
    assert error is None


def test_validate_file_too_large(document_service):
    """Test file size validation."""
    is_valid, error = document_service.validate_file("test.pdf", 20 * 1024 * 1024)  # 20MB
    assert is_valid is False
    assert "too large" in error.lower()


def test_validate_file_unsupported_type(document_service):
    """Test file type validation."""
    is_valid, error = document_service.validate_file("test.docx", 1024)
    assert is_valid is False
    assert "unsupported" in error.lower()


def test_extract_text_from_txt(document_service):
    """Test text extraction from plain text file."""
    content = "Hello, world!\nThis is a test."
    file = BytesIO(content.encode("utf-8"))
    
    result = document_service.extract_text(file, "test.txt")
    assert result == content


def test_extract_text_from_markdown(document_service):
    """Test text extraction from markdown file."""
    content = "# Title\n\nSome content."
    file = BytesIO(content.encode("utf-8"))
    
    result = document_service.extract_text(file, "test.md")
    assert result == content


def test_extract_text_unsupported_type(document_service):
    """Test extraction with unsupported file type."""
    file = BytesIO(b"some content")
    
    with pytest.raises(ValueError, match="Unsupported file type"):
        document_service.extract_text(file, "test.docx")


def test_chunk_text(document_service):
    """Test text chunking."""
    text = "A" * 2500  # Text longer than chunk size
    
    chunks = document_service.chunk_text(text)
    
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 + 200 for chunk in chunks)  # chunk_size + overlap


def test_document_metadata_to_dict():
    """Test DocumentMetadata to dictionary conversion."""
    from datetime import datetime
    from datetime import timezone as tz
    
    user_id = uuid4()
    uploaded_at = datetime.now(tz.utc)
    
    metadata = DocumentMetadata(
        document_id="doc-123",
        filename="test.pdf",
        file_type=".pdf",
        file_size=1024,
        user_id=user_id,
        uploaded_at=uploaded_at,
        chunk_index=0,
        total_chunks=5,
        content_hash="abc123",
    )
    
    result = metadata.to_dict()
    
    assert result["document_id"] == "doc-123"
    assert result["filename"] == "test.pdf"
    assert result["user_id"] == str(user_id)
    assert result["chunk_index"] == 0


@pytest.mark.asyncio
async def test_initialize_collection_creates_new(document_service, mock_qdrant_service):
    """Test collection initialization when collection doesn't exist."""
    mock_collections = MagicMock()
    mock_collections.collections = []
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    await document_service.initialize_collection()
    
    assert mock_qdrant_service.client.create_collection.called
    assert document_service._collection_initialized is True


@pytest.mark.asyncio
async def test_initialize_collection_already_exists(document_service, mock_qdrant_service):
    """Test collection initialization when collection exists."""
    mock_collection = MagicMock()
    mock_collection.name = "documents"
    
    mock_collections = MagicMock()
    mock_collections.collections = [mock_collection]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    await document_service.initialize_collection()
    
    assert not mock_qdrant_service.client.create_collection.called
    assert document_service._collection_initialized is True


@pytest.mark.asyncio
async def test_ingest_document_success(document_service, mock_qdrant_service, mock_embedding_service):
    """Test successful document ingestion."""
    # Setup
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    content = "Test document content.\n" * 100  # Make it long enough to chunk
    file = BytesIO(content.encode("utf-8"))
    user_id = uuid4()
    
    # Execute
    result = await document_service.ingest_document(
        file=file,
        filename="test.txt",
        file_size=len(content),
        user_id=user_id,
    )
    
    # Verify
    assert "document_id" in result
    assert result["filename"] == "test.txt"
    assert result["chunks"] > 0
    assert result["characters"] > 0
    assert mock_qdrant_service.client.upsert.called


@pytest.mark.asyncio
async def test_ingest_document_validation_error(document_service):
    """Test document ingestion with validation error."""
    file = BytesIO(b"content")
    user_id = uuid4()
    
    with pytest.raises(ValueError, match="Unsupported file type"):
        await document_service.ingest_document(
            file=file,
            filename="test.docx",
            file_size=100,
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_ingest_document_empty_text(document_service, mock_qdrant_service):
    """Test document ingestion with empty text."""
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    file = BytesIO(b"")
    user_id = uuid4()
    
    with pytest.raises(ValueError, match="No text content"):
        await document_service.ingest_document(
            file=file,
            filename="test.txt",
            file_size=0,
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_list_documents(document_service, mock_qdrant_service):
    """Test listing user documents."""
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    user_id = uuid4()
    
    # Mock scroll results
    mock_point = MagicMock()
    mock_point.payload = {
        "document_id": "doc-1",
        "filename": "test.pdf",
        "file_type": ".pdf",
        "file_size": 1024,
        "user_id": str(user_id),
        "uploaded_at": "2024-01-01T00:00:00",
        "chunk_index": 0,
        "total_chunks": 5,
    }
    
    mock_qdrant_service.client.scroll.return_value = ([mock_point], None)
    
    # Execute
    results = await document_service.list_documents(user_id)
    
    # Verify
    assert len(results) == 1
    assert results[0]["document_id"] == "doc-1"
    assert results[0]["filename"] == "test.pdf"


@pytest.mark.asyncio
async def test_delete_document_success(document_service, mock_qdrant_service):
    """Test successful document deletion."""
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    user_id = uuid4()
    document_id = "doc-1"
    
    # Mock scroll results
    mock_point = MagicMock()
    mock_point.id = "point-1"
    mock_point.payload = {
        "document_id": document_id,
        "user_id": str(user_id),
    }
    
    mock_qdrant_service.client.scroll.return_value = ([mock_point], None)
    
    # Execute
    result = await document_service.delete_document(document_id, user_id)
    
    # Verify
    assert result is True
    assert mock_qdrant_service.client.delete.called


@pytest.mark.asyncio
async def test_delete_document_not_found(document_service, mock_qdrant_service):
    """Test deleting non-existent document."""
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    user_id = uuid4()
    
    # Mock empty scroll results
    mock_qdrant_service.client.scroll.return_value = ([], None)
    
    # Execute
    result = await document_service.delete_document("doc-999", user_id)
    
    # Verify
    assert result is False
    assert not mock_qdrant_service.client.delete.called


@pytest.mark.asyncio
async def test_search_documents(document_service, mock_qdrant_service, mock_embedding_service):
    """Test semantic document search."""
    mock_collections = MagicMock()
    mock_collections.collections = [MagicMock(name="documents")]
    mock_qdrant_service.client.get_collections.return_value = mock_collections
    
    user_id = uuid4()
    
    # Mock search results
    mock_result = MagicMock()
    mock_result.score = 0.95
    mock_result.payload = {
        "text": "Relevant content",
        "document_id": "doc-1",
        "filename": "test.pdf",
        "chunk_index": 0,
        "file_type": ".pdf",
        "user_id": str(user_id),
    }
    
    mock_qdrant_service.client.search.return_value = [mock_result]
    
    # Execute
    results = await document_service.search_documents(
        query="test query",
        user_id=user_id,
        limit=5,
    )
    
    # Verify
    assert len(results) == 1
    assert results[0]["text"] == "Relevant content"
    assert results[0]["score"] == 0.95
    assert mock_embedding_service.embed_text.called
