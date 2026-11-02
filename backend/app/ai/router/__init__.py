"""AI router package: provider-first multi-provider routing and fallback."""

from app.ai.router.core import AIRouter, get_ai_router
from app.ai.router.types import (
    AICapability,
    ModelAttempt,
    ProviderName,
    QualityTier,
    ModelStatus,
    RoutingResult,
)

__all__ = [
    "AIRouter",
    "get_ai_router",
    "AICapability",
    "ModelAttempt",
    "ProviderName",
    "QualityTier",
    "ModelStatus",
    "RoutingResult",
]
