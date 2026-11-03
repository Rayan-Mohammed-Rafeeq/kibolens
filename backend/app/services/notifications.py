"""Idempotent incident email notifications."""

from __future__ import annotations

import asyncio
from html import escape
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.incident import EvidenceRecord, Incident
from app.models.notification import EmailNotification
from app.models.user import User
from app.services.email import MockEmailService, ResendEmailService, render_test_email

UTC = timezone.utc
SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}


def _account_is_eligible(user: User, incident: Incident, event_key: str) -> bool:
    if not user.email or not user.email_verified_at or not user.incident_notifications_enabled:
        return False
    if event_key == "resolved":
        return user.recovery_notifications_enabled
    minimum = SEVERITY_RANK.get(user.incident_notification_min_severity.upper(), 1)
    return SEVERITY_RANK.get(incident.severity, 1) >= minimum


def notification_recipients(
    db: Session,
    incident: Incident,
    event_key: str,
    user: User | None = None,
    configured_recipients: list[str] | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Resolve recipients from the configured owner list first.

    The configured list is deployment authority for infrastructure alerts. User
    preferences remain available for account-scoped delivery when no owner list
    is configured.
    """
    if configured_recipients is not None:
        return sorted({item.strip().lower() for item in configured_recipients if item.strip()})
    if settings is not None and settings.incident_notification_emails.strip():
        return settings.get_incident_notification_emails()
    if user is not None:
        return [user.email.lower()] if _account_is_eligible(user, incident, event_key) else []
    if settings is not None and settings.get_incident_notification_emails():
        return settings.get_incident_notification_emails()
    accounts = db.scalars(select(User).where(User.email.is_not(None))).all()
    recipients = [user.email.lower() for user in accounts if _account_is_eligible(user, incident, event_key)]
    # Preserve the existing server-side recipient integration for deployments
    # that have not yet provisioned an account preference. It is never derived
    # from a client request and remains useful for Alertmanager delivery.
    if not accounts and settings is not None:
        recipients = settings.get_incident_notification_emails()
    return sorted(set(recipients))


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
    text_body, html_body = render_test_email()
    return await asyncio.to_thread(
        service.send_incident_email,
        recipient,
        "KiboLens test notification",
        text_body,
        html_body,
    )


async def notify_incident(
    db: Session,
    incident: Incident,
    event_key: str,
    settings: Settings,
    recipients: list[str] | None = None,
    user: User | None = None,
) -> list[dict]:
    recipients = notification_recipients(db, incident, event_key, user, recipients, settings)
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
    for recipient in sorted({item.strip().lower() for item in recipients if item.strip()}):
        existing = db.scalar(select(EmailNotification).where(
            EmailNotification.incident_id == incident.id,
            EmailNotification.event_key == event_key,
            EmailNotification.recipient == recipient,
        ))
        if existing and existing.status in {"queued", "accepted", "sent", "delivered"}:
            sent.append({"recipient": recipient, "status": "duplicate"})
            continue
        delivery = existing or EmailNotification(incident_id=incident.id, event_key=event_key, recipient=recipient, status="pending")
        if existing is None:
            db.add(delivery)
            db.flush()
        simulated = incident.source in {"simulation", "docker_lab"}
        subject = f"{'[SIMULATED] ' if simulated else ''}{incident.severity}: {incident.title}"
        link = f"{settings.public_app_url.rstrip('/')}/incidents/{incident.id}"
        evidence = db.scalar(
            select(EvidenceRecord)
            .where(EvidenceRecord.incident_id == incident.id)
            .order_by(
                (EvidenceRecord.metric_name.is_(None)),
                desc(EvidenceRecord.collected_at),
            )
        )
        observed, threshold, evidence_text, observed_at = _evidence_values(evidence)
        diagnostic_context = incident.description
        if simulated:
            diagnostic_context = f"This is a simulated demonstration only. {diagnostic_context}"
        text = _incident_text(incident, simulated, observed, threshold, observed_at, evidence_text, diagnostic_context, link)
        html = _incident_html(incident, simulated, observed, threshold, observed_at, evidence_text, diagnostic_context, link)
        try:
            delivery.attempts += 1
            delivery.last_attempt_at = datetime.now(UTC)
            if service is None:
                raise RuntimeError("Resend email delivery is not configured.")
            provider_id = await asyncio.to_thread(service.send_incident_email, recipient, subject, text, html)
            # Resend's synchronous API response means the provider accepted the
            # message. It does not prove inbox delivery.
            delivery.status = "accepted"
            delivery.provider_id = provider_id
            delivery.sent_at = datetime.now(UTC)
            delivery.error = None
            sent.append({"recipient": recipient, "status": "accepted", "provider_id": provider_id})
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)[:500]
            sent.append({"recipient": recipient, "status": "failed", "error": delivery.error})
        db.flush()
    return sent


def _evidence_values(evidence: EvidenceRecord | None) -> tuple[str, str, str, str]:
    if evidence is None:
        return "No metric observation", "Not applicable", "No structured evidence was persisted.", "Not recorded"
    if evidence.metric_name and evidence.metric_value is not None:
        observed = f"{evidence.metric_value:g} {evidence.unit or ''}".strip()
        metadata = evidence.evidence_metadata or {}
        if evidence.unit == "boolean" and evidence.metric_name == "configuration_valid":
            observed = "Configuration invalid"
        elif evidence.unit == "failed" and evidence.metric_name == "health_status":
            observed = "Health check failed"
        threshold_value = metadata.get("threshold", "Not configured")
        threshold = f"{threshold_value:g} {evidence.unit}" if isinstance(threshold_value, (int, float)) and evidence.unit not in {"boolean", "failed"} else str(threshold_value)
        timestamp = evidence.observed_at or evidence.collected_at
        return observed, threshold, metadata.get("logs", ""), timestamp.isoformat()
    metadata = evidence.evidence_metadata or {}
    details = "; ".join(f"{key}: {value}" for key, value in metadata.items() if key not in {"simulated", "labels"})
    timestamp = evidence.observed_at or evidence.collected_at
    return "Operational state", "Not applicable", details or "Operational evidence is available on the incident page.", timestamp.isoformat()


def _incident_text(incident: Incident, simulated: bool, observed: str, threshold: str, observed_at: str, evidence_text: str, diagnosis: str, link: str) -> str:
    label = "[SIMULATED] " if simulated else ""
    demo_label = "SIMULATED DEMONSTRATION\n" if simulated else ""
    return f"""{label}KiboLens incident alert

{demo_label}Incident: {incident.incident_number}
Title: {incident.title}
Severity: {incident.severity}
Status: {incident.status}
Resource: {incident.affected_service or incident.affected_host or 'Unknown'}
Observed: {observed}
Threshold: {threshold}
Observed at: {observed_at}

Diagnosis
{diagnosis}

Evidence
{evidence_text}

    View incident: {link}
    Open incident: {link}
{"This synthetic event is for demonstration only." if simulated else "This alert was generated from monitored infrastructure."}
"""


def _incident_html(incident: Incident, simulated: bool, observed: str, threshold: str, observed_at: str, evidence_text: str, diagnosis: str, link: str) -> str:
    def safe(value: object) -> str:
        return escape(str(value))

    badge_colors = {"INFO": "#38bdf8", "WARNING": "#fbbf24", "HIGH": "#fb923c", "CRITICAL": "#f87171"}
    severity_color = badge_colors.get(incident.severity, "#67e8f9")
    simulation_banner = '<tr><td style="padding:12px 24px;background:#422006;color:#fde68a;font-weight:bold">[SIMULATED] Demonstration event only</td></tr>' if simulated else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#0b1220;color:#dbeafe;font-family:Arial,Helvetica,sans-serif;line-height:1.5"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 12px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#111827;border:1px solid #26354d;border-radius:14px;overflow:hidden">
<tr><td style="padding:22px 24px;background:#0f1c33;border-bottom:1px solid #26354d"><strong style="font-size:20px;color:#67e8f9">KiboLens</strong><span style="float:right;color:#94a3b8;font-size:12px">INCIDENT ALERT</span></td></tr>{simulation_banner}
<tr><td style="padding:28px 24px"><p style="margin:0;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:1.5px">{'SIMULATED' if simulated else 'REAL'} infrastructure event</p><h1 style="margin:8px 0 18px;color:#f8fafc;font-size:24px">{safe(incident.title)}</h1><span style="display:inline-block;padding:5px 10px;border-radius:999px;background:{severity_color};color:#111827;font-weight:bold;font-size:12px">{safe(incident.severity)}</span></td></tr>
<tr><td style="padding:0 24px 22px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1220;border:1px solid #26354d;border-radius:10px"><tr><td style="padding:16px"><p style="margin:0 0 10px;color:#94a3b8;font-size:12px">INCIDENT SUMMARY</p><p style="margin:4px 0;color:#f8fafc"><strong>{safe(incident.incident_number)}</strong> · {safe(incident.status)}</p><p style="margin:4px 0;color:#cbd5e1">Resource: {safe(incident.affected_service or incident.affected_host or 'Unknown')}</p></td></tr></table></td></tr>
<tr><td style="padding:0 24px 22px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding:14px;background:#172236"><p style="margin:0;color:#94a3b8;font-size:12px">METRIC OBSERVATION</p><p style="margin:6px 0;color:#f8fafc;font-size:18px"><strong>{safe(observed)}</strong></p><p style="margin:0;color:#94a3b8;font-size:13px">Threshold: {safe(threshold)} · Observed: {safe(observed_at)}</p></td></tr></table></td></tr>
<tr><td style="padding:0 24px 22px"><p style="margin:0 0 6px;color:#67e8f9;font-weight:bold">Diagnosis</p><p style="margin:0;color:#cbd5e1">{safe(diagnosis)}</p><p style="margin:14px 0 0;color:#94a3b8;font-size:13px"><strong>Evidence:</strong> {safe(evidence_text)}</p></td></tr>
<tr><td align="center" style="padding:0 24px 30px"><a href="{escape(link, quote=True)}" style="display:inline-block;background:#22d3ee;color:#082f49;text-decoration:none;font-weight:bold;padding:13px 24px;border-radius:8px">View Incident</a></td></tr>
<tr><td style="padding:18px 24px;border-top:1px solid #26354d;color:#64748b;font-size:12px">KiboLens · Secure infrastructure operations<br>{'Synthetic events are demonstrations only.' if simulated else 'You are receiving this because this resource is monitored by KiboLens.'}</td></tr></table></td></tr></table></body></html>"""


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
