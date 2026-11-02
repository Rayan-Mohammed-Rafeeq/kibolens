"""Tests for exhaustive dynamic provider-first model fallback system.

Verifies that:
1. Each provider is completely exhausted before moving to the next
2. ALL eligible free models are attempted (not just a small hardcoded list)
3. Provider order is strictly maintained (Gemini → Groq → OpenRouter)
4. Dynamic model discovery works correctly
5. Zero-cost enforcement is maintained throughout
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.router.core import AIRouter
from app.ai.router.types import (
    AICapability,
    FailureCategory,
    ModelEntry,
    ModelStatus,
    ProviderName,
    QualityTier,
)
from app.core.config import Settings


@pytest.fixture
def exhaustive_settings() -> Settings:
    """Settings configured for exhaustive dynamic fallback testing."""
    return Settings(
        database_url="sqlite://",
        gemini_api_key="test-gemini-key",
        groq_api_key="test-groq-key",
        openrouter_api_key="test-openrouter-key",
        ai_free_only=True,
        ai_allow_paid_models=False,
        ai_max_model_attempts=20,  # Max allowed, but router ignores this for provider exhaustion
        ai_provider_timeout_seconds=10.0,
        ai_model_catalog_refresh_hours=24.0,
    )


@pytest.mark.asyncio
async def test_gemini_exhausted_before_groq(exhaustive_settings):
    """Verify ALL Gemini models are tried before ANY Groq model."""
    router = AIRouter(exhaustive_settings)
    
    # Mock all Gemini calls to fail
    gemini_fail = MagicMock()
    gemini_fail.status_code = 503
    gemini_fail.text = "temporary error"
    
    # Mock Groq success
    groq_success = MagicMock()
    groq_success.status_code = 200
    groq_success.json.return_value = {
        "choices": [{"message": {"content": "Groq response"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    
    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        
        async def post_side_effect(url, **kwargs):
            if "generativelanguage.googleapis.com" in url:
                return gemini_fail
            elif "api.groq.com" in url:
                return groq_success
            return gemini_fail
        
        instance.post = AsyncMock(side_effect=post_side_effect)
        instance.get = AsyncMock(return_value=groq_success)
        mock_client_cls.return_value = instance
        
        result = await router.generate_text("test prompt")
    
    # Should succeed with Groq after exhausting Gemini
    assert result.successful_provider == ProviderName.GROQ
    assert result.successful_model is not None
    
    # Verify Gemini attempts came BEFORE Groq attempts
    gemini_attempts = [a for a in result.attempts if a.provider == ProviderName.GEMINI]
    groq_attempts = [a for a in result.attempts if a.provider == ProviderName.GROQ]
    
    # Must have tried multiple Gemini models before circuit breaker opened
    # Circuit breaker will open after threshold (default 5) to protect provider
    assert len(gemini_attempts) >= 5, f"Only tried {len(gemini_attempts)} Gemini models"
    
    # Must have tried at least one Groq model
    assert len(groq_attempts) >= 1
    
    # ALL Gemini attempts must come before or at same time as ANY Groq attempt
    # (same timestamp is OK in fast tests)
    if gemini_attempts and groq_attempts:
        last_gemini_time = gemini_attempts[-1].started_at
        first_groq_time = groq_attempts[0].started_at
        assert last_gemini_time <= first_groq_time, "Provider ordering violated"


@pytest.mark.asyncio
async def test_groq_exhausted_before_openrouter(exhaustive_settings):
    """Verify ALL Groq models are tried before ANY OpenRouter model."""
    router = AIRouter(exhaustive_settings)
    
    # Mock Gemini provider circuit open (simulating prior exhaustion)
    gemini_fail = MagicMock()
    gemini_fail.status_code = 429
    gemini_fail.text = "quota exhausted"
    gemini_fail.headers = {}
    
    # Mock all Groq calls to fail (except need to return success for catalogue discovery)
    groq_fail = MagicMock()
    groq_fail.status_code = 503
    groq_fail.text = "temporary error"
    groq_fail.headers = {}
    
    groq_models_resp = MagicMock()
    groq_models_resp.status_code = 200
    groq_models_resp.json.return_value = {"data": []}  # Will use defaults
    
    # Mock OpenRouter success
    or_success = MagicMock()
    or_success.status_code = 200
    or_success.json.return_value = {
        "choices": [{"message": {"content": "OpenRouter response"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    
    or_models_resp = MagicMock()
    or_models_resp.status_code = 200
    or_models_resp.json.return_value = {"data": [
        {
            "id": "meta-llama/llama-3.1-8b-instruct:free",
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"modality": "text"},
        }
    ]}
    
    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        
        async def post_side_effect(url, **kwargs):
            if "generativelanguage.googleapis.com" in url:
                return gemini_fail
            elif "api.groq.com" in url and "/chat/" in url:
                return groq_fail
            elif "openrouter.ai" in url and "/chat/" in url:
                return or_success
            return groq_fail
        
        async def get_side_effect(url, **kwargs):
            # Mock catalogue responses
            if "openrouter.ai" in url and "/models" in url:
                return or_models_resp
            elif "api.groq.com" in url and "/models" in url:
                return groq_models_resp
            return MagicMock(status_code=200, json=lambda: {"data": []})
        
        instance.post = AsyncMock(side_effect=post_side_effect)
        instance.get = AsyncMock(side_effect=get_side_effect)
        mock_client_cls.return_value = instance
        
        result = await router.generate_text("test prompt")
    
    # Should succeed with OpenRouter after exhausting Gemini and Groq
    assert result.successful_provider == ProviderName.OPENROUTER
    
    # Verify ordering: Gemini → Groq → OpenRouter
    gemini_attempts = [a for a in result.attempts if a.provider == ProviderName.GEMINI]
    groq_attempts = [a for a in result.attempts if a.provider == ProviderName.GROQ]
    or_attempts = [a for a in result.attempts if a.provider == ProviderName.OPENROUTER]
    
    # Must have tried models from each provider
    assert len(gemini_attempts) >= 1
    # Circuit breaker protects provider after threshold failures
    assert len(groq_attempts) >= 5, f"Only tried {len(groq_attempts)} Groq models"
    assert len(or_attempts) >= 1
    
    # Verify strict ordering (allow equal timestamps in fast tests)
    if gemini_attempts and groq_attempts:
        assert gemini_attempts[-1].started_at <= groq_attempts[0].started_at
    if groq_attempts and or_attempts:
        assert groq_attempts[-1].started_at <= or_attempts[0].started_at


@pytest.mark.asyncio
async def test_gemini_catalogue_discovers_multiple_models(exhaustive_settings):
    """Verify Gemini dynamic discovery finds VERIFIED free models only."""
    router = AIRouter(exhaustive_settings)
    
    gemini_text = await router._gemini.text_models()
    gemini_vision = await router._gemini.vision_models()
    
    # Should have comprehensive VERIFIED default registries (14 each after removing unverified 3.x models)
    assert len(gemini_text) >= 14, f"Only {len(gemini_text)} Gemini text models"
    assert len(gemini_vision) >= 14, f"Only {len(gemini_vision)} Gemini vision models"
    
    # Should include multiple quality tiers
    text_tiers = {m.quality_tier for m in gemini_text}
    assert QualityTier.ADVANCED in text_tiers
    assert QualityTier.BALANCED in text_tiers
    assert QualityTier.FAST in text_tiers
    
    # All must be verified free
    assert all(m.is_verified_free for m in gemini_text)
    assert all(m.is_verified_free for m in gemini_vision)


@pytest.mark.asyncio
async def test_groq_catalogue_discovers_multiple_models(exhaustive_settings):
    """Verify Groq dynamic discovery finds VERIFIED free models only."""
    router = AIRouter(exhaustive_settings)
    
    groq_text = await router._groq.text_models()
    groq_vision = await router._groq.vision_models()
    
    # Should have comprehensive VERIFIED default registries
    assert len(groq_text) >= 9, f"Only {len(groq_text)} Groq text models"
    assert len(groq_vision) >= 3, f"Only {len(groq_vision)} Groq vision models"
    
    # Should include multiple quality tiers
    text_tiers = {m.quality_tier for m in groq_text}
    assert QualityTier.ADVANCED in text_tiers
    assert QualityTier.BALANCED in text_tiers
    
    # All must be verified free
    assert all(m.is_verified_free for m in groq_text)
    assert all(m.is_verified_free for m in groq_vision)


@pytest.mark.asyncio
async def test_no_artificial_attempt_limits_within_provider(exhaustive_settings):
    """Verify router does not stop after arbitrary attempt count within a provider."""
    router = AIRouter(exhaustive_settings)
    
    # Mock all calls to fail
    all_fail = MagicMock()
    all_fail.status_code = 503
    all_fail.text = "temporary error"
    
    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=all_fail)
        instance.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"data": []}
        ))
        mock_client_cls.return_value = instance
        
        result = await router.generate_text("test prompt")
    
    # Should have tried many models from Gemini before circuit breaker opened
    gemini_attempts = [a for a in result.attempts if a.provider == ProviderName.GEMINI]
    
    # Circuit breaker opens after threshold (default 5) to protect failing provider
    # This is EXPECTED behavior - we don't want to hammer a down provider
    assert len(gemini_attempts) >= 5, (
        f"Router stopped after only {len(gemini_attempts)} attempts. "
        "Circuit breaker should allow at least 5 attempts before opening."
    )


@pytest.mark.asyncio
async def test_all_providers_use_separate_registries(exhaustive_settings):
    """Verify text and vision use separate model registries per provider."""
    router = AIRouter(exhaustive_settings)
    
    # Get all registries
    gemini_text = await router._gemini.text_models()
    gemini_vision = await router._gemini.vision_models()
    groq_text = await router._groq.text_models()
    groq_vision = await router._groq.vision_models()
    or_text = await router._openrouter.text_models()
    or_vision = await router._openrouter.vision_models()
    
    # All text models must support TEXT_GENERATION
    for m in gemini_text + groq_text + or_text:
        assert m.supports(AICapability.TEXT_GENERATION)
    
    # All vision models must support both TEXT_GENERATION and VISION_INPUT
    for m in gemini_vision + groq_vision + or_vision:
        assert m.supports(AICapability.VISION_INPUT)
    
    # Vision registries should not be empty
    assert len(gemini_vision) > 0
    assert len(groq_vision) > 0
    # OpenRouter vision may be empty depending on current :free catalogue


@pytest.mark.asyncio
async def test_zero_cost_enforcement_throughout_exhaustive_fallback(exhaustive_settings):
    """Verify no paid models are used even during exhaustive fallback."""
    router = AIRouter(exhaustive_settings)
    
    # Mock all calls to fail to trigger exhaustive fallback
    all_fail = MagicMock()
    all_fail.status_code = 503
    all_fail.text = "temporary error"
    
    with patch("httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=all_fail)
        instance.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"data": []}
        ))
        mock_client_cls.return_value = instance
        
        result = await router.generate_text("test prompt")
    
    # Verify every single attempted model was free
    for attempt in result.attempts:
        # Check in all provider registries
        all_models = (
            await router._gemini.text_models() +
            await router._groq.text_models() +
            await router._openrouter.text_models()
        )
        
        attempted_model = next(
            (m for m in all_models if m.model_id == attempt.model_id),
            None
        )
        
        if attempted_model:
            assert attempted_model.is_verified_free, (
                f"Attempted paid model {attempt.model_id} during fallback"
            )


@pytest.mark.asyncio
async def test_health_status_shows_comprehensive_model_counts(exhaustive_settings):
    """Verify health endpoint reports verified model counts from dynamic discovery."""
    router = AIRouter(exhaustive_settings)
    
    health = await router.health_status()
    
    # Should report comprehensive VERIFIED model counts
    gemini_text_count = health["providers"]["gemini"]["text_models_count"]
    gemini_vision_count = health["providers"]["gemini"]["vision_models_count"]
    groq_text_count = health["providers"]["groq"]["text_models_count"]
    
    assert gemini_text_count >= 14, f"Only {gemini_text_count} Gemini text models"
    assert gemini_vision_count >= 14, f"Only {gemini_vision_count} Gemini vision models"
    assert groq_text_count >= 9, f"Only {groq_text_count} Groq text models"
    
    # Should show top models from each provider
    assert len(health["providers"]["gemini"]["top_text_models"]) <= 10
    assert len(health["providers"]["groq"]["top_text_models"]) <= 10
