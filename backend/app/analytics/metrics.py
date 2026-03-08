from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RuleMetrics:
    rule_id: str
    hit_count: int = 0
    execution_time_ms: float = 0.0


class MetricsCollector:
    def __init__(self):
        self._metrics: Dict[str, RuleMetrics] = {}

    def record_hit(self, rule_id: str, execution_time_ms: float) -> None:
        metric = self._metrics.setdefault(rule_id, RuleMetrics(rule_id=rule_id))
        metric.hit_count += 1
        metric.execution_time_ms += execution_time_ms

    def snapshot(self) -> Dict[str, RuleMetrics]:
        return self._metrics
