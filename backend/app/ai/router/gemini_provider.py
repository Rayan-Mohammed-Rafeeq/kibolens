"""Gemini provider adapter with exhaustive dynamic model discovery.

Wraps Google's Generative AI REST API (v1beta) for text generation and embeddings.
Dynamically discovers ALL eligible free-tier models from Google's /models endpoint.

AUTHENTICATION:
  - Supports both legacy AIza* and new AQ.* API key formats
  - Uses x-goog-api-key header (recommended) for REST API authentication
  - Keys are validated locally (non-empty) and remotely (Google API response)
  - Never logs or exposes actual key values

MODEL DISCOVERY:
  - Fetches live model catalogue from Google's /models API endpoint
  - Filters for generateContent-capable models (text generation)
  - Separates multimodal (vision-capable) models into vision registry
  - Falls back to comprehensive default registry on discovery failure
  - Refreshes periodically (default 24 hours)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.ai.router.types import (
    AICapability,
    FailureCategory,
    ModelAttempt,
    ModelEntry,
    ModelStatus,
    ProviderName,
    QualityTier,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Comprehensive default free-tier Gemini text model registry.
# Last-known-good fallback if dynamic discovery fails.
# ONLY includes models with VERIFIED free-tier eligibility.
# Ordered by quality tier (ADVANCED → BALANCED → FAST) and priority.
# Models must be in _GEMINI_VERIFIED_FREE_MODEL_IDS set.
# ---------------------------------------------------------------------------
_GEMINI_TEXT_REGISTRY: list[dict[str, Any]] = [
    # NOTE: All explicitly retired model IDs removed per 2026-10-31 final audit.
    # Removed: gemini-2.0-flash-exp, gemini-exp-1206, gemini-exp-1121, gemini-2.0-flash,
    #          gemini-1.5-flash*, all 1.5-flash-8b* variants (retired by Google).
    # Registry intentionally minimal - dynamic discovery from Google's /models API is primary.
    # Only include models whose current free-tier eligibility is explicitly verified.
    
    # Current Flash models verified against the live catalogue and free-tier
    # API smoke test on the configured account. Keep this list explicit because
    # the Gemini model catalogue does not expose pricing metadata.
    {
        "model_id": "gemini-3-flash-preview",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 10,
        "context_limit": 1_000_000,
        "capabilities": {AICapability.TEXT_GENERATION},
        "prompt_price_usd": 0.0,
        "completion_price_usd": 0.0,
    },
    {"model_id": "gemini-3.1-flash-lite", "quality_tier": QualityTier.FAST, "priority": 20, "context_limit": 1_000_000, "capabilities": {AICapability.TEXT_GENERATION}, "prompt_price_usd": 0.0, "completion_price_usd": 0.0},
    {"model_id": "gemini-3.1-flash-lite-preview", "quality_tier": QualityTier.FAST, "priority": 30, "context_limit": 1_000_000, "capabilities": {AICapability.TEXT_GENERATION}, "prompt_price_usd": 0.0, "completion_price_usd": 0.0},
    {"model_id": "gemini-flash-lite-latest", "quality_tier": QualityTier.FAST, "priority": 40, "context_limit": 1_000_000, "capabilities": {AICapability.TEXT_GENERATION}, "prompt_price_usd": 0.0, "completion_price_usd": 0.0},
]

# ---------------------------------------------------------------------------
# Comprehensive default free-tier Gemini VISION-capable model registry.
# Separate registry strictly for models with verified image-input support.
# ONLY includes models with VERIFIED free-tier eligibility + vision support.
# ---------------------------------------------------------------------------
_GEMINI_VISION_REGISTRY: list[dict[str, Any]] = [
    # NOTE: All explicitly retired model IDs removed per 2026-10-31 final audit.
    # Removed: gemini-2.0-flash-exp, gemini-exp-1206, gemini-exp-1121, gemini-2.0-flash,
    #          gemini-1.5-flash*, all 1.5-flash-8b* variants (retired by Google).
    # Registry intentionally minimal - dynamic discovery from Google's /models API is primary.
    # Only include models whose current free-tier eligibility AND vision support are verified.
    
    # The tested Flash registries are multimodal-capable according to the
    # live model metadata.
    {
        "model_id": "gemini-3-flash-preview",
        "quality_tier": QualityTier.ADVANCED,
        "priority": 10,
        "context_limit": 1_000_000,
        "capabilities": {AICapability.TEXT_GENERATION, AICapability.VISION_INPUT},
        "prompt_price_usd": 0.0,
        "completion_price_usd": 0.0,
    },
    {"model_id": "gemini-3.1-flash-lite", "quality_tier": QualityTier.FAST, "priority": 20, "context_limit": 1_000_000, "capabilities": {AICapability.TEXT_GENERATION, AICapability.VISION_INPUT}, "prompt_price_usd": 0.0, "completion_price_usd": 0.0},
    {"model_id": "gemini-3.1-flash-lite-preview", "quality_tier": QualityTier.FAST, "priority": 30, "context_limit": 1_000_000, "capabilities": {AICapability.TEXT_GENERATION, AICapability.VISION_INPUT}, "prompt_price_usd": 0.0, "completion_price_usd": 0.0},
]

# Canonical embedding model & dimension
_DEFAULT_GEMINI_EMBEDDING_MODEL_ID = "gemini-embedding-2"
_DEFAULT_GEMINI_EMBEDDING_DIMENSION = 768
_GEMINI_EMBEDDING_DIMENSION = _DEFAULT_GEMINI_EMBEDDING_DIMENSION
_GEMINI_EMBEDDING_MODEL_ID = _DEFAULT_GEMINI_EMBEDDING_MODEL_ID

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_MODELS_URL = f"{_GEMINI_API_BASE}/models"

# Known vision-capable model name patterns (partial match)
_VISION_CAPABLE_PATTERNS = (
    "flash",  # All flash models support vision
    "pro-vision",
    "pro-002",  # Pro 002 supports vision
)

# EXPLICIT FREE-TIER VERIFIED MODEL IDS
# These models are confirmed available on Google's free API tier.
# DO NOT add models unless you have verified free-tier eligibility.
# Presence in /models endpoint is NOT sufficient proof.
_GEMINI_VERIFIED_FREE_MODEL_IDS = frozenset({
    # NOTE: All explicitly retired model IDs removed per 2026-10-31 final audit.
    # Removed: gemini-2.0-flash-exp, gemini-exp-1206, gemini-exp-1121, gemini-2.0-flash,
    #          gemini-1.5-flash, gemini-1.5-flash-latest, gemini-1.5-flash-002, gemini-1.5-flash-001,
    #          gemini-1.5-flash-8b, gemini-1.5-flash-8b-latest, gemini-1.5-flash-8b-001,
    #          gemini-1.5-flash-8b-exp-0827, gemini-1.5-flash-exp-0827 (all retired by Google).
    #
    # MINIMAL REGISTRY - Dynamic discovery from Google's /models API is primary source.
    # Only explicitly verified current free-tier models listed here.
    
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-flash-lite-latest",
    
})


def _validate_gemini_api_key(api_key: str | None) -> bool:
    """Validate Gemini API key format locally.
    
    Accepts both formats:
    - Legacy AIza* keys
    - New AQ.* authorization keys
    
    Does NOT verify actual authorization - that's determined by Google's API response.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        True if key format is acceptable for local validation
    """
    if not api_key or not api_key.strip():
        return False
    
    # Accept non-empty keys
    # Common prefixes: AIza (legacy), AQ. (new authorization format)
    # Do not reject unfamiliar prefixes - let Google's API determine validity
    return True


def _classify_gemini_status(status_code: int, body: str) -> FailureCategory:
    """Map an HTTP status + body to a FailureCategory."""
    if status_code == 401 or status_code == 403:
        return FailureCategory.AUTH_FAILURE
    if status_code == 429:
        low = body.lower()
        if "quota" in low or "resource exhausted" in low:
            return FailureCategory.QUOTA_EXHAUSTED
        return FailureCategory.RATE_LIMITED
    if status_code == 400:
        return FailureCategory.INVALID_REQUEST
    if status_code in (408, 504):
        return FailureCategory.TIMEOUT
    if status_code in (500, 502, 503):
        return FailureCategory.SERVER_ERROR
    return FailureCategory.UNKNOWN


class GeminiCatalogue:
    """Live cached Gemini model catalogue with automatic periodic refresh.
    
    Dynamically discovers all eligible free-tier models from Google's /models API.
    Falls back to comprehensive default registry on discovery failure.
    """

    def __init__(self, refresh_hours: float = 24.0):
        self._refresh_seconds = refresh_hours * 3600
        self._text_models: list[ModelEntry] = []
        self._vision_models: list[ModelEntry] = []
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

        # Pre-seed with comprehensive default models
        self._seed_default_models()

    def _seed_default_models(self) -> None:
        """Initialize with comprehensive default registry."""
        text_entries = []
        for m in _GEMINI_TEXT_REGISTRY:
            text_entries.append(
                ModelEntry(
                    provider=ProviderName.GEMINI,
                    model_id=m["model_id"],
                    capabilities=frozenset(m["capabilities"]),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=m["quality_tier"],
                    priority=m["priority"],
                    context_limit=m.get("context_limit"),
                    prompt_price_usd=m.get("prompt_price_usd", 0.0),
                    completion_price_usd=m.get("completion_price_usd", 0.0),
                    last_verified_at=datetime.now(timezone.utc),
                )
            )
        vision_entries = []
        for m in _GEMINI_VISION_REGISTRY:
            vision_entries.append(
                ModelEntry(
                    provider=ProviderName.GEMINI,
                    model_id=m["model_id"],
                    capabilities=frozenset(m["capabilities"]),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=m["quality_tier"],
                    priority=m["priority"],
                    context_limit=m.get("context_limit"),
                    prompt_price_usd=m.get("prompt_price_usd", 0.0),
                    completion_price_usd=m.get("completion_price_usd", 0.0),
                    last_verified_at=datetime.now(timezone.utc),
                )
            )
        self._text_models = text_entries
        self._vision_models = vision_entries

    async def get_text_models(self, api_key: str, timeout: float) -> list[ModelEntry]:
        await self._maybe_refresh(api_key, timeout)
        return list(self._text_models)

    async def get_vision_models(self, api_key: str, timeout: float) -> list[ModelEntry]:
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
        """Dynamically fetch all eligible free-tier models from Google's API."""
        logger.info("Refreshing Gemini model catalogue from %s ...", _GEMINI_MODELS_URL)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    _GEMINI_MODELS_URL,
                    headers={"x-goog-api-key": api_key},
                )
            if resp.status_code != 200:
                logger.warning(
                    "Gemini catalogue fetch failed with status %d; keeping cached models",
                    resp.status_code,
                )
                return
            raw_models = resp.json().get("models", [])
        except Exception as exc:
            logger.warning(
                "Gemini catalogue fetch exception: %s; keeping cached models", exc
            )
            return

        text_entries: list[ModelEntry] = []
        vision_entries: list[ModelEntry] = []

        # Map of known priorities from default registry
        known_text_priorities = {
            m["model_id"]: (m["quality_tier"], m["priority"])
            for m in _GEMINI_TEXT_REGISTRY
        }
        known_vision_priorities = {
            m["model_id"]: (m["quality_tier"], m["priority"])
            for m in _GEMINI_VISION_REGISTRY
        }

        for item in raw_models:
            # Extract model name from full resource name (e.g., "models/gemini-1.5-flash")
            full_name: str = item.get("name", "")
            if not full_name.startswith("models/"):
                continue
            model_id = full_name.replace("models/", "")

            # Check supported generation methods
            supported_methods: list[str] = item.get("supportedGenerationMethods", [])
            if "generateContent" not in supported_methods:
                # Only interested in text generation models
                continue

            # CRITICAL: Filter through verified free-tier eligibility list
            # Gemini's /models endpoint presence is NOT proof of free-tier access
            if model_id not in _GEMINI_VERIFIED_FREE_MODEL_IDS:
                logger.debug(
                    "Skipping unverified Gemini model (not in free-tier allowlist): %s",
                    model_id
                )
                continue

            # Filter out paid Pro models (Pro, Pro Vision, Ultra) unless in free default list
            if ("pro" in model_id.lower() or "ultra" in model_id.lower()) and model_id not in known_text_priorities:
                # Pro models require paid tier unless explicitly in our free list
                continue

            # Context window
            context_limit = item.get("inputTokenLimit", 1_000_000)

            # Determine if vision-capable (multimodal)
            is_vision = any(pattern in model_id.lower() for pattern in _VISION_CAPABLE_PATTERNS)

            # Determine quality tier and priority
            if model_id in known_text_priorities:
                quality_tier, priority = known_text_priorities[model_id]
            else:
                # Infer from model name for unknown models
                low_id = model_id.lower()
                if "exp" in low_id or "2.0" in low_id:
                    quality_tier = QualityTier.ADVANCED
                    priority = 50
                elif "8b" in low_id or "exp-0827" in low_id:
                    quality_tier = QualityTier.FAST
                    priority = 70
                else:
                    quality_tier = QualityTier.BALANCED
                    priority = 60

            # Text entry
            caps = {AICapability.TEXT_GENERATION}
            if is_vision:
                caps.add(AICapability.VISION_INPUT)

            entry = ModelEntry(
                provider=ProviderName.GEMINI,
                model_id=model_id,
                capabilities=frozenset(caps),
                free_tier=True,
                status=ModelStatus.ACTIVE,
                quality_tier=quality_tier,
                priority=priority,
                context_limit=context_limit,
                prompt_price_usd=0.0,
                completion_price_usd=0.0,
                last_verified_at=datetime.now(timezone.utc),
                extra={"display_name": item.get("displayName", model_id)},
            )

            text_entries.append(entry)
            if is_vision:
                v_qt, v_pri = known_vision_priorities.get(model_id, (quality_tier, priority))
                v_entry = ModelEntry(
                    provider=ProviderName.GEMINI,
                    model_id=model_id,
                    capabilities=frozenset(caps),
                    free_tier=True,
                    status=ModelStatus.ACTIVE,
                    quality_tier=v_qt,
                    priority=v_pri,
                    context_limit=context_limit,
                    prompt_price_usd=0.0,
                    completion_price_usd=0.0,
                    last_verified_at=datetime.now(timezone.utc),
                    extra={"display_name": item.get("displayName", model_id)},
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
            "Gemini catalogue refreshed: %d text models, %d vision models",
            len(self._text_models),
            len(self._vision_models),
        )


