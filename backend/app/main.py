from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.services.qdrant import get_qdrant_service

# Global Qdrant service instance
_qdrant_service = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global _qdrant_service

    # Startup: Initialize Qdrant service
    settings = get_settings()
    _qdrant_service = get_qdrant_service(settings)

    # Pre-warm the AI router singleton (validates configuration)
    if settings.llm_provider.lower() == "cloud":
        try:
            from app.ai.router.core import get_ai_router
            await get_ai_router(settings)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "AI router pre-warm failed (non-fatal): %s", exc
            )
    else:
        # Legacy Ollama path: validate embedding service configuration
        try:
            from app.ai.embeddings import get_embedding_service
            get_embedding_service(settings)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Ollama embedding service init failed (non-fatal): %s", exc
            )

    yield

    # Shutdown: Close Qdrant client
    if _qdrant_service:
        await _qdrant_service.close()

    # Reset AI router singleton
    try:
        from app.ai.router.core import reset_ai_router
        reset_ai_router()
    except Exception:
        pass


def create_application() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_application()
