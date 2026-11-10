import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import FeedbackValue, MessageResponse, SourceResponse
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    FeedbackRequest,
    FeedbackResponse,
)


router = APIRouter(tags=["conversations"])
@router.get("/conversations", response_model=list[ConversationResponse], response_model_by_alias=True)
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationResponse]:
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [serialize_conversation(item) for item in conversations]


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conversation = Conversation(user_id=user.id, title=payload.title.strip())
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return serialize_conversation(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse, response_model_by_alias=True)
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    return serialize_conversation(require_conversation(db, conversation_id, user.id))


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse, response_model_by_alias=True)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conversation = require_conversation(db, conversation_id, user.id)
    conversation.title = payload.title.strip()
    db.commit()
    db.refresh(conversation)
    return serialize_conversation(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    conversation = require_conversation(db, conversation_id, user.id)
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    message_id: uuid.UUID,
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    message = db.scalar(
        select(Message)
        .join(Conversation)
        .where(Message.id == message_id, Conversation.user_id == user.id)
    )
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Message assistant introuvable.")
    message.feedback_type = payload.type
    message.feedback_reason = payload.reason
    message.feedback_comment = payload.comment
    db.commit()
    return FeedbackResponse(**payload.model_dump())


def require_conversation(db: Session, conversation_id: uuid.UUID, user_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    return conversation


def serialize_message(message: Message) -> MessageResponse:
    feedback = None
    if message.feedback_type:
        feedback = FeedbackValue(
            type=message.feedback_type,
            reason=message.feedback_reason,
            comment=message.feedback_comment,
        )
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        confidenceScore=message.confidence_score,
        sources=[SourceResponse.model_validate(source) for source in (message.sources or [])],
        feedback=feedback,
        createdAt=message.created_at,
    )


def serialize_conversation(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        updatedAt=conversation.updated_at,
        messages=[serialize_message(message) for message in conversation.messages],
    )
