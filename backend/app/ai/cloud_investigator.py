"""Cloud-aware AI investigator using the central AI router.

This replaces the direct Ollama / ChatOllama dependency while preserving:
- LangGraph investigation workflow structure
- Prometheus tool access
- Incident context
- RAG retrieval
- Evidence-vs-hypothesis distinction
- Source references

The investigation response now includes provider/model routing metadata.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.ai.router.core import AIRouter, get_ai_router
from app.ai.router.types import RoutingResult
from app.core.config import Settings
from app.monitoring.prometheus import PrometheusClient
from app.services.documents import DocumentService
from app.services.incidents import IncidentService

UTC = tz.utc

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# State definition (unchanged from original for LangGraph compatibility)
# ─────────────────────────────────────────────────────────────────────────────

class InvestigationState(TypedDict):
    """State passed between investigation workflow nodes."""

    messages: Annotated[list, add_messages]
    question: str
    incident_context: str | None
    metrics_data: str | None
    document_context: str | None
    findings: str | None
    recommendations: str | None
    error: str | None
    # Routing metadata injected by the cloud investigator
    routing_metadata: dict | None
    user_id: UUID | None
    conversation_context: str | None


class InvestigationFindings(BaseModel):
    """Structured output for investigation findings."""

    summary: str = Field(description="Brief summary of the investigation")
    root_cause_hypothesis: str = Field(
        description="AI-generated hypothesis about root cause (clearly marked as hypothesis)"
    )
    supporting_evidence: list[str] = Field(
        description="List of observed evidence from metrics, logs, or documents"
    )
    confidence_level: Literal["low", "medium", "high"] = Field(
        description="Confidence level in the hypothesis"
    )
    recommendations: list[str] = Field(
        description="Recommended actions based on findings"
    )
    data_sources: list[str] = Field(
        description="Data sources consulted (metrics, documents, incidents)"
    )


class CloudAIInvestigator:
    """LangGraph-based AI investigator using the central cloud AI router.

    Orchestrates context gathering from multiple sources, then uses the
    provider-first fallback router to generate evidence-based findings.
    """

    def __init__(
        self,
        settings: Settings,
        router: AIRouter,
        document_service: DocumentService | None = None,
        incident_service: IncidentService | None = None,
        prometheus_client: PrometheusClient | None = None,
    ):
        self.settings = settings
        self._router = router
        self.document_service = document_service
        self.incident_service = incident_service
        self.prometheus_client = prometheus_client
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph investigation workflow."""
        workflow = StateGraph(InvestigationState)

        workflow.add_node("gather_incident_context", self._gather_incident_context)
        workflow.add_node("gather_metrics", self._gather_metrics)
        workflow.add_node("gather_documents", self._gather_documents)
        workflow.add_node("analyze_and_conclude", self._analyze_and_conclude)

        workflow.set_entry_point("gather_incident_context")
        workflow.add_edge("gather_incident_context", "gather_metrics")
        workflow.add_edge("gather_metrics", "gather_documents")
        workflow.add_edge("gather_documents", "analyze_and_conclude")
        workflow.add_edge("analyze_and_conclude", END)

        return workflow.compile()

    # ─── Context-gathering nodes (semantics preserved from original) ──────────

    async def _gather_incident_context(
        self, state: InvestigationState
    ) -> InvestigationState:
        if not self.incident_service:
            state["incident_context"] = None
            return state
        try:
            context_parts = ["Recent incident context: "]
            context_parts.append("Incident data available from incident management system.")
            state["incident_context"] = "\n".join(context_parts)
            logger.info("Gathered incident context")
        except Exception as e:
            logger.warning("Failed to gather incident context: %s", e)
            state["incident_context"] = None
        return state

    async def _gather_metrics(self, state: InvestigationState) -> InvestigationState:
        if not self.prometheus_client:
            state["metrics_data"] = None
            return state
        try:
            question_lower = state["question"].lower()
            metrics_parts = ["Prometheus metrics: "]
            queries_executed = []

            if any(word in question_lower for word in ["cpu", "processor", "load"]):
                try:
                    result = await self.prometheus_client.instant_query(
                        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
                    )
                    if result:
                        cpu_value = result[0].get("value", [None, None])[1]
                        metrics_parts.append(f"CPU Utilization: {cpu_value}%")
                        queries_executed.append("cpu_utilization")
                except Exception as e:
                    logger.warning("CPU query failed: %s", e)

            if any(word in question_lower for word in ["memory", "ram", "oom"]):
                try:
                    result = await self.prometheus_client.instant_query(
                        "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))"
                    )
                    if result:
                        mem_value = result[0].get("value", [None, None])[1]
                        metrics_parts.append(f"Memory Utilization: {mem_value}%")
                        queries_executed.append("memory_utilization")
                except Exception as e:
                    logger.warning("Memory query failed: %s", e)

            if any(word in question_lower for word in ["disk", "storage", "filesystem"]):
                try:
                    result = await self.prometheus_client.instant_query(
                        'max(100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})))'
                    )
                    if result:
                        disk_value = result[0].get("value", [None, None])[1]
                        metrics_parts.append(f"Disk Utilization: {disk_value}%")
                        queries_executed.append("disk_utilization")
                except Exception as e:
                    logger.warning("Disk query failed: %s", e)

            if any(word in question_lower for word in ["network", "bandwidth", "traffic"]):
                try:
                    result = await self.prometheus_client.instant_query(
                        'sum(rate(node_network_receive_bytes_total{device!="lo"}[5m]))'
                    )
                    if result:
                        net_rx = result[0].get("value", [None, None])[1]
                        metrics_parts.append(f"Network Receive: {net_rx} bytes/sec")
                        queries_executed.append("network_receive")
                except Exception as e:
                    logger.warning("Network query failed: %s", e)

            if queries_executed:
                state["metrics_data"] = "\n".join(metrics_parts)
                logger.info("Gathered metrics: %s", ", ".join(queries_executed))
            else:
                state["metrics_data"] = "No specific metrics queries matched the question."

        except Exception as e:
            logger.warning("Failed to gather metrics: %s", e)
            state["metrics_data"] = None

        return state

    async def _gather_documents(self, state: InvestigationState) -> InvestigationState:
        if not self.document_service:
            state["document_context"] = None
            return state
        try:
            if state.get("user_id") is None:
                state["document_context"] = None
                logger.info("Document gathering skipped because no authenticated owner was supplied")
                return state
            results = await self.document_service.search_documents(
                query=state["question"],
                user_id=state["user_id"],
                limit=5,
            )
            if not results:
                state["document_context"] = None
                return state
            excerpts = []
            for result in results:
                excerpts.append(
                    f"[{result['filename']} · chunk {result['chunk_index']} · "
                    f"score {result['score']:.3f}]\n{result['text']}"
                )
            state["document_context"] = "\n\n".join(excerpts)
            logger.info("Retrieved %d knowledge-base chunks", len(results))
        except Exception as e:
            logger.warning("Failed to gather documents: %s", e)
            state["document_context"] = None
        return state

    # ─── Analysis node ────────────────────────────────────────────────────────

    async def _analyze_and_conclude(
        self, state: InvestigationState
    ) -> InvestigationState:
        try:
            context_parts = [
                "You are an AI Site Reliability Engineer investigating an infrastructure issue.",
                "",
                f"QUESTION: {state['question']}",
                "",
            ]

            data_sources = []

            if state.get("incident_context"):
                context_parts.extend(["INCIDENT CONTEXT:", state["incident_context"], ""])
                data_sources.append("Incident Management System")

            if state.get("metrics_data"):
                context_parts.extend(["METRICS DATA:", state["metrics_data"], ""])
                data_sources.append("Prometheus Metrics")

            if state.get("document_context"):
                context_parts.extend(["DOCUMENTATION:", state["document_context"], ""])
                data_sources.append("Knowledge Base Documents")

            if state.get("conversation_context"):
                context_parts.extend(["PREVIOUS CONVERSATION:", state["conversation_context"], ""])
                data_sources.append("Conversation History")

            if not data_sources:
                context_parts.append(
                    "WARNING: No data sources were available for this investigation."
                )
                context_parts.append(
                    "The following analysis is based solely on general knowledge."
                )
                data_sources.append("General Knowledge Only (No Live Data)")

            context_parts.extend([
                "",
                "INSTRUCTIONS:",
                "1. Analyze the available evidence",
                "2. Formulate a hypothesis about the root cause (clearly label as hypothesis)",
                "3. List specific observed evidence that supports your hypothesis",
                "4. Provide confidence level (low/medium/high)",
                "5. Recommend concrete next steps",
                "6. NEVER fabricate metrics or logs - only use provided data",
                "7. Distinguish between observed evidence and AI-generated hypotheses",
            ])

            system_prompt = "\n".join(context_parts)

            # Use the central AI router — provider-first fallback
            routing_result: RoutingResult = await self._router.generate_text(
                prompt=state["question"],
                system_prompt=system_prompt,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )

            # Build routing metadata for the response
            routing_metadata = {
                "provider": (
                    routing_result.successful_provider.value
                    if routing_result.successful_provider
                    else None
                ),
                "model": routing_result.successful_model,
                "quality_tier": (
                    routing_result.successful_quality_tier.value
                    if routing_result.successful_quality_tier
                    else None
                ),
                "total_latency_seconds": routing_result.total_latency_seconds,
                "input_tokens": routing_result.input_tokens,
                "output_tokens": routing_result.output_tokens,
                "attempts": [
                    {
                        "provider": a.provider.value,
                        "model": a.model_id,
                        "succeeded": a.succeeded,
                        "failure_category": (
                            a.failure_category.value if a.failure_category else None
                        ),
                        "latency_seconds": a.latency_seconds,
                    }
                    for a in routing_result.attempts
                ],
            }

            state["routing_metadata"] = routing_metadata

            if routing_result.unavailable or not routing_result.content:
                error_msg = (
                    routing_result.error
                    or "All AI providers are currently unavailable. No paid models were used."
                )
                logger.warning("Investigation analysis unavailable: %s", error_msg)
                state["error"] = error_msg
                state["findings"] = None
                state["recommendations"] = None
            else:
                findings_text = routing_result.content
                state["findings"] = findings_text
                state["recommendations"] = findings_text
                state["messages"] = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=state["question"]),
                    AIMessage(content=findings_text),
                ]
                logger.info(
                    "Generated investigation findings via %s/%s",
                    routing_result.successful_provider,
                    routing_result.successful_model,
                )

        except Exception as e:
            logger.exception("Analysis failed: %s", e)
            state["error"] = f"Analysis failed: {str(e)}"
            state["findings"] = None
            state["recommendations"] = None

        return state

    # ─── Public investigation entry point ─────────────────────────────────────

    async def investigate(
        self,
        question: str,
        user_id: UUID | None = None,
        conversation_context: str | None = None,
    ) -> dict:
        """Run investigation workflow.

        Returns:
            Dictionary with findings, evidence, routing metadata and timestamp.
        """
        try:
            initial_state: InvestigationState = {
                "messages": [],
                "question": question,
                "incident_context": None,
                "metrics_data": None,
                "document_context": None,
                "findings": None,
                "recommendations": None,
                "error": None,
                "routing_metadata": None,
                "user_id": user_id,
                "conversation_context": conversation_context,
            }

            final_state = await self.graph.ainvoke(initial_state)

            data_sources = []
            if final_state.get("incident_context"):
                data_sources.append("Incident Management")
            if final_state.get("metrics_data"):
                data_sources.append("Prometheus Metrics")
            if final_state.get("document_context"):
                data_sources.append("Knowledge Base")
            if not data_sources:
                data_sources.append("General Knowledge Only")

            # If findings are None but we have an error, the error is more informative
            findings_value = final_state.get("findings")
            error_value = final_state.get("error")
            
            # If no findings and no error, provide helpful message
            if not findings_value and not error_value:
                findings_value = "Investigation completed but no AI response was generated. Check that cloud AI provider keys are configured."
            
            return {
                "question": question,
                "findings": findings_value,
                "evidence": {
                    "incident_context": final_state.get("incident_context"),
                    "metrics_data": final_state.get("metrics_data"),
                    "document_context": final_state.get("document_context"),
                },
                "data_sources": data_sources,
                "error": error_value,
                "routing_metadata": final_state.get("routing_metadata"),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.exception("Investigation failed: %s", e)
            return {
                "question": question,
                "findings": None,
                "evidence": {},
                "data_sources": [],
                "error": str(e),
                "routing_metadata": None,
                "timestamp": datetime.now(UTC).isoformat(),
            }


async def get_cloud_investigator(
    settings: Settings,
    document_service: DocumentService | None = None,
    incident_service: IncidentService | None = None,
    prometheus_client: PrometheusClient | None = None,
) -> CloudAIInvestigator:
    """Async factory: creates a CloudAIInvestigator backed by the singleton router."""
    router = await get_ai_router(settings)
    return CloudAIInvestigator(
        settings=settings,
        router=router,
        document_service=document_service,
        incident_service=incident_service,
        prometheus_client=prometheus_client,
    )
