"""Focused coverage for the real LangGraph/LangChain investigation path."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.ai.cloud_investigator import CloudAIInvestigator
from app.ai.router.types import AICapability, ProviderName, QualityTier, RoutingResult
from app.core.config import Settings


class FakeRouter:
    async def generate_text(self, **kwargs):
        return RoutingResult(
            capability=AICapability.TEXT_GENERATION,
            successful_provider=ProviderName.GEMINI,
            successful_model="test-free-model",
            successful_quality_tier=QualityTier.FAST,
            content="## Evidence\nCPU was observed at 42%.\n\n**Hypothesis:** test only.",
        )


class FakePrometheus:
    async def instant_query(self, query: str):
        return [{"metric": {}, "value": [datetime.now(timezone.utc).timestamp(), "42"]}]


class FakeDocuments:
    async def search_documents(self, query, user_id, limit):
        return [{
            "filename": "runbook.md", "chunk_index": 0, "score": 0.9,
            "text": "Check CPU saturation before restarting services.",
        }]


@pytest.mark.asyncio
async def test_langgraph_routes_relevant_sources_and_uses_langchain_adapter():
    investigator = CloudAIInvestigator(
        settings=Settings(database_url="sqlite://", llm_provider="cloud"),
        router=FakeRouter(),
        document_service=FakeDocuments(),
        prometheus_client=FakePrometheus(),
    )
    result = await investigator.investigate(
        "Why was CPU high according to the runbook?",
        user_id=uuid4(),
        conversation_id=uuid4(),
    )
    assert result["findings"]
    assert "Prometheus Metrics" in result["data_sources"]
    assert "Knowledge Base" in result["data_sources"]
    assert result["routing_metadata"]["provider"] == "gemini"
    assert result["evidence"]["execution"]["retrieval_counts"] == {"metrics": 1, "documents": 1}


@pytest.mark.asyncio
async def test_langgraph_preserves_full_response_and_reports_output_limit():
    full_content = "## Complete section\n\n" + ("Evidence line. " * 150)

    class TruncatedRouter(FakeRouter):
        async def generate_text(self, **kwargs):
            result = await super().generate_text(**kwargs)
            result.content = full_content
            result.finish_reason = "MAX_TOKENS"
            result.incomplete = True
            result.incomplete_reason = "output_token_limit"
            return result

    investigator = CloudAIInvestigator(
        settings=Settings(database_url="sqlite://", llm_provider="cloud"),
        router=TruncatedRouter(),
    )
    result = await investigator.investigate("Provide the complete infrastructure analysis")

    assert full_content in result["findings"]
    assert "output-token limit" in result["findings"]
    assert result["routing_metadata"]["incomplete"] is True
