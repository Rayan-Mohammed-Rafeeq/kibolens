"""AI investigator workflow using LangGraph for incident investigation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.monitoring.prometheus import PrometheusClient
from app.services.documents import DocumentService
from app.services.incidents import IncidentService

UTC = tz.utc

logger = logging.getLogger(__name__)


# State for the investigation workflow
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
    routing_metadata: dict | None


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


class AIInvestigator:
    """LangGraph-based AI investigator for infrastructure incidents.
    
    Orchestrates gathering context from multiple sources and generating
    evidence-based investigation findings.
    """

    def __init__(
        self,
        settings: Settings,
        document_service: DocumentService | None = None,
        incident_service: IncidentService | None = None,
        prometheus_client: PrometheusClient | None = None,
    ):
        """Initialize AI investigator.
        
        Args:
            settings: Application settings
            document_service: Document service for RAG retrieval (optional)
            incident_service: Incident service for context (optional)
            prometheus_client: Prometheus client for metrics (optional)
        """
        self.settings = settings
        self.document_service = document_service
        self.incident_service = incident_service
        self.prometheus_client = prometheus_client

        # Initialize LLM only if legacy Ollama is explicitly selected
        if settings.llm_provider.lower() == "ollama":
            self.llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=settings.llm_temperature,
                num_ctx=2048,  # Context window
                num_thread=2,  # Conservative threading for low resources
            )
        else:
            self.llm = None

        # Build workflow graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph investigation workflow.
        
        Returns:
            Compiled state graph
        """
        workflow = StateGraph(InvestigationState)

        # Add nodes
        workflow.add_node("gather_incident_context", self._gather_incident_context)
        workflow.add_node("gather_metrics", self._gather_metrics)
        workflow.add_node("gather_documents", self._gather_documents)
        workflow.add_node("analyze_and_conclude", self._analyze_and_conclude)

        # Define edges
        workflow.set_entry_point("gather_incident_context")
        workflow.add_edge("gather_incident_context", "gather_metrics")
        workflow.add_edge("gather_metrics", "gather_documents")
        workflow.add_edge("gather_documents", "analyze_and_conclude")
        workflow.add_edge("analyze_and_conclude", END)

        return workflow.compile()

    async def _gather_incident_context(
        self, state: InvestigationState
    ) -> InvestigationState:
        """Gather context from incident management system.
        
        Args:
            state: Current investigation state
            
        Returns:
            Updated state with incident context
        """
        if not self.incident_service:
            state["incident_context"] = None
            return state

        try:
            # Get recent incidents (last 24 hours)
            # This is a simplified implementation
            # In production, would need database session and more sophisticated filtering
            
            context_parts = ["Recent incident context: "]
            context_parts.append("Incident data available from incident management system.")
            
            state["incident_context"] = "\n".join(context_parts)
            logger.info("Gathered incident context")

        except Exception as e:
            logger.warning(f"Failed to gather incident context: {e}")
            state["incident_context"] = None

        return state

    async def _gather_metrics(self, state: InvestigationState) -> InvestigationState:
        """Gather relevant metrics from Prometheus.
        
        Args:
            state: Current investigation state
            
        Returns:
            Updated state with metrics data
        """
        if not self.prometheus_client:
            state["metrics_data"] = None
            return state

        try:
            # Query relevant metrics based on the question
            question_lower = state["question"].lower()
            
            metrics_parts = ["Prometheus metrics: "]
            queries_executed = []

            # CPU metrics
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
                    logger.warning(f"CPU query failed: {e}")

            # Memory metrics
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
                    logger.warning(f"Memory query failed: {e}")

            # Disk metrics
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
                    logger.warning(f"Disk query failed: {e}")

            # Network metrics
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
                    logger.warning(f"Network query failed: {e}")

            if queries_executed:
                state["metrics_data"] = "\n".join(metrics_parts)
                logger.info(f"Gathered metrics: {', '.join(queries_executed)}")
            else:
                state["metrics_data"] = "No specific metrics queries matched the question."

        except Exception as e:
            logger.warning(f"Failed to gather metrics: {e}")
            state["metrics_data"] = None

        return state

    async def _gather_documents(self, state: InvestigationState) -> InvestigationState:
        """Gather relevant documentation using RAG.
        
        Args:
            state: Current investigation state
            
        Returns:
            Updated state with document context
        """
        if not self.document_service:
            state["document_context"] = None
            return state

        try:
            # This requires user_id which isn't in state
            # For now, we'll skip document retrieval or implement a shared documents collection
            # In production, implement proper user context or shared knowledge base
            
            state["document_context"] = "Document search not available in this context."
            logger.info("Document gathering skipped (requires user context)")

        except Exception as e:
            logger.warning(f"Failed to gather documents: {e}")
            state["document_context"] = None

        return state

    async def _analyze_and_conclude(
        self, state: InvestigationState
    ) -> InvestigationState:
        """Analyze gathered evidence and generate findings.
        
        Args:
            state: Current investigation state
            
        Returns:
            Updated state with findings and recommendations
        """
        try:
            # Build context for the LLM
            context_parts = [
                "You are an AI Site Reliability Engineer investigating an infrastructure issue.",
                "",
                f"QUESTION: {state['question']}",
                "",
            ]

            data_sources = []

            if state.get("incident_context"):
                context_parts.append("INCIDENT CONTEXT:")
                context_parts.append(state["incident_context"])
                context_parts.append("")
                data_sources.append("Incident Management System")

            if state.get("metrics_data"):
                context_parts.append("METRICS DATA:")
                context_parts.append(state["metrics_data"])
                context_parts.append("")
                data_sources.append("Prometheus Metrics")

            if state.get("document_context"):
                context_parts.append("DOCUMENTATION:")
                context_parts.append(state["document_context"])
                context_parts.append("")
                data_sources.append("Knowledge Base Documents")

            if not data_sources:
                context_parts.append("WARNING: No data sources were available for this investigation.")
                context_parts.append("The following analysis is based solely on general knowledge.")
                data_sources.append("General Knowledge Only (No Live Data)")

            context_parts.append("")
            context_parts.append("INSTRUCTIONS:")
            context_parts.append("1. Analyze the available evidence")
            context_parts.append("2. Formulate a hypothesis about the root cause (clearly label as hypothesis)")
            context_parts.append("3. List specific observed evidence that supports your hypothesis")
            context_parts.append("4. Provide confidence level (low/medium/high)")
            context_parts.append("5. Recommend concrete next steps")
            context_parts.append("6. NEVER fabricate metrics or logs - only use provided data")
            context_parts.append("7. Distinguish between observed evidence and AI-generated hypotheses")

            system_message = "\n".join(context_parts)

            # Generate analysis
            if self.llm is not None:
                messages = [
                    SystemMessage(content=system_message),
                    HumanMessage(content=state["question"]),
                ]
                response = await self.llm.ainvoke(messages)
                findings_text = response.content if hasattr(response, "content") else str(response)
                state["findings"] = findings_text
                state["recommendations"] = findings_text
                state["messages"] = messages + [AIMessage(content=findings_text)]
                state["routing_metadata"] = {"provider": "ollama", "model": self.settings.ollama_model}
            else:
                from app.ai.router.core import get_ai_router

                router = await get_ai_router(self.settings)
                routing_result = await router.generate_text(
                    prompt=state["question"],
                    system_prompt=system_message,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )

                state["routing_metadata"] = {
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

                if routing_result.unavailable or not routing_result.content:
                    error_msg = routing_result.error or "All AI providers are currently unavailable."
                    state["error"] = error_msg
                    state["findings"] = None
                    state["recommendations"] = None
                else:
                    findings_text = routing_result.content
                    state["findings"] = findings_text
                    state["recommendations"] = findings_text
                    messages = [
                        SystemMessage(content=system_message),
                        HumanMessage(content=state["question"]),
                        AIMessage(content=findings_text),
                    ]
                    state["messages"] = messages

            logger.info("Generated investigation findings")

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            state["error"] = f"Analysis failed: {str(e)}"
            state["findings"] = None
            state["recommendations"] = None

        return state

    async def investigate(
        self,
        question: str,
        user_id: UUID | None = None,
    ) -> dict:
        """Run investigation workflow for a question.
        
        Args:
            question: Investigation question
            user_id: Optional user ID for personalized document retrieval
            
        Returns:
            Investigation results with findings and recommendations
        """
        try:
            # Initialize state
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
            }

            # Run workflow
            final_state = await self.graph.ainvoke(initial_state)

            # Build response
            data_sources = []
            if final_state.get("incident_context"):
                data_sources.append("Incident Management")
            if final_state.get("metrics_data"):
                data_sources.append("Prometheus Metrics")
            if final_state.get("document_context"):
                data_sources.append("Knowledge Base")

            if not data_sources:
                data_sources.append("General Knowledge Only")

            return {
                "question": question,
                "findings": final_state.get("findings") or "No findings generated",
                "evidence": {
                    "incident_context": final_state.get("incident_context"),
                    "metrics_data": final_state.get("metrics_data"),
                    "document_context": final_state.get("document_context"),
                },
                "data_sources": data_sources,
                "error": final_state.get("error"),
                "routing_metadata": final_state.get("routing_metadata"),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.exception(f"Investigation failed: {e}")
            return {
                "question": question,
                "findings": None,
                "evidence": {},
                "data_sources": [],
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }


def get_investigator(
    settings: Settings,
    document_service: DocumentService | None = None,
    incident_service: IncidentService | None = None,
    prometheus_client: PrometheusClient | None = None,
) -> AIInvestigator:
    """Factory function to create AI investigator.
    
    Args:
        settings: Application settings
        document_service: Optional document service
        incident_service: Optional incident service
        prometheus_client: Optional Prometheus client
        
    Returns:
        AIInvestigator instance
    """
    return AIInvestigator(
        settings,
        document_service=document_service,
        incident_service=incident_service,
        prometheus_client=prometheus_client,
    )
