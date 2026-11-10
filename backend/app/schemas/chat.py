from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(min_length=1, max_length=2_000)
    conversation_id: str | None = Field(default=None, alias="conversationId")


class SourceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_title: str | None = Field(default=None, alias="documentTitle")
    file_name: str | None = Field(default=None, alias="fileName")
    pages: list[int] = Field(default_factory=list)
    section: str | None = None
    excerpt: str
    chunk_id: str | None = Field(default=None, alias="chunkId")


class FeedbackValue(BaseModel):
    type: str
    reason: str | None = None
    comment: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime = Field(alias="createdAt")
    status: str | None = None
    confidence_score: float | None = Field(default=None, alias="confidenceScore")
    sources: list[SourceResponse] = Field(default_factory=list)
    feedback: FeedbackValue | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_message: MessageResponse = Field(alias="userMessage")
    response: MessageResponse
