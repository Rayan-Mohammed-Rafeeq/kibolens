"""Authenticated operational and account notification settings."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from app.ai.router.core import get_ai_router
from app.api.dependencies import CsrfSession, CurrentUser, DatabaseSession
from app.core.config import Settings, get_settings
from app.services.email import EmailSendError, MockEmailService, ResendEmailService
from app.services.notifications import send_test_email
from app.services.otp import OTPError, create_otp_challenge, generate_otp, verify_otp

router = APIRouter(prefix="/settings", tags=["settings"])


UTC = timezone.utc


class NotificationPreferencesRequest(BaseModel):
    enabled: bool
    minimum_severity: Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
    recovery_enabled: bool


class VerifyEmailRequest(BaseModel):
    otp: str


@router.get("")
async def settings_summary(
    user: CurrentUser,
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
            "provider_configured": bool(settings.resend_api_key),
            "account_email": user.email,
            "email_verified": user.email_verified_at is not None,
            "incident_notifications_enabled": user.incident_notifications_enabled,
            "minimum_severity": user.incident_notification_min_severity,
            "recovery_notifications_enabled": user.recovery_notifications_enabled,
            "delivery_status": (
                "ready" if user.email and user.email_verified_at and settings.resend_api_key
                else "email_not_verified" if not user.email or not user.email_verified_at
                else "resend_not_configured"
            ),
        },
    }


@router.patch("/notifications")
async def update_notification_preferences(
    payload: NotificationPreferencesRequest,
    user: CurrentUser,
    _: CsrfSession,
    database: DatabaseSession,
) -> dict:
    user.incident_notifications_enabled = payload.enabled
    user.incident_notification_min_severity = payload.minimum_severity
    user.recovery_notifications_enabled = payload.recovery_enabled
    database.commit()
    return {
        "enabled": user.incident_notifications_enabled,
        "minimum_severity": user.incident_notification_min_severity,
        "recovery_enabled": user.recovery_notifications_enabled,
    }


@router.post("/verify-email")
async def send_account_verification(
    user: CurrentUser,
    _: CsrfSession,
    database: DatabaseSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not user.email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account has no email address.")
    if user.email_verified_at:
        return {"status": "verified"}
    if not settings.resend_api_key and settings.environment != "test":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Resend email delivery is not configured.")
    otp = generate_otp()
    create_otp_challenge(database, str(user.id), otp, settings)
    service = MockEmailService() if settings.environment == "test" else ResendEmailService(
        api_key=settings.resend_api_key.get_secret_value(), from_email=settings.email_from, reply_to=settings.email_reply_to
    )
    try:
        service.send_otp_email(user.email, otp)
    except EmailSendError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email verification delivery failed.") from exc
    return {"status": "sent"}


@router.post("/verify-email/confirm")
async def confirm_account_verification(
    payload: VerifyEmailRequest,
    user: CurrentUser,
    _: CsrfSession,
    database: DatabaseSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    try:
        verify_otp(database, str(user.id), payload.otp, settings)
    except OTPError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code.") from exc
    user.email_verified_at = datetime.now(UTC)
    database.commit()
    return {"status": "verified"}


@router.post("/test-email")
async def test_email(
    user: CurrentUser,
    _: CsrfSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")
    if not user.email or not user.email_verified_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Verify your account email before sending a test notification.")
    recipient = user.email.lower()
    try:
        provider_id = await send_test_email(settings, recipient)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "sent", "recipient": recipient, "provider_id": provider_id}
