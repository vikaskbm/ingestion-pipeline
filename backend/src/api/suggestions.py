"""
Suggestions API: list and generate improvement suggestions.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.services.suggestion_generator import generate_suggestions
from src.services.suggestion_service import get_suggestions

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("")
def list_suggestions(
    type_filter: Optional[str] = Query(None, description="Filter by suggestion type (prompt, tool, etc.)"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum confidence threshold"),
    affected_component: Optional[str] = Query(None, description="Filter by affected component"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List suggestions with optional filters. Returns paginated list."""
    items, total = get_suggestions(
        db,
        type_filter=type_filter,
        min_confidence=min_confidence,
        affected_component=affected_component,
        limit=limit,
        offset=offset,
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/generate")
def trigger_generate_suggestions(
    agent_version: Optional[str] = Query(None, description="Limit to specific agent version"),
    db: Session = Depends(get_db),
):
    """Trigger suggestion generation from failure clusters (admin)."""
    created = generate_suggestions(db, agent_version=agent_version)
    return {
        "generated": len(created),
        "suggestions": [
            {
                "type": s.type,
                "suggestion": s.suggestion,
                "confidence": s.confidence,
            }
            for s in created
        ],
    }
