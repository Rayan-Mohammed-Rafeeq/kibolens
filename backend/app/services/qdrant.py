"""Qdrant vector database service."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.config import Settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Asynchronous Qdrant vector database service.
    
    Provides connection management and health checking for Qdrant.
    Used for RAG (Retrieval-Augmented Generation) vector storage.
    """

    def __init__(self, settings: Settings):
        """Initialize Qdrant service.
        
        Args:
            settings: Application settings with Qdrant configuration
        """
        self.settings = settings
        self.url = settings.qdrant_url
        self.timeout = settings.qdrant_timeout_seconds
        
        # Initialize async client
        # Note: No API key configured - internal Docker network only
        self._client = AsyncQdrantClient(
            url=self.url,
            timeout=self.timeout,
            # api_key=None - not needed for internal network
        )

    @property
    def client(self) -> AsyncQdrantClient:
        """Get the underlying Qdrant async client.
        
        Returns:
            AsyncQdrantClient instance
        """
        return self._client

    async def health_check(self) -> bool:
        """Check if Qdrant is reachable and healthy.
        
        Returns:
            True if Qdrant is healthy, False otherwise
        """
        try:
            # Try to get collections list as a health check
            # This will fail if Qdrant is not reachable
            collections = await self._client.get_collections()
            return collections is not None
            
        except (ResponseHandlingException, UnexpectedResponse, Exception) as e:
            logger.warning(f"Qdrant health check failed: {e}")
            return False

    async def get_version(self) -> str | None:
        """Get Qdrant server version.
        
        Returns:
            Version string if available, None on error
        """
        try:
            # Get version info from Qdrant using the REST API directly
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{self.url}/")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("version")
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get Qdrant version: {e}")
            return None

    async def close(self) -> None:
        """Close the Qdrant client connection.
        
        Call this during application shutdown to clean up resources.
        """
        try:
            await self._client.close()
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {e}")


def get_qdrant_service(settings: Settings) -> QdrantService:
    """Factory function to create Qdrant service.
    
    Args:
        settings: Application settings
        
    Returns:
        QdrantService instance
    """
    return QdrantService(settings)
