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

    @model_validator(mode="after")
    def validate_production_session_settings(self) -> Settings:
        if self.environment == "production":
            if self.session_hash_secret is None or not self.session_hash_secret.get_secret_value():
                raise ValueError("KIBOLENS_SESSION_HASH_SECRET is required in production.")
            if not self.session_cookie_secure:
                raise ValueError("KIBOLENS_SESSION_COOKIE_SECURE must be true in production.")
            if self.alert_webhook_token is None or not self.alert_webhook_token.get_secret_value():
                raise ValueError("KIBOLENS_ALERT_WEBHOOK_TOKEN is required in production.")
        if self.cpu_warning_percent >= self.cpu_critical_percent:
            raise ValueError("CPU warning threshold must be less than its critical threshold.")
        if self.memory_warning_percent >= self.memory_critical_percent:
            raise ValueError("Memory warning threshold must be less than its critical threshold.")
        if self.disk_warning_percent >= self.disk_critical_percent:
            raise ValueError("Disk warning threshold must be less than its critical threshold.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
