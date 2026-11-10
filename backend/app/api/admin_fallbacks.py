import csv
import hashlib
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin_dashboard import build_audit_rows
from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models.fallback_annotation import FallbackAnnotation
from app.models.user import User
from app.schemas.fallback import FallbackItem, FallbackUpdateRequest

router = APIRouter(tags=["admin-fallbacks"])

FALLBACK_STATUSES = {"reponse_non_trouvee", "information_insuffisante"}
DEFAULT_STATUS = "À analyser"


def _question_key(question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _build_fallback_items(db: Session) -> list[FallbackItem]:
    rows = [r for r in build_audit_rows(db) if r.status in FALLBACK_STATUSES]

    groups: dict[str, dict] = {}
    for row in rows:
        key = _question_key(row.question)
        group = groups.setdefault(key, {"question": row.question, "dates": []})
        group["dates"].append(row.date)

    annotations = {a.id: a for a in db.scalars(select(FallbackAnnotation)).all()}

    items = [
        FallbackItem(
            id=key,
            question=group["question"],
            occurrences=len(group["dates"]),
            first=min(group["dates"]),
            last=max(group["dates"]),
            status=annotations[key].status if key in annotations else DEFAULT_STATUS,
            comment=(annotations[key].comment or "") if key in annotations else "",
        )
        for key, group in groups.items()
    ]
    return sorted(items, key=lambda item: item.occurrences, reverse=True)


def _apply_filters(items: list[FallbackItem], query: str | None, status: str | None) -> list[FallbackItem]:
    if query:
        needle = query.strip().lower()
        items = [item for item in items if needle in item.question.lower()]
    if status:
        items = [item for item in items if item.status == status]
    return items


@router.get("/admin/fallbacks", response_model=list[FallbackItem])
def list_fallbacks(
    query: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[FallbackItem]:
    return _apply_filters(_build_fallback_items(db), query, status)


@router.patch("/admin/fallbacks/{fallback_id}", response_model=FallbackItem)
def update_fallback(
    fallback_id: str,
    payload: FallbackUpdateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FallbackItem:
    items = {item.id: item for item in _build_fallback_items(db)}
    current = items.get(fallback_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Question introuvable.")

    annotation = db.get(FallbackAnnotation, fallback_id)
    if annotation is None:
        annotation = FallbackAnnotation(id=fallback_id)
        db.add(annotation)

    if payload.status is not None:
        annotation.status = payload.status
    if payload.comment is not None:
        annotation.comment = payload.comment
    db.commit()

    return FallbackItem(
        id=current.id,
        question=current.question,
        occurrences=current.occurrences,
        first=current.first,
        last=current.last,
        status=annotation.status,
        comment=annotation.comment or "",
    )


@router.get("/admin/fallbacks/export.csv")
def export_fallbacks_csv(
    query: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    items = _apply_filters(_build_fallback_items(db), query, status)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "question", "occurrences", "first", "last", "status", "comment"])
    for item in items:
        writer.writerow([item.id, item.question, item.occurrences, item.first, item.last, item.status, item.comment])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=fallbacks.csv"},
    )
