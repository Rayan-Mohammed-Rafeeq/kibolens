"""Ollama LLM provider implementation."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from app.ai.llm.base import BaseLLMProvider, LLMResponse
from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama LLM provider using langchain-ollama.
    
    Supports both text generation and structured outputs via JSON mode + Pydantic parsing.
    """

    def __init__(self, settings: Settings):
        """Initialize Ollama provider.
        
        Args:
            settings: Application settings with Ollama configuration
        """
        self.settings = settings
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.default_temperature = settings.llm_temperature
        self.default_max_tokens = settings.llm_max_tokens
        self.timeout = settings.ollama_timeout_seconds

        # Initialize ChatOllama client
        self._client = ChatOllama(
            base_url=self.base_url,
            model=self.model,
            temperature=self.default_temperature,
            num_predict=self.default_max_tokens,
            timeout=self.timeout,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse[None]:
        """Generate unstructured text response from Ollama.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            temperature: Override temperature
            max_tokens: Override max tokens
            
        Returns:
            LLMResponse with text content
        """
        try:
            start_time = time.time()

            # Build message list
            messages: list[SystemMessage | HumanMessage] = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))

            # Configure generation parameters
            client = self._client
            if temperature is not None:
                client = client.bind(temperature=temperature)
            if max_tokens is not None:
                client = client.bind(num_predict=max_tokens)

            # Generate response
            response = await client.ainvoke(messages)
            latency = time.time() - start_time

            content = response.content if isinstance(response.content, str) else str(response.content)

            metadata = {
                "model": self.model,
                "provider": "ollama",
                "latency_seconds": round(latency, 3),
                "temperature": temperature or self.default_temperature,
            }

            # Extract token usage if available
            if hasattr(response, "response_metadata"):
                response_meta = response.response_metadata
                if "eval_count" in response_meta:
                    metadata["output_tokens"] = response_meta["eval_count"]
                if "prompt_eval_count" in response_meta:
                    metadata["input_tokens"] = response_meta["prompt_eval_count"]

            return LLMResponse[None](
                content=content,
                structured_output=None,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception(f"Ollama generation failed: {e}")
            return LLMResponse[None](
                content="",
                structured_output=None,
                metadata={"model": self.model, "provider": "ollama"},
                error=str(e),
            )

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse[T]:
        """Generate structured output conforming to a Pydantic model.
        
        Uses JSON mode + schema injection + validation. Falls back gracefully on parsing errors.
        
        Args:
            prompt: User prompt
            response_model: Pydantic model for structured output
            system_prompt: Optional system instructions
            temperature: Override temperature
            max_tokens: Override max tokens
            
        Returns:
            LLMResponse with structured_output parsed into response_model
        """
        try:
            start_time = time.time()

            # Generate JSON schema from Pydantic model
            schema = response_model.model_json_schema()
            schema_str = json.dumps(schema, indent=2)

            # Augment system prompt with schema instructions
            structured_system_prompt = (
                f"{system_prompt}\n\n" if system_prompt else ""
            ) + f"""You must respond with valid JSON conforming to this schema:

{schema_str}

Respond ONLY with the JSON object. Do not include explanations, markdown formatting, or code blocks."""

            # Build messages
            messages: list[SystemMessage | HumanMessage] = [
                SystemMessage(content=structured_system_prompt),
                HumanMessage(content=prompt),
            ]

            # Configure generation with JSON format
            client = self._client.bind(format="json")
            if temperature is not None:
                client = client.bind(temperature=temperature)
            if max_tokens is not None:
                client = client.bind(num_predict=max_tokens)

            # Generate response
            response = await client.ainvoke(messages)
            latency = time.time() - start_time

            content = response.content if isinstance(response.content, str) else str(response.content)

            # Parse JSON and validate against Pydantic model
            try:
                json_data = json.loads(content)
                structured_output = response_model.model_validate(json_data)
                parse_error = None
            except (json.JSONDecodeError, ValidationError) as parse_err:
                logger.warning(f"Failed to parse structured output: {parse_err}")
                structured_output = None
                parse_error = str(parse_err)

            metadata: dict[str, Any] = {
                "model": self.model,
                "provider": "ollama",
                "latency_seconds": round(latency, 3),
                "temperature": temperature or self.default_temperature,
                "format": "json",
            }

            if parse_error:
                metadata["parse_error"] = parse_error

            # Extract token usage
            if hasattr(response, "response_metadata"):
                response_meta = response.response_metadata
                if "eval_count" in response_meta:
                    metadata["output_tokens"] = response_meta["eval_count"]
                if "prompt_eval_count" in response_meta:
                    metadata["input_tokens"] = response_meta["prompt_eval_count"]

            return LLMResponse[T](
                content=content,
                structured_output=structured_output,
                metadata=metadata,
                error=parse_error,
            )

        except Exception as e:
            logger.exception(f"Ollama structured generation failed: {e}")
            return LLMResponse[T](
                content="",
                structured_output=None,
                metadata={"model": self.model, "provider": "ollama", "format": "json"},
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and the model is available.
        
        Returns:
            True if Ollama is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check Ollama is running
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False

                # Check if the configured model is available
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Exact match or prefix match (e.g., "llama3.2:3b" matches "llama3.2:3b")
                return any(self.model in name or name in self.model for name in model_names)

        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
