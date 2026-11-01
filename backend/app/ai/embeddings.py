"""Embedding service using Ollama for vector representations."""

from __future__ import annotations

import logging
from typing import Literal

from ollama import AsyncClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Embedding model dimensions
EMBEDDING_DIMENSIONS = {
    "all-minilm": 384,  # all-minilm:latest (Sentence Transformers)
    "nomic-embed-text": 768,  # nomic-embed-text:latest
    "mxbai-embed-large": 1024,  # mxbai-embed-large:latest
}

EmbeddingModel = Literal["all-minilm", "nomic-embed-text", "mxbai-embed-large"]


class EmbeddingService:
    """Service for generating text embeddings using Ollama.
    
    Uses lightweight all-minilm model by default for low resource usage.
    """

    def __init__(
        self,
        settings: Settings,
        model: EmbeddingModel = "all-minilm",
    ):
        """Initialize embedding service.
        
        Args:
            settings: Application settings with Ollama configuration
            model: Embedding model to use (default: all-minilm for low resource usage)
        """
        self.settings = settings
        self.model = model
        self.base_url = settings.ollama_base_url
        self.timeout = settings.ollama_timeout_seconds
        
        # Initialize Ollama AsyncClient
        self._client = AsyncClient(host=self.base_url, timeout=self.timeout)

    @property
    def dimension(self) -> int:
        """Get embedding dimension for the configured model.
        
        Returns:
            Embedding vector dimension
        """
        return EMBEDDING_DIMENSIONS[self.model]

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            Embedding vector as list of floats
            
        Raises:
            Exception: If embedding generation fails
        """
        try:
            response = await self._client.embeddings(
                model=self.model,
                prompt=text,
            )
            
            # Extract embedding from response
            embedding = response.get("embedding", [])
            
            if not embedding:
                raise ValueError("Empty embedding returned from Ollama")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            Exception: If any embedding generation fails
        """
        embeddings = []
        
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        
        return embeddings

    async def health_check(self) -> bool:
        """Check if Ollama is available and embedding model is installed.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False

                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check if embedding model is available
                return any(self.model in name for name in model_names)

        except Exception as e:
            logger.warning(f"Embedding service health check failed: {e}")
            return False


def get_embedding_service(
    settings: Settings,
    model: EmbeddingModel = "all-minilm",
) -> EmbeddingService:
    """Factory function to create embedding service.
    
    Args:
        settings: Application settings
        model: Embedding model to use
        
    Returns:
        EmbeddingService instance
    """
    return EmbeddingService(settings, model)
