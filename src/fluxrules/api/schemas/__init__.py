"""API Schemas package."""

from typing import Any

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    execution_id: str
    matched_rules: list[int] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    execution_id: str
    matched_rules: list[int] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] | None = None


class SimulateRequest(BaseModel):
    samples: list[dict[str, Any]] = Field(default_factory=list)


class ValidateResponse(BaseModel):
    issues: list[str] = Field(default_factory=list)
