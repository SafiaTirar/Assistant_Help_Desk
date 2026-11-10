import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models.evaluation import EvaluationQuestion, EvaluationRun
from app.models.user import User
from app.schemas.evaluation import (
    EvaluationImportRequest,
    EvaluationImportResponse,
    EvaluationQuestionCreate,
    EvaluationQuestionResponse,
    EvaluationQuestionUpdate,
    EvaluationRunCreate,
    EvaluationRunDetail,
    EvaluationRunSummary,
)
from app.services.evaluation_service import DATASET_SPLITS, run_evaluation_campaign


router = APIRouter(prefix="/admin/evaluations", tags=["admin-evaluations"])
ALLOWED_EXPECTED_STATUSES = {
    "reponse_trouvee",
    "reponse_non_trouvee",
    "hors_perimetre",
    "question_ambigue",
    "prompt_injection",
}


def _validate_expected_status(value: str) -> None:
    if value not in ALLOWED_EXPECTED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Statut attendu non supporté : {value}.",
        )


def _validate_dataset_split(value: str, allow_all: bool = False) -> None:
    allowed = DATASET_SPLITS if allow_all else DATASET_SPLITS - {"all"}
    if value not in allowed:
        raise HTTPException(status_code=422, detail=f"Jeu d'évaluation non supporté : {value}.")


def _question_or_404(db: Session, question_id: str) -> EvaluationQuestion:
    try:
        item_id = uuid.UUID(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Identifiant invalide.") from exc
    question = db.get(EvaluationQuestion, item_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question de référence introuvable.")
    return question


def _run_or_404(db: Session, run_id: str) -> EvaluationRun:
    try:
        item_id = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Identifiant invalide.") from exc
    run = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == item_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Campagne d'évaluation introuvable.")
    return run


@router.get(
    "/questions",
    response_model=list[EvaluationQuestionResponse],
    response_model_by_alias=True,
)
def list_evaluation_questions(
    include_inactive: bool = True,
    dataset_split: str | None = None,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(EvaluationQuestion).order_by(EvaluationQuestion.code)
    if dataset_split is not None:
        _validate_dataset_split(dataset_split)
        query = query.where(EvaluationQuestion.dataset_split == dataset_split)
    if not include_inactive:
        query = query.where(EvaluationQuestion.active.is_(True))
    return db.scalars(query).all()


@router.post(
    "/questions",
    response_model=EvaluationQuestionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_question(
    payload: EvaluationQuestionCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _validate_expected_status(payload.expected_status)
    _validate_dataset_split(payload.dataset_split)
    if db.scalar(select(EvaluationQuestion).where(EvaluationQuestion.code == payload.code)):
        raise HTTPException(status_code=409, detail="Ce code de question existe déjà.")
    question = EvaluationQuestion(**payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.patch(
    "/questions/{question_id}",
    response_model=EvaluationQuestionResponse,
    response_model_by_alias=True,
)
def update_evaluation_question(
    question_id: str,
    payload: EvaluationQuestionUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question = _question_or_404(db, question_id)
    changes = payload.model_dump(exclude_unset=True)
    if "expected_status" in changes:
        _validate_expected_status(changes["expected_status"])
    if "dataset_split" in changes:
        _validate_dataset_split(changes["dataset_split"])
    if "code" in changes:
        duplicate = db.scalar(
            select(EvaluationQuestion).where(
                EvaluationQuestion.code == changes["code"],
                EvaluationQuestion.id != question.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Ce code de question existe déjà.")
    for name, value in changes.items():
        setattr(question, name, value)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evaluation_question(
    question_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question = _question_or_404(db, question_id)
    db.delete(question)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/questions/import",
    response_model=EvaluationImportResponse,
)
def import_evaluation_questions(
    payload: EvaluationImportRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = {
        question.code: question
        for question in db.scalars(select(EvaluationQuestion)).all()
    }
    created = 0
    updated = 0
    for item in payload.questions:
        _validate_expected_status(item.expected_status)
        _validate_dataset_split(item.dataset_split)
        values = item.model_dump()
        question = existing.get(item.code)
        if question is None:
            question = EvaluationQuestion(**values)
            db.add(question)
            existing[item.code] = question
            created += 1
        else:
            for name, value in values.items():
                setattr(question, name, value)
            updated += 1
    db.commit()
    return EvaluationImportResponse(
        created=created,
        updated=updated,
        total=len(payload.questions),
    )


@router.get(
    "/runs",
    response_model=list[EvaluationRunSummary],
    response_model_by_alias=True,
)
def list_evaluation_runs(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.started_at.desc())
    ).all()


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunDetail,
    response_model_by_alias=True,
)
def get_evaluation_run(
    run_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run_or_404(db, run_id)


@router.post(
    "/runs",
    response_model=EvaluationRunDetail,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_run(
    payload: EvaluationRunCreate = EvaluationRunCreate(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _validate_dataset_split(payload.dataset_split, allow_all=True)
    run = run_evaluation_campaign(db, str(admin.id), payload.dataset_split)
    return _run_or_404(db, str(run.id))


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evaluation_run(
    run_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs/{run_id}/export.csv")
def export_evaluation_run(
    run_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = _run_or_404(db, run_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "run_id",
        "question_code",
        "category",
        "dataset_split",
        "question",
        "expected_status",
        "actual_status",
        "expected_answer",
        "actual_answer",
        "answer_similarity",
        "expected_pages",
        "actual_pages",
        "expected_documents",
        "retrieval_rank",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "reciprocal_rank",
        "retrieval_latency_ms",
        "checks",
        "failure_reasons",
        "confidence_score",
        "latency_ms",
        "success",
        "error",
        "diagnostics",
    ])
    for result in run.results:
        writer.writerow([
            run.id,
            result.question_code,
            result.category,
            result.dataset_split,
            result.question_text,
            result.expected_status,
            result.actual_status or "",
            result.expected_answer,
            result.actual_answer,
            result.answer_similarity,
            json.dumps(result.expected_pages, ensure_ascii=False),
            json.dumps(result.actual_pages, ensure_ascii=False),
            json.dumps(result.expected_documents, ensure_ascii=False),
            result.retrieval_rank,
            result.recall_at_1,
            result.recall_at_3,
            result.recall_at_5,
            result.reciprocal_rank,
            result.retrieval_latency_ms,
            json.dumps(result.checks, ensure_ascii=False),
            json.dumps(result.failure_reasons, ensure_ascii=False),
            result.confidence_score,
            result.latency_ms,
            result.success,
            result.error or "",
            json.dumps(result.diagnostics, ensure_ascii=False),
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="evaluation-{run.id}.csv"'
            )
        },
    )
