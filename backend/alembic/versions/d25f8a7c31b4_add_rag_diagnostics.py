"""add nullable RAG diagnostics

Revision ID: d25f8a7c31b4
Revises: c94e7b2a61f3
Create Date: 2026-08-24 18:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d25f8a7c31b4"
down_revision: Union[str, None] = "c94e7b2a61f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evaluation_runs", sa.Column("diagnostics", sa.JSON(), nullable=True))
    op.add_column("evaluation_results", sa.Column("diagnostics", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_results", "diagnostics")
    op.drop_column("evaluation_runs", "diagnostics")
