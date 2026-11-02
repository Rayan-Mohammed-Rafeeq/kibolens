from app.api.dependencies import CsrfSession, CurrentUser, DatabaseSession, require_session
from app.core.config import get_settings
from app.core.throttle import LoginThrottle
from app.models.user import User
from app.schemas.auth import (
    CsrfTokenResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    LoginStage1Response,
    OTPResendRequest,
    OTPResendResponse,
    OTPVerifyRequest,
)
from app.services.auth import (
    InvalidCredentialsError,
    authenticate_by_email,
    create_session,
    revoke_session,
    rotate_csrf_token,
)
from app.services.email import EmailSendError, MockEmailService, ResendEmailService
from app.services.otp import (
    OTPAlreadyConsumedError,
    OTPError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsError,
    OTPResendCooldownError,
    can_resend_otp,
    create_otp_challenge,
    generate_otp,
    verify_otp,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
# Testing Mode - Login throttle DISABLED (max attempts set to 999999)
throttle = LoginThrottle(get_settings().login_max_attempts)


def get_email_service():
    """
    Dependency injection for email service.
    
    SECURITY: Returns MockEmailService ONLY in test environment.
    Production MUST have RESEND_API_KEY configured.
    """
    settings = get_settings()
    
    # Only use mock in test environment
    if settings.environment == "test":
        return MockEmailService()
    
    # Production requires Resend API key
    if not settings.resend_api_key:
        logger.error("RESEND_API_KEY not configured in production environment")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not configured. Contact administrator."
        )
    
    return ResendEmailService(
        api_key=settings.resend_api_key.get_secret_value(),
        from_email=settings.email_from,
        reply_to=settings.email_reply_to,
    )


def mask_email(email: str) -> str:
    """Mask email for display (show first 2 chars + domain)."""
    parts = email.split('@')
    if len(parts) != 2:
        return "***@***"
    local, domain = parts
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"


def user_response(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id), 
        username=user.username, 
        email=user.email,  # May be None for legacy users
        role=user.role, 
        created_at=user.created_at
    )


@router.post("/login", response_model=LoginStage1Response)
def login_stage1(
    payload: LoginRequest, 
    request: Request, 
    database: DatabaseSession,
    email_service = Depends(get_email_service)
) -> LoginStage1Response:
    """
    Stage 1: Verify email/password and send OTP.
    
    Returns masked email and OTP status.
    Does NOT create session - that requires OTP verification.
    """
    client_host = request.client.host if request.client else "unknown"
    throttle_key = f"{client_host}:{payload.email.lower()}"
    
    # Rate limiting
    if throttle.is_limited(throttle_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail="Too many login attempts."
        )
    
    # Verify credentials
    try:
        user = authenticate_by_email(database, payload.email, payload.password)
    except InvalidCredentialsError:
        throttle.record_failure(throttle_key)
        # Generic error to prevent account enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid credentials."
        ) from None
    
    if not user.email:
        # Legacy user without email - cannot use OTP auth
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )
    
    throttle.clear(throttle_key)
    
    # Check resend cooldown
    settings = get_settings()
    can_send, seconds_remaining = can_resend_otp(database, str(user.id), settings)
    
    if not can_send:
        return LoginStage1Response(
            requires_otp=True,
            masked_email=mask_email(user.email),
            resend_available_in=seconds_remaining
        )
    
    # Generate and send OTP
    otp_code = generate_otp()
    
    try:
        # Create OTP challenge (stores HMAC digest only)
        create_otp_challenge(database, str(user.id), otp_code, settings)
        
        # Send OTP via email
        email_service.send_otp_email(user.email, otp_code)
        
        logger.info(f"OTP sent for user {user.id}")
        
        return LoginStage1Response(
            requires_otp=True,
            masked_email=mask_email(user.email),
            resend_available_in=settings.otp_resend_cooldown_seconds
        )
        
    except EmailSendError as e:
        logger.error(f"Failed to send OTP email: {e}")
        # Fail closed - do not allow authentication without OTP
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service unavailable. Please try again later."
        ) from None
    except Exception as e:
        logger.error(f"Unexpected error during OTP creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error."
        ) from None


