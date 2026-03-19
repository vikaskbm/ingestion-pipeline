import json
import os
import time
from typing import Any, Optional

from litellm import completion

from src.evaluators.base import BaseEvaluator

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2.0

SYSTEM_PROMPT = """You are an expert evaluator of AI agent conversations. Evaluate the conversation and respond with a JSON object containing:
- response_quality (0-1): How well-formed, coherent, and appropriate are the assistant's responses?
- helpfulness (0-1): How helpful was the agent in addressing the user's needs?
- factuality (0-1): How accurate and factually correct is the information provided?
- rationale: A brief explanation of your scores (1-2 sentences).

Respond ONLY with valid JSON, no other text."""

USER_PROMPT_TEMPLATE = """Evaluate this AI agent conversation:

{conversation_text}

{custom_rubric}

Respond with JSON: {{"response_quality": <0-1>, "helpfulness": <0-1>, "factuality": <0-1>, "rationale": "<string>"}}"""


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
            result_str = f" -> {json.dumps(result)[:100]}..." if result else ""
            parts.append(f"  [tool: {name}({params_str}){result_str}]")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _parse_llm_response(text: str) -> dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        return {
                            "response_quality": float(data.get("response_quality", 0)),
                            "helpfulness": float(data.get("helpfulness", 0)),
                            "factuality": float(data.get("factuality", 0)),
                            "rationale": str(data.get("rationale", "")),
                        }
                    except (json.JSONDecodeError, ValueError, TypeError):
                        break
    return {
        "response_quality": 0.0,
        "helpfulness": 0.0,
        "factuality": 0.0,
        "rationale": "Failed to parse LLM response",
    }


def _call_llm(
    messages: list[dict[str, str]],
    model: str,
    timeout: int,
) -> str:
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


class LLMJudgeEvaluator(BaseEvaluator):
    def __init__(
        self,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self._model = model or os.getenv("LLM_JUDGE_MODEL", DEFAULT_MODEL)
        self._timeout = timeout or int(os.getenv("LLM_JUDGE_TIMEOUT", str(DEFAULT_TIMEOUT)))

    @property
    def evaluator_id(self) -> str:
        return "llm_judge"

    @property
    def evaluator_name(self) -> str:
        return "LLM-as-Judge Evaluator"

    def evaluate(self, conversation: dict[str, Any]) -> dict[str, Any]:
        turns = conversation.get("turns") or []
        rubric = conversation.get("rubric")
        conversation_text = _format_turns_for_prompt(turns)
        custom_rubric = ""
        if rubric:
            custom_rubric = f"Additional criteria to consider:\n{rubric}\n\n"

        user_prompt = USER_PROMPT_TEMPLATE.format(
            conversation_text=conversation_text,
            custom_rubric=custom_rubric,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = _call_llm(messages, self._model, self._timeout)
            parsed = _parse_llm_response(content)
            return {
                "scores": {
                    "response_quality": parsed["response_quality"],
                    "helpfulness": parsed["helpfulness"],
                    "factuality": parsed["factuality"],
                },
                "issues": [],
                "suggestions": [
                    {
                        "type": "llm_judge",
                        "suggestion": parsed["rationale"],
                        "rationale": parsed["rationale"],
                        "confidence": 0.8,
                    }
                ],
            }
        except Exception as e:
            return {
                "scores": {
                    "response_quality": 0.0,
                    "helpfulness": 0.0,
                    "factuality": 0.0,
                },
                "issues": [
                    {
                        "type": "llm_error",
                        "severity": "warning",
                        "description": f"LLM evaluation failed: {e}",
                        "turn_id": None,
                    }
                ],
                "suggestions": [],
            }
