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


def bootstrap_administrator(database: Session, username: str, password: str) -> User:
    if database.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        raise BootstrapAlreadyCompletedError
    user = User(username=username, password_hash=hash_password(password), role="admin")
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


def authenticate(database: Session, username: str, password: str) -> User:
    user = database.scalar(select(User).where(User.username == username))
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
