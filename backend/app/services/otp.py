"""
OTP (One-Time Password) service for two-factor authentication.

Security properties:
- Cryptographically secure random generation
- HMAC-based digest storage (never stores plaintext OTP)
- Constant-time comparison
- Time-limited validity
- Attempt limiting
- Single-use enforcement
- Resend cooldown
- Automatic invalidation of old OTPs
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from datetime import timezone as tz

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.otp_challenge import OTPChallenge

UTC = tz.utc


class OTPError(Exception):
    """Base exception for OTP operations."""
    pass


class OTPExpiredError(OTPError):
    """OTP has expired."""
    pass


class OTPMaxAttemptsError(OTPError):
    """Maximum verification attempts exceeded."""
    pass


class OTPAlreadyConsumedError(OTPError):
    """OTP has already been used."""
    pass


class OTPInvalidError(OTPError):
    """OTP verification failed."""
    pass


class OTPResendCooldownError(OTPError):
    """Too soon to resend OTP."""
    pass


def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit OTP.
    
    Uses secrets module for cryptographic randomness.
    """
    return f"{secrets.randbelow(1000000):06d}"


def otp_digest(otp: str, secret: str) -> str:
    """
    Create HMAC-SHA256 digest of OTP.
    
    Uses constant-time HMAC for secure storage and comparison.
    Never stores or logs the plaintext OTP.
    """
    return hmac.new(
        secret.encode(),
        otp.encode(),
        hashlib.sha256
    ).hexdigest()


def create_otp_challenge(
    database: Session,
    user_id: uuid.UUID | str,
    otp: str,
    settings: Settings
) -> OTPChallenge:
    """
    Create a new OTP challenge for a user.
    
    Invalidates any existing active challenges for the user.
    Stores only the HMAC digest, not the plaintext OTP.
    """
    # Convert string to UUID if needed
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    
    # Invalidate any existing active challenges
    existing_challenges = database.scalars(
        select(OTPChallenge).where(
            OTPChallenge.user_id == user_id,
            OTPChallenge.consumed == False,  # noqa: E712
            OTPChallenge.invalidated_at.is_(None)
        )
    ).all()
    
    now = datetime.now(UTC)
    for challenge in existing_challenges:
        challenge.invalidated_at = now
    
    # Create new challenge
    challenge = OTPChallenge(
        user_id=user_id,
        otp_digest=otp_digest(otp, settings.otp_hash_secret.get_secret_value()),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        consumed=False,
        attempts=0,
    )
    
    database.add(challenge)
    database.commit()
    database.refresh(challenge)
    
    return challenge


def verify_otp(
    database: Session,
    user_id: uuid.UUID | str,
    otp: str,
    settings: Settings
) -> OTPChallenge:
    """
    Verify an OTP for a user.
    
    Security:
    - Uses constant-time comparison
    - Enforces expiration
    - Enforces attempt limits
    - Enforces single-use
    - Marks as consumed on success
    
    Raises:
        OTPInvalidError: No active challenge found
        OTPExpiredError: Challenge expired
        OTPAlreadyConsumedError: Already used
        OTPMaxAttemptsError: Too many attempts
        OTPInvalidError: Verification failed
    """
    # Convert string to UUID if needed
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    
    # Find active challenge
    challenge = database.scalar(
        select(OTPChallenge).where(
            OTPChallenge.user_id == user_id,
            OTPChallenge.consumed == False,  # noqa: E712
            OTPChallenge.invalidated_at.is_(None)
        ).order_by(OTPChallenge.created_at.desc())
    )
    
    if not challenge:
        raise OTPInvalidError("No active OTP challenge found")
    
    # Check expiration
    now = datetime.now(UTC)
    if challenge.expires_at.replace(tzinfo=UTC) <= now:
        raise OTPExpiredError("OTP has expired")
    
    # Check if already consumed
    if challenge.consumed:
        raise OTPAlreadyConsumedError("OTP has already been used")
    
    # Check attempts
    if challenge.attempts >= settings.otp_max_attempts:
        raise OTPMaxAttemptsError("Maximum verification attempts exceeded")
    
    # Increment attempts
    challenge.attempts += 1
    database.commit()
    
    # Verify OTP using constant-time comparison
    expected_digest = otp_digest(otp, settings.otp_hash_secret.get_secret_value())
    if not hmac.compare_digest(challenge.otp_digest, expected_digest):
        database.commit()  # Save incremented attempts
        raise OTPInvalidError("Invalid OTP")
    
    # Mark as consumed
    challenge.consumed = True
    database.commit()
    database.refresh(challenge)
    
    return challenge


def can_resend_otp(
    database: Session,
    user_id: uuid.UUID | str,
    settings: Settings
) -> tuple[bool, int]:
    """
    Check if user can request a new OTP (resend cooldown).
    
    Returns:
        Tuple of (can_resend: bool, seconds_remaining: int)
    """
    # Convert string to UUID if needed
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    
    # Find most recent challenge
    latest_challenge = database.scalar(
        select(OTPChallenge).where(
            OTPChallenge.user_id == user_id
        ).order_by(OTPChallenge.created_at.desc())
    )
    
    if not latest_challenge:
        return True, 0
    
    # Check cooldown
    now = datetime.now(UTC)
    cooldown_expires = latest_challenge.created_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.otp_resend_cooldown_seconds
    )
    
    if now >= cooldown_expires:
        return True, 0
    
    # A blocked request should always communicate at least one second left;
    # truncating a sub-second remainder to zero makes clients retry too early.
    seconds_remaining = max(1, int((cooldown_expires - now).total_seconds() + 0.999999))
    return False, seconds_remaining


def cleanup_expired_challenges(database: Session) -> int:
    """
    Clean up expired OTP challenges.
    
    Should be called periodically (e.g., via background task).
    Returns the number of challenges deleted.
    """
    # Delete challenges expired more than 1 hour ago
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    
    result = database.execute(
        select(OTPChallenge).where(
            OTPChallenge.expires_at < cutoff
        )
    )
    
    challenges = result.scalars().all()
    count = len(challenges)
    
    for challenge in challenges:
        database.delete(challenge)
    
    database.commit()
    return count
