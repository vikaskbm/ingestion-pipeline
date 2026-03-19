from typing import Optional

from pydantic import BaseModel, Field

from src.schemas.evaluation import ImprovementSuggestionSchema


class SuggestionFilterSchema(BaseModel):

    type: Optional[str] = Field(None, description="Filter by suggestion type")
    min_confidence: Optional[float] = Field(None, ge=0, le=1, description="Minimum confidence threshold")
    affected_component: Optional[str] = Field(None, description="Filter by affected component")


class SuggestionResponseSchema(BaseModel):

    items: list[ImprovementSuggestionSchema] = Field(..., description="List of suggestion items")
    total: int = Field(..., ge=0, description="Total count for pagination")
    page: int = Field(1, ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
