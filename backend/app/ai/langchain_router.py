"""LangChain chat-model adapter backed by KiboLens' centralized cloud router.

LangChain and LangGraph call this adapter; provider selection, free-only
policy, capability checks and fallback remain exclusively in AIRouter.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from app.ai.router.core import AIRouter


class CloudRouterChatModel(BaseChatModel):
    """A LangChain-compatible chat model that never bypasses AIRouter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    router: Any
    temperature: float = 0.1
    max_tokens: int = 2000
    last_routing_metadata: dict[str, Any] | None = None

    @property
    def _llm_type(self) -> str:
        return "kibolens-cloud-router"

    @staticmethod
    def _prompt(messages: list[BaseMessage]) -> tuple[str | None, str]:
        system_parts: list[str] = []
        user_parts: list[str] = []
        for message in messages:
            content = str(message.content)
            if message.type == "system":
                system_parts.append(content)
            elif message.type == "human":
                user_parts.append(content)
            else:
                user_parts.append(f"{message.type.upper()}: {content}")
        return ("\n\n".join(system_parts) or None, "\n\n".join(user_parts))

    @staticmethod
    def _metadata(result) -> dict[str, Any]:
        return {
            "provider": result.successful_provider.value if result.successful_provider else None,
            "model": result.successful_model,
            "quality_tier": result.successful_quality_tier.value if result.successful_quality_tier else None,
            "latency_seconds": result.total_latency_seconds,
            "unavailable": result.unavailable,
            "error": result.error,
            "attempts": [
                {
                    "provider": attempt.provider.value,
                    "model": attempt.model_id,
                    "succeeded": attempt.succeeded,
                    "failure_category": attempt.failure_category.value if attempt.failure_category else None,
                }
                for attempt in result.attempts
            ],
        }

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        system_prompt, prompt = self._prompt(messages)
        result = asyncio.run(self.router.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        ))
        self.last_routing_metadata = self._metadata(result)
        content = result.content if result.content else (result.error or "Cloud AI providers returned no response.")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=content,
            response_metadata=self.last_routing_metadata,
        ))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        system_prompt, prompt = self._prompt(messages)
        result = await self.router.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        self.last_routing_metadata = self._metadata(result)
        content = result.content if result.content else (result.error or "Cloud AI providers returned no response.")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=content,
            response_metadata=self.last_routing_metadata,
        ))])
