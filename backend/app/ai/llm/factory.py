"""LLM provider factory for dependency injection."""

from __future__ import annotations

import logging

from app.ai.llm.base import BaseLLMProvider
from app.ai.llm.ollama import OllamaProvider
from app.core.config import Settings

logger = logging.getLogger(__name__)


def get_llm_provider(settings: Settings | None = None) -> BaseLLMProvider:
    """Factory function to get the configured LLM provider.
    
    Args:
        settings: Application settings (defaults to get_settings())
        
    Returns:
        BaseLLMProvider implementation (currently only Ollama)
        
    Raises:
        ValueError: If provider is not supported
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    provider_name = settings.llm_provider.lower()

    if provider_name == "ollama":
        return OllamaProvider(settings)

    # Future providers can be added here:
    # elif provider_name == "openai":
    #     return OpenAIProvider(settings)
    # elif provider_name == "anthropic":
    #     return AnthropicProvider(settings)

    raise ValueError(f"Unsupported LLM provider: {provider_name}. Supported: ollama")
