"""Tests for Gemini API key format compatibility (AIza* and AQ.* formats)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.router.gemini_provider import GeminiProvider, _validate_gemini_api_key
from app.ai.router.types import FailureCategory
from app.core.config import Settings


# ═══════════════════════════════════════════════════════════════════════════
# Local Key Format Validation Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_validate_aiza_legacy_key():
    """Test that legacy AIza* keys pass local validation."""
    assert _validate_gemini_api_key("AIzaSyDummyKey1234567890AbCdEfGhIj") is True
    assert _validate_gemini_api_key("AIzaShortKey") is True
    assert _validate_gemini_api_key("AIza") is True


def test_validate_aq_new_authorization_key():
    """Test that new AQ.* authorization keys pass local validation."""
    assert _validate_gemini_api_key("AQ.dummyAuthKey1234567890") is True
    assert _validate_gemini_api_key("AQ.shortKey") is True
    assert _validate_gemini_api_key("AQ.") is True


def test_validate_empty_key_rejected():
    """Test that empty keys are rejected."""
    assert _validate_gemini_api_key(None) is False
    assert _validate_gemini_api_key("") is False
    assert _validate_gemini_api_key("   ") is False


def test_validate_unknown_prefix_accepted():
    """Test that unfamiliar prefixes are accepted (let Google decide validity)."""
    # Future-proof: don't reject new formats Google might introduce
    assert _validate_gemini_api_key("NewFormat123") is True
    assert _validate_gemini_api_key("XYZ.authkey") is True


# ═══════════════════════════════════════════════════════════════════════════
# Provider Initialization Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_provider_init_with_aiza_key():
    """Test provider initialization with AIza* key."""
    settings = Settings(gemini_api_key="AIzaSyTestKey123")
    provider = GeminiProvider(settings)
    
    assert provider.available is True
    assert provider._api_key == "AIzaSyTestKey123"


def test_provider_init_with_aq_key():
    """Test provider initialization with AQ.* key."""
    settings = Settings(gemini_api_key="AQ.testAuthKey456")
    provider = GeminiProvider(settings)
    
    assert provider.available is True
    assert provider._api_key == "AQ.testAuthKey456"


def test_provider_init_with_empty_key():
    """Test provider initialization with empty key."""
    settings = Settings(gemini_api_key="")
    provider = GeminiProvider(settings)
    
    assert provider.available is False
    assert provider._api_key is None


def test_provider_init_with_no_key():
    """Test provider initialization without key."""
    settings = Settings()
    provider = GeminiProvider(settings)
    
    assert provider.available is False
    assert provider._api_key is None


# ═══════════════════════════════════════════════════════════════════════════
# Authentication Header Tests (x-goog-api-key)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_uses_x_goog_api_key_header():
    """Test that generate() uses x-goog-api-key header, not Bearer token."""
    settings = Settings(gemini_api_key="AQ.testKey")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Test response"}]},
            "finishReason": "STOP"
        }],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        content, metadata, failure = await provider.generate(
            model_id="gemini-3.6-flash",
            prompt="Test prompt",
        )
        
        # Verify x-goog-api-key header was used
        call_kwargs = mock_client.post.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["x-goog-api-key"] == "AQ.testKey"
        assert "Content-Type" in call_kwargs["headers"]
        
        # Verify NO Bearer token was used
        assert "Authorization" not in call_kwargs["headers"]
        
        # Verify NO query parameters with key
        assert "params" not in call_kwargs or "key" not in call_kwargs.get("params", {})
        
        assert content == "Test response"
        assert failure is None


@pytest.mark.asyncio
async def test_embed_uses_x_goog_api_key_header():
    """Test that embed() uses x-goog-api-key header, not Bearer token."""
    settings = Settings(gemini_api_key="AIzaSyLegacyKey")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "embedding": {"values": [0.1] * 768}
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        vector, failure = await provider.embed("Test text")
        
        # Verify x-goog-api-key header was used
        call_kwargs = mock_client.post.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["x-goog-api-key"] == "AIzaSyLegacyKey"
        
        # Verify NO Bearer token
        assert "Authorization" not in call_kwargs["headers"]
        
        # Verify NO query params
        assert "params" not in call_kwargs or "key" not in call_kwargs.get("params", {})
        
        assert len(vector) == 768
        assert failure is None


@pytest.mark.asyncio
async def test_health_check_uses_x_goog_api_key_header():
    """Test that health_check() uses x-goog-api-key header."""
    settings = Settings(gemini_api_key="AQ.newFormatKey")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        result = await provider.health_check()
        
        # Verify x-goog-api-key header was used
        call_kwargs = mock_client.get.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["x-goog-api-key"] == "AQ.newFormatKey"
        
        # Verify NO query params with key
        assert "params" not in call_kwargs or "key" not in call_kwargs.get("params", {})
        
        assert result is True


# ═══════════════════════════════════════════════════════════════════════════
# Key Preservation Tests (No Conversion to Bearer)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aq_key_not_converted_to_bearer_token():
    """Test that AQ.* keys are NOT converted to Bearer tokens."""
    settings = Settings(gemini_api_key="AQ.authKey123")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Response"}]},
            "finishReason": "STOP"
        }]
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        await provider.generate(model_id="gemini-3.6-flash", prompt="Test")
        
        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        
        # Key must be in x-goog-api-key, not Authorization Bearer
        assert headers["x-goog-api-key"] == "AQ.authKey123"
        assert "Authorization" not in headers
        
        # Should NOT be "Bearer AQ.authKey123"
        if "Authorization" in headers:
            assert not headers["Authorization"].startswith("Bearer")


@pytest.mark.asyncio
async def test_aiza_key_not_converted_to_bearer_token():
    """Test that AIza* keys are NOT converted to Bearer tokens."""
    settings = Settings(gemini_api_key="AIzaSyLegacy456")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Response"}]},
            "finishReason": "STOP"
        }]
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        await provider.generate(model_id="gemini-3.6-flash", prompt="Test")
        
        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        
        # Key must remain as-is in x-goog-api-key
        assert headers["x-goog-api-key"] == "AIzaSyLegacy456"
        assert "Authorization" not in headers


# ═══════════════════════════════════════════════════════════════════════════
# Remote Authentication Failure Handling
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_invalid_credentials_classified_as_auth_failure():
    """Test that 401/403 responses are classified as AUTH_FAILURE."""
    settings = Settings(gemini_api_key="AQ.invalidKey")
    provider = GeminiProvider(settings)
    
    for status_code in [401, 403]:
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = "Invalid API key"
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            content, metadata, failure = await provider.generate(
                model_id="gemini-3.6-flash",
                prompt="Test"
            )
            
            assert failure == FailureCategory.AUTH_FAILURE
            assert content == ""


@pytest.mark.asyncio
async def test_aq_key_remote_validation():
    """Test that AQ.* keys reach remote API for validation."""
    settings = Settings(gemini_api_key="AQ.testKey")
    provider = GeminiProvider(settings)
    
    # Simulate Google API rejecting the key (remote validation)
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "API key not valid. Please pass a valid API key."
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        content, metadata, failure = await provider.generate(
            model_id="gemini-3.6-flash",
            prompt="Test"
        )
        
        # Key was sent to Google API (passed local validation)
        assert mock_client.post.called
        
        # Google rejected it (remote validation)
        assert failure == FailureCategory.AUTH_FAILURE


# ═══════════════════════════════════════════════════════════════════════════
# Security: No Key Exposure in Logs
# ═══════════════════════════════════════════════════════════════════════════


def test_api_key_not_in_string_representation():
    """Test that API keys are not exposed in string representations."""
    settings = Settings(gemini_api_key="AQ.secretKey123")
    provider = GeminiProvider(settings)
    
    # Provider string representation should not contain the actual key
    provider_str = str(provider)
    assert "AQ.secretKey123" not in provider_str
    
    # Settings should use SecretStr which masks the value
    settings_str = str(settings.gemini_api_key)
    assert "AQ.secretKey123" not in settings_str


@pytest.mark.asyncio
async def test_failed_request_logs_dont_expose_key():
    """Test that failed requests don't log the actual API key."""
    settings = Settings(gemini_api_key="AQ.secretKey456")
    provider = GeminiProvider(settings)
    
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials"
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        with patch("app.ai.router.gemini_provider.logger") as mock_logger:
            await provider.generate(model_id="gemini-3.6-flash", prompt="Test")
            
            # Check that logger.warning was called but didn't include the key
            if mock_logger.warning.called:
                for call in mock_logger.warning.call_args_list:
                    call_str = str(call)
                    assert "AQ.secretKey456" not in call_str
