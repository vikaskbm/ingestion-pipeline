import os
from collections import Counter
from typing import Any, Optional

DISAGREEMENT_THRESHOLD = 2
TIEBREAKER_ANNOTATOR_ENV = "TIEBREAKER_ANNOTATOR_ID"


def resolve_labels(
    annotations: list[dict[str, Any]],
    tiebreaker_annotator_id: Optional[str] = None,
) -> dict[str, Any]:
    if not annotations:
        return {"resolved_label": None, "agreement": True, "needs_review": False}

    tiebreaker = tiebreaker_annotator_id or os.getenv(TIEBREAKER_ANNOTATOR_ENV)
    labels = [a.get("label") for a in annotations if a.get("label") is not None]

    if not labels:
        return {"resolved_label": None, "agreement": True, "needs_review": False}

    counter = Counter(labels)
    most_common = counter.most_common(2)

    if len(most_common) == 1:
        return {
            "resolved_label": most_common[0][0],
            "agreement": True,
            "needs_review": False,
        }

    top_label, top_count = most_common[0]
    second_label, second_count = most_common[1]

    if top_count > second_count:
        return {
            "resolved_label": top_label,
            "agreement": True,
            "needs_review": False,
        }

    if tiebreaker:
        for a in annotations:
            if a.get("annotator_id") == tiebreaker:
                return {
                    "resolved_label": a.get("label"),
                    "agreement": False,
                    "needs_review": False,
                }

    needs_review = len(annotations) >= int(os.getenv("DISAGREEMENT_THRESHOLD", str(DISAGREEMENT_THRESHOLD)))
    return {
        "resolved_label": top_label,
        "agreement": False,
        "needs_review": needs_review,
    }


def get_resolved_feedback_for_type(
    annotations: list[dict[str, Any]],
    annotation_type: str,
    tiebreaker_annotator_id: Optional[str] = None,
) -> dict[str, Any]:
    filtered = [a for a in annotations if a.get("type") == annotation_type]
    result = resolve_labels(filtered, tiebreaker_annotator_id)
    result["type"] = annotation_type
    return result
