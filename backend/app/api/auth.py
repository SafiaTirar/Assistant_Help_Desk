from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, UserResponse


router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse, response_model_by_alias=True)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")
    if user.status != "Actif":
        raise HTTPException(status_code=403, detail="Ce compte est désactivé.")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return LoginResponse(accessToken=create_access_token(user.id), user=serialize_user(db, user))


@router.get("/auth/me", response_model=UserResponse, response_model_by_alias=True)
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    return serialize_user(db, user)


@router.post("/auth/change-password", response_model=UserResponse, response_model_by_alias=True)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Le mot de passe actuel est incorrect.")
    validate_new_password(payload.new_password)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent.")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return serialize_user(db, user)


def validate_new_password(password: str) -> None:
    if not any(char.islower() for char in password) or not any(char.isupper() for char in password) or not any(char.isdigit() for char in password):
        raise HTTPException(
            status_code=422,
            detail="Le mot de passe doit contenir une minuscule, une majuscule et un chiffre.",
        )


def serialize_user(db: Session, user: User) -> UserResponse:
    conversation_count = db.scalar(
        select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
    ) or 0
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        mustChangePassword=user.must_change_password,
        createdAt=user.created_at,
        lastLogin=user.last_login,
        conversations=conversation_count,
    )
