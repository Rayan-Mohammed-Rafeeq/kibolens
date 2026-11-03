"""
Email service using Resend for transactional email delivery.

Security notes:
- Never logs email content or OTP codes
- Uses Resend Python SDK or HTTP API
- Fails closed: no silent fallback if sending fails
"""
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when email sending fails."""
    pass


class EmailServiceProtocol(Protocol):
    """Protocol for email service implementations."""
    
    def send_otp_email(self, to_email: str, otp_code: str) -> None:
        """
        Send OTP code via email.
        
        Args:
            to_email: Recipient email address
            otp_code: Six-digit OTP code
            
        Raises:
            EmailSendError: If email cannot be sent
        """
        ...


class ResendEmailService:
    """
    Email service using Resend API.
    
    Uses HTTP API directly for minimal dependencies and explicit control.
    """
    
    def __init__(self, api_key: str, from_email: str, reply_to: str | None = None):
        self.api_key = api_key
        self.from_email = from_email
        self.reply_to = reply_to or from_email
        self.base_url = "https://api.resend.com"
        
    def send_otp_email(self, to_email: str, otp_code: str) -> None:
        """Send OTP verification email via Resend."""
        # Mask email for logging (show first 2 chars + domain)
        email_parts = to_email.split('@')
        masked_email = f"{email_parts[0][:2]}***@{email_parts[1]}" if len(email_parts) == 2 else "***"
        
        logger.info(f"Sending OTP email to {masked_email}")
        
        # Email content
        subject = "KiboLens - Your verification code"
        
        # Plain text version
        text_body = f"""Your KiboLens verification code is: {otp_code}

This code will expire in 5 minutes.

If you didn't request this code, please ignore this email.

---
KiboLens Incident Management System
"""
        
        # HTML version
        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px; text-align: center;">
        <h1 style="color: #2563eb; margin: 0 0 20px 0;">KiboLens</h1>
        <p style="font-size: 16px; color: #666; margin: 0 0 30px 0;">Your verification code</p>
        
        <div style="background-color: white; padding: 30px; border-radius: 8px; margin: 0 0 30px 0; border: 2px solid #e5e7eb;">
            <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; margin: 0; font-family: 'Courier New', monospace; color: #1e40af;">
                {otp_code}
            </p>
        </div>
        
        <p style="font-size: 14px; color: #666; margin: 0 0 10px 0;">
            This code will expire in <strong>5 minutes</strong>.
        </p>
        
        <p style="font-size: 14px; color: #999; margin: 30px 0 0 0;">
            If you didn't request this code, please ignore this email.
        </p>
    </div>
    
    <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
        <p style="font-size: 12px; color: #999; margin: 0;">
            KiboLens Incident Management System
        </p>
    </div>
</body>
</html>"""
        
        self._send_email(to_email, subject, text_body, html_body)

    def send_incident_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> str:
        """Send an incident notification and return Resend's message ID."""
        return self._send_email(to_email, subject, text_body, html_body)

    def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> str:
        # Send via Resend API
        email_parts = to_email.split("@")
        masked_email = f"{email_parts[0][:2]}***@{email_parts[1]}" if len(email_parts) == 2 else "***"
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
                    logger.error(
                        f"Resend API error: status={response.status_code}, "
                        f"response={response.text[:200]}"
                    )
                    raise EmailSendError(f"Failed to send email: HTTP {response.status_code}")
                    
                logger.info(f"Email sent successfully to {masked_email}")
                return str(response.json().get("id", ""))
                
        except httpx.TimeoutException as e:
            logger.error(f"Resend API timeout: {e}")
            raise EmailSendError("Email service timeout") from e
        except httpx.RequestError as e:
            logger.error(f"Resend API request error: {e}")
            raise EmailSendError("Email service unavailable") from e
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise EmailSendError("Failed to send email") from e


class MockEmailService:
    """
    Mock email service for testing.
    
    Stores sent emails in memory instead of actually sending them.
    """
    
    def __init__(self):
        self.sent_emails: list[dict[str, str]] = []
        
    def send_otp_email(self, to_email: str, otp_code: str) -> None:
        """Record email instead of sending it."""
        self.sent_emails.append({
            "to": to_email,
            "otp": otp_code,
        })
        logger.info(f"Mock: OTP email recorded for {to_email}")

    def send_incident_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> str:
        self.sent_emails.append({"to": to_email, "subject": subject, "text": text_body, "html": html_body})
        return "mock-email-id"
        
    def get_last_otp(self, email: str) -> str | None:
        """Get the last OTP sent to an email address (test helper)."""
        for sent in reversed(self.sent_emails):
            if sent["to"] == email:
                return sent["otp"]
        return None
        
    def clear(self) -> None:
        """Clear sent email history (test helper)."""
        self.sent_emails.clear()
