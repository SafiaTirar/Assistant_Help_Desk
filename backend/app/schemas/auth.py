from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    # Les entrées restent validées avec EmailStr. La sortie accepte toutefois les
    # anciens comptes créés avant cette validation afin qu'une ligne historique
    # invalide ne fasse pas échouer toute la liste d'administration.
    email: str
    role: str
    status: str
    must_change_password: bool = Field(alias="mustChangePassword")
    created_at: datetime = Field(alias="createdAt")
    last_login: datetime | None = Field(default=None, alias="lastLogin")
    conversations: int = 0


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(alias="currentPassword", min_length=8, max_length=128)
    new_password: str = Field(alias="newPassword", min_length=12, max_length=128)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    role: str = Field(default="USER", pattern="^(USER|ADMIN)$")
    temporary_password: str = Field(alias="temporaryPassword", min_length=12, max_length=128)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(USER|ADMIN)$")
    status: str | None = Field(default=None, pattern="^(Actif|Inactif)$")
