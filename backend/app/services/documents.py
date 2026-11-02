"""Document ingestion and management service."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from datetime import datetime
from datetime import timezone as tz
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Union
from uuid import UUID, uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.ai.embeddings import EmbeddingService
from app.services.qdrant import QdrantService

if TYPE_CHECKING:
    from app.ai.cloud_embeddings import CloudEmbeddingService

# Accept both the legacy Ollama EmbeddingService and the new CloudEmbeddingService
AnyEmbeddingService = Union["EmbeddingService", "CloudEmbeddingService"]

UTC = tz.utc

logger = logging.getLogger(__name__)

# Document processing configuration
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
}

# Chunking configuration
CHUNK_SIZE = 1000  # characters
CHUNK_OVERLAP = 200  # characters overlap between chunks


class DocumentMetadata:
    """Document metadata structure."""

    def __init__(
        self,
        document_id: str,
        filename: str,
        file_type: str,
        file_size: int,
        user_id: UUID,
        uploaded_at: datetime,
        chunk_index: int,
        total_chunks: int,
        content_hash: str,
    ):
        self.document_id = document_id
        self.filename = filename
        self.file_type = file_type
        self.file_size = file_size
        self.user_id = str(user_id)
        self.uploaded_at = uploaded_at.isoformat()
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        self.content_hash = content_hash

    def to_dict(self) -> dict:
        """Convert to dictionary for Qdrant storage."""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "user_id": self.user_id,
            "uploaded_at": self.uploaded_at,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "content_hash": self.content_hash,
        }


class DocumentService:
    """Service for document ingestion, storage, and retrieval."""

    def __init__(
        self,
        qdrant_service: QdrantService,
        embedding_service: AnyEmbeddingService,
        collection_name: str = "documents",
    ):
        """Initialize document service.
        
        Args:
            qdrant_service: Qdrant vector database service
            embedding_service: Embedding generation service
            collection_name: Qdrant collection name for documents
        """
        self.qdrant = qdrant_service
        self.embeddings = embedding_service
        self.collection_name = collection_name
        self._collection_initialized = False

    async def initialize_collection(self) -> None:
        """Initialize Qdrant collection if it doesn't exist."""
        if self._collection_initialized:
            return

        try:
            # Check if collection exists
            collections = await self.qdrant.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                # Create collection with correct vector dimensions
                await self.qdrant.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embeddings.dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            
            self._collection_initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            raise

    def validate_file(self, filename: str, file_size: int) -> tuple[bool, str | None]:
        """Validate uploaded file.
        
        Args:
            filename: Name of the uploaded file
            file_size: Size of the file in bytes
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file size
        if file_size > MAX_FILE_SIZE_BYTES:
            return False, f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"

        # Check file extension
        file_path = Path(filename)
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(ALLOWED_EXTENSIONS)
            return False, f"Unsupported file type. Allowed: {allowed}"

        return True, None

    def extract_text(self, file: BinaryIO, filename: str) -> str:
        """Extract text content from uploaded file.
        
        Args:
            file: Binary file object
            filename: Original filename
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If file type is not supported or extraction fails
        """
        file_ext = Path(filename).suffix.lower()

        try:
            if file_ext == ".pdf":
                return self._extract_pdf(file)
            elif file_ext in {".txt", ".md", ".markdown"}:
                return self._extract_text_file(file)
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")

        except Exception as e:
            logger.error(f"Text extraction failed for {filename}: {e}")
            raise ValueError(f"Failed to extract text: {str(e)}")

    def _extract_pdf(self, file: BinaryIO) -> str:
        """Extract text from PDF file.
        
        Args:
            file: Binary PDF file
            
        Returns:
            Extracted text
        """
        reader = PdfReader(file)
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n\n".join(text_parts)

    def _extract_text_file(self, file: BinaryIO) -> str:
        """Extract text from plain text or markdown file.
        
        Args:
            file: Binary text file
            
        Returns:
            Decoded text content
        """
        content = file.read()
        
        # Try UTF-8 first, fall back to latin-1
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")

    def chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for embedding.
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of text chunks
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            length_function=len,
            is_separator_regex=False,
        )

        chunks = splitter.split_text(text)
        return chunks

    async def ingest_document(
        self,
        file: BinaryIO,
        filename: str,
        file_size: int,
        user_id: UUID,
    ) -> dict:
        """Ingest a document: extract text, chunk, embed, and store in Qdrant.
        
        Args:
            file: Binary file content
            filename: Original filename
            file_size: File size in bytes
            user_id: ID of user uploading the document
            
        Returns:
            Dictionary with document ID and ingestion stats
            
        Raises:
            ValueError: If validation fails or processing error occurs
        """
        # Ensure collection exists
        await self.initialize_collection()

        # Validate file
        is_valid, error = self.validate_file(filename, file_size)
        if not is_valid:
            raise ValueError(error)

        # Extract text
        text = self.extract_text(file, filename)
        
        if not text or not text.strip():
            raise ValueError("No text content found in document")

        # Generate content hash
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Chunk text
        chunks = self.chunk_text(text)
        
        if not chunks:
            raise ValueError("Failed to generate chunks from document")

        # Generate document ID
        document_id = str(uuid4())
        uploaded_at = datetime.now(UTC)

        # Generate embeddings for all chunks
        embeddings = await self.embeddings.embed_batch(chunks)

        # Create points for Qdrant
        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = DocumentMetadata(
                document_id=document_id,
                filename=filename,
                file_type=Path(filename).suffix.lower(),
                file_size=file_size,
                user_id=user_id,
                uploaded_at=uploaded_at,
                chunk_index=idx,
                total_chunks=len(chunks),
                content_hash=content_hash,
            )

            point = PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload={
                    "text": chunk,
                    **metadata.to_dict(),
                },
            )
            points.append(point)

        # Store in Qdrant
        await self.qdrant.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

        logger.info(
            f"Ingested document {document_id} ({filename}): "
            f"{len(chunks)} chunks, {len(text)} characters"
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "chunks": len(chunks),
            "characters": len(text),
            "uploaded_at": uploaded_at.isoformat(),
        }

    async def list_documents(self, user_id: UUID) -> list[dict]:
        """List documents uploaded by a specific user.
        
        Args:
            user_id: User ID to filter by
            
        Returns:
            List of document metadata dictionaries
        """
        try:
            # Ensure collection exists
            await self.initialize_collection()

            # Scroll through all points and filter by user_id
            # Note: This is not the most efficient for large datasets
            # In production, consider maintaining a separate metadata store
            
            all_points = []
            offset = None
            
            while True:
                result = await self.qdrant.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                
                points, next_offset = result
                
                if not points:
                    break
                
                # Filter by user_id and deduplicate by document_id
                for point in points:
                    payload = point.payload
                    if payload.get("user_id") == str(user_id):
                        # Only keep first chunk of each document
                        if payload.get("chunk_index") == 0:
                            all_points.append(payload)
                
                if next_offset is None:
                    break
                    
                offset = next_offset

            # Sort by upload time (newest first)
            all_points.sort(key=lambda p: p.get("uploaded_at", ""), reverse=True)

            return all_points

        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    async def delete_document(self, document_id: str, user_id: UUID) -> bool:
        """Delete a document and all its chunks.
        
        Args:
            document_id: Document ID to delete
            user_id: User ID (for authorization check)
            
        Returns:
            True if deleted, False if not found or unauthorized
        """
        try:
            # Ensure collection exists
            await self.initialize_collection()

            # Scroll to find all points for this document
            points_to_delete = []
            offset = None
            user_id_str = str(user_id)

            while True:
                result = await self.qdrant.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                points, next_offset = result

                if not points:
                    break

                # Find matching document chunks
                for point in points:
                    payload = point.payload
                    if (
                        payload.get("document_id") == document_id
                        and payload.get("user_id") == user_id_str
                    ):
                        points_to_delete.append(point.id)

                if next_offset is None:
                    break

                offset = next_offset

            if not points_to_delete:
                return False

            # Delete all points
            await self.qdrant.client.delete(
                collection_name=self.collection_name,
                points_selector=points_to_delete,
            )

            logger.info(
                f"Deleted document {document_id}: {len(points_to_delete)} chunks"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False

    async def search_documents(
        self,
        query: str,
        user_id: UUID,
        limit: int = 5,
    ) -> list[dict]:
        """Semantic search across user's documents.
        
        Args:
            query: Search query text
            user_id: User ID to filter results
            limit: Maximum number of results
            
        Returns:
            List of matching chunks with metadata and scores
        """
        try:
            # Ensure collection exists
            await self.initialize_collection()

            # Generate query embedding
            query_embedding = await self.embeddings.embed_text(query)

            # Search in Qdrant
            results = await self.qdrant.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit * 3,  # Get more, then filter
                with_payload=True,
            )

            # Filter by user_id and format results
            user_results = []
            for result in results:
                if result.payload.get("user_id") == str(user_id):
                    user_results.append({
                        "text": result.payload.get("text", ""),
                        "score": result.score,
                        "document_id": result.payload.get("document_id"),
                        "filename": result.payload.get("filename"),
                        "chunk_index": result.payload.get("chunk_index"),
                        "file_type": result.payload.get("file_type"),
                    })
                    
                    if len(user_results) >= limit:
                        break

            return user_results

        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
