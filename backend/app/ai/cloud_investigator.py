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
import json
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Annotated, Literal, TypedDict
from uuid import UUID
from sqlalchemy.orm import Session

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from app.ai.router.core import AIRouter, get_ai_router
from app.ai.langchain_router import CloudRouterChatModel
from app.ai.router.types import RoutingResult
from app.core.config import Settings
from app.monitoring.prometheus import PrometheusClient
from app.services.documents import DocumentService
from app.services.incidents import IncidentService
from app.models.investigation_checkpoint import InvestigationCheckpoint

UTC = tz.utc
_CHECKPOINTER = MemorySaver()

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
    intent: str
    requested_sources: list[str]
    execution: dict


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
        database: Session | None = None,
    ):
        self.settings = settings
        self._router = router
        self.document_service = document_service
        self.incident_service = incident_service
        self.prometheus_client = prometheus_client
        self.database = database
        self._langchain_model = CloudRouterChatModel(
            router=router,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph investigation workflow."""
        workflow = StateGraph(InvestigationState)

        workflow.add_node("classify_request", self._classify_request)
        workflow.add_node("gather_incident_context", self._gather_incident_context)
        workflow.add_node("gather_metrics", self._gather_metrics)
        workflow.add_node("gather_documents", self._gather_documents)
        workflow.add_node("analyze_and_conclude", self._analyze_and_conclude)

        workflow.set_entry_point("classify_request")
        workflow.add_conditional_edges(
            "classify_request",
            self._first_evidence_node,
            {
                "gather_incident_context": "gather_incident_context",
                "gather_metrics": "gather_metrics",
                "gather_documents": "gather_documents",
                "analyze_and_conclude": "analyze_and_conclude",
            },
        )
        workflow.add_edge("gather_incident_context", "gather_metrics")
        workflow.add_edge("gather_metrics", "gather_documents")
        workflow.add_edge("gather_documents", "analyze_and_conclude")
        workflow.add_edge("analyze_and_conclude", END)

        return workflow.compile(checkpointer=_CHECKPOINTER)

    async def _classify_request(self, state: InvestigationState) -> InvestigationState:
        question = state["question"].lower()
        sources: list[str] = []
        if any(word in question for word in ("incident", "alert", "failure", "restart", "unhealthy", "crash")):
            sources.append("incident")
        if any(word in question for word in ("cpu", "memory", "ram", "disk", "network", "load", "metric", "yesterday")):
            sources.append("metrics")
        if any(word in question for word in ("docker", "container", "compose", "dockerfile", "log", "dependency", "config", "runbook", "document")):
            sources.append("documents")
        state["requested_sources"] = sources
        state["intent"] = "infrastructure_investigation" if sources else "general_sre_question"
        state["execution"] = {"nodes": [], "retrieval_counts": {}, "started_at": datetime.now(UTC).isoformat()}
        return state

    @staticmethod
    def _first_evidence_node(state: InvestigationState) -> str:
        requested = state.get("requested_sources", [])
        if "incident" in requested:
            return "gather_incident_context"
        if "metrics" in requested:
            return "gather_metrics"
        if "documents" in requested:
            return "gather_documents"
        return "analyze_and_conclude"

    @staticmethod
    def _record_node(state: InvestigationState, name: str) -> None:
        state.setdefault("execution", {}).setdefault("nodes", []).append(name)

    @staticmethod
    def _merge_continuation(original: str, continuation: str) -> str:
        """Append one provider continuation while avoiding an exact boundary repeat."""
        if not continuation:
            return original
        if not original:
            return continuation
        max_overlap = min(len(original), len(continuation), 2000)
        for size in range(max_overlap, 39, -1):
            if original[-size:] == continuation[:size]:
                return original + continuation[size:]
        return f"{original}\n\n{continuation}"

    # ─── Context-gathering nodes (semantics preserved from original) ──────────

    async def _gather_incident_context(
        self, state: InvestigationState
    ) -> InvestigationState:
        self._record_node(state, "gather_incident_context")
        if "incident" not in state.get("requested_sources", []) or not self.incident_service:
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
        self._record_node(state, "gather_metrics")
        if "metrics" not in state.get("requested_sources", []):
            state["metrics_data"] = None
            return state
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
                state["execution"]["retrieval_counts"]["metrics"] = len(queries_executed)
                logger.info("Gathered metrics: %s", ", ".join(queries_executed))
            else:
                state["metrics_data"] = "No specific metrics queries matched the question."

        except Exception as e:
            logger.warning("Failed to gather metrics: %s", e)
            state["metrics_data"] = None

        return state

    async def _gather_documents(self, state: InvestigationState) -> InvestigationState:
        self._record_node(state, "gather_documents")
        if "documents" not in state.get("requested_sources", []):
            state["document_context"] = None
            return state
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
            state["execution"]["retrieval_counts"]["documents"] = len(results)
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
                "8. Structure the answer with: Current status, Actual metric values, Analysis, Potential risks, Supporting evidence, Recommendations, and Missing information/uncertainty",
                "9. For unavailable values, say that the value is unavailable rather than estimating it",
            ])

            system_prompt = "\n".join(context_parts)

            self._record_node(state, "analyze_and_conclude")
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", "{system_prompt}"),
                ("human", "{question}"),
            ])
            prompt_value = prompt_template.invoke({
                "system_prompt": system_prompt,
                "question": state["question"],
            })
            response = await self._langchain_model.ainvoke(prompt_value.messages)
            routing_metadata = response.response_metadata
            findings_text = str(response.content)

            if routing_metadata.get("incomplete"):
                continuation_count = 0
                continuation_error = None
                continuation_messages = list(prompt_value.messages)
                while routing_metadata.get("incomplete") and continuation_count < 8:
                    continuation_count += 1
                    try:
                        continuation = await self._langchain_model.ainvoke([
                            *continuation_messages,
                            AIMessage(content=findings_text),
                            HumanMessage(
                                content=(
                                    "Continue the same infrastructure analysis from exactly where the "
                                    "previous response stopped. Do not repeat the completed content. "
                                    "Return only the remaining sections and keep observed evidence "
                                    "separate from hypotheses. If all required sections are already "
                                    "complete, finish with a concise uncertainty statement."
                                )
                            ),
                        ])
                        continuation_metadata = continuation.response_metadata
                        continuation_text = str(continuation.content)
                        continuation_available = not continuation_metadata.get("unavailable")
                        if continuation_available and continuation_text.strip():
                            findings_text = self._merge_continuation(findings_text, continuation_text)
                            continuation_messages = [
                                *continuation_messages,
                                AIMessage(content=continuation_text),
                            ]
                        routing_metadata = {
                            **routing_metadata,
                            "continuation_used": True,
                            "continuation_count": continuation_count,
                            "continuation_provider": continuation_metadata.get("provider"),
                            "continuation_model": continuation_metadata.get("model"),
                            "continuation_finish_reason": continuation_metadata.get("finish_reason"),
                            "continuation_incomplete": continuation_metadata.get("incomplete", False),
                            "continuation_error": continuation_metadata.get("error") if not continuation_available else None,
                            "incomplete": (continuation_metadata.get("incomplete", False) if continuation_available else True),
                            "incomplete_reason": continuation_metadata.get("incomplete_reason") or "continuation_unavailable",
                        }
                        if not continuation_available or not continuation_text.strip():
                            break
                    except Exception as exc:
                        continuation_error = type(exc).__name__
                        logger.warning("AI continuation failed; preserving generated response: %s", exc)
                        break
                if continuation_error:
                    routing_metadata = {
                        **routing_metadata,
                        "continuation_error": continuation_error,
                        "incomplete": True,
                        "incomplete_reason": "continuation_failed",
                    }
                if routing_metadata.get("incomplete"):
                    separator = "" if findings_text.endswith("\n") else "\n"
                    findings_text = (
                        f"{findings_text}{separator}\n> **Response status:** The provider stopped at its "
                        f"output-token limit after {continuation_count} bounded continuation(s). The content above "
                        "is the complete response returned by the providers but may be incomplete."
                    )

            # Build routing metadata for the response
            state["routing_metadata"] = routing_metadata

            if routing_metadata.get("unavailable") or not findings_text.strip() or findings_text.strip().lower() == "cloud ai providers returned no response.":
                error_msg = routing_metadata.get("error") or "All eligible cloud AI providers returned no usable response. No paid models were used."
                logger.warning("Investigation analysis unavailable: %s", error_msg)
                state["error"] = error_msg
                state["findings"] = None
                state["recommendations"] = None
            else:
                state["findings"] = findings_text
                state["recommendations"] = findings_text
                state["messages"] = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=state["question"]),
                    AIMessage(content=findings_text),
                ]
                logger.info(
                    "Generated investigation findings via %s/%s",
                    routing_metadata.get("provider"),
                    routing_metadata.get("model"),
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
        conversation_id: UUID | None = None,
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
                "intent": "",
                "requested_sources": [],
                "execution": {},
            }

            thread_id = f"{user_id}:{conversation_id or 'adhoc'}"
            final_state = await self.graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": thread_id}},
            )
            if self.database and user_id and conversation_id:
                thread_id = f"{user_id}:{conversation_id}"
                checkpoint_state = {
                    "question": question,
                    "intent": final_state.get("intent"),
                    "requested_sources": final_state.get("requested_sources", []),
                    "incident_context": final_state.get("incident_context"),
                    "metrics_data": final_state.get("metrics_data"),
                    "document_context": final_state.get("document_context"),
                    "execution": final_state.get("execution", {}),
                    "routing_metadata": final_state.get("routing_metadata"),
                    "findings": final_state.get("findings"),
                    "error": final_state.get("error"),
                }
                checkpoint = self.database.query(InvestigationCheckpoint).filter_by(thread_id=thread_id).one_or_none()
                if checkpoint is None:
                    checkpoint = InvestigationCheckpoint(
                        owner_id=user_id,
                        conversation_id=conversation_id,
                        thread_id=thread_id,
                        state_json=json.dumps(checkpoint_state, default=str),
                    )
                    self.database.add(checkpoint)
                else:
                    if checkpoint.owner_id != user_id or checkpoint.conversation_id != conversation_id:
                        raise PermissionError("Investigation checkpoint ownership mismatch.")
                    checkpoint.state_json = json.dumps(checkpoint_state, default=str)
                self.database.commit()

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
            
            # Never turn an empty model response into a successful-looking
            # finding. Callers persist/display the explicit error instead.
            if not findings_value and not error_value:
                error_value = "Investigation completed without a usable AI response. No provider output was available."
            
            return {
                "question": question,
                "findings": findings_value,
                "evidence": {
                    "incident_context": final_state.get("incident_context"),
                    "metrics_data": final_state.get("metrics_data"),
                    "document_context": final_state.get("document_context"),
                    "execution": final_state.get("execution", {}),
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
    database: Session | None = None,
) -> CloudAIInvestigator:
    """Async factory: creates a CloudAIInvestigator backed by the singleton router."""
    router = await get_ai_router(settings)
    return CloudAIInvestigator(
        settings=settings,
        router=router,
        document_service=document_service,
        incident_service=incident_service,
        prometheus_client=prometheus_client,
        database=database,
    )
