from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ToolCallSchema(BaseModel):

    tool_name: str = Field(..., description="Name of the tool invoked")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    result: Optional[Any] = Field(None, description="Tool execution result")
    latency_ms: Optional[int] = Field(None, ge=0, description="Tool execution latency in milliseconds")


class TurnSchema(BaseModel):

    turn_id: int = Field(..., ge=1, description="Turn sequence number")
    role: str = Field(..., pattern="^(user|assistant)$", description="Turn role: user or assistant")
    content: str = Field(..., description="Message content")
    timestamp: Optional[Union[datetime, str]] = Field(None, description="ISO 8601 timestamp")
    tool_calls: Optional[list[ToolCallSchema]] = Field(None, description="Tool invocations (assistant turns only)")


class AnnotationSchema(BaseModel):

    type: str = Field(..., description="Annotation type (e.g., tool_accuracy, helpfulness)")
    label: str = Field(..., description="Annotation label/value")
    annotator_id: str = Field(..., description="ID of the annotator")


class OpsReviewSchema(BaseModel):

    quality: Optional[float] = Field(None, ge=0, le=1, description="Quality score 0-1")
    notes: Optional[str] = Field(None, description="Ops notes or comments")


class FeedbackSchema(BaseModel):

    user_rating: Optional[int | float] = Field(None, ge=0, description="User-provided rating (e.g., 1-5)")
    ops_review: Optional[OpsReviewSchema] = Field(None, description="Ops quality review")
    annotations: Optional[list[AnnotationSchema]] = Field(default_factory=list, description="Human annotations")


class ConversationMetadataSchema(BaseModel):

    total_latency_ms: Optional[int] = Field(None, ge=0, description="Total conversation latency in ms")
    mission_completed: Optional[bool] = Field(None, description="Whether the user's mission was completed")


class ConversationCreateSchema(BaseModel):

    conversation_id: str = Field(..., description="Unique conversation identifier")
    agent_version: str = Field(..., description="Agent version that handled the conversation")
    turns: list[TurnSchema] = Field(..., min_length=1, description="Ordered list of turns")
    feedback: Optional[FeedbackSchema] = Field(None, description="Feedback (user, ops, annotations)")
    metadata: Optional[ConversationMetadataSchema] = Field(None, description="Conversation metadata")


class ConversationResponseSchema(BaseModel):

    id: int = Field(..., description="Internal DB id")
    conversation_id: str = Field(..., description="Unique conversation identifier")
    agent_version: str = Field(..., description="Agent version")
    turns: list[TurnSchema] = Field(..., description="Ordered list of turns")
    feedback: Optional[FeedbackSchema] = Field(None, description="Feedback")
    metadata: Optional[ConversationMetadataSchema] = Field(None, description="Metadata")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
