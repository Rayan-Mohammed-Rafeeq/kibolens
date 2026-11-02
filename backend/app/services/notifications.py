"""Idempotent incident email notifications."""

from __future__ import annotations

import asyncio
from html import escape
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.incident import Incident
from app.models.notification import EmailNotification
from app.services.email import MockEmailService, ResendEmailService

UTC = timezone.utc


async def send_test_email(settings: Settings, recipient: str) -> str:
    service = MockEmailService() if settings.environment == "test" else (
        ResendEmailService(
            api_key=settings.resend_api_key.get_secret_value(),
            from_email=settings.email_from,
            reply_to=settings.email_reply_to,
        ) if settings.resend_api_key else None
    )
    if service is None:
        raise RuntimeError("Email service is not configured.")
    return await asyncio.to_thread(
        service.send_incident_email,
        recipient,
        "KiboLens test notification",
        "This is a KiboLens administrator test email. No infrastructure action was performed.",
        "<html><body><p>This is a KiboLens administrator test email.</p><p>No infrastructure action was performed.</p></body></html>",
    )


async def notify_incident(
    db: Session,
    incident: Incident,
    event_key: str,
    settings: Settings,
    recipients: list[str] | None = None,
) -> list[dict]:
    recipients = recipients if recipients is not None else settings.get_incident_notification_emails()
    if not recipients:
        return []
    sent: list[dict] = []
    service = MockEmailService() if settings.environment == "test" else (
        ResendEmailService(
            api_key=settings.resend_api_key.get_secret_value(),
            from_email=settings.email_from,
            reply_to=settings.email_reply_to,
        ) if settings.resend_api_key else None
    )
    if service is None:
        return [{"recipient": recipient, "status": "not_configured"} for recipient in recipients]
    for recipient in sorted({item.strip().lower() for item in recipients if item.strip()}):
        existing = db.scalar(select(EmailNotification).where(
            EmailNotification.incident_id == incident.id,
            EmailNotification.event_key == event_key,
            EmailNotification.recipient == recipient,
        ))
        if existing and existing.status == "sent":
            sent.append({"recipient": recipient, "status": "duplicate"})
            continue
        delivery = existing or EmailNotification(incident_id=incident.id, event_key=event_key, recipient=recipient, status="pending")
        if existing is None:
            db.add(delivery)
            db.flush()
        simulated = incident.source == "simulation"
        subject = f"{'[SIMULATED] ' if simulated else ''}{incident.severity}: {incident.title}"
        link = f"{settings.public_app_url.rstrip('/')}/incidents/{incident.id}"
        text = (
            f"KiboLens incident {incident.incident_number}\n"
            f"Severity: {incident.severity}\nResource: {incident.affected_service or incident.affected_host or 'unknown'}\n"
            f"Status: {incident.status}\nDetected: {incident.first_detected_at.isoformat()}\n\n"
            f"{incident.description}\n\nOpen incident: {link}\nInvestigate with AI from the incident page."
        )
        html = "<html><body>" + "".join(
            f"<p><strong>{escape(label)}</strong> {escape(str(value))}</p>" for label, value in (
                ("Incident", incident.incident_number), ("Severity", incident.severity),
                ("Resource", incident.affected_service or incident.affected_host or "unknown"),
                ("Status", incident.status), ("Detected", incident.first_detected_at.isoformat()),
            )
        ) + f"<p>{escape(incident.description)}</p><p><a href='{escape(link, quote=True)}'>Open incident and investigate with AI</a></p></body></html>"
        try:
            delivery.attempts += 1
            delivery.last_attempt_at = datetime.now(UTC)
            provider_id = await asyncio.to_thread(service.send_incident_email, recipient, subject, text, html)
            delivery.status = "sent"
            delivery.provider_id = provider_id
            delivery.sent_at = datetime.now(UTC)
            delivery.error = None
            sent.append({"recipient": recipient, "status": "sent"})
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = type(exc).__name__
            sent.append({"recipient": recipient, "status": "failed"})
        db.flush()
    return sent


async def retry_failed_notifications(db: Session, settings: Settings, limit: int = 20) -> int:
    """Retry failed incident notifications at most twice after the first try."""
    failed = db.scalars(
        select(EmailNotification)
        .where(EmailNotification.status == "failed", EmailNotification.attempts < 3)
        .order_by(EmailNotification.last_attempt_at)
        .limit(limit)
    ).all()
    retried = 0
    for delivery in failed:
        incident = db.get(Incident, delivery.incident_id) if delivery.incident_id else None
        if incident is None:
            continue
        await notify_incident(db, incident, delivery.event_key, settings, [delivery.recipient])
        retried += 1
    db.commit()
    return retried
