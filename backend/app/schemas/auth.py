from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: datetime


class LoginResponse(BaseModel):
    user: CurrentUserResponse
    csrf_token: str


class CsrfTokenResponse(BaseModel):
    csrf_token: str
