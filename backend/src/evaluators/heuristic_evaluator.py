import json
import os
import re
from typing import Any

from src.evaluators.base import BaseEvaluator

DATE_PARAM_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$"
)
DATE_RANGE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$"
)
DEFAULT_DATE_PARAM_NAMES = frozenset(
    {"date", "start_date", "end_date", "departure_date", "arrival_date", "date_range"}
)


def _get_int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val and val.isdigit() else default


def _get_date_param_names() -> frozenset[str]:
    val = os.getenv("HEURISTIC_DATE_PARAM_NAMES")
    if val:
        return frozenset(p.strip().lower() for p in val.split(",") if p.strip())
    return DEFAULT_DATE_PARAM_NAMES


def _get_required_params() -> dict[str, list[str]]:
    val = os.getenv("HEURISTIC_REQUIRED_PARAMS")
    if val:
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass
    return {}


def _add_issue(
    issues: list[dict[str, Any]],
    issue_type: str,
    severity: str,
    description: str,
    turn_id: int | None = None,
) -> None:
    issues.append({
        "type": issue_type,
        "severity": severity,
        "description": description,
        "turn_id": turn_id,
    })


def _is_valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if DATE_PARAM_PATTERN.match(value):
        return True
    if DATE_RANGE_PATTERN.match(value):
        return True
    return False


class HeuristicEvaluator(BaseEvaluator):
    @property
    def evaluator_id(self) -> str:
        return "heuristic"

    @property
    def evaluator_name(self) -> str:
        return "Heuristic Evaluator"

    def evaluate(self, conversation: dict[str, Any]) -> dict[str, Any]:
        total_latency_ms = _get_int_env("HEURISTIC_TOTAL_LATENCY_MS", 1000)
        tool_latency_ms = _get_int_env("HEURISTIC_TOOL_LATENCY_MS", 500)
        max_response_length = _get_int_env("HEURISTIC_MAX_RESPONSE_LENGTH", 0)
        date_param_names = _get_date_param_names()
        required_params = _get_required_params()

        issues: list[dict[str, Any]] = []
        turns = conversation.get("turns") or []
        metadata = conversation.get("metadata") or {}

        if metadata.get("total_latency_ms") is not None:
            tlm = metadata["total_latency_ms"]
            if isinstance(tlm, (int, float)) and tlm > total_latency_ms:
                severity = "critical" if tlm > total_latency_ms * 2 else "warning"
                _add_issue(
                    issues,
                    "total_latency",
                    severity,
                    f"Total latency {tlm}ms exceeds threshold {total_latency_ms}ms",
                    None,
                )

        for turn in turns:
            turn_id = turn.get("turn_id")
            tool_calls = turn.get("tool_calls") or []
            content = turn.get("content") or ""

            for tc in tool_calls:
                latency = tc.get("latency_ms")
                if latency is not None and isinstance(latency, (int, float)) and latency > tool_latency_ms:
                    _add_issue(
                        issues,
                        "tool_latency",
                        "warning",
                        f"Tool {tc.get('tool_name', '?')} latency {latency}ms exceeds {tool_latency_ms}ms",
                        turn_id,
                    )

                tool_name = tc.get("tool_name", "")
                params = tc.get("parameters") or {}

                req_params = required_params.get(tool_name, [])
                for rp in req_params:
                    if rp not in params or params[rp] is None or params[rp] == "":
                        _add_issue(
                            issues,
                            "required_field",
                            "critical",
                            f"Tool {tool_name} missing required parameter '{rp}'",
                            turn_id,
                        )

                for pname, pval in params.items():
                    if pname.lower() in date_param_names and pval:
                        if not _is_valid_date(pval):
                            _add_issue(
                                issues,
                                "date_format",
                                "warning",
                                f"Parameter '{pname}' value '{pval}' is not ISO 8601 or YYYY-MM-DD",
                                turn_id,
                            )

            if max_response_length > 0 and content and len(content) > max_response_length:
                _add_issue(
                    issues,
                    "response_length",
                    "info",
                    f"Response length {len(content)} exceeds max {max_response_length}",
                    turn_id,
                )

        passed = len([i for i in issues if i["severity"] == "critical"]) == 0
        score = 0.0 if not passed else max(0, 1.0 - len(issues) * 0.1)

        return {
            "scores": {"heuristic_pass": 1.0 if passed else 0.0, "heuristic_score": min(1.0, score)},
            "issues": issues,
            "suggestions": [],
        }
