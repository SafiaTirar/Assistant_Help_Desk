from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FallbackAnnotation(Base):
    __tablename__ = "fallback_annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # hash de la question normalisée
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="À analyser")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
