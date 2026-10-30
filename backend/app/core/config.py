from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KIBOLENS_", extra="ignore")

    app_name: str = "KiboLens"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://kibolens:change-me@localhost:5432/kibolens"
    cors_origins: list[AnyHttpUrl | str] = Field(default_factory=lambda: ["http://localhost:5173"])
    session_hash_secret: SecretStr | None = None
    session_cookie_name: str = "kibolens_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    login_max_attempts: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_production_session_settings(self) -> Settings:
        if self.environment == "production":
            if self.session_hash_secret is None or not self.session_hash_secret.get_secret_value():
                raise ValueError("KIBOLENS_SESSION_HASH_SECRET is required in production.")
            if not self.session_cookie_secure:
                raise ValueError("KIBOLENS_SESSION_COOKIE_SECURE must be true in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
