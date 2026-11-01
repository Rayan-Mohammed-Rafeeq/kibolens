from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    generate_token,
    hash_password,
    password_matches,
    token_hash,
    tokens_match,
)
from app.models.session import UserSession
from app.models.user import User


class BootstrapAlreadyCompletedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class EmailNotAllowedError(Exception):
    """Email address not in administrator allowlist."""
    pass


class DuplicateEmailError(Exception):
    """Email address already registered."""
    pass


class DuplicateUsernameError(Exception):
    """Username already taken."""
    pass


def normalize_email(email: str) -> str:
    """Normalize email address for comparison (lowercase)."""
    return email.strip().lower()


def bootstrap_administrator(database: Session, username: str, email: str, password: str) -> User:
    """
    Bootstrap first administrator account.
    
    Deprecated: Use provision_administrator instead for multi-admin support.
    Kept for backward compatibility.
    """
    if database.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        raise BootstrapAlreadyCompletedError
    
    email_normalized = normalize_email(email)
    user = User(
        username=username,
        email=email,
        email_normalized=email_normalized,
        password_hash=hash_password(password),
        role="admin"
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


def provision_administrator(
    database: Session,
    username: str,
    email: str,
    password: str,
    settings: Settings
) -> User:
    """
    Provision an administrator account.
    
    Validates:
    - Email is in allowed list
    - Email not already registered
    - Username not already taken
    """
    email_normalized = normalize_email(email)
    allowed_emails = settings.get_allowed_emails()
    
    if email_normalized not in allowed_emails:
        raise EmailNotAllowedError(f"Email {email} is not in the administrator allowlist")
    
    # Check for duplicate email
    existing_email = database.scalar(
        select(User.id).where(User.email_normalized == email_normalized)
    )
    if existing_email:
        raise DuplicateEmailError(f"Email {email} is already registered")
    
    # Check for duplicate username
    existing_username = database.scalar(
        select(User.id).where(User.username == username)
    )
    if existing_username:
        raise DuplicateUsernameError(f"Username {username} is already taken")
    
    user = User(
        username=username,
        email=email,
        email_normalized=email_normalized,
        password_hash=hash_password(password),
        role="admin"
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


def authenticate(database: Session, username: str, password: str) -> User:
    """
    Authenticate user by username and password.
    
    Note: This only verifies credentials. Session creation requires OTP verification.
    """
    user = database.scalar(select(User).where(User.username == username))
    if user is None or not password_matches(user.password_hash, password):
        raise InvalidCredentialsError
    return user


def authenticate_by_email(database: Session, email: str, password: str) -> User:
    """
    Authenticate user by email and password.
    
    Note: This only verifies credentials. Session creation requires OTP verification.
    """
    email_normalized = normalize_email(email)
    user = database.scalar(select(User).where(User.email_normalized == email_normalized))
    if user is None or not password_matches(user.password_hash, password):
        raise InvalidCredentialsError
    return user


def create_session(
    database: Session, user: User, settings: Settings
) -> tuple[str, str, UserSession]:
    raw_token = generate_token()
    raw_csrf_token = generate_token()
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw_token, settings),
        csrf_token_hash=token_hash(raw_csrf_token, settings),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
    )
    database.add(session)
    database.commit()
    return raw_token, raw_csrf_token, session


def get_active_session(database: Session, raw_token: str, settings: Settings) -> UserSession | None:
    session = database.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(raw_token, settings))
    )
    if session is None or session.revoked_at is not None or _is_expired(session.expires_at):
        return None
    return session


def revoke_session(database: Session, session: UserSession) -> None:
    session.revoked_at = datetime.now(UTC)
    database.commit()


def csrf_token_matches(session: UserSession, csrf_token: str, settings: Settings) -> bool:
    return tokens_match(session.csrf_token_hash, csrf_token, settings)


def rotate_csrf_token(database: Session, session: UserSession, settings: Settings) -> str:
    raw_csrf_token = generate_token()
    session.csrf_token_hash = token_hash(raw_csrf_token, settings)
    database.commit()
    return raw_csrf_token


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)
