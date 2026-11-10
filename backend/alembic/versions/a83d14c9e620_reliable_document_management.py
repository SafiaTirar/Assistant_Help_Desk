"""reliable document management

Revision ID: a83d14c9e620
Revises: f7a91c2d4e10
Create Date: 2026-08-20 16:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a83d14c9e620"
down_revision: Union[str, None] = "f7a91c2d4e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("mime_type", sa.String(length=150), nullable=True))
    op.add_column("documents", sa.Column("file_size", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("current_generation", sa.String(length=36), nullable=True))
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.execute("""
        INSERT INTO document_versions (
            id, document_id, version, file_name, file_path, format, page_count,
            chunk_count, status, is_current, uploaded_by, created_at
        )
        SELECT id, id, version, file_name, file_path, format, page_count,
               chunk_count, status, true, uploaded_by, created_at
        FROM documents
    """)
    op.execute("""
        UPDATE documents
        SET mime_type = CASE format
            WHEN 'PDF' THEN 'application/pdf'
            WHEN 'DOCX' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        END
        WHERE mime_type IS NULL
    """)
    op.execute("""
        UPDATE document_versions
        SET mime_type = CASE format
            WHEN 'PDF' THEN 'application/pdf'
            WHEN 'DOCX' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        END
        WHERE mime_type IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_column("documents", "current_generation")
    op.drop_column("documents", "file_size")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "progress")
