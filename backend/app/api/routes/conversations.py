import uuid

from app.api.dependencies import CsrfSession, CurrentUser, DatabaseSession
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.services import conversations
from fastapi import APIRouter, HTTPException, Query, Response, status

router = APIRouter(prefix="/conversations", tags=["conversations"])


def conversation_response(conversation) -> ConversationResponse:
    return ConversationResponse(
        id=str(conversation.id),
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
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
