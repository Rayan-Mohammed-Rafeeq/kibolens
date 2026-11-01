from __future__ import annotations

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
    prometheus_url: str = "http://localhost:9090"
    prometheus_timeout_seconds: float = Field(default=5, gt=0, le=30)
    monitoring_stale_seconds: int = Field(default=120, ge=15, le=900)
    cpu_warning_percent: float = Field(default=80, ge=1, le=100)
    cpu_critical_percent: float = Field(default=90, ge=1, le=100)
    memory_warning_percent: float = Field(default=80, ge=1, le=100)
    memory_critical_percent: float = Field(default=90, ge=1, le=100)
    disk_warning_percent: float = Field(default=80, ge=1, le=100)
    disk_critical_percent: float = Field(default=90, ge=1, le=100)
    alert_webhook_token: SecretStr | None = None

    # AI/LLM Configuration
    llm_provider: str = Field(default="ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = Field(default=60, gt=0, le=300)
    llm_temperature: float = Field(default=0.1, ge=0, le=1)
    llm_max_tokens: int = Field(default=2000, ge=100, le=32000)
    llm_request_timeout_seconds: float = Field(default=120, gt=0, le=600)

    # Email/OTP Configuration
    resend_api_key: SecretStr | None = Field(default=None, alias="RESEND_API_KEY")
    email_from: str = Field(default="noreply@example.com")
    email_reply_to: str | None = None
    allowed_emails: str = Field(
        default=""  # Must be configured via KIBOLENS_ALLOWED_EMAILS
    )
    otp_hash_secret: SecretStr = Field(default=SecretStr("change-me-otp-secret"))
    otp_ttl_seconds: int = Field(default=300, ge=60, le=600)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=30, le=300)
    otp_max_attempts: int = Field(default=5, ge=3, le=10)

    @model_validator(mode="after")
    def validate_production_session_settings(self) -> Settings:
        if self.environment == "production":
            if self.session_hash_secret is None or not self.session_hash_secret.get_secret_value():
                raise ValueError("KIBOLENS_SESSION_HASH_SECRET is required in production.")
            if not self.session_cookie_secure:
                raise ValueError("KIBOLENS_SESSION_COOKIE_SECURE must be true in production.")
            if self.alert_webhook_token is None or not self.alert_webhook_token.get_secret_value():
                raise ValueError("KIBOLENS_ALERT_WEBHOOK_TOKEN is required in production.")
            if self.resend_api_key is None or not self.resend_api_key.get_secret_value():
                raise ValueError("RESEND_API_KEY is required in production.")
            if self.otp_hash_secret.get_secret_value() == "change-me-otp-secret":
                raise ValueError("KIBOLENS_OTP_HASH_SECRET must be set in production.")
        if self.cpu_warning_percent >= self.cpu_critical_percent:
            raise ValueError("CPU warning threshold must be less than its critical threshold.")
        if self.memory_warning_percent >= self.memory_critical_percent:
            raise ValueError("Memory warning threshold must be less than its critical threshold.")
        if self.disk_warning_percent >= self.disk_critical_percent:
            raise ValueError("Disk warning threshold must be less than its critical threshold.")
        return self
    
    def get_allowed_emails(self) -> set[str]:
        """Parse and normalize allowed email addresses."""
        emails = {email.strip().lower() for email in self.allowed_emails.split(",")}
        return {email for email in emails if email}  # Remove empty strings


@lru_cache
def get_settings() -> Settings:
    return Settings()
