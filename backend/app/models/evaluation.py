import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationQuestion(Base):
    __tablename__ = "evaluation_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_split: Mapped[str] = mapped_column(
        String(20), nullable=False, default="calibration", index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_status: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    results: Mapped[list["EvaluationResult"]] = relationship(back_populates="question_ref")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    dataset_split: Mapped[str] = mapped_column(String(20), nullable=False, default="calibration")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_latency_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_latency_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recall_at_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_at_3: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_at_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_documents_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_documents_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_coverage_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uncovered_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    initiated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvaluationResult.created_at",
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_code: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_split: Mapped[str] = mapped_column(String(20), nullable=False, default="calibration")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_status: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actual_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    actual_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retrieved_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retrieval_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recall_at_1: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recall_at_3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recall_at_5: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reciprocal_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    checks: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
    question_ref: Mapped[EvaluationQuestion | None] = relationship(back_populates="results")
