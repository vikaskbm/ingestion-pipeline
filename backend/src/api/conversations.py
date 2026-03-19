from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.schemas.conversation import ConversationCreateSchema, ConversationResponseSchema
from src.services import get_conversation, get_conversations, ingest_batch, to_response_schema, upsert_conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=201)
def create_conversation(
    data: ConversationCreateSchema,
    db: Session = Depends(get_db),
):
    conv = upsert_conversation(db, data)
    return {"conversation_id": conv.conversation_id, "id": conv.id}


@router.post("/batch")
def create_conversations_batch(
    conversations: list[ConversationCreateSchema],
    db: Session = Depends(get_db),
):
    result = ingest_batch(db, [c.model_dump() for c in conversations])
    return {
        "ingested": result["ingested"],
        "failed": result["failed"],
        "errors": result["errors"],
    }


@router.get("/{conversation_id}", response_model=ConversationResponseSchema)
def get_conversation_by_id(
    conversation_id: str,
    agent_version: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return to_response_schema(conv)


@router.get("")
def list_conversations(
    agent_version: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = get_conversations(
        db,
        agent_version=agent_version,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [to_response_schema(c) for c in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
