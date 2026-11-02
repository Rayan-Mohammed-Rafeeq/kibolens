import pytest

from app.ai.langchain_router import CloudRouterChatModel
from app.ai.router.types import AICapability, ProviderName, RoutingResult


class StubRouter:
    async def generate_text(self, **kwargs):
        return RoutingResult(
            capability=AICapability.TEXT_GENERATION,
            successful_provider=ProviderName.GROQ,
            successful_model="qwen/qwen3.8-27b",
            content="adapter response",
        )


@pytest.mark.asyncio
async def test_langchain_adapter_preserves_messages_and_routing_metadata():
    model = CloudRouterChatModel(router=StubRouter(), temperature=0, max_tokens=40)
    response = await model.ainvoke([
        ("system", "Use evidence only."),
        ("human", "What is the current CPU?"),
    ])
    assert response.content == "adapter response"
    assert response.response_metadata["provider"] == "groq"
    assert response.response_metadata["model"] == "qwen/qwen3.8-27b"


@pytest.mark.asyncio
async def test_langchain_adapter_preserves_full_incomplete_response_metadata():
    full_content = "# Status\n\n" + ("Observed evidence. " * 200)

    class LongRouter:
        async def generate_text(self, **kwargs):
            return RoutingResult(
                capability=AICapability.TEXT_GENERATION,
                successful_provider=ProviderName.GEMINI,
                successful_model="gemini-3-flash-preview",
                content=full_content,
                finish_reason="MAX_TOKENS",
                incomplete=True,
                incomplete_reason="output_token_limit",
            )

    model = CloudRouterChatModel(router=LongRouter(), max_tokens=8000)
    response = await model.ainvoke("Provide the full analysis")

    assert response.content == full_content
    assert response.response_metadata["incomplete"] is True
    assert response.response_metadata["finish_reason"] == "MAX_TOKENS"
