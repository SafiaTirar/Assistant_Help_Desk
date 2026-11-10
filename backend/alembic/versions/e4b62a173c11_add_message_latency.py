"""add message latency

Revision ID: e4b62a173c11
Revises: c31a48e7d902
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b62a173c11"
down_revision: Union[str, None] = "c31a48e7d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "latency_ms")
