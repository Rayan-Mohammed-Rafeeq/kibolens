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
