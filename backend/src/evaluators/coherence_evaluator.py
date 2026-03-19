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

SYSTEM_PROMPT = """You are an expert evaluator of multi-turn AI agent conversations. Evaluate the conversation for coherence, consistency, and context resolution. Respond with a JSON object containing:
- coherence (0-1): Logical flow and relevance across turns. Do responses build on prior context?
- consistency (0-1): No contradictions with earlier statements. Are there conflicting claims or preferences?
- context_resolution (0-1): References like "that flight", "the earlier option" resolved correctly. Does the agent understand what the user refers to?
- rationale: A brief explanation (1-2 sentences).

Respond ONLY with valid JSON, no other text."""

USER_PROMPT_TEMPLATE = """Evaluate this multi-turn conversation for coherence, consistency, and context resolution:

{conversation_text}

Respond with JSON: {{"coherence": <0-1>, "consistency": <0-1>, "context_resolution": <0-1>, "rationale": "<string>"}}"""


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
                            "coherence": float(data.get("coherence", 0)),
                            "consistency": float(data.get("consistency", 0)),
                            "context_resolution": float(data.get("context_resolution", 0)),
                            "rationale": str(data.get("rationale", "")),
                        }
                    except (json.JSONDecodeError, ValueError, TypeError):
                        break
    return {
        "coherence": 0.0,
        "consistency": 0.0,
        "context_resolution": 0.0,
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


class CoherenceEvaluator(BaseEvaluator):
    def __init__(self, model: str | None = None, timeout: int | None = None):
        self._model = model or os.getenv("COHERENCE_EVALUATOR_MODEL", DEFAULT_MODEL)
        self._timeout = timeout or int(os.getenv("COHERENCE_EVALUATOR_TIMEOUT", str(DEFAULT_TIMEOUT)))

    @property
    def evaluator_id(self) -> str:
        return "coherence"

    @property
    def evaluator_name(self) -> str:
        return "Multi-turn Coherence Evaluator"

    def evaluate(self, conversation: dict[str, Any]) -> dict[str, Any]:
        turns = conversation.get("turns") or []
        if len(turns) < 2:
            return {
                "scores": {"coherence": 1.0, "consistency": 1.0, "context_resolution": 1.0},
                "issues": [],
                "suggestions": [],
            }

        conversation_text = _format_turns_for_prompt(turns)
        user_prompt = USER_PROMPT_TEMPLATE.format(conversation_text=conversation_text)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = _call_llm(messages, self._model, self._timeout)
            parsed = _parse_llm_response(content)
            return {
                "scores": {
                    "coherence": parsed["coherence"],
                    "consistency": parsed["consistency"],
                    "context_resolution": parsed["context_resolution"],
                },
                "issues": [],
                "suggestions": [
                    {
                        "type": "coherence",
                        "suggestion": parsed["rationale"],
                        "rationale": parsed["rationale"],
                        "confidence": 0.8,
                    }
                ],
            }
        except Exception as e:
            return {
                "scores": {"coherence": 0.0, "consistency": 0.0, "context_resolution": 0.0},
                "issues": [
                    {
                        "type": "llm_error",
                        "severity": "warning",
                        "description": f"Coherence evaluation failed: {e}",
                        "turn_id": None,
                    }
                ],
                "suggestions": [],
            }
