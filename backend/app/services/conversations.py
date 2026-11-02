import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


def get_conversation(
    database: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    return database.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == owner_id
        )
    )


def create_conversation(database: Session, owner_id: uuid.UUID, title: str) -> Conversation:
    conversation = Conversation(owner_id=owner_id, title=title.strip())
    database.add(conversation)
    database.commit()
    database.refresh(conversation)
    return conversation


def list_conversations(
    database: Session, owner_id: uuid.UUID, offset: int, limit: int
) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.owner_id == owner_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(database.scalars(statement))


def rename_conversation(database: Session, conversation: Conversation, title: str) -> Conversation:
    conversation.title = title.strip()
    database.commit()
    database.refresh(conversation)
    return conversation


def delete_conversation(database: Session, conversation: Conversation) -> None:
    database.delete(conversation)
    database.commit()


def list_messages(
    database: Session, conversation_id: uuid.UUID, offset: int, limit: int
) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(database.scalars(statement))


def add_user_message(database: Session, conversation: Conversation, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role="user", content=content.strip())
    database.add(message)
    database.commit()
    database.refresh(message)
    return message


def add_assistant_message(database: Session, conversation: Conversation, content: str) -> Message:
    """Add an assistant message to a conversation."""
    message = Message(conversation_id=conversation.id, role="assistant", content=content.strip())
    database.add(message)
    database.commit()
    database.refresh(message)
    return message
