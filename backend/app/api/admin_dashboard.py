from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.admin import (
    AdminConversationResponse,
    AttentionItem,
    DashboardResponse,
    MetricResponse,
    StatusStat,
    TopQuestion,
)


router = APIRouter(tags=["admin-dashboard"])
STATUS_LABELS = {
    "reponse_trouvee": "Réponse trouvée",
    "reponse_non_trouvee": "Information insuffisante",
    "information_insuffisante": "Information insuffisante",
    "hors_perimetre": "Hors périmètre",
    "question_ambigue": "Question ambiguë",
    "erreur_technique": "Erreur technique",
}


@router.get("/admin/dashboard", response_model=DashboardResponse, response_model_by_alias=True)
def dashboard(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    rows = build_audit_rows(db)
    total = len(rows)
    found = sum(row.status == "reponse_trouvee" for row in rows)
    unanswered = sum(row.status in {"reponse_non_trouvee", "information_insuffisante"} for row in rows)
    out_of_scope = sum(row.status == "hors_perimetre" for row in rows)
    useful = sum(row.feedback == "Utile" for row in rows)
    not_useful = sum(row.feedback == "Non utile" for row in rows)
    feedback_total = useful + not_useful
    latencies = [message.latency_ms for message in assistant_messages(db) if message.latency_ms is not None]
    average = f"{sum(latencies) / len(latencies) / 1000:.1f} s" if latencies else "—"

    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    counts_by_day = Counter(_as_utc_date(row.date) for row in rows)
    status_counts = Counter(row.status for row in rows)
    question_counts = Counter(row.question for row in rows)
    question_status = {row.question: row.status for row in rows}
    top = question_counts.most_common(5)
    attention_counts = Counter(
        row.question for row in rows
        if row.status in {"reponse_non_trouvee", "information_insuffisante"} or row.feedback == "Non utile"
    )

    return DashboardResponse(
        metrics=MetricResponse(
            total=total,
            found=found,
            unanswered=unanswered,
            outOfScope=out_of_scope,
            positive=_percentage(useful, feedback_total),
            negative=_percentage(not_useful, feedback_total),
            average=average,
        ),
        trend=[counts_by_day[day] for day in days],
        trendLabels=[day.strftime("%d/%m") for day in days],
        statuses=[
            StatusStat(label=STATUS_LABELS.get(key, key), value=value)
            for key, value in status_counts.most_common()
        ],
        topQuestions=[
            TopQuestion(question=question, occurrences=count, status=question_status[question])
            for question, count in top
        ],
        attention=[
            AttentionItem(question=question, occurrences=count, reason="Sans réponse ou retour négatif")
            for question, count in attention_counts.most_common(5)
        ],
    )


@router.get("/admin/conversations", response_model=list[AdminConversationResponse], response_model_by_alias=True)
def admin_conversations(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminConversationResponse]:
    return build_audit_rows(db)


def assistant_messages(db: Session) -> list[Message]:
    return list(db.scalars(select(Message).where(Message.role == "assistant")).all())


def build_audit_rows(db: Session) -> list[AdminConversationResponse]:
    conversations = db.scalars(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    ).all()
    user_names = {user.id: user.name for user in db.scalars(select(User)).all()}
    rows = []
    for conversation in conversations:
        questions = [message for message in conversation.messages if message.role == "user"]
        for message in conversation.messages:
            if message.role != "assistant":
                continue
            eligible = [question for question in questions if question.created_at <= message.created_at]
            question = max(eligible, key=lambda item: item.created_at).content if eligible else "Question indisponible"
            rows.append(AdminConversationResponse(
                id=str(message.id),
                date=message.created_at.isoformat(),
                user=user_names.get(conversation.user_id, "Utilisateur inconnu"),
                question=question,
                status=message.status or "erreur_technique",
                answer=message.content,
                feedback={"utile": "Utile", "non_utile": "Non utile"}.get(message.feedback_type, "—"),
                duration=f"{message.latency_ms / 1000:.1f} s" if message.latency_ms is not None else "—",
                internalReferences=message.sources or [],
            ))
    return sorted(rows, key=lambda row: row.date, reverse=True)


def _percentage(value: int, total: int) -> str:
    return f"{round(value / total * 100)} %" if total else "—"


def _as_utc_date(value: str):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()
