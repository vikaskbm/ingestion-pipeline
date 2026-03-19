"""
Suggestion generator: map failure clusters to prompt and tool suggestions.
"""

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.models.suggestion import Suggestion
from src.services.failure_clustering_service import FailureCluster, cluster_failures

# Extract parameter name from descriptions like "Tool X missing required parameter 'Y'" or "Parameter 'Y' value..."
PARAM_PATTERN = re.compile(r"parameter\s+['\"]?(\w+)['\"]?", re.IGNORECASE)
PARAM_PATTERN_2 = re.compile(r"Parameter\s+['\"]?(\w+)['\"]?", re.IGNORECASE)


def _extract_param_name(cluster: FailureCluster) -> Optional[str]:
    """Extract parameter name from sample descriptions."""
    for desc in cluster.sample_descriptions:
        m = PARAM_PATTERN.search(desc) or PARAM_PATTERN_2.search(desc)
        if m:
            return m.group(1)
    return None


def _compute_confidence(cluster: FailureCluster) -> float:
    """Confidence based on cluster size and consistency (how often per conversation)."""
    if cluster.size < 2:
        return 0.3
    # More occurrences = higher confidence; frequency > 1 = same conv had multiple = stronger signal
    size_score = min(1.0, cluster.size / 10) * 0.5
    freq_score = min(1.0, cluster.frequency) * 0.5
    return round(min(1.0, 0.3 + size_score + freq_score), 2)


def _cluster_to_prompt_suggestion(cluster: FailureCluster) -> Optional[dict[str, Any]]:
    """Map failure cluster to a prompt suggestion."""
    confidence = _compute_confidence(cluster)
    evidence = {"conversation_ids": cluster.conversation_ids[:10], "cluster_size": cluster.size}

    if cluster.issue_type == "date_format":
        return {
            "type": "prompt",
            "suggestion": "Add ISO 8601 format instruction for date parameters (e.g., YYYY-MM-DD or full ISO 8601).",
            "rationale": f"Date format issues detected {cluster.size} times across {len(cluster.conversation_ids)} conversations.",
            "confidence": confidence,
            "affected_components": ["prompt", "system_instructions"],
            "evidence": evidence,
        }

    if cluster.issue_type == "tool_latency":
        tool_part = f" for tool '{cluster.tool_name}'" if cluster.tool_name else ""
        return {
            "type": "prompt",
            "suggestion": f"Optimize tool latency{tool_part} or add caching for frequently used tools.",
            "rationale": f"Tool latency exceeded threshold {cluster.size} times.",
            "confidence": confidence,
            "affected_components": ["prompt", "tool_config"] if cluster.tool_name else ["prompt"],
            "evidence": evidence,
        }

    if cluster.issue_type == "total_latency":
        return {
            "type": "prompt",
            "suggestion": "Optimize overall response latency; consider parallel tool calls or streaming.",
            "rationale": f"Total latency exceeded threshold {cluster.size} times.",
            "confidence": confidence,
            "affected_components": ["prompt", "system"],
            "evidence": evidence,
        }

    if cluster.issue_type == "response_length":
        return {
            "type": "prompt",
            "suggestion": "Add instruction to keep responses concise or summarize long outputs.",
            "rationale": f"Response length exceeded limit {cluster.size} times.",
            "confidence": confidence,
            "affected_components": ["prompt"],
            "evidence": evidence,
        }

    return None


def _cluster_to_tool_suggestion(cluster: FailureCluster) -> Optional[dict[str, Any]]:
    """Map failure cluster to a tool suggestion. Returns at most one suggestion per cluster."""
    confidence = _compute_confidence(cluster)
    evidence = {"conversation_ids": cluster.conversation_ids[:10], "cluster_size": cluster.size}
    param_name = _extract_param_name(cluster)

    if cluster.issue_type == "required_field":
        param = param_name or "X"
        tool = cluster.tool_name or "tool"
        return {
            "type": "tool",
            "suggestion": f"Parameter '{param}' often missing for {tool}; consider making optional or adding clearer parameter descriptions.",
            "rationale": f"Required parameter missing {cluster.size} times.",
            "confidence": confidence,
            "affected_components": [f"tool:{tool}" if cluster.tool_name else "tool_schema"],
            "evidence": evidence,
        }

    if cluster.issue_type == "date_format" and (cluster.tool_name or param_name):
        param = param_name or "date parameter"
        tool_part = f" in {cluster.tool_name}" if cluster.tool_name else " in tool schema"
        components = [f"tool:{cluster.tool_name}"] if cluster.tool_name else ["tool_schema"]
        return {
            "type": "tool",
            "suggestion": f"Clarify format for parameter '{param}'{tool_part}: use ISO 8601 (YYYY-MM-DD) in parameter description.",
            "rationale": f"Date format issues for {param} detected {cluster.size} times.",
            "confidence": confidence,
            "affected_components": components,
            "evidence": evidence,
        }

    if cluster.issue_type == "tool_latency" and cluster.tool_name:
        return {
            "type": "tool",
            "suggestion": f"Review implementation of '{cluster.tool_name}'; consider caching or async execution.",
            "rationale": f"Tool latency exceeded threshold {cluster.size} times.",
            "confidence": confidence,
            "affected_components": [f"tool:{cluster.tool_name}"],
            "evidence": evidence,
        }

    # Generic validation suggestion for other parameter-related issues
    if param_name and cluster.issue_type not in ("required_field", "date_format", "tool_latency"):
        tool = cluster.tool_name or "tool"
        return {
            "type": "tool",
            "suggestion": f"Add validation for parameter '{param_name}' in {tool} (e.g., format, required checks).",
            "rationale": f"Issues with parameter '{param_name}' detected {cluster.size} times.",
            "confidence": confidence,
            "affected_components": [f"tool:{tool}"],
            "evidence": evidence,
        }

    return None


def generate_suggestions(db: Session, agent_version: Optional[str] = None) -> list[Suggestion]:
    """
    Run failure clustering, map clusters to suggestions, and store in Suggestion model.
    Returns list of created Suggestion records.
    """
    clusters = cluster_failures(db, agent_version=agent_version, min_cluster_size=1)
    created: list[Suggestion] = []

    for cluster in clusters:
        # Prompt suggestions
        prompt_sug = _cluster_to_prompt_suggestion(cluster)
        if prompt_sug:
            s = Suggestion(
                type=prompt_sug["type"],
                suggestion=prompt_sug["suggestion"],
                rationale=prompt_sug.get("rationale"),
                confidence=prompt_sug.get("confidence"),
                affected_components_json=prompt_sug.get("affected_components"),
                evidence_json=prompt_sug.get("evidence"),
            )
            db.add(s)
            created.append(s)

        # Tool suggestions (avoid duplicate if same cluster yielded both)
        tool_sug = _cluster_to_tool_suggestion(cluster)
        if tool_sug and tool_sug != prompt_sug:
            s = Suggestion(
                type=tool_sug["type"],
                suggestion=tool_sug["suggestion"],
                rationale=tool_sug.get("rationale"),
                confidence=tool_sug.get("confidence"),
                affected_components_json=tool_sug.get("affected_components"),
                evidence_json=tool_sug.get("evidence"),
            )
            db.add(s)
            created.append(s)

    db.commit()
    for s in created:
        db.refresh(s)
    return created
