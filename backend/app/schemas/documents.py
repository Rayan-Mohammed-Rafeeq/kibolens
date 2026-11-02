"""Document management schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Response after successful document upload."""

    document_id: str
    filename: str
    chunks: int
    characters: int
    uploaded_at: str


class DocumentListItem(BaseModel):
    """Document list item."""

    document_id: str
    filename: str
    file_type: str
    file_size: int
    uploaded_at: str
    total_chunks: int


class DocumentDeleteResponse(BaseModel):
    """Response after document deletion."""

    success: bool
    document_id: str
    message: str


class DocumentSearchRequest(BaseModel):
    """Document search request."""

    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class DocumentSearchResult(BaseModel):
    """Single document search result."""

    text: str
    score: float
    document_id: str
    filename: str
    chunk_index: int
    file_type: str


class DocumentSearchResponse(BaseModel):
    """Document search response."""

    query: str
    results: list[DocumentSearchResult]
    count: int


class InvestigationRequest(BaseModel):
    """AI investigation request."""

    question: str = Field(..., min_length=1, max_length=1000)


class InvestigationResponse(BaseModel):
    """AI investigation response."""

    question: str
    findings: str | None
    evidence: dict
    data_sources: list[str]
    error: str | None
    timestamp: str
    # Cloud routing metadata (provider, model, attempt history, latency)
    routing_metadata: dict | None = None
