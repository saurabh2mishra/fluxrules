from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RuleRuntimeMetric(BaseModel):
    rule_id: str
    rule_name: Optional[str] = None
    hit_count: int = 0
    total_execution_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    last_fired_at: Optional[datetime] = None


class RuleExplainabilityEntry(BaseModel):
    rule_id: str
    explanation: str
    matched_conditions: List[str] = Field(default_factory=list)
    missing_conditions: List[str] = Field(default_factory=list)
    sample_fact: Dict[str, Any] = Field(default_factory=dict)
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
    top_hot_rules: List[RuleRuntimeMetric] = Field(default_factory=list)
    cold_rules: List[RuleRuntimeMetric] = Field(default_factory=list)


class RuleRuntimeDetail(BaseModel):
    metric: RuleRuntimeMetric
    recent_explanations: List[RuleExplainabilityEntry] = Field(default_factory=list)


class AnalyticsCoverageResponse(BaseModel):
    summary: RuntimeAnalyticsSummary
    triggered_rule_ids: List[str] = Field(default_factory=list)
    never_fired_rule_ids: List[str] = Field(default_factory=list)


class RuntimeAnalyticsResponse(BaseModel):
    summary: RuntimeAnalyticsSummary
    top_hot_rules: List[RuleRuntimeMetric] = Field(default_factory=list)
    cold_rules: List[RuleRuntimeMetric] = Field(default_factory=list)
    recent_explanations: List[RuleExplainabilityEntry] = Field(default_factory=list)
