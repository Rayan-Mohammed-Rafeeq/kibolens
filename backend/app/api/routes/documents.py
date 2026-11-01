"""Document management and RAG API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedding_service
from app.api.dependencies import get_db, require_session
from app.core.config import get_settings, Settings
from app.models.session import UserSession
from app.schemas.documents import (
    DocumentDeleteResponse,
    DocumentListItem,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentUploadResponse,
)
from app.services.documents import DocumentService
from app.services.qdrant import get_qdrant_service

router = APIRouter(prefix="/documents", tags=["documents"])

logger = logging.getLogger(__name__)


def get_document_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentService:
    """Dependency to create document service with Qdrant and embeddings.
    
    Args:
        settings: Application settings
        
    Returns:
        DocumentService instance
    """
    qdrant_service = get_qdrant_service(settings)
    embedding_service = get_embedding_service(settings)
    return DocumentService(qdrant_service, embedding_service)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    session: UserSession = Depends(require_session),
    document_service: DocumentService = Depends(get_document_service),
):
    """Upload and ingest a document for RAG.
    
    Supports PDF, TXT, and Markdown files. Maximum size: 10MB.
    
    Args:
        file: Uploaded file
        session: Authenticated user session
        document_service: Document service dependency
        
    Returns:
        DocumentUploadResponse with ingestion stats
        
    Raises:
        HTTPException: If upload fails or validation error
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    try:
        # Read file content
        content = await file.read()
        file_size = len(content)

        # Ingest document
        from io import BytesIO
        
        result = await document_service.ingest_document(
            file=BytesIO(content),
            filename=file.filename,
            file_size=file_size,
            user_id=session.user_id,
        )

        return DocumentUploadResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Document upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document",
        )


@router.get("/list", response_model=list[DocumentListItem])
async def list_documents(
    session: UserSession = Depends(require_session),
    document_service: DocumentService = Depends(get_document_service),
):
    """List all documents uploaded by the authenticated user.
    
    Args:
        session: Authenticated user session
        document_service: Document service dependency
        
    Returns:
        List of DocumentListItem
    """
    try:
        documents = await document_service.list_documents(session.user_id)
        
        # Convert to response models
        items = [
            DocumentListItem(
                document_id=doc["document_id"],
                filename=doc["filename"],
                file_type=doc["file_type"],
                file_size=doc["file_size"],
                uploaded_at=doc["uploaded_at"],
                total_chunks=doc["total_chunks"],
            )
            for doc in documents
        ]
        
        return items

    except Exception as e:
        logger.exception(f"Failed to list documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents",
        )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    session: UserSession = Depends(require_session),
    document_service: DocumentService = Depends(get_document_service),
):
    """Delete a document and all its chunks.
    
    Args:
        document_id: Document ID to delete
        session: Authenticated user session
        document_service: Document service dependency
        
    Returns:
        DocumentDeleteResponse
        
    Raises:
        HTTPException: If document not found or unauthorized
    """
    try:
        success = await document_service.delete_document(
            document_id=document_id,
            user_id=session.user_id,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or unauthorized",
            )

        return DocumentDeleteResponse(
            success=True,
            document_id=document_id,
            message="Document deleted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    session: UserSession = Depends(require_session),
    document_service: DocumentService = Depends(get_document_service),
):
    """Semantic search across uploaded documents.
    
    Args:
        request: Search request with query and limit
        session: Authenticated user session
        document_service: Document service dependency
        
    Returns:
        DocumentSearchResponse with matching chunks
    """
    try:
        results = await document_service.search_documents(
            query=request.query,
            user_id=session.user_id,
            limit=request.limit,
        )

        # Convert to response models
        search_results = [
            DocumentSearchResult(
                text=r["text"],
                score=r["score"],
                document_id=r["document_id"],
                filename=r["filename"],
                chunk_index=r["chunk_index"],
                file_type=r["file_type"],
            )
            for r in results
        ]

        return DocumentSearchResponse(
            query=request.query,
            results=search_results,
            count=len(search_results),
        )

    except Exception as e:
        logger.exception(f"Document search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed",
        )
