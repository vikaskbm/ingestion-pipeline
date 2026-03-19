"""
Failure clustering service: query evaluations with issues and group by type, tool, version.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.models.conversation import Conversation
from src.models.evaluation import Evaluation

# Pattern to extract tool name from issue descriptions like "Tool search_flights latency..." or "Tool X missing..."
TOOL_NAME_PATTERN = re.compile(r"^Tool\s+(\S+)\s+", re.IGNORECASE)
# Words that are not tool names (e.g. "call" from "Tool call evaluation failed")
TOOL_NAME_BLACKLIST = frozenset({"call", "evaluation", "latency", "missing"})


@dataclass
class FailureCluster:
    """A cluster of failures grouped by type, tool, and agent version."""

    issue_type: str
    tool_name: Optional[str]
    agent_version: str
    size: int
    frequency: float  # occurrences per evaluation in cluster
    conversation_ids: list[str] = field(default_factory=list)
    sample_descriptions: list[str] = field(default_factory=list)


def _extract_tool_name(issue: dict[str, Any]) -> Optional[str]:
    """Extract tool name from issue description if present."""
    desc = issue.get("description") or ""
    m = TOOL_NAME_PATTERN.match(desc)
    if not m:
        return None
    name = m.group(1).lower()
    return m.group(1) if name not in TOOL_NAME_BLACKLIST else None


def _is_tool_related(issue_type: str) -> bool:
    """Whether this issue type is typically tool-related."""
    return issue_type in (
        "required_field",
        "date_format",
        "tool_latency",
        "tool_failure",
        "parameter_accuracy",
        "selection_accuracy",
        "hallucination_detected",
        "execution_success",
    )


def get_evaluations_with_issues(
    db: Session,
    agent_version: Optional[str] = None,
    limit: int = 1000,
) -> list[tuple[Evaluation, list[dict[str, Any]]]]:
    """
    Query evaluations that have at least one issue.
    Returns list of (evaluation, issues) tuples.
    """
    q = (
        select(Evaluation)
        .join(Conversation, Evaluation.conversation_id == Conversation.id)
        .where(Evaluation.issues_json.isnot(None))
        .options(joinedload(Evaluation.conversation))
    )
    if agent_version:
        q = q.where(Conversation.agent_version == agent_version)
    q = q.order_by(Evaluation.created_at.desc()).limit(limit)
    rows = db.execute(q).scalars().all()

    result: list[tuple[Evaluation, list[dict[str, Any]]]] = []
    for ev in rows:
        issues = ev.issues_json or []
        if issues:
            result.append((ev, issues))
    return result


def cluster_failures(
    db: Session,
    agent_version: Optional[str] = None,
    min_cluster_size: int = 1,
) -> list[FailureCluster]:
    """
    Group evaluations with issues by issue_type, tool_name (for tool-related), and agent_version.
    Compute cluster size, frequency, and collect conversation IDs for evidence.
    """
    evals_with_issues = get_evaluations_with_issues(db, agent_version=agent_version)

    # Key: (issue_type, tool_name or "", agent_version) -> list of (conv_id, description)
    clusters: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)

    for ev, issues in evals_with_issues:
        conv = ev.conversation
        conv_id_str = conv.conversation_id if conv else ""
        agent_ver = conv.agent_version if conv else ""

        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_type = issue.get("type") or "unknown"
            description = issue.get("description") or ""

            tool_name = _extract_tool_name(issue)
            if not tool_name and _is_tool_related(issue_type):
                tool_name = None  # keep as None for grouping
            tool_key = tool_name or ""

            key = (issue_type, tool_key, agent_ver)
            clusters[key].append((conv_id_str, description))

    result: list[FailureCluster] = []
    for (issue_type, tool_key, agent_ver), items in clusters.items():
        if len(items) < min_cluster_size:
            continue
        conv_ids = list(dict.fromkeys(c for c, _ in items))  # unique, preserve order
        descriptions = list(dict.fromkeys(d for _, d in items))[:5]  # unique sample, max 5
        tool_name = tool_key if tool_key else None
        frequency = len(items) / max(1, len(conv_ids))
        result.append(
            FailureCluster(
                issue_type=issue_type,
                tool_name=tool_name,
                agent_version=agent_ver,
                size=len(items),
                frequency=round(frequency, 2),
                conversation_ids=conv_ids,
                sample_descriptions=descriptions,
            )
        )

    result.sort(key=lambda c: (-c.size, c.issue_type))
    return result
