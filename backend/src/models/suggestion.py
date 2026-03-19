from typing import Any, Optional

from sqlalchemy import Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class Suggestion(Base, TimestampMixin):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(index=True, nullable=False)
    suggestion: Mapped[str] = mapped_column(nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    affected_components_json: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[Optional[dict[str, Any] | list[Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_suggestions_type_confidence", "type", "confidence"),
    )
