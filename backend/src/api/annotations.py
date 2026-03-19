from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db


class AnnotationCreateSchema(BaseModel):
    annotator_id: str = Field(..., description="Annotator identifier")
    type: str = Field(..., description="Annotation type")
    label: str = Field(..., description="Annotation label/value")
from src.services.annotation_service import (
    add_annotation,
    get_annotations,
    get_resolved_feedback,
)
from src.services.conversation_service import get_conversation

router = APIRouter(tags=["annotations"])


def _annotation_to_dict(a) -> dict:
    return {
        "id": a.id,
        "conversation_id": a.conversation.conversation_id if a.conversation else None,
        "annotator_id": a.annotator_id,
        "type": a.type,
        "label": a.label,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/{conversation_id}/annotations", status_code=201)
def create_annotation(
    conversation_id: str,
    data: AnnotationCreateSchema,
    agent_version: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        ann = add_annotation(
            db,
            conversation_id,
            data.annotator_id,
            data.type,
            data.label,
            agent_version,
        )
        return _annotation_to_dict(ann)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Conversation not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{conversation_id}/annotations")
def list_annotations(
    conversation_id: str,
    agent_version: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    anns = get_annotations(db, conversation_id, agent_version)
    return {"items": [_annotation_to_dict(a) for a in anns]}


@router.get("/{conversation_id}/resolved-feedback")
def get_resolved_feedback_endpoint(
    conversation_id: str,
    agent_version: Optional[str] = Query(None),
    tiebreaker_annotator_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = get_resolved_feedback(db, conversation_id, agent_version, tiebreaker_annotator_id)
    return result
