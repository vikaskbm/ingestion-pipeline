import os
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from src.evaluators import run_evaluators

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.8"))
from src.models.conversation import Conversation
from src.models.evaluation import Evaluation
from src.services.conversation_service import get_conversation


def _conversation_to_dict(conv: Conversation) -> dict[str, Any]:
    return {
        "conversation_id": conv.conversation_id,
        "agent_version": conv.agent_version,
        "turns": conv.turns_json,
        "feedback": conv.feedback_json,
        "metadata": conv.metadata_json,
    }


def _aggregate_scores(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    values = [v for v in scores.values() if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else 0.0


def run_evaluation(
    db: Session,
    conversation_id: str,
    agent_version: Optional[str] = None,
    evaluator_ids: Optional[list[str]] = None,
) -> Evaluation:
    conv = get_conversation(db, conversation_id, agent_version)
    if not conv:
        raise ValueError(f"Conversation not found: {conversation_id}")

    conversation_dict = _conversation_to_dict(conv)
    result = run_evaluators(conversation_dict, evaluator_ids)

    scores = result.get("scores") or {}
    issues = result.get("issues") or []
    suggestions = result.get("suggestions") or []

    overall = _aggregate_scores(scores)
    scores["overall"] = overall

    evaluation_id = str(uuid.uuid4())
    needs_review = overall < CONFIDENCE_THRESHOLD
    evaluation = Evaluation(
        evaluation_id=evaluation_id,
        conversation_id=conv.id,
        scores_json=scores,
        tool_eval_json=None,
        issues_json=issues,
        suggestions_json=suggestions,
        needs_review=needs_review,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


def get_evaluation(db: Session, evaluation_id: str) -> Optional[Evaluation]:
    return (
        db.execute(
            select(Evaluation)
            .where(Evaluation.evaluation_id == evaluation_id)
            .options(joinedload(Evaluation.conversation))
        )
        .scalars()
        .first()
    )


def run_evaluation_batch(
    db: Session,
    conversation_ids: list[str],
    agent_version: Optional[str] = None,
    evaluator_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    evaluated = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    evaluation_ids: list[str] = []

    for cid in conversation_ids:
        try:
            ev = run_evaluation(db, cid, agent_version, evaluator_ids)
            evaluated += 1
            evaluation_ids.append(ev.evaluation_id)
        except ValueError as e:
            failed += 1
            errors.append({"conversation_id": cid, "error": str(e)})
        except Exception as e:
            failed += 1
            errors.append({"conversation_id": cid, "error": str(e)})

    return {
        "evaluated": evaluated,
        "failed": failed,
        "evaluation_ids": evaluation_ids,
        "errors": errors,
    }


def _evaluation_to_response(ev: Evaluation) -> dict[str, Any]:
    conv_id_str = ev.conversation.conversation_id if ev.conversation else ""
    return {
        "id": ev.id,
        "evaluation_id": ev.evaluation_id,
        "conversation_id": conv_id_str,
        "scores": ev.scores_json,
        "tool_eval": ev.tool_eval_json,
        "issues": ev.issues_json or [],
        "suggestions": ev.suggestions_json or [],
        "needs_review": ev.needs_review,
        "created_at": ev.created_at,
    }


def get_conversations_for_review(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Evaluation], int]:
    q = (
        select(Evaluation)
        .where(Evaluation.needs_review == True)
        .join(Conversation, Evaluation.conversation_id == Conversation.id)
        .options(joinedload(Evaluation.conversation))
    )
    count_q = select(func.count(Evaluation.id)).where(Evaluation.needs_review == True)
    total = db.execute(count_q).scalar() or 0
    q = q.order_by(Evaluation.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(q).scalars().all()
    return list(rows), total


def get_evaluations(
    db: Session,
    conversation_id: Optional[str] = None,
    agent_version: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Evaluation], int]:
    q = (
        select(Evaluation)
        .join(Conversation, Evaluation.conversation_id == Conversation.id)
        .options(joinedload(Evaluation.conversation))
    )
    count_q = select(func.count(Evaluation.id)).select_from(Evaluation).join(
        Conversation, Evaluation.conversation_id == Conversation.id
    )

    base_filter = []
    if conversation_id:
        base_filter.append(Conversation.conversation_id == conversation_id)
    if agent_version:
        base_filter.append(Conversation.agent_version == agent_version)
    if date_from:
        base_filter.append(Evaluation.created_at >= date_from)
    if date_to:
        base_filter.append(Evaluation.created_at <= date_to)

    if base_filter:
        q = q.where(*base_filter)
        count_q = count_q.where(*base_filter)

    total = db.execute(count_q).scalar() or 0

    q = q.order_by(Evaluation.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(q).scalars().all()
    return list(rows), total
