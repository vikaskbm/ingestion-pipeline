import json
import os
import time
from typing import Any

from litellm import completion

from src.evaluators.base import BaseEvaluator

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2.0

SYSTEM_PROMPT = """You evaluate AI agent tool calls. For each tool call, assess:
1. selection_accuracy (0-1): Was the correct tool selected for the user's intent?
2. parameter_accuracy (0-1): Were parameters correctly extracted from context?
3. hallucination_detected (true/false): Were any parameters made up or not derivable from the conversation?

Respond with a JSON array: one object per tool call in order, each with selection_accuracy, parameter_accuracy, hallucination_detected.
If there are no tool calls, respond with []."""

USER_PROMPT_TEMPLATE = """Conversation:

{conversation_text}

Tool calls to evaluate (in order):
{tool_calls_text}

Respond with JSON array only, e.g. [{{"selection_accuracy": 0.9, "parameter_accuracy": 0.85, "hallucination_detected": false}}, ...]"""


def _format_turns_for_prompt(turns: list[dict[str, Any]]) -> str:
    lines = []
    for t in turns:
        role = t.get("role", "unknown")
        content = (t.get("content") or "").strip()
        tool_calls = t.get("tool_calls") or []
        parts = [f"[{role}] {content}"]
        for tc in tool_calls:
            name = tc.get("tool_name", "?")
            params = tc.get("parameters", {})
            params_str = json.dumps(params) if params else ""
            result = tc.get("result")
            result_str = f" -> {json.dumps(result)[:80]}..." if result else ""
            parts.append(f"  [tool: {name}({params_str}){result_str}]")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _check_execution_success(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, dict):
        status = result.get("status", result.get("success"))
        if status is True or (isinstance(status, str) and status.lower() == "success"):
            return True
        if status is False or (isinstance(status, str) and status.lower() in ("fail", "error")):
            return False
    return True


def _parse_llm_tool_eval(text: str, num_tool_calls: int) -> list[dict[str, Any]]:
    text = text.strip()
    start = text.find("[")
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        if not isinstance(data, list):
                            data = [data]
                        results = []
                        for item in data:
                            if isinstance(item, dict):
                                results.append({
                                    "selection_accuracy": float(item.get("selection_accuracy", 0)),
                                    "parameter_accuracy": float(item.get("parameter_accuracy", 0)),
                                    "hallucination_detected": bool(item.get("hallucination_detected", False)),
                                })
                            else:
                                results.append({
                                    "selection_accuracy": 0.0,
                                    "parameter_accuracy": 0.0,
                                    "hallucination_detected": False,
                                })
                        return results[:num_tool_calls]
                    except (json.JSONDecodeError, ValueError, TypeError):
                        break
    return []


def _call_llm(messages: list[dict[str, str]], model: str, timeout: int) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            response = completion(
                model=model,
                messages=messages,
                timeout=timeout,
                temperature=0.1,
            )
            content = response.choices[0].message.content
            if content:
                return content
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            raise
    return ""


class ToolCallEvaluator(BaseEvaluator):
    def __init__(self, model: str | None = None, timeout: int | None = None):
        self._model = model or os.getenv("TOOL_CALL_EVALUATOR_MODEL", DEFAULT_MODEL)
        self._timeout = timeout or int(os.getenv("TOOL_CALL_EVALUATOR_TIMEOUT", str(DEFAULT_TIMEOUT)))

    @property
    def evaluator_id(self) -> str:
        return "tool_call"

    @property
    def evaluator_name(self) -> str:
        return "Tool Call Evaluator"

    def evaluate(self, conversation: dict[str, Any]) -> dict[str, Any]:
        turns = conversation.get("turns") or []
        tool_calls_flat: list[tuple[int, dict[str, Any]]] = []
        for t in turns:
            turn_id = t.get("turn_id")
            for tc in t.get("tool_calls") or []:
                tool_calls_flat.append((turn_id, tc))

        if not tool_calls_flat:
            return {
                "scores": {
                    "selection_accuracy": 1.0,
                    "parameter_accuracy": 1.0,
                    "hallucination_detected": 0.0,
                    "execution_success": 1.0,
                },
                "issues": [],
                "suggestions": [],
            }

        exec_successes = []
        for turn_id, tc in tool_calls_flat:
            result = tc.get("result")
            exec_successes.append(_check_execution_success(result))

        exec_success_rate = sum(exec_successes) / len(exec_successes) if exec_successes else 1.0

        conversation_text = _format_turns_for_prompt(turns)
        tool_calls_text = "\n".join(
            f"{i+1}. {tc.get('tool_name', '?')}({json.dumps(tc.get('parameters', {}))})"
            for i, (_, tc) in enumerate(tool_calls_flat)
        )

        try:
            user_prompt = USER_PROMPT_TEMPLATE.format(
                conversation_text=conversation_text,
                tool_calls_text=tool_calls_text,
            )
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            content = _call_llm(messages, self._model, self._timeout)
            llm_results = _parse_llm_tool_eval(content, len(tool_calls_flat))

            selection_accs = []
            param_accs = []
            halluc_count = 0

            for i, (_, tc) in enumerate(tool_calls_flat):
                if i < len(llm_results):
                    r = llm_results[i]
                    selection_accs.append(r["selection_accuracy"])
                    param_accs.append(r["parameter_accuracy"])
                    if r["hallucination_detected"]:
                        halluc_count += 1
                else:
                    selection_accs.append(0.5)
                    param_accs.append(0.5)

            selection_accuracy = sum(selection_accs) / len(selection_accs) if selection_accs else 0.0
            parameter_accuracy = sum(param_accs) / len(param_accs) if param_accs else 0.0
            hallucination_rate = halluc_count / len(tool_calls_flat) if tool_calls_flat else 0.0

            return {
                "scores": {
                    "selection_accuracy": selection_accuracy,
                    "parameter_accuracy": parameter_accuracy,
                    "hallucination_detected": hallucination_rate,
                    "execution_success": exec_success_rate,
                },
                "issues": [],
                "suggestions": [],
            }
        except Exception as e:
            return {
                "scores": {
                    "selection_accuracy": 0.0,
                    "parameter_accuracy": 0.0,
                    "hallucination_detected": 0.0,
                    "execution_success": exec_success_rate,
                },
                "issues": [
                    {
                        "type": "llm_error",
                        "severity": "warning",
                        "description": f"Tool call evaluation failed: {e}",
                        "turn_id": None,
                    }
                ],
                "suggestions": [],
            }
