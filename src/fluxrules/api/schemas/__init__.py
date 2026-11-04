"""API Schemas package."""

from typing import Any

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)


class ComparisonIssueResponse(BaseModel):
    """A comparison that could not be made, such as ``"abc" > 5``."""

    field: str
    operator: str
    fact_type: str
    rule_type: str
    reason: str


def comparison_issues(result: Any) -> list[ComparisonIssueResponse]:
    """The result's comparison issues as response models."""
    return [
        ComparisonIssueResponse(**issue.to_dict())
        for issue in getattr(result, "comparison_issues", ())
    ]


class EvaluateResponse(BaseModel):
    execution_id: str
    matched_rules: list[int] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    comparison_issues: list[ComparisonIssueResponse] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    execution_id: str
    matched_rules: list[int] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] | None = None


class SimulateRequest(BaseModel):
    samples: list[dict[str, Any]] = Field(default_factory=list)


class ValidateResponse(BaseModel):
    issues: list[str] = Field(default_factory=list)
