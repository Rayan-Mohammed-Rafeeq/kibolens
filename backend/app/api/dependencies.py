from typing import Annotated

from app.core.config import get_settings
from app.database.session import get_db
from app.models.session import UserSession
from app.models.user import User
from app.services.auth import csrf_token_matches, get_active_session
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

DatabaseSession = Annotated[Session, Depends(get_db)]


def require_session(
    database: DatabaseSession,
    session_token: str | None = Cookie(default=None, alias="kibolens_session"),
) -> UserSession:
    if session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required."
        )
    session = get_active_session(database, session_token, get_settings())
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired."
        )
    return session


def require_current_user(
    database: DatabaseSession,
    session: Annotated[UserSession, Depends(require_session)],
) -> User:
    user = database.get(User, session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session user no longer exists."
        )
    return user


def require_csrf(
    session: Annotated[UserSession, Depends(require_session)],
    x_csrf_token: str | None = Header(default=None),
) -> UserSession:
    if x_csrf_token is None or not csrf_token_matches(session, x_csrf_token, get_settings()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    return session


CurrentUser = Annotated[User, Depends(require_current_user)]
CsrfSession = Annotated[UserSession, Depends(require_csrf)]
