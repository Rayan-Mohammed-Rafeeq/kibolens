import logging
import uuid

from app.ai.cloud_embeddings import CloudEmbeddingService
from app.ai.investigator import get_investigator
from app.api.dependencies import CsrfSession, CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.monitoring.prometheus import PrometheusClient
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.schemas.documents import InvestigationResponse
from app.services import conversations
from app.services.documents import DocumentService
from app.services.qdrant import get_qdrant_service
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def conversation_response(conversation) -> ConversationResponse:
    return ConversationResponse(
        id=str(conversation.id),
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        incident_id=str(conversation.incident_id) if conversation.incident_id else None,
    )


def message_response(message) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


def owned_conversation(database: DatabaseSession, user: CurrentUser, conversation_id: uuid.UUID):
    conversation = conversations.get_conversation(database, user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate, database: DatabaseSession, user: CurrentUser, _: CsrfSession
) -> ConversationResponse:
    return conversation_response(
        conversations.create_conversation(database, user.id, payload.title)
    )


@router.get("", response_model=ConversationListResponse)
def get_conversations(
    database: DatabaseSession,
    user: CurrentUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> ConversationListResponse:
    items = conversations.list_conversations(database, user.id, offset, limit + 1)
    has_next = len(items) > limit
    return ConversationListResponse(
        items=[conversation_response(item) for item in items[:limit]],
        next_offset=offset + limit if has_next else None,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: uuid.UUID, database: DatabaseSession, user: CurrentUser
) -> ConversationResponse:
    return conversation_response(owned_conversation(database, user, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    database: DatabaseSession,
    user: CurrentUser,
    _: CsrfSession,
) -> ConversationResponse:
    conversation = owned_conversation(database, user, conversation_id)
    return conversation_response(
        conversations.rename_conversation(database, conversation, payload.title)
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: uuid.UUID,
    database: DatabaseSession,
    user: CurrentUser,
    _: CsrfSession,
) -> Response:
    conversation = owned_conversation(database, user, conversation_id)
    conversations.delete_conversation(database, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def get_messages(
    conversation_id: uuid.UUID,
    database: DatabaseSession,
    user: CurrentUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> MessageListResponse:
    conversation = owned_conversation(database, user, conversation_id)
    items = conversations.list_messages(database, conversation.id, offset, limit + 1)
    has_next = len(items) > limit
    return MessageListResponse(
        items=[message_response(item) for item in items[:limit]],
        next_offset=offset + limit if has_next else None,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    database: DatabaseSession,
    user: CurrentUser,
    _: CsrfSession,
) -> MessageResponse:
    conversation = owned_conversation(database, user, conversation_id)
    return message_response(conversations.add_user_message(database, conversation, payload.content))


@router.post(
    "/{conversation_id}/investigate",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
)
async def investigate_and_respond(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    database: DatabaseSession,
    user: CurrentUser,
    _: CsrfSession,
    settings = Depends(get_settings),
) -> InvestigationResponse:
    """Create user message, run AI investigation, and add assistant response.
    
    This endpoint:
    1. Creates a user message with the question
    2. Runs AI investigation using cloud router
    3. Retrieves Prometheus metrics and Qdrant documents
    4. Creates an assistant message with the findings
    5. Returns the investigation response with routing metadata
    """
    conversation = owned_conversation(database, user, conversation_id)
    previous_messages = conversations.list_messages(database, conversation.id, 0, 12)
    conversation_context = "\n".join(
        f"{message.role.upper()}: {message.content}" for message in previous_messages
    )

    # Add user message
    conversations.add_user_message(database, conversation, payload.content)
    
    try:
        # Initialize services
        qdrant_service = get_qdrant_service(settings)
        embedding_service = CloudEmbeddingService(settings)
        document_service = DocumentService(qdrant_service, embedding_service)
        
        prometheus_client = PrometheusClient(
            base_url=settings.prometheus_url,
            timeout_seconds=settings.prometheus_timeout_seconds,
        )
        
        # Create investigator with cloud router
        investigator = await get_investigator(
            settings=settings,
            document_service=document_service,
            incident_service=None,
            prometheus_client=prometheus_client,
        )
        
        # Run investigation
        result = await investigator.investigate(
            question=payload.content,
            user_id=user.id,
            conversation_context=conversation_context,
        )
        
        # Determine what to persist as assistant message
        # Priority: findings > error > default message
        findings = result.get("findings")
        error = result.get("error")
        
        if findings:
            # We have actual findings from the AI
            assistant_content = findings
        elif error:
            # AI router failed, show the actual error
            assistant_content = f"Investigation could not be completed: {error}"
        else:
            # Shouldn't happen, but provide fallback
            assistant_content = "Investigation completed but no response was generated. Please check that AI provider keys are configured."
        
        # Add assistant message with the determined content
        conversations.add_assistant_message(database, conversation, assistant_content)
        
        return InvestigationResponse(**result)
        
    except Exception as e:
        logger.exception("Investigation failed: %s", e)
        error_response = f"Investigation failed: {str(e)}"
        conversations.add_assistant_message(database, conversation, error_response)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response,
        )
