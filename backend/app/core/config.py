from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KIBOLENS_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "KiboLens"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://kibolens:change-me@localhost:5432/kibolens"
    cors_origins: list[AnyHttpUrl | str] = Field(default_factory=lambda: ["http://localhost:5173"])
    session_hash_secret: SecretStr | None = None
    session_cookie_name: str = "kibolens_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    login_max_attempts: int = Field(default=5, ge=1, le=100)
    prometheus_url: str = "http://localhost:9090"
    prometheus_timeout_seconds: float = Field(default=5, gt=0, le=30)
    monitoring_stale_seconds: int = Field(default=120, ge=15, le=900)
    cpu_warning_percent: float = Field(default=80, ge=1, le=100)
    cpu_critical_percent: float = Field(default=90, ge=1, le=100)
    memory_warning_percent: float = Field(default=80, ge=1, le=100)
    memory_critical_percent: float = Field(default=90, ge=1, le=100)
    disk_warning_percent: float = Field(default=80, ge=1, le=100)
    disk_critical_percent: float = Field(default=90, ge=1, le=100)
    temperature_warning_celsius: float = Field(default=80, ge=1, le=150)
    temperature_critical_celsius: float = Field(default=90, ge=1, le=150)
    alert_webhook_token: SecretStr | None = None

    # ── Legacy Ollama (kept for rollback; not invoked by default when cloud routing is active) ──
    llm_provider: str = Field(default="cloud")  # "cloud" | "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = Field(default=30, gt=0, le=300)
    llm_temperature: float = Field(default=0.1, ge=0, le=1)
    llm_max_tokens: int = Field(default=2000, ge=100, le=32000)
    llm_request_timeout_seconds: float = Field(default=45, gt=0, le=600)

    # ── Cloud AI Provider Keys ──────────────────────────────────────────────
    # Stored as SecretStr so they are never logged or serialised in plain text.
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # ── Free-only Enforcement ───────────────────────────────────────────────
    ai_free_only: bool = Field(default=True)
    ai_allow_paid_models: bool = Field(default=False)

    # ── Routing Parameters ──────────────────────────────────────────────────
    # Operational safeguards are bounded; this is not an AI usage quota.
    ai_provider_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    ai_model_catalog_refresh_hours: float = Field(default=24.0, gt=0, le=168)
    ai_gemini_text_models: str = Field(
        default="gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-flash-lite-latest"
    )
    ai_gemini_vision_models: str = Field(
        default="gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview"
    )
    ai_groq_text_models: str = Field(
        default="qwen/qwen3.8-27b"
    )
    ai_groq_vision_models: str = Field(
        default="qwen/qwen3.8-27b"
    )

    # ── Canonical Cloud Embedding Configuration (Gemini Embedding 2) ───────
    gemini_embedding_model: str = Field(default="gemini-embedding-2")
    gemini_embedding_dimension: int = Field(default=768)

    # ── RAG / Vector Database Configuration ────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_timeout_seconds: float = Field(default=10, gt=0, le=60)

    # ── Embedding Configuration ─────────────────────────────────────────────
    # Legacy Ollama embedding model kept for reference; cloud routing uses Gemini Embedding.
    embedding_model: str = Field(default="all-minilm")

    # ── Email/OTP Configuration ─────────────────────────────────────────────
    resend_api_key: SecretStr | None = Field(default=None, alias="RESEND_API_KEY")
    email_from: str = Field(default="noreply@example.com")
    email_reply_to: str | None = None
    public_app_url: str = "https://kibolens.alliededge.app"
    incident_notification_emails: str = ""
    incident_test_recipient_emails: str = ""
    allowed_emails: str = Field(
        default=""  # Must be configured via KIBOLENS_ALLOWED_EMAILS
    )
    otp_hash_secret: SecretStr = Field(default=SecretStr("change-me-otp-secret"))
    otp_ttl_seconds: int = Field(default=300, ge=60, le=600)
    otp_resend_cooldown_seconds: int = Field(default=30, ge=1, le=300)
    otp_max_attempts: int = Field(default=5, ge=3, le=20)

    # Docker inspection is optional and only uses the local Engine API socket.
    docker_observer_enabled: bool = True
    docker_socket_path: str = "/var/run/docker.sock"
    vm_observer_enabled: bool = True
    libvirt_uri: str = "qemu:///system"

    @field_validator("otp_max_attempts", mode="before")
    @classmethod
    def normalize_legacy_otp_attempts(cls, value: object) -> object:
        """Bound legacy test-mode values before the constrained field parses."""
        try:
            return 5 if int(value) > 20 else value
        except (TypeError, ValueError):
            return value

    @model_validator(mode="after")
    def validate_production_session_settings(self) -> Settings:
        # Normalize legacy timeout values safely. The effective provider
        # deadline remains bounded even when an older env file used 300s.
        if self.ai_provider_timeout_seconds > 60:
            self.ai_provider_timeout_seconds = 45
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
            if self.ai_allow_paid_models:
                raise ValueError(
                    "KIBOLENS_AI_ALLOW_PAID_MODELS must not be enabled in production "
                    "unless explicitly reviewed and approved."
                )
        if self.cpu_warning_percent >= self.cpu_critical_percent:
            raise ValueError("CPU warning threshold must be less than its critical threshold.")
        if self.memory_warning_percent >= self.memory_critical_percent:
            raise ValueError("Memory warning threshold must be less than its critical threshold.")
        if self.disk_warning_percent >= self.disk_critical_percent:
            raise ValueError("Disk warning threshold must be less than its critical threshold.")
        if self.temperature_warning_celsius >= self.temperature_critical_celsius:
            raise ValueError("Temperature warning threshold must be less than its critical threshold.")
        return self

    def get_allowed_emails(self) -> set[str]:
        """Parse and normalize allowed email addresses."""
        emails = {email.strip().lower() for email in self.allowed_emails.split(",")}
        return {email for email in emails if email}  # Remove empty strings

    def get_incident_notification_emails(self) -> list[str]:
        configured = {email.strip().lower() for email in self.incident_notification_emails.split(",") if email.strip()}
        return sorted(configured or self.get_allowed_emails())

    def get_incident_test_recipient_emails(self) -> set[str]:
        return {email.strip().lower() for email in self.incident_test_recipient_emails.split(",") if email.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
