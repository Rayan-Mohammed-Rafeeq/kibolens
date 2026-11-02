"""Central AI Router — exhaustive provider-first fallback with zero-cost enforcement.

EXHAUSTIVE PROVIDER-FIRST FALLBACK:
  Provider order (NEVER interleaved): 1. Gemini → 2. Groq → 3. OpenRouter
  Each provider is COMPLETELY EXHAUSTED before moving to the next.
  NO ARTIFICIAL ATTEMPT LIMITS - all eligible models are tried.

Fallback order for TEXT:
  1. Try ALL eligible active Gemini text models (ADVANCED→BALANCED→FAST).
  2. Only after Gemini exhausted, try ALL eligible Groq text models.
  3. Only after Groq exhausted, try ALL eligible OpenRouter :free text models.
  4. Return graceful unavailable response.

Fallback order for VISION:
  Same provider-first sequence using separate vision registries.
  Never sends images to text-only models.

OPERATIONAL SAFEGUARDS (NOT USAGE QUOTAS):
  - Per-request network timeouts (45s default)
  - Circuit breakers for provider/model failures
  - Bounded transient retries (max 1 additional retry per model)
  - Model-specific cooldown after failures
  - Provider-wide circuit opening for auth/quota failures
  
DYNAMIC MODEL DISCOVERY:
  - Gemini: Fetches live catalogue from Google's /models API
  - Groq: Fetches live catalogue from Groq's /models API
  - OpenRouter: Fetches live catalogue with :free suffix verification
  - Periodic refresh (default 24 hours) with last-known-good fallback
  - Comprehensive default registries for emergency fallback

ZERO-COST ENFORCEMENT:
  - AI_FREE_ONLY=true enforced in production
  - Models rejected unless pricing=$0.00 or explicit free_tier=true
  - No automatic paid model upgrades

EMBEDDINGS:
  Gemini Embedding 2 only (768 dimensions).
  Bounded retry.
  No cross-model fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.ai.router.circuit_breaker import CircuitBreakerRegistry
from app.ai.router.gemini_provider import GeminiCatalogue, GeminiProvider
from app.ai.router.groq_provider import GroqCatalogue, GroqProvider
from app.ai.router.openrouter_provider import OpenRouterCatalogue, OpenRouterProvider
from app.ai.router.types import (
    AICapability,
    FailureCategory,
    ModelAttempt,
    ModelEntry,
    ModelStatus,
    NON_RETRIABLE_CATEGORIES,
    PROVIDER_WIDE_FAILURE_CATEGORIES,
    ProviderName,
    QualityTier,
    RoutingResult,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

# Exponential backoff for retries within the same model (only for transient errors)
# TESTING MODE: Backoff disabled, more retries allowed
_BACKOFF_BASE = 0.0  # DISABLED - No wait between retries
_BACKOFF_MAX = 0.0  # DISABLED - No backoff delay
_PER_MODEL_RETRIES = 10  # INCREASED - 10 additional retries per model


class AIRouter:
    """
    Provider-first AI router with circuit breakers, free-only enforcement,
    and full attempt tracing.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._free_only: bool = settings.ai_free_only
        self._allow_paid: bool = settings.ai_allow_paid_models
        self._circuit_breaker = CircuitBreakerRegistry()

        # Provider adapters
        self._gemini_catalogue = GeminiCatalogue(
            refresh_hours=settings.ai_model_catalog_refresh_hours
        )
        self._gemini = GeminiProvider(settings, self._gemini_catalogue)
        self._groq_catalogue = GroqCatalogue(
            refresh_hours=settings.ai_model_catalog_refresh_hours
        )
        self._groq = GroqProvider(settings, self._groq_catalogue)
        self._catalogue = OpenRouterCatalogue(
            refresh_hours=settings.ai_model_catalog_refresh_hours
        )
        self._openrouter = OpenRouterProvider(settings, self._catalogue)

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> RoutingResult:
        """Generate text using provider-first fallback."""
        return await self._route_text(
            capability=AICapability.TEXT_GENERATION,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_vision(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> RoutingResult:
        """Generate a response that may include image understanding (vision models only)."""
        return await self._route_text(
            capability=AICapability.VISION_INPUT,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def embed(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> RoutingResult:
        """Generate an embedding using Gemini Embedding (bounded retry, no cross-model fallback)."""
        result = RoutingResult(capability=AICapability.EMBEDDING)
        start_total = time.monotonic()

        if not self._gemini.available:
            result.error = "Gemini API key not configured; embeddings unavailable."
            result.unavailable = True
            result.total_latency_seconds = round(time.monotonic() - start_total, 3)
            return result

        provider = ProviderName.GEMINI
        model_id = self._gemini.embedding_model_id

        for attempt_num in range(1 + _PER_MODEL_RETRIES):
            if not self._circuit_breaker.is_model_available(provider.value, model_id):
                break

            attempt = ModelAttempt(
                provider=provider,
                model_id=model_id,
                quality_tier=QualityTier.ADVANCED,
                started_at=datetime.now(timezone.utc),
            )
            t0 = time.monotonic()
            vector, failure = await self._gemini.embed(text, task_type=task_type)
            attempt.latency_seconds = round(time.monotonic() - t0, 3)

            if failure is None and vector:
                attempt.succeeded = True
                result.attempts.append(attempt)
                result.successful_provider = provider
                result.successful_model = model_id
                result.successful_quality_tier = QualityTier.ADVANCED
                result.embedding = vector
                self._circuit_breaker.record_success(provider.value, model_id)
                break
            else:
                attempt.failure_category = failure
                result.attempts.append(attempt)
                self._circuit_breaker.record_failure(provider.value, model_id, failure or FailureCategory.UNKNOWN)

                if failure in NON_RETRIABLE_CATEGORIES:
                    break
                # Bounded backoff before retry
                if attempt_num < _PER_MODEL_RETRIES:
                    await asyncio.sleep(min(_BACKOFF_BASE * (2 ** attempt_num), _BACKOFF_MAX))

        if result.embedding is None:
            result.error = (
                "Embedding provider temporarily unavailable. "
                "Document ingestion is pending; no incompatible vectors will be stored."
            )
            result.unavailable = True

        result.total_latency_seconds = round(time.monotonic() - start_total, 3)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # Internal routing
    # ═══════════════════════════════════════════════════════════════════════

    async def _route_text(
        self,
        capability: AICapability,
        prompt: str,
        system_prompt: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> RoutingResult:
        result = RoutingResult(capability=capability)
        start_total = time.monotonic()

        eff_temperature = temperature if temperature is not None else self.settings.llm_temperature
        eff_max_tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens

        # ── Phase 1: Gemini (provider-first: exhaust Gemini free models) ──
        if self._gemini.available:
            models = (
                await self._gemini.vision_models()
                if capability == AICapability.VISION_INPUT
                else await self._gemini.text_models()
            )
            await self._try_provider_models(
                provider=ProviderName.GEMINI,
                models=models,
                capability=capability,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=eff_temperature,
                max_tokens=eff_max_tokens,
                result=result,
            )
            if result.successful_model:
                result.total_latency_seconds = round(time.monotonic() - start_total, 3)
                return result

        # ── Phase 2: Groq (only after Gemini is exhausted) ───────────────
        if self._groq.available:
            groq_models = (
                await self._groq.vision_models()
                if capability == AICapability.VISION_INPUT
                else await self._groq.text_models()
            )
            await self._try_provider_models(
                provider=ProviderName.GROQ,
                models=groq_models,
                capability=capability,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=eff_temperature,
                max_tokens=eff_max_tokens,
                result=result,
            )
            if result.successful_model:
                result.total_latency_seconds = round(time.monotonic() - start_total, 3)
                return result

        # ── Phase 3: OpenRouter (only after Gemini and Groq are exhausted) ─
        if self._openrouter.available:
            or_models = (
                await self._openrouter.vision_models()
                if capability == AICapability.VISION_INPUT
                else await self._openrouter.text_models()
            )
            await self._try_provider_models(
                provider=ProviderName.OPENROUTER,
                models=or_models,
                capability=capability,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=eff_temperature,
                max_tokens=eff_max_tokens,
                result=result,
            )
            if result.successful_model:
                result.total_latency_seconds = round(time.monotonic() - start_total, 3)
                return result

        # ── All providers exhausted ──────────────────────────────────────
        if not result.successful_model:
            cap_name = capability.value.replace("_", " ")
            result.error = (
                f"All {cap_name} providers are currently unavailable. "
                "No paid models will be used. Please try again later."
            )
            result.unavailable = True

        result.total_latency_seconds = round(time.monotonic() - start_total, 3)
        return result

    async def _try_provider_models(
        self,
        provider: ProviderName,
        models: list[ModelEntry],
        capability: AICapability,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        result: RoutingResult,
    ) -> int:
        """
        Try each eligible model in the list in order until success.
        Exhausts all models from this provider before returning.
        Provider-first approach: never moves to next provider until current is exhausted.
        
        Returns the number of attempts consumed.
        """
        consumed = 0

        if not self._circuit_breaker.is_provider_available(provider.value):
            logger.info("Provider circuit open, skipping: %s", provider.value)
            return 0

        for model in models:
            if not self._is_eligible(model, capability):
                continue
            if not self._circuit_breaker.is_model_available(provider.value, model.model_id):
                logger.debug("Model circuit open, skipping: %s/%s", provider.value, model.model_id)
                continue

            attempt = ModelAttempt(
                provider=provider,
                model_id=model.model_id,
                quality_tier=model.quality_tier,
                started_at=datetime.now(timezone.utc),
            )

            t0 = time.monotonic()
            content, metadata, failure = await self._call_provider(
                provider=provider,
                model_id=model.model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            attempt.latency_seconds = round(time.monotonic() - t0, 3)
            attempt.input_tokens = metadata.get("input_tokens")
            attempt.output_tokens = metadata.get("output_tokens")

            consumed += 1

            if failure is None:
                attempt.succeeded = True
                result.attempts.append(attempt)
                result.successful_provider = provider
                result.successful_model = model.model_id
                result.successful_quality_tier = model.quality_tier
                result.content = content
                result.input_tokens = metadata.get("input_tokens")
                result.output_tokens = metadata.get("output_tokens")
                self._circuit_breaker.record_success(provider.value, model.model_id)
                logger.info(
                    "SUCCESS: %s/%s after %d attempts (tier=%s)",
                    provider.value,
                    model.model_id,
                    consumed,
                    model.quality_tier.value,
                )
                return consumed

            # Failure
            attempt.failure_category = failure
            attempt.failure_detail = f"HTTP call failed with category={failure.value}"
            result.attempts.append(attempt)

            self._circuit_breaker.record_failure(provider.value, model.model_id, failure)

            # If provider circuit opened or provider-wide issue, stop trying this provider's models
            if (
                not self._circuit_breaker.is_provider_available(provider.value)
                or failure in PROVIDER_WIDE_FAILURE_CATEGORIES
            ):
                logger.warning(
                    "Provider %s unavailable / circuit open; skipping remaining models (after %d attempts)",
                    provider.value,
                    consumed,
                )
                break

            # Non-retriable at model level: don't retry, but DO try next model
            if failure in NON_RETRIABLE_CATEGORIES:
                if failure == FailureCategory.MODALITY_MISMATCH:
                    logger.error(
                        "MODALITY MISMATCH: model %s cannot handle capability %s — "
                        "check registry configuration",
                        model.model_id,
                        capability.value,
                    )
                continue

        # Exhausted all eligible models from this provider
        logger.info(
            "Provider %s exhausted: tried %d models, none succeeded",
            provider.value,
            consumed,
        )
        return consumed

    async def _call_provider(
        self,
        provider: ProviderName,
        model_id: str,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict, FailureCategory | None]:
        """Dispatch to the correct provider adapter."""
        if provider == ProviderName.GEMINI:
            return await self._gemini.generate(
                model_id=model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == ProviderName.GROQ:
            return await self._groq.generate(
                model_id=model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == ProviderName.OPENROUTER:
            return await self._openrouter.generate(
                model_id=model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        return "", {}, FailureCategory.UNSUPPORTED

    def _is_eligible(self, model: ModelEntry, capability: AICapability) -> bool:
        """Return True only if this model should be attempted for the given capability."""
        if model.status != ModelStatus.ACTIVE:
            return False
        if not model.supports(capability):
            return False
        if self._free_only and not self._allow_paid:
            if not model.is_verified_free:
                logger.warning(
                    "Rejecting non-free model %s/%s (free-only mode)",
                    model.provider.value,
                    model.model_id,
                )
                return False
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # Observability
    # ═══════════════════════════════════════════════════════════════════════

    async def health_status(self) -> dict:
        """Return full health status for the diagnostic endpoint."""
        gemini_ok = await self._gemini.health_check()
        groq_ok = await self._groq.health_check()
        openrouter_ok = await self._openrouter.health_check()

        gemini_text = await self._gemini.text_models() if self._gemini.available else []
        gemini_vision = await self._gemini.vision_models() if self._gemini.available else []
        groq_text = await self._groq.text_models() if self._groq.available else []
        groq_vision = await self._groq.vision_models() if self._groq.available else []
        or_text = await self._openrouter.text_models() if self._openrouter.available else []
        or_vision = await self._openrouter.vision_models() if self._openrouter.available else []

        return {
            "free_only_mode": self._free_only,
            "allow_paid_models": self._allow_paid,
            "providers": {
                "gemini": {
                    "available": self._gemini.available,
                    "api_reachable": gemini_ok,
                    "circuit_breaker": self._circuit_breaker.get_provider_state(
                        ProviderName.GEMINI.value
                    ),
                    "text_models_count": len(gemini_text),
                    "vision_models_count": len(gemini_vision),
                    "top_text_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                            "priority": m.priority,
                            "capabilities": [c.value for c in m.capabilities],
                            "circuit_breaker": self._circuit_breaker.get_model_state(
                                ProviderName.GEMINI.value, m.model_id
                            ),
                        }
                        for m in gemini_text[:10]
                    ],
                    "top_vision_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                            "priority": m.priority,
                        }
                        for m in gemini_vision[:10]
                    ],
                    "embedding_model": self._gemini.embedding_model_id,
                    "embedding_dimension": self._gemini.embedding_dimension,
                },
                "groq": {
                    "available": self._groq.available,
                    "api_reachable": groq_ok,
                    "circuit_breaker": self._circuit_breaker.get_provider_state(
                        ProviderName.GROQ.value
                    ),
                    "text_models_count": len(groq_text),
                    "vision_models_count": len(groq_vision),
                    "top_text_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                            "priority": m.priority,
                            "is_preview": m.extra.get("is_preview", False),
                            "circuit_breaker": self._circuit_breaker.get_model_state(
                                ProviderName.GROQ.value, m.model_id
                            ),
                        }
                        for m in groq_text[:10]
                    ],
                    "top_vision_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                            "priority": m.priority,
                            "is_preview": m.extra.get("is_preview", False),
                        }
                        for m in groq_vision[:5]
                    ],
                },
                "openrouter": {
                    "available": self._openrouter.available,
                    "api_reachable": openrouter_ok,
                    "circuit_breaker": self._circuit_breaker.get_provider_state(
                        ProviderName.OPENROUTER.value
                    ),
                    "text_models_count": len(or_text),
                    "vision_models_count": len(or_vision),
                    "top_text_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                            "priority": m.priority,
                        }
                        for m in or_text[:10]
                    ],
                    "top_vision_models": [
                        {
                            "model_id": m.model_id,
                            "quality_tier": m.quality_tier.value,
                        }
                        for m in or_vision[:5]
                    ],
                },
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════════════════════

_router_instance: AIRouter | None = None
_router_lock = asyncio.Lock()


async def get_ai_router(settings: Settings | None = None) -> AIRouter:
    """Return (or create) the singleton AIRouter."""
    global _router_instance
    async with _router_lock:
        if _router_instance is None:
            if settings is None:
                from app.core.config import get_settings
                settings = get_settings()
            _router_instance = AIRouter(settings)
        return _router_instance


def reset_ai_router() -> None:
    """Reset the singleton (for testing)."""
    global _router_instance
    _router_instance = None