@router.post("/verify-otp", response_model=LoginResponse)
def verify_otp_endpoint(
    payload: OTPVerifyRequest,
    request: Request,
    response: Response,
    database: DatabaseSession,
) -> LoginResponse:
    """
    Stage 2: Verify OTP and create authenticated session.
    
    Only successful OTP verification establishes a session.
    """
    client_host = request.client.host if request.client else "unknown"
    throttle_key = f"{client_host}:{payload.email.lower()}:otp"
    
    # Rate limiting for OTP attempts
    if throttle.is_limited(throttle_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts."
        )
    
    # Get user by email (no password verification needed for OTP step)
    email_normalized = payload.email.lower().strip()
    user = database.scalar(
        select(User).where(User.email_normalized == email_normalized)
    )
    
    if not user or not user.email:
        # Generic error for security (don't reveal if email exists)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code."
        )
    
    # Verify OTP
    settings = get_settings()
    try:
        verify_otp(database, str(user.id), payload.otp, settings)
        
        # OTP verified - clear throttle and create session
        throttle.clear(throttle_key)
        
        raw_token, csrf_token, _ = create_session(database, user, settings)
        
        response.set_cookie(
            key=settings.session_cookie_name,
            value=raw_token,
            max_age=settings.session_ttl_hours * 3600,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        
        logger.info(f"User {user.id} authenticated successfully via OTP")
        
        return LoginResponse(user=user_response(user), csrf_token=csrf_token)
        
    except OTPExpiredError:
        throttle.record_failure(throttle_key)
        logger.warning(f"Expired OTP attempt for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verification code has expired. Please request a new one."
        ) from None
    except OTPMaxAttemptsError:
        throttle.record_failure(throttle_key)
        logger.warning(f"Max OTP attempts exceeded for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Maximum verification attempts exceeded. Please request a new code."
        ) from None
    except OTPAlreadyConsumedError:
        throttle.record_failure(throttle_key)
        logger.warning(f"Already-consumed OTP attempt for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This verification code has already been used. Please request a new one."
        ) from None
    except (OTPInvalidError, OTPError) as e:
        throttle.record_failure(throttle_key)
        logger.warning(f"Invalid OTP attempt for user {user.id}: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code."
        ) from None


@router.post("/resend-otp", response_model=OTPResendResponse)
def resend_otp_endpoint(
    payload: OTPResendRequest,
    request: Request,
    database: DatabaseSession,
    email_service = Depends(get_email_service)
) -> OTPResendResponse:
    """
    Resend OTP to user's email.
    
    Enforces cooldown period to prevent spam.
    """
    client_host = request.client.host if request.client else "unknown"
    throttle_key = f"{client_host}:{payload.email.lower()}:resend"
    
    # Rate limiting
    if throttle.is_limited(throttle_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many resend requests."
        )
    
    # Get user by email
    try:
        user = authenticate_by_email(database, payload.email, "")
    except InvalidCredentialsError:
        # Don't reveal if email exists
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to resend code."
        ) from None
    
    if not user.email:
        # Legacy user without email - cannot use OTP auth
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to resend code."
        )
    
    # Check cooldown
    settings = get_settings()
    can_send, seconds_remaining = can_resend_otp(database, str(user.id), settings)
    
    if not can_send:
        return OTPResendResponse(
            success=False,
            masked_email=mask_email(user.email),
            resend_available_in=seconds_remaining
        )
    
    # Generate and send new OTP
    otp_code = generate_otp()
    
    try:
        create_otp_challenge(database, str(user.id), otp_code, settings)
        email_service.send_otp_email(user.email, otp_code)
        
        throttle.clear(throttle_key)
        logger.info(f"OTP resent for user {user.id}")
        
        return OTPResendResponse(
            success=True,
            masked_email=mask_email(user.email),
            resend_available_in=settings.otp_resend_cooldown_seconds
        )
        
    except EmailSendError as e:
        logger.error(f"Failed to resend OTP: {e}")
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service unavailable. Please try again later."
        ) from None
    except Exception as e:
        logger.error(f"Unexpected error during OTP resend: {e}")
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resend code."
        ) from None


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
