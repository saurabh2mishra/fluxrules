from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RuleRuntimeMetric(BaseModel):
    rule_id: str
    rule_name: str | None = None
    hit_count: int = 0
    total_execution_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    last_fired_at: datetime | None = None


class RuleExplainabilityEntry(BaseModel):
    rule_id: str
    explanation: str
    matched_conditions: list[str] = Field(default_factory=list)
    missing_conditions: list[str] = Field(default_factory=list)
    sample_fact: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class RuntimeAnalyticsSummary(BaseModel):
    total_rules: int
    triggered_rules: int
    coverage_pct: float
    rules_never_fired_count: int
    events_processed: int
    rules_fired: int
    avg_processing_time_ms: float


class TopRulesResponse(BaseModel):
    top_hot_rules: list[RuleRuntimeMetric] = Field(default_factory=list)
    cold_rules: list[RuleRuntimeMetric] = Field(default_factory=list)


class RuleRuntimeDetail(BaseModel):
    metric: RuleRuntimeMetric
    recent_explanations: list[RuleExplainabilityEntry] = Field(default_factory=list)


class AnalyticsCoverageResponse(BaseModel):
    summary: RuntimeAnalyticsSummary
    triggered_rule_ids: list[str] = Field(default_factory=list)
    never_fired_rule_ids: list[str] = Field(default_factory=list)


class RuntimeAnalyticsResponse(BaseModel):
    summary: RuntimeAnalyticsSummary
    top_hot_rules: list[RuleRuntimeMetric] = Field(default_factory=list)
    cold_rules: list[RuleRuntimeMetric] = Field(default_factory=list)
    recent_explanations: list[RuleExplainabilityEntry] = Field(default_factory=list)
