from app.api.routes.auth import router as auth_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.infrastructure import alerts_router
from app.api.routes.infrastructure import router as infrastructure_router
from app.api.routes.investigation import router as investigation_router
from app.api.routes.ai_router import router as ai_router_health_router
from app.api.routes.llm import router as llm_router
from app.api.routes.qdrant import router as qdrant_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(conversations_router)
api_router.include_router(infrastructure_router)
api_router.include_router(incidents_router)
api_router.include_router(alerts_router)
# Cloud AI router health (new: /ai/health, /ai/llm/health, /ai/llm/test)
api_router.include_router(ai_router_health_router)
# Legacy LLM endpoints kept for backward compatibility (/llm/health, /llm/test)
api_router.include_router(llm_router)
api_router.include_router(qdrant_router)
api_router.include_router(documents_router)
api_router.include_router(investigation_router)
