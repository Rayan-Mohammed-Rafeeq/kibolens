"""OpenRouter provider adapter.

Uses the OpenRouter OpenAI-compatible API.
Maintains a live free-model catalogue refreshed periodically.
Only models with :free suffix AND zero prompt+completion pricing are permitted.
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
    output_limit_reached,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_MODELS_URL = f"{_OPENROUTER_API_BASE}/models"

# ---------------------------------------------------------------------------
# Priority configuration: known free model names → (quality_tier, priority).
# Models not in this list are assigned FAST/999.
# Keep this list short — it's a hint, not a hardcoded allowlist.
# ---------------------------------------------------------------------------
_PRIORITY_HINTS: dict[str, tuple[QualityTier, int]] = {
    # Meta Llama
    "meta-llama/llama-4-maverick:free": (QualityTier.ADVANCED, 10),
    "meta-llama/llama-4-scout:free": (QualityTier.BALANCED, 20),
    "meta-llama/llama-3.3-70b-instruct:free": (QualityTier.ADVANCED, 15),
    "meta-llama/llama-3.1-70b-instruct:free": (QualityTier.ADVANCED, 16),
    "meta-llama/llama-3.1-8b-instruct:free": (QualityTier.BALANCED, 25),
    "meta-llama/llama-3.2-3b-instruct:free": (QualityTier.FAST, 35),
    "meta-llama/llama-3.2-1b-instruct:free": (QualityTier.FAST, 45),
    # Mistral
    "mistralai/mistral-7b-instruct:free": (QualityTier.BALANCED, 30),
    "mistralai/mistral-small-3.1-24b-instruct:free": (QualityTier.ADVANCED, 12),
    # Qwen
    "qwen/qwen-2.5-72b-instruct:free": (QualityTier.ADVANCED, 14),
    "qwen/qwen-2.5-7b-instruct:free": (QualityTier.BALANCED, 28),
    "qwen/qwq-32b:free": (QualityTier.ADVANCED, 11),
    # DeepSeek
    "deepseek/deepseek-r1:free": (QualityTier.ADVANCED, 13),
    "deepseek/deepseek-chat:free": (QualityTier.BALANCED, 22),
    # Google (via OpenRouter)
    "google/gemini-2.0-flash-exp:free": (QualityTier.ADVANCED, 17),
    # OpenRouter automatic routing
    "openrouter/auto": (QualityTier.FAST, 990),
}

# Vision-capable models on OpenRouter (from :free catalogue)
_VISION_MODEL_HINTS: set[str] = {
    "meta-llama/llama-4-maverick:free",
    "meta-llama/llama-4-scout:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "qwen/qwen-2.5-vl-72b-instruct:free",
    "qwen/qwen-2.5-vl-7b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
}


def _classify_openrouter_status(status_code: int, body: str) -> FailureCategory:
    if status_code in (401, 403):
        return FailureCategory.AUTH_FAILURE
    if status_code == 402:
        return FailureCategory.QUOTA_EXHAUSTED
    if status_code == 429:
        low = body.lower()
        # OpenRouter commonly wraps an upstream provider's temporary 429 in a
        # message containing "rate-limited" or "limit". That is model-level
        # transient pressure, not account quota exhaustion.
        if any(marker in low for marker in ("quota exceeded", "daily quota", "credits exhausted", "billing")):
            return FailureCategory.QUOTA_EXHAUSTED
        return FailureCategory.RATE_LIMITED
    if status_code == 400:
        return FailureCategory.INVALID_REQUEST
    if status_code in (408, 504):
        return FailureCategory.TIMEOUT
    if status_code in (500, 502, 503):
        return FailureCategory.SERVER_ERROR
    return FailureCategory.UNKNOWN


class OpenRouterCatalogue:
    """Periodically fetched and cached free-model catalogue from OpenRouter."""

    def __init__(self, refresh_hours: float = 24.0):
        self._refresh_seconds = refresh_hours * 3600
        self._text_models: list[ModelEntry] = []
        self._vision_models: list[ModelEntry] = []
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_text_models(
        self, api_key: str, timeout: float
    ) -> list[ModelEntry]:
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
        logger.info("Refreshing OpenRouter free-model catalogue …")
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    _OPENROUTER_MODELS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code != 200:
                logger.warning(
                    "OpenRouter catalogue fetch failed: %s — keeping previous cache",
                    resp.status_code,
                )
                return
            raw_models = resp.json().get("data", [])
        except Exception as exc:
            logger.warning(
                "OpenRouter catalogue fetch exception: %s — keeping previous cache", exc
            )
            return

        text_entries: list[ModelEntry] = []
        vision_entries: list[ModelEntry] = []

        for m in raw_models:
            model_id: str = m.get("id", "")
            if not model_id.endswith(":free"):
                continue

            # Check pricing
            pricing = m.get("pricing", {})
            try:
                prompt_price = float(pricing.get("prompt", 1.0))
                completion_price = float(pricing.get("completion", 1.0))
            except (TypeError, ValueError):
                # Cannot verify pricing — skip
                continue

            if prompt_price != 0.0 or completion_price != 0.0:
                continue

            # Capabilities from architecture
            arch = m.get("architecture", {})
            input_modalities: list[str] = arch.get("input_modalities", arch.get("modality", "text").split("+"))
            output_modalities: list[str] = arch.get("output_modalities", ["text"])

            has_text_in = "text" in input_modalities
            has_text_out = "text" in output_modalities
            has_image_in = "image" in input_modalities

            if not has_text_in or not has_text_out:
                continue  # Must at least do text→text

            # Check deprecation/disabled
            if m.get("deprecated", False) or m.get("disabled", False):
                continue

            qt, pri = _PRIORITY_HINTS.get(model_id, (QualityTier.FAST, 500))

            caps: set[AICapability] = {AICapability.TEXT_GENERATION}
            if has_image_in or model_id in _VISION_MODEL_HINTS:
                caps.add(AICapability.VISION_INPUT)

            entry = ModelEntry(
                provider=ProviderName.OPENROUTER,
                model_id=model_id,
                capabilities=frozenset(caps),
                free_tier=True,
                status=ModelStatus.ACTIVE,
                quality_tier=qt,
                priority=pri,
                context_limit=m.get("context_length"),
                max_output_tokens=(m.get("top_provider") or {}).get("max_completion_tokens") or m.get("max_completion_tokens"),
                prompt_price_usd=prompt_price,
                completion_price_usd=completion_price,
                last_verified_at=datetime.now(timezone.utc),
                extra={"name": m.get("name", model_id)},
            )

            text_entries.append(entry)
            if AICapability.VISION_INPUT in entry.capabilities:
                vision_entries.append(entry)

        # Sort by priority
        text_entries.sort(key=lambda e: e.priority)
        vision_entries.sort(key=lambda e: e.priority)

        # This is a free-only router endpoint, not a paid model. Expose it as
        # the final candidate only after the live catalogue proves that the
        # account has at least one eligible zero-priced text model.
        if text_entries and not any(entry.model_id == "openrouter/free" for entry in text_entries):
            text_entries.append(ModelEntry(
                provider=ProviderName.OPENROUTER,
                model_id="openrouter/free",
                capabilities=frozenset({AICapability.TEXT_GENERATION, AICapability.VISION_INPUT}),
                free_tier=True,
                status=ModelStatus.ACTIVE,
                quality_tier=QualityTier.FAST,
                priority=999,
                prompt_price_usd=0.0,
                completion_price_usd=0.0,
                last_verified_at=datetime.now(timezone.utc),
                extra={"router_endpoint": True},
            ))

        self._text_models = text_entries
        self._vision_models = vision_entries
        self._fetched_at = time.monotonic()

        logger.info(
            "OpenRouter catalogue refreshed: %d text models, %d vision models",
            len(text_entries),
            len(vision_entries),
        )


class OpenRouterProvider:
    """Adapter for the OpenRouter OpenAI-compatible API (free-only)."""

    def __init__(self, settings: Settings, catalogue: OpenRouterCatalogue):
        self.settings = settings
        self._api_key = (
            settings.openrouter_api_key.get_secret_value()
            if settings.openrouter_api_key
            else None
        )
        self._timeout = settings.ai_provider_timeout_seconds
        self._catalogue = catalogue

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
        """Call OpenRouter /chat/completions.

        Returns (content, metadata, failure_or_None).
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
                    f"{_OPENROUTER_API_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "HTTP-Referer": "https://kibolens.app",
                        "X-Title": "KiboLens",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException:
            return "", {}, FailureCategory.TIMEOUT
        except httpx.ConnectError:
            return "", {}, FailureCategory.SERVER_ERROR
        except Exception as exc:
            logger.warning("OpenRouter generate unexpected error: %s", exc)
            return "", {}, FailureCategory.UNKNOWN

        latency = time.monotonic() - start

        if resp.status_code != 200:
            cat = _classify_openrouter_status(resp.status_code, resp.text)
            logger.warning(
                "OpenRouter %s responded %s: %s (category=%s)",
                model_id,
                resp.status_code,
                resp.text[:200],
                cat.value,
            )
            return "", {}, cat

        try:
            data = resp.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not isinstance(content, str) or not content.strip():
                return "", {}, FailureCategory.UNKNOWN
            finish_reason = data["choices"][0].get("finish_reason", "")
            usage = data.get("usage", {})
            metadata = {
                "provider": ProviderName.OPENROUTER.value,
                "model": model_id,
                "latency_seconds": round(latency, 3),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            }
            metadata["finish_reason"] = finish_reason or None
            metadata["incomplete"] = output_limit_reached(finish_reason)
            if finish_reason == "content_filter":
                return "", metadata, FailureCategory.SAFETY_REFUSAL
            if output_limit_reached(finish_reason):
                logger.warning("OpenRouter %s stopped at the output token limit", model_id)
            return content, metadata, None
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning(
                "OpenRouter response parse error: %s — body: %s", exc, resp.text[:300]
            )
            return "", {}, FailureCategory.UNKNOWN

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _OPENROUTER_MODELS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            return resp.status_code == 200
        except Exception:
            return False
