"""Cloud embedding service using Gemini Embedding.

This module replaces the Ollama-based embedding service for cloud deployments.
The critical invariant: vectors from different embedding models MUST NOT be
mixed in the same Qdrant collection.  This service uses a single canonical
model (gemini text-embedding-004, 768 dimensions) for all operations.

If Gemini embedding is temporarily unavailable, the service raises
EmbeddingUnavailableError so callers can keep ingestion pending rather than
silently inserting incompatible vectors.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.ai.router.types import FailureCategory
from app.core.config import Settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Canonical embedding model — do not change without migrating the
# Qdrant collection and re-indexing all documents.
# ─────────────────────────────────────────────────────────────────
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_EMBEDDING_DIMENSION = 768

# Supported Gemini task types
EmbeddingTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY"]


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding provider is temporarily unavailable.

    Callers should keep ingestion pending rather than inserting vectors from
    a different (incompatible) model.
    """


class CloudEmbeddingService:
    """Embedding service that routes through the central AI router.

    Wraps AIRouter.embed() to present the same interface as the legacy
    EmbeddingService, while enforcing single-model vector-space integrity.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = getattr(settings, "gemini_embedding_model", GEMINI_EMBEDDING_MODEL)
        self._dimension = getattr(settings, "gemini_embedding_dimension", GEMINI_EMBEDDING_DIMENSION)

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(
        self,
        text: str,
        task_type: EmbeddingTaskType = "RETRIEVAL_DOCUMENT",
    ) -> list[float]:
        """Generate a single embedding vector.

        Raises:
            EmbeddingUnavailableError: If Gemini is temporarily unavailable.
            ValueError: If the returned vector has the wrong dimension.
        """
        from app.ai.router.core import get_ai_router

        router = await get_ai_router(self.settings)
        result = await router.embed(text, task_type=task_type)

        if result.unavailable or result.embedding is None:
            last_cat = None
            if result.attempts:
                last_cat = result.attempts[-1].failure_category
            raise EmbeddingUnavailableError(
                f"Gemini embedding temporarily unavailable "
                f"(last failure: {last_cat.value if last_cat else 'unknown'}). "
                "Document ingestion is pending."
            )

        vec = result.embedding
        if len(vec) != self._dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._dimension}, "
                f"got {len(vec)}.  Cannot insert incompatible vectors."
            )
        return vec

    async def embed_query(self, text: str) -> list[float]:
        """Generate a query embedding (uses RETRIEVAL_QUERY task type)."""
        return await self.embed_text(text, task_type="RETRIEVAL_QUERY")

    async def embed_batch(
        self,
        texts: list[str],
        task_type: EmbeddingTaskType = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts sequentially.

        Raises:
            EmbeddingUnavailableError: On the first unavailable response.
        """
        results = []
        for text in texts:
            vec = await self.embed_text(text, task_type=task_type)
            results.append(vec)
        return results

    async def health_check(self) -> bool:
        """Return True if the Gemini embedding API is reachable."""
        from app.ai.router.gemini_provider import GeminiProvider

        provider = GeminiProvider(self.settings)
        return await provider.health_check()


def get_cloud_embedding_service(settings: Settings) -> CloudEmbeddingService:
    """Factory function — returns a CloudEmbeddingService instance."""
    return CloudEmbeddingService(settings)
