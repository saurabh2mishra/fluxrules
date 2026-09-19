from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConditionNode(BaseModel):
    type: str
    op: str | None = None
    field: str | None = None
    value: Any | None = None
    children: list["ConditionNode"] | None = None


class RuleBase(BaseModel):
    name: str
    description: str | None = None
    group: str | None = None
    priority: int = 0
    enabled: bool = True
    condition_dsl: dict[str, Any]
    action: str
    rule_metadata: dict[str, Any] | None = None
    evaluation_mode: str | None = "stateless"


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    group: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    condition_dsl: dict[str, Any] | None = None
    action: str | None = None
    rule_metadata: dict[str, Any] | None = None
    evaluation_mode: str | None = "stateless"


class RuleResponse(RuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None


class RuleVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    version: int
    name: str
    description: str | None = None
    group: str | None = None
    priority: int
    enabled: bool
    condition_dsl: dict[str, Any]
    action: str
    rule_metadata: dict[str, Any] | None = None
    created_at: datetime
    created_by: int | None = None


class SimulateRequest(BaseModel):
    event: dict[str, Any]
    rule_ids: list[int] | None = None


class SimulateStats(BaseModel):
    total_rules: int | None = None
    candidates_evaluated: int | None = None
    rules_matched: int | None = None
    evaluation_time_ms: float | None = None
    optimization: str | None = None


class SimulateResponse(BaseModel):
    matched_rules: list[dict[str, Any]]
    execution_order: list[int]
    explanations: dict[int, str]
    dry_run: bool = True
    stats: SimulateStats | None = None


class DependencyGraph(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ConflictReport(BaseModel):
    conflicts: list[dict[str, Any]]
