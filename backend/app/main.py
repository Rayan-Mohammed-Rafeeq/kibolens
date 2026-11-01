from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.embeddings import get_embedding_service
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
    
    # Initialize embedding service to validate configuration
    embedding_service = get_embedding_service(settings)
    
    yield
    
    # Shutdown: Close Qdrant client
    if _qdrant_service:
        await _qdrant_service.close()


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
