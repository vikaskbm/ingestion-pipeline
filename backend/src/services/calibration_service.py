"""
Calibration service: compare automated evaluations with human annotations.
Computes Pearson/Spearman correlation, RMSE, precision/recall/F1.
"""

import math
import os
from dataclasses import dataclass
from typing import Any, Optional

from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.models.calibration import CalibrationMetric
from src.models.conversation import Conversation
from src.models.evaluation import Evaluation
from src.services.annotation_service import get_resolved_feedback

# Annotation type -> evaluation score key (evaluator_id.score_name)
ANNOTATION_TO_SCORE: dict[str, list[str]] = {
    "helpfulness": ["llm_judge.helpfulness"],
    "quality": ["llm_judge.response_quality"],
    "factuality": ["llm_judge.factuality"],
    "overall": ["overall"],
}

# Labels considered "negative" (human caught failure) for precision/recall
NEGATIVE_LABELS = frozenset({"bad", "poor", "fail", "failed", "low", "negative", "0", "no"})
POSITIVE_LABELS = frozenset({"good", "excellent", "pass", "high", "positive", "1", "yes"})

CORRELATION_THRESHOLD = float(os.getenv("CALIBRATION_CORRELATION_THRESHOLD", "0.5"))
SCORE_THRESHOLD = float(os.getenv("CALIBRATION_SCORE_THRESHOLD", "0.5"))


@dataclass
class CalibrationResult:
    evaluator_id: str
    score_type: Optional[str]
    pearson_correlation: Optional[float]
    spearman_correlation: Optional[float]
    rmse: Optional[float]
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    sample_count: int
    divergence_detected: bool


def _parse_label_as_float(label: str) -> Optional[float]:
    """Parse annotation label as float (0-1)."""
    if label is None:
        return None
    s = str(label).strip().lower()
    if s in NEGATIVE_LABELS:
        return 0.0
    if s in POSITIVE_LABELS:
        return 1.0
    try:
        v = float(label)
        return max(0.0, min(1.0, v)) if 0 <= v <= 1 else v
    except (ValueError, TypeError):
        return None


def _label_to_binary(label: str) -> Optional[bool]:
    """True = human says negative (failure), False = positive (pass)."""
    s = str(label).strip().lower()
    if s in NEGATIVE_LABELS:
        return True
    if s in POSITIVE_LABELS:
        return False
    try:
        v = float(label)
        return v < SCORE_THRESHOLD
    except (ValueError, TypeError):
        return None


def _get_eval_score(scores: dict[str, float], keys: list[str]) -> Optional[float]:
    """Get first matching score from evaluation."""
    for k in keys:
        if k in scores and scores[k] is not None:
            v = scores[k]
            if isinstance(v, (int, float)):
                return float(v)
    return None


def _fetch_pairs(db: Session, agent_version: Optional[str] = None) -> list[tuple[Evaluation, dict[str, str]]]:
    """Fetch (evaluation, resolved_annotations) for conversations with both."""
    q = (
        select(Evaluation)
        .join(Conversation, Evaluation.conversation_id == Conversation.id)
        .where(Evaluation.scores_json.isnot(None))
        .options(joinedload(Evaluation.conversation))
    )
    if agent_version:
        q = q.where(Conversation.agent_version == agent_version)
    rows = db.execute(q).scalars().all()

    pairs: list[tuple[Evaluation, dict[str, str]]] = []
    for ev in rows:
        conv = ev.conversation
        if not conv:
            continue
        resolved = get_resolved_feedback(db, conv.conversation_id, conv.agent_version)
        labels = resolved.get("resolved") or {}
        if labels:
            pairs.append((ev, labels))
    return pairs


