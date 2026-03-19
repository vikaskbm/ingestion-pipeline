"""
Calibration API: get latest metrics, trigger calibration run, evaluator metrics.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.services.calibration_service import (
    detect_blind_spots,
    get_latest_calibration,
    run_calibration,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])


def _metric_to_dict(m: Any) -> dict[str, Any]:
    return {
        "evaluator_id": m.evaluator_id,
        "score_type": m.score_type,
        "pearson_correlation": m.pearson_correlation,
        "spearman_correlation": m.spearman_correlation,
        "rmse": m.rmse,
        "precision": m.precision,
        "recall": m.recall,
        "f1": m.f1,
        "sample_count": m.sample_count,
        "divergence_detected": m.divergence_detected,
        "computed_at": m.computed_at,
    }


@router.get("")
def get_calibration(
    evaluator_id: Optional[str] = Query(None, description="Filter by evaluator ID"),
    db: Session = Depends(get_db),
):
    """Get latest calibration metrics."""
    metrics = get_latest_calibration(db, evaluator_id=evaluator_id)
    return {"metrics": [_metric_to_dict(m) for m in metrics]}


@router.post("/run")
def trigger_calibration_run(
    agent_version: Optional[str] = Query(None),
    evaluator_ids: Optional[str] = Query(None, description="Comma-separated evaluator IDs"),
    db: Session = Depends(get_db),
):
    """Trigger calibration run (compute metrics from evaluations + human annotations)."""
    ev_ids = [x.strip() for x in evaluator_ids.split(",")] if evaluator_ids else None
    results = run_calibration(db, agent_version=agent_version, evaluator_ids=ev_ids)
    return {
        "computed": len(results),
        "metrics": [
            {
                "evaluator_id": r.evaluator_id,
                "score_type": r.score_type,
                "pearson_correlation": r.pearson_correlation,
                "spearman_correlation": r.spearman_correlation,
                "rmse": r.rmse,
                "precision": r.precision,
                "recall": r.recall,
                "f1": r.f1,
                "sample_count": r.sample_count,
                "divergence_detected": r.divergence_detected,
            }
            for r in results
        ],
    }


@router.get("/blind-spots")
def get_blind_spots(
    agent_version: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get blind spots: failures human caught but automated missed."""
    clusters = detect_blind_spots(db, agent_version=agent_version)
    return {
        "clusters": [
            {
                "annotation_type": c.annotation_type,
                "count": c.count,
                "conversation_ids": c.conversation_ids,
                "evaluator_suggestion": c.evaluator_suggestion,
            }
            for c in clusters
        ],
    }
