from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate


router = APIRouter(tags=["admin-contacts"])
OPTIONAL_TEXT_FIELDS = {"email", "phone", "step", "document", "page"}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@router.get(
    "/admin/contacts",
    response_model=list[ContactResponse],
    response_model_by_alias=True,
)
def list_contacts(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Contact]:
    return list(db.scalars(select(Contact).order_by(Contact.name.asc())).all())


@router.post(
    "/admin/contacts",
    response_model=ContactResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    payload: ContactCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Contact:
    values = payload.model_dump()
    values["name"] = payload.name.strip()
    values["service"] = payload.service.strip()
    for field in OPTIONAL_TEXT_FIELDS:
        values[field] = _clean_text(values[field])
    contact = Contact(**values)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact

@router.patch(
    "/admin/contacts/{contact_id}",
    response_model=ContactResponse,
    response_model_by_alias=True,
)
def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact introuvable.")

    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field in {"name", "service"}:
            cleaned = value.strip() if value is not None else ""
            if not cleaned:
                raise HTTPException(
                    status_code=422,
                    detail=f"Le champ {field} ne peut pas être vide.",
                )
            value = cleaned
        elif field in OPTIONAL_TEXT_FIELDS:
            value = _clean_text(value)
        setattr(contact, field, value)

    db.commit()
    db.refresh(contact)
    return contact

