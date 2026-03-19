from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.models.annotation import Annotation
from src.models.conversation import Conversation
from src.services.conversation_service import get_conversation


def add_annotation(
    db: Session,
    conversation_id: str,
    annotator_id: str,
    type: str,
    label: str,
    agent_version: Optional[str] = None,
) -> Annotation:
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        raise ValueError(f"Conversation not found: {conversation_id}")

    existing = db.execute(
        select(Annotation).where(
            Annotation.conversation_id == conv.id,
            Annotation.annotator_id == annotator_id,
            Annotation.type == type,
        )
    ).scalars().first()

    if existing:
        existing.label = label
        db.commit()
        db.refresh(existing)
        return existing

    ann = Annotation(
        conversation_id=conv.id,
        annotator_id=annotator_id,
        type=type,
        label=label,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return ann


def get_annotations(
    db: Session,
    conversation_id: str,
    agent_version: Optional[str] = None,
) -> list[Annotation]:
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        return []

    rows = (
        db.execute(
            select(Annotation)
            .where(Annotation.conversation_id == conv.id)
            .options(joinedload(Annotation.conversation))
        )
        .scalars().all()
    )
    return list(rows)


def get_resolved_feedback(
    db: Session,
    conversation_id: str,
    agent_version: Optional[str] = None,
    tiebreaker_annotator_id: Optional[str] = None,
) -> dict[str, Any]:
    anns = get_annotations(db, conversation_id, agent_version)
    if not anns:
        return {"resolved": {}, "needs_review": False}

    by_type: dict[str, list[dict[str, Any]]] = {}
    for a in anns:
        t = a.type
        if t not in by_type:
            by_type[t] = []
        by_type[t].append({
            "annotator_id": a.annotator_id,
            "type": a.type,
            "label": a.label,
        })

    from src.services.disagreement_resolver import resolve_labels

    resolved = {}
    any_needs_review = False
    for t, items in by_type.items():
        r = resolve_labels(items, tiebreaker_annotator_id)
        resolved[t] = r["resolved_label"]
        if r.get("needs_review"):
            any_needs_review = True

    return {"resolved": resolved, "needs_review": any_needs_review}


def get_annotations_by_annotator(
    db: Session,
    annotator_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Annotation]:
    rows = (
        db.execute(
            select(Annotation)
            .where(Annotation.annotator_id == annotator_id)
            .order_by(Annotation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars().all()
    )
    return list(rows)
