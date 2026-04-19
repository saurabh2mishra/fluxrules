from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EvaluateRequest(BaseModel):
    facts: dict[str, Any]


class SimulateRequest(BaseModel):
    samples: list[dict[str, Any]]


class EvaluateResponse(BaseModel):
    execution_id: str
    matched_rules: list[str]
    actions: list[str]


class ExplainResponse(BaseModel):
    execution_id: str
    matched_rules: list[str]
    actions: list[str]
    trace: list[dict[str, Any]]


class ValidateResponse(BaseModel):
    issues: list[str]
