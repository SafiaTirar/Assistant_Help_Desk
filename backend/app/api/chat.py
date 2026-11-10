import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.conversations import require_conversation
from app.api.dependencies import get_current_user
from app.models.conversation import Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, MessageResponse, SourceResponse
from app.services.rag_service import FALLBACK_MESSAGE, RagResult, get_rag_service
from app.services.conversation_memory_service import (
    contextualize_question,
    get_conversation_history,
    needs_contextualization,
)
from app.services.rag_observability import record_trace_event, trace_question
from app.services.rag_deadline import QuestionTimeoutError, question_deadline

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=["chat"])
RAG_QUESTION_TIMEOUT_SECONDS = float(os.getenv("RAG_QUESTION_TIMEOUT_SECONDS", "180"))


@router.post("/chat", response_model=ChatResponse, response_model_by_alias=True)
@limiter.limit("10/minute")
def chat(
    request: Request,
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    question = payload.question.strip()
    received_at = datetime.now(timezone.utc)
    if not question:
        raise HTTPException(status_code=422, detail="La question ne peut pas être vide.")

    if payload.conversation_id is None:
        raise HTTPException(status_code=422, detail="Une conversation est requise.")
    try:
        conversation_id = uuid.UUID(payload.conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Identifiant de conversation invalide.") from exc
    conversation = require_conversation(db, conversation_id, user.id)
    history = get_conversation_history(db, conversation)
    rag_service = get_rag_service()
    started_at = time.perf_counter()
    with trace_question(f"chat:{conversation.id}", question):
        try:
            with question_deadline(RAG_QUESTION_TIMEOUT_SECONDS):
                if needs_contextualization(question) and not history:
                    result = RagResult(FALLBACK_MESSAGE, "question_ambigue", 0.0)
                else:
                    contextualized_question = contextualize_question(
                        question,
                        history,
                        rag_service.llm,
                    )
                    record_trace_event(
                        "memory_end", contextualized=contextualized_question != question
                    )
                    result = rag_service.answer_question(contextualized_question)
        except QuestionTimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="La deadline globale de la question a été dépassée.",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Le moteur documentaire est momentanément indisponible.",
            ) from exc

    try:
        latency_ms = round((time.perf_counter() - started_at) * 1_000)
        user_message, assistant_message = _save_messages(
            db,
            conversation,
            question,
            result,
            latency_ms,
            received_at,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="La réponse a été générée mais n'a pas pu être enregistrée.",
        ) from exc

    sources = [
        SourceResponse(
            documentTitle=source.document_title,
            fileName=source.file_name,
            pages=source.pages,
            section=source.section,
            excerpt=source.excerpt,
            chunkId=source.chunk_id,
        )
        for source in result.sources
    ]
    return ChatResponse(
        userMessage=MessageResponse(
            id=user_message.id,
            role="user",
            content=question,
            createdAt=user_message.created_at,
        ),
        response=MessageResponse(
            id=assistant_message.id,
            role="assistant",
            content=result.answer,
            status=result.status,
            confidenceScore=result.confidence_score,
            sources=sources,
            createdAt=assistant_message.created_at,
        ),
    )


def _save_messages(
    db: Session,
    conversation,
    question: str,
    result: RagResult,
    latency_ms: int,
    user_created_at: datetime,
) -> tuple[Message, Message]:
    assistant_created_at = datetime.now(timezone.utc)
    source_payload = [
        {
            "documentTitle": source.document_title,
            "fileName": source.file_name,
            "pages": source.pages,
            "section": source.section,
            "excerpt": source.excerpt,
            "chunkId": source.chunk_id,
        }
        for source in result.sources
    ]
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=question,
        sources=[],
        created_at=user_created_at,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.answer,
        status=result.status,
        confidence_score=result.confidence_score,
        latency_ms=latency_ms,
        sources=source_payload,
        created_at=assistant_created_at,
    )

    if not conversation.messages:
        conversation.title = " ".join(question.split()[:7])
    conversation.updated_at = assistant_created_at
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return user_message, assistant_message
