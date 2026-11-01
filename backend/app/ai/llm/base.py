"""Base LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel, Generic[T]):
    """Standardized LLM response wrapper.
    
    Attributes:
        content: Raw text response from the LLM
        structured_output: Parsed Pydantic model (if structured output was requested)
        metadata: Provider-specific metadata (model, tokens, latency, etc.)
        error: Error message if the request failed
    """

    content: str
    structured_output: T | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All providers (Ollama, OpenAI, Anthropic, etc.) must implement this interface.
    Provides both unstructured (text) and structured (Pydantic model) generation.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse[None]:
        """Generate unstructured text response.
        
        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions
            temperature: Override default temperature (0=deterministic, 1=creative)
            max_tokens: Override default max tokens
            
        Returns:
            LLMResponse with content and metadata
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse[T]:
        """Generate structured output conforming to a Pydantic model.
        
        Args:
            prompt: User prompt/question
            response_model: Pydantic model class for structured output
            system_prompt: Optional system instructions
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            LLMResponse with structured_output parsed into response_model
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM provider is reachable and healthy.
        
        Returns:
            True if provider is available, False otherwise
        """
        pass
