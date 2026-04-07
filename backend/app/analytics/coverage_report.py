from __future__ import annotations

from typing import Any, Dict

from app.analytics.metrics import MetricsCollector


class RuntimeCoverageReport:
    def __init__(self, metrics: MetricsCollector):
        self._metrics = metrics

    def coverage_report(self, total_rules: int) -> Dict[str, Any]:
        snapshot = self._metrics.snapshot()
        triggered = sum(1 for m in snapshot.values() if m.hit_count > 0)
        return {
            "total_rules": total_rules,
            "triggered_rules": triggered,
            "coverage_pct": (triggered / total_rules * 100.0) if total_rules else 0.0,
            "rule_metrics": {rule_id: metric.__dict__ for rule_id, metric in snapshot.items()},
        }
