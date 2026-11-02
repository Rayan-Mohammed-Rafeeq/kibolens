"""Authenticated, read-only operational settings for the administrator UI."""

from fastapi import APIRouter, Depends

from app.ai.router.core import get_ai_router
from app.api.dependencies import CurrentUser
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def settings_summary(
    _: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Expose safe configuration metadata; secrets are never serialized."""
    ai_status = await (await get_ai_router(settings)).health_status()
    return {
        "environment": settings.environment,
        "monitoring": {
            "prometheus_url": settings.prometheus_url,
            "stale_after_seconds": settings.monitoring_stale_seconds,
        },
        "ai": {
            "provider_order": ["gemini", "groq", "openrouter"],
            "free_only": settings.ai_free_only,
            "paid_models_allowed": settings.ai_allow_paid_models,
            "router": ai_status,
        },
        "documents": {
            "max_file_size_mb": 10,
            "embedding_model": settings.gemini_embedding_model,
            "embedding_dimension": settings.gemini_embedding_dimension,
        },
        "authentication": {
            "otp_ttl_seconds": settings.otp_ttl_seconds,
            "secure_cookie": settings.session_cookie_secure,
            "allowed_email_count": len(settings.get_allowed_emails()),
        },
    }
