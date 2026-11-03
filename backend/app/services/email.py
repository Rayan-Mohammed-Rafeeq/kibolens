"""Transactional email delivery and branded KiboLens templates."""

from __future__ import annotations

import logging
from html import escape
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when email sending fails."""


class EmailServiceProtocol(Protocol):
    def send_otp_email(self, to_email: str, otp_code: str) -> None: ...


class ResendEmailService:
    """Email service using the Resend HTTP API."""

    def __init__(self, api_key: str, from_email: str, reply_to: str | None = None):
        self.api_key = api_key
        self.from_email = from_email
        self.reply_to = reply_to or from_email
        self.base_url = "https://api.resend.com"

    def send_otp_email(self, to_email: str, otp_code: str) -> None:
        self._send_email(to_email, "KiboLens - Your verification code", *render_otp_email(otp_code))

    def send_incident_email(
        self, to_email: str, subject: str, text_body: str, html_body: str
    ) -> str:
        return self._send_email(to_email, subject, text_body, html_body)

    def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> str:
        parts = to_email.split("@")
        masked = f"{parts[0][:2]}***@{parts[1]}" if len(parts) == 2 else "***"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.base_url}/emails",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": self.from_email,
                        "to": [to_email],
                        "reply_to": self.reply_to,
                        "subject": subject,
                        "text": text_body,
                        "html": html_body,
                    },
                )
                if response.status_code not in (200, 201):
                    logger.error("Resend API error: status=%s response=%s", response.status_code, response.text[:200])
                    raise EmailSendError(f"Failed to send email: HTTP {response.status_code}")
                logger.info("Email accepted by provider for %s", masked)
                return str(response.json().get("id", ""))
        except EmailSendError:
            raise
        except httpx.TimeoutException as exc:
            logger.error("Resend API timeout: %s", exc)
            raise EmailSendError("Email service timeout") from exc
        except httpx.RequestError as exc:
            logger.error("Resend API request error: %s", exc)
            raise EmailSendError("Email service unavailable") from exc
        except Exception as exc:
            logger.error("Unexpected error sending email: %s", exc)
            raise EmailSendError("Failed to send email") from exc


class MockEmailService:
    """In-memory email service used by tests."""

    def __init__(self):
        self.sent_emails: list[dict[str, str]] = []

    def send_otp_email(self, to_email: str, otp_code: str) -> None:
        self.sent_emails.append({"to": to_email, "otp": otp_code})

    def send_incident_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> str:
        self.sent_emails.append({"to": to_email, "subject": subject, "text": text_body, "html": html_body})
        return "mock-email-id"

    def get_last_otp(self, email: str) -> str | None:
        for sent in reversed(self.sent_emails):
            if sent["to"] == email and "otp" in sent:
                return sent["otp"]
        return None

    def clear(self) -> None:
        self.sent_emails.clear()


def render_otp_email(otp_code: str) -> tuple[str, str]:
    """Return mobile-safe plain text and inline-styled HTML OTP content."""
    safe_code = escape(otp_code)
    text = (
        f"Your KiboLens verification code is {otp_code}.\n\n"
        "This code expires in 5 minutes. If you did not request it, you can safely ignore this email.\n\n"
        "KiboLens - Secure infrastructure operations"
    )
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#0b1220;color:#dbeafe;font-family:Arial,Helvetica,sans-serif;line-height:1.5">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1220"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#111827;border:1px solid #26354d;border-radius:14px;overflow:hidden">
<tr><td style="padding:22px 28px;background:#0f1c33;border-bottom:1px solid #26354d"><strong style="font-size:20px;color:#67e8f9">KiboLens</strong><span style="float:right;font-size:12px;color:#94a3b8">SECURE ACCESS</span></td></tr>
<tr><td style="padding:36px 28px;text-align:center"><p style="margin:0;color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:1.5px">Verification code</p><div style="margin:22px 0;padding:20px;background:#0b1220;border:1px solid #22d3ee;border-radius:10px"><span style="font-family:Courier New,monospace;font-size:32px;letter-spacing:8px;font-weight:bold;color:#f8fafc">{safe_code}</span></div><p style="margin:0;color:#cbd5e1;font-size:15px">This code expires in <strong style="color:#67e8f9">5 minutes</strong>.</p><p style="margin:24px 0 0;color:#64748b;font-size:13px">If you did not request this code, you can safely ignore this email.</p></td></tr>
<tr><td style="padding:18px 28px;border-top:1px solid #26354d;color:#64748b;font-size:12px">KiboLens - Secure infrastructure operations</td></tr></table>
</td></tr></table></body></html>"""
    return text, html


def render_test_email() -> tuple[str, str]:
    text = "KiboLens test notification\n\nThis confirms that the configured email provider can accept KiboLens notifications. No infrastructure action was performed."
    html = """<!doctype html><html><body style="margin:0;background:#0b1220;color:#dbeafe;font-family:Arial,Helvetica,sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:32px 16px"><table role="presentation" width="100%" style="max-width:560px;background:#111827;border:1px solid #26354d;border-radius:14px;padding:32px"><tr><td><strong style="font-size:20px;color:#67e8f9">KiboLens</strong><h1 style="color:#f8fafc;font-size:24px;margin:32px 0 12px">Test notification</h1><p style="color:#cbd5e1">Your configured email provider accepted this test message. No infrastructure action was performed.</p><p style="color:#64748b;font-size:12px;margin-top:32px">KiboLens - Secure infrastructure operations</p></td></tr></table></td></tr></table></body></html>"""
    return text, html
