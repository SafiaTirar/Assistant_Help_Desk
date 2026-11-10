from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import serialize_user, validate_new_password
from app.api.dependencies import require_admin
from app.core.security import hash_password
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserResponse, UserUpdate


router = APIRouter(tags=["admin-users"])


@router.get("/admin/users", response_model=list[UserResponse], response_model_by_alias=True)
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserResponse]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [serialize_user(db, user) for user in users]


@router.post(
    "/admin/users",
    response_model=UserResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Un compte utilise déjà cet e-mail.")
    validate_new_password(payload.temporary_password)
    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.temporary_password),
        role=payload.role,
        status="Actif",
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(db, user)


@router.patch("/admin/users/{user_id}", response_model=list[UserResponse], response_model_by_alias=True)
def update_user(
    user_id: str,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserResponse]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if user.id == admin.id and (payload.role == "USER" or payload.status == "Inactif"):
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer votre propre accès administrateur.")
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        user.status = payload.status
    db.commit()
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [serialize_user(db, item) for item in users]
