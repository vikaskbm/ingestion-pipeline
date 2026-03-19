from typing import Any, Optional

from sqlalchemy import Index, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(index=True, nullable=False)
    agent_version: Mapped[str] = mapped_column(index=True, nullable=False)
    turns_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    feedback_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "agent_version", name="uq_conversation_agent_version"),
        Index("ix_conversations_conversation_id_agent_version_created_at", "conversation_id", "agent_version", "created_at"),
    )

    evaluations = relationship("Evaluation", back_populates="conversation", cascade="all, delete-orphan")
    annotations = relationship("Annotation", back_populates="conversation", cascade="all, delete-orphan")
