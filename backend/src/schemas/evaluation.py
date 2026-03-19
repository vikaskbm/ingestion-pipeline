from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class IssueSchema(BaseModel):

    type: str = Field(..., description="Issue type (e.g., context_loss, hallucination)")
    severity: str = Field(..., description="Severity: critical, warning, info")
    description: str = Field(..., description="Human-readable description")
    turn_id: Optional[int] = Field(None, description="Associated turn ID if applicable")


class ToolEvaluationSchema(BaseModel):

    selection_accuracy: Optional[float] = Field(None, ge=0, le=1, description="Correct tool selection score")
    parameter_accuracy: Optional[float] = Field(None, ge=0, le=1, description="Correct parameter score")
    hallucination_detected: Optional[bool] = Field(None, description="Whether hallucination was detected")
    execution_success: Optional[bool] = Field(None, description="Whether tool execution succeeded")


class ImprovementSuggestionSchema(BaseModel):

    type: str = Field(..., description="Suggestion type (e.g., prompt, tool, system)")
    suggestion: str = Field(..., description="The suggestion text")
    rationale: Optional[str] = Field(None, description="Reasoning for the suggestion")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Confidence score 0-1")
    affected_components: Optional[list[str]] = Field(None, description="Components this affects")
    evidence: Optional[Union[list[str], dict[str, Any]]] = Field(None, description="Supporting evidence")


class EvaluationCreateSchema(BaseModel):

    conversation_id: str = Field(..., description="Conversation to evaluate")
    agent_version: Optional[str] = Field(None, description="Agent version (optional)")
    evaluator_ids: Optional[list[str]] = Field(None, description="Specific evaluators to run (default: all)")


class EvaluationBatchCreateSchema(BaseModel):

    conversation_ids: list[str] = Field(..., min_length=1, description="Conversations to evaluate")
    agent_version: Optional[str] = Field(None, description="Agent version (optional)")
    evaluator_ids: Optional[list[str]] = Field(None, description="Specific evaluators to run (default: all)")


class EvaluationResponseSchema(BaseModel):

    id: int = Field(..., description="Internal DB id")
    evaluation_id: str = Field(..., description="Unique evaluation identifier")
    conversation_id: str = Field(..., description="Evaluated conversation")
    scores: Optional[dict[str, float]] = Field(None, description="Evaluator scores (e.g., quality, coherence)")
    tool_eval: Optional[Union[ToolEvaluationSchema, dict[str, Any]]] = Field(
        None, description="Tool call evaluation"
    )
    issues: Optional[list[IssueSchema]] = Field(default_factory=list, description="Detected issues")
    suggestions: Optional[list[ImprovementSuggestionSchema]] = Field(
        default_factory=list, description="Improvement suggestions"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
