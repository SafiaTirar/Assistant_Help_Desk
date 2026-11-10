"""add RAG evaluation datasets and retrieval metrics

Revision ID: c94e7b2a61f3
Revises: a83d14c9e620
Create Date: 2026-08-23 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c94e7b2a61f3"
down_revision: Union[str, None] = "a83d14c9e620"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_questions",
        sa.Column("dataset_split", sa.String(length=20), nullable=False, server_default="calibration"),
    )
    op.add_column(
        "evaluation_questions",
        sa.Column("expected_documents", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index(
        "ix_evaluation_questions_dataset_split",
        "evaluation_questions",
        ["dataset_split"],
    )

    op.add_column(
        "evaluation_runs",
        sa.Column("dataset_split", sa.String(length=20), nullable=False, server_default="calibration"),
    )
    for name in (
        "latency_p50_ms",
        "latency_p95_ms",
        "retrieval_latency_p50_ms",
        "retrieval_latency_p95_ms",
    ):
        op.add_column("evaluation_runs", sa.Column(name, sa.Integer(), nullable=True))
    for name in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr"):
        op.add_column("evaluation_runs", sa.Column(name, sa.Float(), nullable=True))
    op.add_column(
        "evaluation_runs",
        sa.Column("active_documents_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("covered_documents_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("document_coverage_percent", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("uncovered_documents", sa.JSON(), nullable=False, server_default="[]"),
    )

    op.add_column(
        "evaluation_results",
        sa.Column("dataset_split", sa.String(length=20), nullable=False, server_default="calibration"),
    )
    op.add_column(
        "evaluation_results",
        sa.Column("expected_documents", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "evaluation_results",
        sa.Column("retrieved_documents", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("evaluation_results", sa.Column("retrieval_rank", sa.Integer(), nullable=True))
    for name in ("recall_at_1", "recall_at_3", "recall_at_5"):
        op.add_column("evaluation_results", sa.Column(name, sa.Boolean(), nullable=True))
    op.add_column("evaluation_results", sa.Column("reciprocal_rank", sa.Float(), nullable=True))
    op.add_column("evaluation_results", sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    for name in (
        "retrieval_latency_ms",
        "reciprocal_rank",
        "recall_at_5",
        "recall_at_3",
        "recall_at_1",
        "retrieval_rank",
        "retrieved_documents",
        "expected_documents",
        "dataset_split",
    ):
        op.drop_column("evaluation_results", name)
    for name in (
        "uncovered_documents",
        "document_coverage_percent",
        "covered_documents_total",
        "active_documents_total",
        "mrr",
        "recall_at_5",
        "recall_at_3",
        "recall_at_1",
        "retrieval_latency_p95_ms",
        "retrieval_latency_p50_ms",
        "latency_p95_ms",
        "latency_p50_ms",
        "dataset_split",
    ):
        op.drop_column("evaluation_runs", name)
    op.drop_index("ix_evaluation_questions_dataset_split", table_name="evaluation_questions")
    op.drop_column("evaluation_questions", "expected_documents")
    op.drop_column("evaluation_questions", "dataset_split")
