from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    file_name: str = Field(serialization_alias="fileName")
    format: str
    version: str
    versions: list[str]
    date: str
    pages: str
    added_at: str = Field(serialization_alias="addedAt")
    status: str
    active: bool
    progress: int = 0
    error_message: str | None = Field(default=None, serialization_alias="errorMessage")
    mime_type: str | None = Field(default=None, serialization_alias="mimeType")
    file_size: int | None = Field(default=None, serialization_alias="fileSize")


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    document_id: str = Field(serialization_alias="documentId")
    version: str
    file_name: str = Field(serialization_alias="fileName")
    format: str
    mime_type: str | None = Field(default=None, serialization_alias="mimeType")
    file_size: int | None = Field(default=None, serialization_alias="fileSize")
    pages: int | None = None
    chunks: int | None = None
    status: str
    error_message: str | None = Field(default=None, serialization_alias="errorMessage")
    is_current: bool = Field(serialization_alias="isCurrent")
    created_at: datetime = Field(serialization_alias="createdAt")
