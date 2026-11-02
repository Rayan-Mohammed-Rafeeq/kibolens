"""Authenticated, read-only operational settings for the administrator UI."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.ai.router.core import get_ai_router
from app.api.dependencies import CsrfSession, CurrentUser
from app.core.config import Settings, get_settings
from app.services.notifications import send_test_email

router = APIRouter(prefix="/settings", tags=["settings"])


class TestEmailRequest(BaseModel):
    recipient: EmailStr | None = None


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
        "notifications": {
            "configured_recipient_count": len(settings.get_incident_notification_emails()),
            "test_recipient_count": len(settings.get_incident_test_recipient_emails()),
        },
    }


@router.post("/test-email")
async def test_email(
    payload: TestEmailRequest,
    user: CurrentUser,
    _: CsrfSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")
    configured = settings.get_incident_test_recipient_emails()
    recipient = str(payload.recipient).lower() if payload.recipient else next(iter(configured), None)
    if not recipient or recipient not in configured:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recipient is not configured as an incident test recipient.")
    try:
        provider_id = await send_test_email(settings, recipient)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "sent", "recipient": recipient, "provider_id": provider_id}
