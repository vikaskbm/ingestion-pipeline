from typing import Any, Optional

from src.evaluators.base import BaseEvaluator
from src.evaluators.coherence_evaluator import CoherenceEvaluator
from src.evaluators.heuristic_evaluator import HeuristicEvaluator
from src.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
from src.evaluators.tool_call_evaluator import ToolCallEvaluator

EVALUATOR_REGISTRY: dict[str, BaseEvaluator] = {}


def register_evaluator(evaluator: BaseEvaluator) -> None:
    EVALUATOR_REGISTRY[evaluator.evaluator_id] = evaluator


register_evaluator(HeuristicEvaluator())
register_evaluator(LLMJudgeEvaluator())
register_evaluator(CoherenceEvaluator())
register_evaluator(ToolCallEvaluator())


def run_evaluators(
    conversation: dict[str, Any],
    evaluator_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    ids = evaluator_ids if evaluator_ids is not None else list(EVALUATOR_REGISTRY.keys())
    evaluators = [EVALUATOR_REGISTRY[eid] for eid in ids if eid in EVALUATOR_REGISTRY]

    scores: dict[str, float] = {}
    issues: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []

    for ev in evaluators:
        result = ev.evaluate(conversation)
        if "scores" in result:
            for k, v in result["scores"].items():
                if isinstance(v, (int, float)):
                    scores[f"{ev.evaluator_id}.{k}"] = float(v)
        if "issues" in result:
            issues.extend(result["issues"])
        if "suggestions" in result:
            suggestions.extend(result["suggestions"])

    return {
        "scores": scores,
        "issues": issues,
        "suggestions": suggestions,
    }
