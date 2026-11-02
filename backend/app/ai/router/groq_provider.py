"""Groq provider adapter.

Uses Groq's official OpenAI-compatible API (https://api.groq.com/openai/v1).
Enforces zero-cost Free-tier policy:
- Dynamically retrieves active models from GET /models
- Filters out audio, whisper, moderation/guard, deprecated, and inactive models
- Rejects deprecated Qwen 3.6 in favor of Qwen 3.8 / current versions
- Inspects Groq rate-limit headers (x-ratelimit-*) to classify 429 errors
- Maintains separate text and vision registries
- Categorizes models into ADVANCED, BALANCED, and FAST quality tiers
- Distinguishes production and preview models
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.ai.router.types import (
    AICapability,
    FailureCategory,
    ModelEntry,
    ModelStatus,
    ProviderName,
    QualityTier,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

_GROQ_API_BASE = "https://api.groq.com/openai/v1"
_GROQ_MODELS_URL = f"{_GROQ_API_BASE}/models"
_GROQ_CHAT_URL = f"{_GROQ_API_BASE}/chat/completions"

# Non-chat models to filter out from general text/vision generation
_NON_CHAT_PREFIXES = (
    "whisper",
    "distil-whisper",
    "llama-guard",
    "guard-",
    "tts",
    "embed",
)

# Known deprecated model identifiers to exclude
_DEPRECATED_MODEL_SUBSTRINGS = (
    "qwen-3.6",
    "qwen3.6",
    "llama-3-70b-8192",  # Deprecated in favor of 3.1/3.3
    "llama-3-8b-8192",
)

# Known vision-capable multimodal model patterns on Groq
_VISION_MODEL_SUBSTRINGS = (
    "vision",
    "vl",
    "qwen-3.8-27b",
    "qwen-2.5-32b",
)

# EXPLICIT FREE-TIER VERIFIED MODEL IDS FOR GROQ
# These models are confirmed available on Groq's free plan.
# DO NOT add models unless you have verified free-plan eligibility.
# Presence in /models endpoint is NOT sufficient proof.
_GROQ_VERIFIED_FREE_MODEL_IDS = frozenset({
    # Llama 3.3 (free-plan confirmed)
    "llama-3.3-70b-versatile",
    "llama-3.3-70b-specdec",
    # Llama 3.2 (free-plan confirmed)
    "llama-3.2-1b-preview",
    "llama-3.2-3b-preview",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
    # Llama 3.1 (free-plan confirmed)
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    # Mixtral (free-plan confirmed)
    "mixtral-8x7b-32768",
    # Gemma 2 (free-plan confirmed)
    "gemma2-9b-it",
    "gemma-7b-it",
    # DeepSeek (free-plan confirmed)
    "deepseek-r1-distill-llama-70b",
    # Qwen (free-plan confirmed for these)
    "qwen-2.5-32b",
    "qwen-3.8-27b",
})

# Default verified Free-plan candidate models
_DEFAULT_GROQ_TEXT_MODELS: list[dict[str, Any]] = [
    # ADVANCED
    {
        "model_id": "llama-3.3-70b-versatile",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 10,
        "context_limit": 131072,
        "is_preview": False,
    },
    {
        "model_id": "llama-3.1-70b-versatile",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 15,
        "context_limit": 131072,
        "is_preview": False,
    },
    {
        "model_id": "deepseek-r1-distill-llama-70b",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 18,
        "context_limit": 131072,
        "is_preview": True,
    },
    # BALANCED
    {
        "model_id": "llama-3.1-8b-instant",
        "quality_tier": QualityTier.BALANCED,
        "priority": 20,
        "context_limit": 131072,
        "is_preview": False,
    },
    {
        "model_id": "mixtral-8x7b-32768",
        "quality_tier": QualityTier.BALANCED,
        "priority": 25,
        "context_limit": 32768,
        "is_preview": False,
    },
    {
        "model_id": "llama-3.3-70b-specdec",
        "quality_tier": QualityTier.BALANCED,
        "priority": 28,
        "context_limit": 8192,
        "is_preview": True,
    },
    # FAST
    {
        "model_id": "gemma2-9b-it",
        "quality_tier": QualityTier.FAST,
        "priority": 30,
        "context_limit": 8192,
        "is_preview": False,
    },
    {
        "model_id": "llama-3.2-3b-preview",
        "quality_tier": QualityTier.FAST,
        "priority": 35,
        "context_limit": 8192,
        "is_preview": True,
    },
    {
        "model_id": "llama-3.2-1b-preview",
        "quality_tier": QualityTier.FAST,
        "priority": 40,
        "context_limit": 8192,
        "is_preview": True,
    },
]

_DEFAULT_GROQ_VISION_MODELS: list[dict[str, Any]] = [
    {
        "model_id": "llama-3.2-90b-vision-preview",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 10,
        "context_limit": 131072,
        "is_preview": True,
    },
    {
        "model_id": "qwen-3.8-27b",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 15,
        "context_limit": 32768,
        "is_preview": True,
    },
    {
        "model_id": "llama-3.2-11b-vision-preview",
        "quality_tier": QualityTier.BALANCED,
        "priority": 20,
        "context_limit": 131072,
        "is_preview": True,
    },
]


def _classify_groq_status(
    status_code: int,
    body: str,
    headers: dict[str, str] | None = None,
) -> FailureCategory:
    """Classify Groq HTTP status code and response headers."""
    if status_code in (401, 403):
        return FailureCategory.AUTH_FAILURE
    if status_code == 429:
        headers = headers or {}
        # Parse rate limit headers
        remaining_req = headers.get("x-ratelimit-remaining-requests")
        remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
        low_body = body.lower()

        # If zero tokens or requests remaining for the day, or quota mentioned in message
        if (
            remaining_req == "0"
            or remaining_tokens == "0"
            or "day" in low_body
            or "quota" in low_body
            or "limit exceeded" in low_body
        ):
            return FailureCategory.QUOTA_EXHAUSTED
        return FailureCategory.RATE_LIMITED

    if status_code == 400:
        return FailureCategory.INVALID_REQUEST
    if status_code in (408, 504):
        return FailureCategory.TIMEOUT
    if status_code in (500, 502, 503):
        return FailureCategory.SERVER_ERROR
    return FailureCategory.UNKNOWN


class GroqCatalogue:
    """Live cached Groq model catalogue with automatic periodic refresh."""

    def __init__(self, refresh_hours: float = 24.0):
        self._refresh_seconds = refresh_hours * 3600
        self._text_models: list[ModelEntry] = []
        self._vision_models: list[ModelEntry] = []
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

        # Pre-seed with default verified models
        self._seed_default_models()

    def _seed_default_models(self) -> None:
        text_entries = []
        for m in _DEFAULT_GROQ_TEXT_MODELS:
            text_entries.append(
                ModelEntry(
                    provider=ProviderName.GROQ,
                    model_id=m["model_id"],
                    capabilities=frozenset({AICapability.TEXT_GENERATION}),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=m["quality_tier"],
                    priority=m["priority"],
                    context_limit=m.get("context_limit"),
                    prompt_price_usd=0.0,
                    completion_price_usd=0.0,
                    last_verified_at=datetime.now(timezone.utc),
                    extra={"is_preview": m.get("is_preview", False)},
                )
            )
        vision_entries = []
        for m in _DEFAULT_GROQ_VISION_MODELS:
            vision_entries.append(
                ModelEntry(
                    provider=ProviderName.GROQ,
                    model_id=m["model_id"],
                    capabilities=frozenset(
                        {AICapability.TEXT_GENERATION, AICapability.VISION_INPUT}
                    ),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=m["quality_tier"],
                    priority=m["priority"],
                    context_limit=m.get("context_limit"),
                    prompt_price_usd=0.0,
                    completion_price_usd=0.0,
                    last_verified_at=datetime.now(timezone.utc),
                    extra={"is_preview": m.get("is_preview", True)},
                )
            )
        self._text_models = text_entries
        self._vision_models = vision_entries

    async def get_text_models(self, api_key: str, timeout: float) -> list[ModelEntry]:
        await self._maybe_refresh(api_key, timeout)
        return list(self._text_models)

    async def get_vision_models(
        self, api_key: str, timeout: float
    ) -> list[ModelEntry]:
        await self._maybe_refresh(api_key, timeout)
        return list(self._vision_models)

    async def _maybe_refresh(self, api_key: str, timeout: float) -> None:
        async with self._lock:
            now = time.monotonic()
            if (
                self._fetched_at is not None
                and now - self._fetched_at < self._refresh_seconds
            ):
                return
            await self._refresh(api_key, timeout)

    async def _refresh(self, api_key: str, timeout: float) -> None:
        logger.info("Refreshing Groq model catalogue from %s ...", _GROQ_MODELS_URL)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    _GROQ_MODELS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code != 200:
                logger.warning(
                    "Groq catalogue fetch failed with status %d; keeping cached models",
                    resp.status_code,
                )
                return
            raw_models = resp.json().get("data", [])
        except Exception as exc:
            logger.warning(
                "Groq catalogue fetch exception: %s; keeping cached models", exc
            )
            return

        text_entries: list[ModelEntry] = []
        vision_entries: list[ModelEntry] = []

        # Map of known priorities
        known_priorities = {
            m["model_id"]: (m["quality_tier"], m["priority"])
            for m in _DEFAULT_GROQ_TEXT_MODELS
        }
        known_vision_priorities = {
            m["model_id"]: (m["quality_tier"], m["priority"])
            for m in _DEFAULT_GROQ_VISION_MODELS
        }

        for item in raw_models:
            model_id: str = item.get("id", "")
            if not model_id:
                continue

            # CRITICAL: Filter through verified free-plan eligibility list
            # Groq's /models endpoint presence is NOT proof of free-plan access
            if model_id not in _GROQ_VERIFIED_FREE_MODEL_IDS:
                logger.debug(
                    "Skipping unverified Groq model (not in free-plan allowlist): %s",
                    model_id
                )
                continue

            # Check if explicitly marked inactive
            if item.get("active") is False:
                continue

            # Filter out non-chat models (audio, moderation, tts, embeddings)
            low_id = model_id.lower()
            if any(low_id.startswith(p) for p in _NON_CHAT_PREFIXES):
                continue

            # Reject known deprecated models (e.g. Qwen 3.6 deprecated in favor of Qwen 3.8)
            if any(dep in low_id for dep in _DEPRECATED_MODEL_SUBSTRINGS):
                logger.debug("Skipping deprecated Groq model: %s", model_id)
                continue

            context_window = item.get("context_window", 8192)
            is_preview = "-preview" in low_id or "distill" in low_id

            # Determine quality tier and priority
            if model_id in known_priorities:
                quality_tier, priority = known_priorities[model_id]
            else:
                if "70b" in low_id or "90b" in low_id or "32b" in low_id or "27b" in low_id:
                    quality_tier = QualityTier.ADVANCED
                    priority = 50
                elif "8b" in low_id or "mixtral" in low_id:
                    quality_tier = QualityTier.BALANCED
                    priority = 60
                else:
                    quality_tier = QualityTier.FAST
                    priority = 70

            is_vision = any(v in low_id for v in _VISION_MODEL_SUBSTRINGS)

            caps = {AICapability.TEXT_GENERATION}
            if is_vision:
                caps.add(AICapability.VISION_INPUT)

            entry = ModelEntry(
                provider=ProviderName.GROQ,
                model_id=model_id,
                capabilities=frozenset(caps),
                free_tier=True,
                status=ModelStatus.ACTIVE,
                quality_tier=quality_tier,
                priority=priority,
                context_limit=context_window,
                prompt_price_usd=0.0,
                completion_price_usd=0.0,
                last_verified_at=datetime.now(timezone.utc),
                extra={"is_preview": is_preview, "owned_by": item.get("owned_by")},
            )

            text_entries.append(entry)
            if is_vision:
                v_qt, v_pri = known_vision_priorities.get(model_id, (quality_tier, priority))
                v_entry = ModelEntry(
                    provider=ProviderName.GROQ,
                    model_id=model_id,
                    capabilities=frozenset(caps),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=v_qt,
                    priority=v_pri,
                    context_limit=context_window,
                    prompt_price_usd=0.0,
                    completion_price_usd=0.0,
                    last_verified_at=datetime.now(timezone.utc),
                    extra={"is_preview": is_preview},
                )
                vision_entries.append(v_entry)

        if text_entries:
            text_entries.sort(key=lambda e: e.priority)
            self._text_models = text_entries
        if vision_entries:
            vision_entries.sort(key=lambda e: e.priority)
            self._vision_models = vision_entries

        self._fetched_at = time.monotonic()
        logger.info(
            "Groq catalogue refreshed: %d text models, %d vision models",
            len(self._text_models),
            len(self._vision_models),
        )


class GroqProvider:
    """Independent Groq AI provider adapter (OpenAI-compatible)."""

    def __init__(self, settings: Settings, catalogue: GroqCatalogue | None = None):
        self.settings = settings
        self._api_key = (
            settings.groq_api_key.get_secret_value()
            if settings.groq_api_key
            else None
        )
        self._timeout = settings.ai_provider_timeout_seconds
        self._catalogue = catalogue or GroqCatalogue(
            refresh_hours=settings.ai_model_catalog_refresh_hours
        )

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def text_models(self) -> list[ModelEntry]:
        if not self._api_key:
            return []
        return await self._catalogue.get_text_models(self._api_key, self._timeout)

    async def vision_models(self) -> list[ModelEntry]:
        if not self._api_key:
            return []
        return await self._catalogue.get_vision_models(self._api_key, self._timeout)

    async def generate(
        self,
        model_id: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[str, dict, FailureCategory | None]:
        """Call Groq /chat/completions endpoint.

        Returns:
            (content, metadata, failure_category_or_None)
        """
        if not self._api_key:
            return "", {}, FailureCategory.AUTH_FAILURE

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException:
            return "", {}, FailureCategory.TIMEOUT
        except httpx.ConnectError:
            return "", {}, FailureCategory.SERVER_ERROR
        except Exception as exc:
            logger.warning("Groq generate unexpected error: %s", exc)
            return "", {}, FailureCategory.UNKNOWN

        latency = time.monotonic() - start

        # Extract rate limit headers where available
        rate_limit_headers = {
            k.lower(): v for k, v in resp.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"
        }

        if resp.status_code != 200:
            cat = _classify_groq_status(resp.status_code, resp.text, rate_limit_headers)
            logger.warning(
                "Groq %s responded %d: %s (category=%s, rate_limits=%s)",
                model_id,
                resp.status_code,
                resp.text[:200],
                cat.value,
                rate_limit_headers,
            )
            return "", {"rate_limit_headers": rate_limit_headers}, cat

        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason", "")
            usage = data.get("usage", {})
            metadata = {
                "provider": ProviderName.GROQ.value,
                "model": model_id,
                "latency_seconds": round(latency, 3),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "rate_limit_headers": rate_limit_headers,
            }
            if finish_reason == "content_filter":
                return "", metadata, FailureCategory.SAFETY_REFUSAL
            return content, metadata, None
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Groq response parse error: %s — body: %s", exc, resp.text[:300])
            return "", {}, FailureCategory.UNKNOWN

    async def health_check(self) -> bool:
        """Lightweight health check against Groq API."""
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _GROQ_MODELS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            return resp.status_code == 200
        except Exception:
            return False
