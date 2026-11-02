"""LLM provider factory for dependency injection.

Cloud routing (Gemini + OpenRouter) is the default.
Ollama is kept for rollback — set KIBOLENS_LLM_PROVIDER=ollama to re-enable it.
"""

from __future__ import annotations

import logging

from app.ai.llm.base import BaseLLMProvider, LLMResponse
from app.core.config import Settings

logger = logging.getLogger(__name__)


class CloudRouterAdapter(BaseLLMProvider):
    """Thin adapter that wraps the central AIRouter as a BaseLLMProvider.

    This lets existing code that calls get_llm_provider() continue to work
    without modification while routing through the new cloud system.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._router = None  # lazy-initialised

    async def _get_router(self):
        if self._router is None:
            from app.ai.router.core import get_ai_router
            self._router = await get_ai_router(self.settings)
        return self._router

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse[None]:
        router = await self._get_router()
        result = await router.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        metadata = {
            "provider": result.successful_provider.value if result.successful_provider else "none",
            "model": result.successful_model or "none",
            "latency_seconds": result.total_latency_seconds,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "attempts": [
                {
                    "provider": a.provider.value,
                    "model": a.model_id,
                    "succeeded": a.succeeded,
                    "failure": a.failure_category.value if a.failure_category else None,
                }
                for a in result.attempts
            ],
        }
        return LLMResponse[None](
            content=result.content,
            structured_output=None,
            metadata=metadata,
            error=result.error if result.unavailable else None,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        import json
        from pydantic import ValidationError

        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2)

        structured_system_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + f"""You must respond with valid JSON conforming to this schema:

{schema_str}

Respond ONLY with the JSON object. Do not include explanations, markdown formatting, or code blocks."""

        router = await self._get_router()
        result = await router.generate_text(
            prompt=prompt,
            system_prompt=structured_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        structured_output = None
        parse_error = None
        if result.content:
            try:
                # Strip markdown code blocks if present
                content = result.content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                json_data = json.loads(content)
                structured_output = response_model.model_validate(json_data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning("Failed to parse structured output: %s", e)
                parse_error = str(e)

        metadata = {
            "provider": result.successful_provider.value if result.successful_provider else "none",
            "model": result.successful_model or "none",
            "latency_seconds": result.total_latency_seconds,
            "format": "json",
        }
        if parse_error:
            metadata["parse_error"] = parse_error

        return LLMResponse(
            content=result.content,
            structured_output=structured_output,
            metadata=metadata,
            error=parse_error or (result.error if result.unavailable else None),
        )

    async def health_check(self) -> bool:
        """Check if ANY cloud provider is available.
        
        Cloud routing is available if ANY of Gemini, Groq, or OpenRouter
        has a valid API key configured. Provider-first fallback ensures
        the system remains operational with any single provider.
        """
        router = await self._get_router()
        status = await router.health_status()
        gemini_up = status["providers"]["gemini"]["available"]
        groq_up = status["providers"]["groq"]["available"]
        openrouter_up = status["providers"]["openrouter"]["available"]
        return gemini_up or groq_up or openrouter_up


def get_llm_provider(settings: Settings | None = None) -> BaseLLMProvider:
    """Factory function to get the configured LLM provider.

    Cloud routing is the default (llm_provider="cloud").
    Set KIBOLENS_LLM_PROVIDER=ollama to roll back to local Ollama inference.

    Returns:
        BaseLLMProvider implementation

    Raises:
        ValueError: If provider is not supported
    """
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()

    provider_name = settings.llm_provider.lower()

    if provider_name == "cloud":
        return CloudRouterAdapter(settings)

    if provider_name == "ollama":
        from app.ai.llm.ollama import OllamaProvider
        return OllamaProvider(settings)

    raise ValueError(
        f"Unsupported LLM provider: {provider_name}. Supported: cloud, ollama"
    )
