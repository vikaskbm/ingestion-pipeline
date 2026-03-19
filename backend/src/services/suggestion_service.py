"""
Suggestion service: query and manage stored suggestions.
"""

from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from src.models.suggestion import Suggestion


def _suggestion_to_item(s: Suggestion) -> dict[str, Any]:
    """Convert Suggestion model to API response item."""
    return {
        "type": s.type,
        "suggestion": s.suggestion,
        "rationale": s.rationale,
        "confidence": s.confidence,
        "affected_components": s.affected_components_json or [],
        "evidence": s.evidence_json,
    }


def get_suggestions(
    db: Session,
    type_filter: Optional[str] = None,
    min_confidence: Optional[float] = None,
    affected_component: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Query suggestions with optional filters.
    Returns (items, total).
    """
    q = select(Suggestion)
    count_q = select(func.count(Suggestion.id))

    filters = []
    if type_filter:
        filters.append(Suggestion.type == type_filter)
    if min_confidence is not None:
        filters.append(Suggestion.confidence >= min_confidence)
    if affected_component:
        # affected_components_json is list of strings; SQLite-compatible containment check
        ac_filter = text(
            "EXISTS (SELECT 1 FROM json_each(affected_components_json) WHERE value = :ac)"
        ).bindparams(ac=affected_component)
        filters.append(ac_filter)

    if filters:
        q = q.where(*filters)
        count_q = count_q.where(*filters)

    total = db.execute(count_q).scalar() or 0
    q = q.order_by(Suggestion.confidence.desc().nullslast(), Suggestion.created_at.desc())
    q = q.limit(limit).offset(offset)
    rows = db.execute(q).scalars().all()
    items = [_suggestion_to_item(s) for s in rows]
    return items, total
