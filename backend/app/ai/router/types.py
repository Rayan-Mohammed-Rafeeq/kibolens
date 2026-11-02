"""Shared types and enumerations for the AI router."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AICapability(str, Enum):
    """AI capabilities exposed by the router."""

    TEXT_GENERATION = "text_generation"
    VISION_INPUT = "vision_input"
    EMBEDDING = "embedding"


class ProviderName(str, Enum):
    """Supported AI providers."""

    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"  # Legacy / rollback only


class QualityTier(str, Enum):
    """Model quality tiers used for ordering fallbacks."""

    ADVANCED = "advanced"
    BALANCED = "balanced"
    FAST = "fast"


class ModelStatus(str, Enum):
    """Operational status of a model registration."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"


class FailureCategory(str, Enum):
    """Classification of request failures for routing decisions."""

    # Retriable – try next model
    RATE_LIMITED = "rate_limited"          # 429
    TIMEOUT = "timeout"                    # Connection/read timeout
    SERVER_ERROR = "server_error"          # 500/502/503/504
    MODEL_UNAVAILABLE = "model_unavailable"  # Model gone / disabled

    # Provider-wide – mark provider down, skip all its models
    QUOTA_EXHAUSTED = "quota_exhausted"    # Account-level quota done
    AUTH_FAILURE = "auth_failure"          # 401/403 invalid key

    # Non-retriable – stop, do not try next model
    INVALID_REQUEST = "invalid_request"    # 400 bad schema
    SAFETY_REFUSAL = "safety_refusal"      # Model refused on policy
    MODALITY_MISMATCH = "modality_mismatch"  # Image to text-only model
    UNSUPPORTED = "unsupported"

    # Internal
    POLICY_VIOLATION = "policy_violation"  # Paid model attempt in free-only mode
    UNKNOWN = "unknown"


# Errors that should NOT trigger fallback to another model
NON_RETRIABLE_CATEGORIES = frozenset(
    [
        FailureCategory.INVALID_REQUEST,
        FailureCategory.SAFETY_REFUSAL,
        FailureCategory.MODALITY_MISMATCH,
        FailureCategory.AUTH_FAILURE,
        FailureCategory.POLICY_VIOLATION,
        FailureCategory.UNSUPPORTED,
    ]
)

# Errors that mark the whole provider as unavailable
PROVIDER_WIDE_FAILURE_CATEGORIES = frozenset(
    [
        FailureCategory.QUOTA_EXHAUSTED,
        FailureCategory.AUTH_FAILURE,
    ]
)


@dataclass
class ModelEntry:
    """A single registered model with all its metadata."""

    provider: ProviderName
    model_id: str
    capabilities: frozenset[AICapability]
    free_tier: bool
    status: ModelStatus
    quality_tier: QualityTier
    priority: int                          # Lower = higher priority
    context_limit: int | None = None
    # Pricing metadata (per 1M tokens, USD)
    prompt_price_usd: float | None = None
    completion_price_usd: float | None = None
    # Runtime
    last_verified_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_verified_free(self) -> bool:
        """Return True only when pricing is confirmed zero or free_tier is set."""
        if not self.free_tier:
            return False
        if self.prompt_price_usd is not None and self.prompt_price_usd > 0:
            return False
        if self.completion_price_usd is not None and self.completion_price_usd > 0:
            return False
        return True

    def supports(self, capability: AICapability) -> bool:
        return capability in self.capabilities


@dataclass
class ModelAttempt:
    """Record of a single model attempt within a routing call."""

    provider: ProviderName
    model_id: str
    quality_tier: QualityTier
    started_at: datetime
    latency_seconds: float | None = None
    failure_category: FailureCategory | None = None
    failure_detail: str | None = None
    succeeded: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class RoutingResult:
    """Final result of a routing call including full attempt history."""

    capability: AICapability
    # The winning attempt (None if all failed)
    successful_provider: ProviderName | None = None
    successful_model: str | None = None
    successful_quality_tier: QualityTier | None = None
    # Attempt log (ALL models tried, in order)
    attempts: list[ModelAttempt] = field(default_factory=list)
    # Aggregated
    total_latency_seconds: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    # The actual generated content / embedding
    content: str = ""
    embedding: list[float] | None = None
    # If everything failed
    error: str | None = None
    unavailable: bool = False
