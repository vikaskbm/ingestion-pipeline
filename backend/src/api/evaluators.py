"""
Evaluators API: get evaluator metadata and accuracy metrics.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.evaluators import EVALUATOR_REGISTRY
from src.services.calibration_service import get_latest_calibration

router = APIRouter(prefix="/evaluators", tags=["evaluators"])


@router.get("")
def list_evaluators():
    """List registered evaluators."""
    return {
        "evaluators": [
            {"id": eid, "name": ev.evaluator_name}
            for eid, ev in EVALUATOR_REGISTRY.items()
        ],
    }


@router.get("/{evaluator_id}/metrics")
def get_evaluator_metrics(
    evaluator_id: str,
    db: Session = Depends(get_db),
):
    """Get calibration/accuracy metrics for an evaluator (precision, recall, F1, correlation)."""
    if evaluator_id not in EVALUATOR_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Evaluator not found: {evaluator_id}")

    metrics = get_latest_calibration(db, evaluator_id=evaluator_id)
    return {
        "evaluator_id": evaluator_id,
        "evaluator_name": EVALUATOR_REGISTRY[evaluator_id].evaluator_name,
        "metrics": [
            {
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
            for m in metrics
        ],
    }
