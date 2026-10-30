from app.api.dependencies import CsrfSession, CurrentUser, DatabaseSession, require_session
from app.core.config import get_settings
from app.core.throttle import LoginThrottle
from app.schemas.auth import CsrfTokenResponse, CurrentUserResponse, LoginRequest, LoginResponse
from app.services.auth import (
    InvalidCredentialsError,
    authenticate,
    create_session,
    revoke_session,
    rotate_csrf_token,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

router = APIRouter(prefix="/auth", tags=["authentication"])
throttle = LoginThrottle(get_settings().login_max_attempts)


def user_response(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id), username=user.username, role=user.role, created_at=user.created_at
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, database: DatabaseSession
) -> LoginResponse:
    client_host = request.client.host if request.client else "unknown"
    throttle_key = f"{client_host}:{payload.username.lower()}"
    if throttle.is_limited(throttle_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts."
        )
    try:
        user = authenticate(database, payload.username, payload.password)
    except InvalidCredentialsError:
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
        ) from None
    throttle.clear(throttle_key)
    raw_token, csrf_token, _ = create_session(database, user, get_settings())
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=user_response(user), csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, database: DatabaseSession, session: CsrfSession) -> None:
    revoke_session(database, session)
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: CurrentUser) -> CurrentUserResponse:
    return user_response(user)


@router.get("/csrf", response_model=CsrfTokenResponse)
def csrf_token(database: DatabaseSession, session=Depends(require_session)) -> CsrfTokenResponse:
    return CsrfTokenResponse(csrf_token=rotate_csrf_token(database, session, get_settings()))