def _compute_numeric_metrics(
    auto_scores: list[float],
    human_scores: list[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Compute Pearson, Spearman, RMSE. Requires at least 2 pairs."""
    if len(auto_scores) < 2 or len(human_scores) < 2 or len(auto_scores) != len(human_scores):
        return None, None, None

    pearson = stats.pearsonr(auto_scores, human_scores)
    spearman = stats.spearmanr(auto_scores, human_scores)
    pearson_r = float(pearson.statistic) if hasattr(pearson, "statistic") else pearson[0]
    spearman_r = float(spearman.statistic) if hasattr(spearman, "statistic") else spearman[0]

    rmse = math.sqrt(sum((a - h) ** 2 for a, h in zip(auto_scores, human_scores)) / len(auto_scores))
    return pearson_r, spearman_r, rmse


def _compute_classification_metrics(
    auto_positive: list[bool],
    human_positive: list[bool],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Compute precision, recall, F1. Positive = failure/negative label."""
    if len(auto_positive) != len(human_positive) or not auto_positive:
        return None, None, None

    tp = sum(1 for a, h in zip(auto_positive, human_positive) if a and h)
    fp = sum(1 for a, h in zip(auto_positive, human_positive) if a and not h)
    fn = sum(1 for a, h in zip(auto_positive, human_positive) if not a and h)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def run_calibration(
    db: Session,
    agent_version: Optional[str] = None,
    evaluator_ids: Optional[list[str]] = None,
) -> list[CalibrationResult]:
    """
    Fetch evaluations + human annotations, compute metrics, store in CalibrationMetric.
    Returns list of calibration results.
    """
    pairs = _fetch_pairs(db, agent_version)
    if not pairs:
        return []

    # Build (evaluator_id, score_type) -> (auto_scores, human_scores) for numeric
    # Build (evaluator_id,) -> (auto_positive, human_positive) for binary
    numeric_data: dict[tuple[str, str], tuple[list[float], list[float]]] = {}
    binary_data: dict[str, tuple[list[bool], list[bool]]] = {}

    for ev, labels in pairs:
        scores = ev.scores_json or {}
        issues = ev.issues_json or []
        has_issues = any(i.get("severity") == "critical" for i in issues if isinstance(i, dict))
        auto_positive = scores.get("overall", 1.0) < SCORE_THRESHOLD or has_issues

        for ann_type, label in labels.items():
            human_float = _parse_label_as_float(label)
            human_binary = _label_to_binary(label)

            score_keys = ANNOTATION_TO_SCORE.get(ann_type, ["overall"])
            key = score_keys[0] if score_keys else "overall"
            parts = key.split(".", 1)
            ev_id = parts[0]
            st = parts[1] if len(parts) > 1 else "overall"

            if evaluator_ids and ev_id not in evaluator_ids:
                continue

            auto_score = _get_eval_score(scores, score_keys)
            if human_float is not None and auto_score is not None:
                k = (ev_id, st)
                if k not in numeric_data:
                    numeric_data[k] = ([], [])
                numeric_data[k][0].append(auto_score)
                numeric_data[k][1].append(human_float)

            if human_binary is not None:
                bin_key = f"aggregate_{ann_type}"
                if bin_key not in binary_data:
                    binary_data[bin_key] = ([], [])
                binary_data[bin_key][0].append(auto_positive)
                binary_data[bin_key][1].append(human_binary)

    results: list[CalibrationResult] = []
    seen: set[tuple[str, Optional[str]]] = set()

    for (ev_id, score_type), (auto_s, human_s) in numeric_data.items():
        if (ev_id, score_type) in seen or len(auto_s) < 2:
            continue
        seen.add((ev_id, score_type))
        pearson, spearman, rmse = _compute_numeric_metrics(auto_s, human_s)
        if pearson is None:
            continue
        div = pearson < CORRELATION_THRESHOLD
        results.append(
            CalibrationResult(
                evaluator_id=ev_id,
                score_type=score_type,
                pearson_correlation=pearson,
                spearman_correlation=spearman,
                rmse=rmse,
                precision=None,
                recall=None,
                f1=None,
                sample_count=len(auto_s),
                divergence_detected=div,
            )
        )
        metric = CalibrationMetric(
            evaluator_id=ev_id,
            score_type=score_type,
            correlation=pearson,
            pearson_correlation=pearson,
            spearman_correlation=spearman,
            rmse=rmse,
            precision=None,
            recall=None,
            f1=None,
            sample_count=len(auto_s),
            divergence_detected=div,
        )
        db.add(metric)

    for bin_key, (auto_p, human_p) in binary_data.items():
        ev_id = "aggregate"
        st = bin_key.replace("aggregate_", "") if bin_key.startswith("aggregate_") else "binary"
        if (ev_id, st) in seen or len(auto_p) < 2:
            continue
        prec, rec, f1 = _compute_classification_metrics(auto_p, human_p)
        if prec is None:
            continue
        div = f1 < CORRELATION_THRESHOLD if f1 is not None else False
        seen.add((ev_id, st))
        results.append(
            CalibrationResult(
                evaluator_id=ev_id,
                score_type=st,
                pearson_correlation=None,
                spearman_correlation=None,
                rmse=None,
                precision=prec,
                recall=rec,
                f1=f1,
                sample_count=len(auto_p),
                divergence_detected=div,
            )
        )
        metric = CalibrationMetric(
            evaluator_id=ev_id,
            score_type=st,
            correlation=None,
            pearson_correlation=None,
            spearman_correlation=None,
            rmse=None,
            precision=prec,
            recall=rec,
            f1=f1,
            sample_count=len(auto_p),
            divergence_detected=div,
        )
        db.add(metric)

    db.commit()
    return results


@dataclass
class BlindSpotCluster:
    """Cluster of blind spots: human caught failure but automated missed."""
    annotation_type: str
    count: int
    conversation_ids: list[str]
    evaluator_suggestion: str


def detect_blind_spots(
    db: Session,
    agent_version: Optional[str] = None,
) -> list[BlindSpotCluster]:
    """
    Find failures human caught but automated missed.
    Cluster by annotation type and propose new evaluator suggestions.
    """
    pairs = _fetch_pairs(db, agent_version)
    blind_spots: list[tuple[str, str]] = []  # (ann_type, conversation_id)

    for ev, labels in pairs:
        scores = ev.scores_json or {}
        issues = ev.issues_json or []
        has_critical = any(i.get("severity") == "critical" for i in issues if isinstance(i, dict))
        auto_positive = scores.get("overall", 1.0) < SCORE_THRESHOLD or has_critical

        conv = ev.conversation
        conv_id = conv.conversation_id if conv else ""

        for ann_type, label in labels.items():
            human_positive = _label_to_binary(label)
            if human_positive is True and not auto_positive:
                blind_spots.append((ann_type, conv_id))

    # Cluster by annotation type
    by_type: dict[str, list[str]] = {}
    for ann_type, conv_id in blind_spots:
        if ann_type not in by_type:
            by_type[ann_type] = []
        by_type[ann_type].append(conv_id)

    clusters: list[BlindSpotCluster] = []
    suggestions_map = {
        "helpfulness": "Consider adding or tuning an evaluator for helpfulness (e.g., LLM-as-Judge with helpfulness rubric).",
        "quality": "Consider adding or tuning a response quality evaluator.",
        "factuality": "Consider adding a factuality-specific evaluator or strengthening factuality checks.",
        "overall": "Consider adding evaluators to catch failure modes currently missed by automation.",
    }
    for ann_type, conv_ids in by_type.items():
        unique_ids = list(dict.fromkeys(conv_ids))
        suggestion = suggestions_map.get(ann_type, f"Consider adding evaluator for '{ann_type}' failures.")
        clusters.append(
            BlindSpotCluster(
                annotation_type=ann_type,
                count=len(unique_ids),
                conversation_ids=unique_ids,
                evaluator_suggestion=suggestion,
            )
        )
    return sorted(clusters, key=lambda c: -c.count)


def get_latest_calibration(db: Session, evaluator_id: Optional[str] = None) -> list[CalibrationMetric]:
    """Get latest calibration metrics per (evaluator_id, score_type)."""
    q = select(CalibrationMetric).order_by(CalibrationMetric.computed_at.desc())
    if evaluator_id:
        q = q.where(CalibrationMetric.evaluator_id == evaluator_id)
    rows = db.execute(q).scalars().all()
    seen: set[tuple[str, Optional[str]]] = set()
    latest: list[CalibrationMetric] = []
    for m in rows:
        key = (m.evaluator_id, m.score_type)
        if key not in seen:
            seen.add(key)
            latest.append(m)
    return latest
