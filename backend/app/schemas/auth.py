from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginStage1Response(BaseModel):
    """Response after successful password verification (before OTP)."""
    requires_otp: bool = True
    masked_email: str
    resend_available_in: int = 0  # seconds


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OTPResendRequest(BaseModel):
    email: EmailStr


class OTPResendResponse(BaseModel):
    success: bool
    masked_email: str
    resend_available_in: int  # seconds


class CurrentUserResponse(BaseModel):
    id: str
    username: str
    email: str | None = None
    role: str
    created_at: datetime


class LoginResponse(BaseModel):
    """Response after successful OTP verification."""
    user: CurrentUserResponse
    csrf_token: str


class CsrfTokenResponse(BaseModel):
    csrf_token: str