class GeminiProvider:
    """Adapter for Google Gemini REST API (exhaustive free-tier discovery)."""

    def __init__(self, settings: Settings, catalogue: GeminiCatalogue | None = None):
        self.settings = settings
        raw_key = (
            settings.gemini_api_key.get_secret_value()
            if settings.gemini_api_key
            else None
        )
        
        # Validate key format locally (accepts AIza* and AQ.* formats)
        if raw_key and _validate_gemini_api_key(raw_key):
            self._api_key = raw_key
        else:
            self._api_key = None
            if raw_key:
                logger.warning("Gemini API key validation failed (empty or invalid format)")
        
        self._timeout = settings.ai_provider_timeout_seconds
        self._catalogue = catalogue or GeminiCatalogue(
            refresh_hours=settings.ai_model_catalog_refresh_hours
        )

    # ─── registry helpers ──────────────────────────────────────────────────

    async def text_models(self) -> list[ModelEntry]:
        if not self._api_key:
            return []
        return await self._catalogue.get_text_models(self._api_key, self._timeout)

    async def vision_models(self) -> list[ModelEntry]:
        if not self._api_key:
            return []
        return await self._catalogue.get_vision_models(self._api_key, self._timeout)

    @property
    def embedding_model_id(self) -> str:
        return getattr(self.settings, "gemini_embedding_model", _DEFAULT_GEMINI_EMBEDDING_MODEL_ID)

    @property
    def embedding_dimension(self) -> int:
        return getattr(self.settings, "gemini_embedding_dimension", _DEFAULT_GEMINI_EMBEDDING_DIMENSION)

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    # ─── text generation ───────────────────────────────────────────────────

    async def generate(
        self,
        model_id: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[str, dict, FailureCategory | None]:
        """
        Generate text with the given Gemini model.

        Returns:
            (content, metadata, failure_category_or_None)
        """
        if not self._api_key:
            return "", {}, FailureCategory.AUTH_FAILURE

        url = f"{_GEMINI_API_BASE}/models/{model_id}:generateContent"
        
        # Use x-goog-api-key header (recommended for REST API)
        # Supports both AIza* (legacy) and AQ.* (new) key formats
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        contents = []
        if system_prompt:
            # Gemini uses a "system_instruction" top-level field
            pass  # handled below
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            body["system_instruction"] = {"parts": [{"text": system_prompt}]}

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            return "", {}, FailureCategory.TIMEOUT
        except httpx.ConnectError:
            return "", {}, FailureCategory.SERVER_ERROR
        except Exception as exc:
            logger.warning("Gemini generate unexpected error: %s", exc)
            return "", {}, FailureCategory.UNKNOWN

        latency = time.monotonic() - start

        if resp.status_code != 200:
            cat = _classify_gemini_status(resp.status_code, resp.text)
            logger.warning(
                "Gemini %s responded %s: %s (category=%s)",
                model_id,
                resp.status_code,
                resp.text[:200],
                cat.value,
            )
            return "", {}, cat

        try:
            data = resp.json()
            candidate = data["candidates"][0]
            content_text = candidate["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            metadata = {
                "provider": ProviderName.GEMINI.value,
                "model": model_id,
                "latency_seconds": round(latency, 3),
                "input_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
            }
            # Check for safety block
            finish_reason = candidate.get("finishReason", "")
            if finish_reason == "SAFETY":
                return "", metadata, FailureCategory.SAFETY_REFUSAL
            return content_text, metadata, None
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Gemini response parse error: %s — body: %s", exc, resp.text[:300])
            return "", {}, FailureCategory.UNKNOWN

    # ─── embeddings ────────────────────────────────────────────────────────

    async def embed(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> tuple[list[float], FailureCategory | None]:
        """Generate an embedding vector.

        Args:
            text: Input text.
            task_type: One of RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY.

        Returns:
            (vector, failure_category_or_None)
        """
        if not self._api_key:
            return [], FailureCategory.AUTH_FAILURE

        model_id = self.embedding_model_id
        url = f"{_GEMINI_API_BASE}/models/{model_id}:embedContent"
        
        # Use x-goog-api-key header (recommended for REST API)
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        
        body = {
            "model": f"models/{model_id}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            return [], FailureCategory.TIMEOUT
        except httpx.ConnectError:
            return [], FailureCategory.SERVER_ERROR
        except Exception as exc:
            logger.warning("Gemini embed unexpected error: %s", exc)
            return [], FailureCategory.UNKNOWN

        if resp.status_code != 200:
            cat = _classify_gemini_status(resp.status_code, resp.text)
            logger.warning(
                "Gemini embed responded %s: %s (category=%s)",
                resp.status_code,
                resp.text[:200],
                cat.value,
            )
            return [], cat

        try:
            data = resp.json()
            vector = data["embedding"]["values"]
            if len(vector) != self.embedding_dimension:
                logger.error(
                    "Gemini embedding dimension mismatch: expected %d got %d",
                    self.embedding_dimension,
                    len(vector),
                )
                return [], FailureCategory.UNKNOWN
            return vector, None
        except (KeyError, ValueError) as exc:
            logger.warning("Gemini embed parse error: %s", exc)
            return [], FailureCategory.UNKNOWN

    # ─── health ────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if Gemini API is reachable with a lightweight call.
        
        Tests actual authorization with Google's API (both AIza* and AQ.* formats).
        """
        if not self._api_key:
            return False
        
        url = f"{_GEMINI_API_BASE}/models"
        headers = {
            "x-goog-api-key": self._api_key,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
            return resp.status_code == 200
        except Exception:
            return False
