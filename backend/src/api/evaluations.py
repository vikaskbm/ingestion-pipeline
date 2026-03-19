from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.schemas.evaluation import EvaluationBatchCreateSchema, EvaluationCreateSchema
from src.services.evaluation_service import (
    _evaluation_to_response,
    get_evaluation,
    get_evaluations,
    get_conversations_for_review,
    run_evaluation,
    run_evaluation_batch,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("")
def create_evaluation(
    data: EvaluationCreateSchema,
    db: Session = Depends(get_db),
):
    try:
        ev = run_evaluation(
            db,
            data.conversation_id,
            agent_version=data.agent_version,
            evaluator_ids=data.evaluator_ids,
        )
        return _evaluation_to_response(ev)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Conversation not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch")
def create_evaluations_batch(
    data: EvaluationBatchCreateSchema,
    db: Session = Depends(get_db),
):
    result = run_evaluation_batch(
        db,
        data.conversation_ids,
        agent_version=data.agent_version,
        evaluator_ids=data.evaluator_ids,
    )
    return {
        "evaluated": result["evaluated"],
        "failed": result["failed"],
        "evaluation_ids": result["evaluation_ids"],
        "errors": result["errors"],
    }


@router.get("/for-review")
def list_evaluations_for_review(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = get_conversations_for_review(db, limit=limit, offset=offset)
    return {
        "items": [_evaluation_to_response(ev) for ev in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{evaluation_id}")
def get_evaluation_by_id(
    evaluation_id: str,
    db: Session = Depends(get_db),
):
    ev = get_evaluation(db, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return _evaluation_to_response(ev)


@router.get("")
def list_evaluations(
    conversation_id: Optional[str] = Query(None),
    agent_version: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = get_evaluations(
        db,
        conversation_id=conversation_id,
        agent_version=agent_version,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_evaluation_to_response(ev) for ev in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
