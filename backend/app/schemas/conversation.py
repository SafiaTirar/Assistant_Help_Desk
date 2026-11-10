from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat import MessageResponse


class ConversationCreate(BaseModel):
    title: str = Field(default="Nouvelle conversation", min_length=1, max_length=160)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    title: str
    updated_at: datetime = Field(alias="updatedAt")
    messages: list[MessageResponse] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    type: str = Field(pattern="^(utile|non_utile)$")
    reason: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=2_000)


class FeedbackResponse(BaseModel):
    type: str
    reason: str | None = None
    comment: str | None = None
