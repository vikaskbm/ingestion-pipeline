from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.conversation import Conversation
from src.schemas.conversation import ConversationCreateSchema, ConversationResponseSchema


def _to_json(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_json(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    return obj


def validate_conversation(data: dict[str, Any]) -> ConversationCreateSchema:
    return ConversationCreateSchema.model_validate(data)


def upsert_conversation(db: Session, data: ConversationCreateSchema) -> Conversation:
    existing = db.execute(
        select(Conversation).where(
            Conversation.conversation_id == data.conversation_id,
            Conversation.agent_version == data.agent_version,
        )
    ).scalars().first()

    turns_json = _to_json(data.turns)
    feedback_json = _to_json(data.feedback)
    metadata_json = _to_json(data.metadata)

    if existing:
        existing.turns_json = turns_json
        existing.feedback_json = feedback_json
        existing.metadata_json = metadata_json
        db.commit()
        db.refresh(existing)
        return existing

    conv = Conversation(
        conversation_id=data.conversation_id,
        agent_version=data.agent_version,
        turns_json=turns_json,
        feedback_json=feedback_json,
        metadata_json=metadata_json,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(
    db: Session,
    conversation_id: str,
    agent_version: Optional[str] = None,
) -> Optional[Conversation]:
    q = select(Conversation).where(Conversation.conversation_id == conversation_id)
    if agent_version:
        q = q.where(Conversation.agent_version == agent_version)
    q = q.order_by(Conversation.created_at.desc()).limit(1)
    return db.execute(q).scalars().first()


def get_conversations(
    db: Session,
    agent_version: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Conversation], int]:
    base_filter = []
    if agent_version:
        base_filter.append(Conversation.agent_version == agent_version)
    if date_from:
        base_filter.append(Conversation.created_at >= date_from)
    if date_to:
        base_filter.append(Conversation.created_at <= date_to)

    count_q = select(func.count()).select_from(Conversation)
    if base_filter:
        count_q = count_q.where(*base_filter)
    total = db.execute(count_q).scalar() or 0

    q = select(Conversation)
    if base_filter:
        q = q.where(*base_filter)
    q = q.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(q).scalars().all()
    return list(rows), total


def to_response_schema(conv: Conversation) -> ConversationResponseSchema:
    return ConversationResponseSchema(
        id=conv.id,
        conversation_id=conv.conversation_id,
        agent_version=conv.agent_version,
        turns=conv.turns_json,
        feedback=conv.feedback_json,
        metadata=conv.metadata_json,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )
