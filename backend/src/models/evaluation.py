from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(unique=True, nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    scores_json: Mapped[Optional[dict[str, float]]] = mapped_column(JSON, nullable=True)
    tool_eval_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    issues_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    suggestions_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_evaluations_conversation_id_created_at", "conversation_id", "created_at"),
    )

    conversation = relationship("Conversation", back_populates="evaluations")
