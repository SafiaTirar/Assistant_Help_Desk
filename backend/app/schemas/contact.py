from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    service: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=60)
    step: str | None = Field(default=None, max_length=160)
    visible: bool = False
    active: bool = True
    document: str | None = Field(default=None, max_length=255)
    page: str | None = Field(default=None, max_length=40)

    @field_validator("name", "service")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Ce champ ne peut pas être vide.")
        return cleaned

    @field_validator("email", "phone", "step", "document", "page", mode="before")
    @classmethod
    def empty_string_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    service: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=60)
    step: str | None = Field(default=None, max_length=160)
    visible: bool | None = None
    active: bool | None = None
    document: str | None = Field(default=None, max_length=255)
    page: str | None = Field(default=None, max_length=40)

    @field_validator("name", "service")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Ce champ ne peut pas être vide.")
        return cleaned

    @field_validator("email", "phone", "step", "document", "page", mode="before")
    @classmethod
    def empty_string_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class ContactResponse(ContactBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
