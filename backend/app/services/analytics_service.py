from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.analytics.coverage_report import RuntimeCoverageReport
from app.analytics.metrics import MetricsCollector
from app.analytics.store import AnalyticsStore, InMemoryAnalyticsStore, RedisAnalyticsStore
from app.models.rule import Rule
from app.schemas.analytics import (
    AnalyticsCoverageResponse,
    RuleExplainabilityEntry,
    RuleRuntimeDetail,
    RuleRuntimeMetric,
    RuntimeAnalyticsResponse,
    RuntimeAnalyticsSummary,
    TopRulesResponse,
)
from app.utils.redis_client import get_redis_client


class AnalyticsService:
    def __init__(self, store: Optional[AnalyticsStore] = None):
        if store is not None:
            self.store = store
        else:
            redis_client = get_redis_client()
            self.store = RedisAnalyticsStore(redis_client) if redis_client else InMemoryAnalyticsStore()
        self._collector = MetricsCollector()
        self._coverage = RuntimeCoverageReport(self._collector)

    def record_rule_execution(
        self,
        rule_id: str,
        execution_time_ms: float,
        event_payload: Dict[str, Any],
        explanation: Optional[str] = None,
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        self.store.increment_rule(str(rule_id), execution_time_ms, timestamp)
        self._collector.record_hit(str(rule_id), execution_time_ms)
        if explanation:
            matched, missing = self._extract_conditions(explanation)
            self.store.add_explanation(
                {
                    "rule_id": str(rule_id),
                    "explanation": explanation,
                    "matched_conditions": matched,
                    "missing_conditions": missing,
                    "sample_fact": event_payload,
                    "timestamp": timestamp,
                }
            )

    def record_event_processed(self, duration_ms: float) -> None:
        self.store.increment_event(duration_ms)

    def get_runtime_summary(self, db: Session) -> RuntimeAnalyticsSummary:
        stats = self.store.read_stats()
        metrics = self.store.read_rule_metrics()
        enabled_rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
        total_rules = len(enabled_rules)
        triggered_rules = len([m for m in metrics.values() if int(m.get("hit_count", 0)) > 0])
        coverage_pct = (triggered_rules / total_rules * 100.0) if total_rules else 0.0
        avg_ms = 0.0
        if stats["evaluation_count"] > 0:
            avg_ms = stats["total_processing_time_ms"] / stats["evaluation_count"]
        return RuntimeAnalyticsSummary(
            total_rules=total_rules,
            triggered_rules=triggered_rules,
            coverage_pct=round(coverage_pct, 2),
            rules_never_fired_count=max(total_rules - triggered_rules, 0),
            events_processed=int(stats["events_processed"]),
            rules_fired=int(stats["rules_fired"]),
            avg_processing_time_ms=round(avg_ms, 2),
        )

    def get_top_rules(self, db: Session, limit: int = 10) -> TopRulesResponse:
        metrics = self.store.read_rule_metrics()
        name_map = self._rule_name_map(db)

        ranked = sorted(metrics.values(), key=lambda m: int(m.get("hit_count", 0)), reverse=True)
        hot = [self._to_rule_metric(item, name_map) for item in ranked[:limit]]

        enabled = db.query(Rule).filter(Rule.enabled.is_(True)).all()
        cold: List[RuleRuntimeMetric] = []
        for rule in enabled:
            existing = metrics.get(str(rule.id))
            if not existing or int(existing.get("hit_count", 0)) == 0:
                cold.append(
                    RuleRuntimeMetric(
                        rule_id=str(rule.id),
                        rule_name=rule.name,
                        hit_count=0,
                        total_execution_time_ms=0.0,
                        avg_execution_time_ms=0.0,
                        last_fired_at=None,
                    )
                )
        return TopRulesResponse(top_hot_rules=hot, cold_rules=cold[:limit])

    def get_rule_metrics(self, db: Session, rule_id: str) -> RuleRuntimeDetail:
        metrics = self.store.read_rule_metrics()
        data = metrics.get(str(rule_id), {"rule_id": str(rule_id), "hit_count": 0, "total_execution_time_ms": 0.0})
        name_map = self._rule_name_map(db)
        metric = self._to_rule_metric(data, name_map)
        explanations = self.get_recent_explanations(rule_id=rule_id, limit=25)
        return RuleRuntimeDetail(metric=metric, recent_explanations=explanations)

    def get_recent_explanations(self, rule_id: Optional[str] = None, limit: int = 50) -> List[RuleExplainabilityEntry]:
        items = self.store.read_explanations(rule_id=rule_id, limit=limit)
        out: List[RuleExplainabilityEntry] = []
        for item in items:
            out.append(
                RuleExplainabilityEntry(
                    rule_id=str(item.get("rule_id")),
                    explanation=item.get("explanation", ""),
                    matched_conditions=item.get("matched_conditions", []),
                    missing_conditions=item.get("missing_conditions", []),
                    sample_fact=item.get("sample_fact", {}),
                    timestamp=datetime.fromisoformat(item.get("timestamp")),
                )
            )
        return out

    def get_runtime_analytics(self, db: Session) -> RuntimeAnalyticsResponse:
        summary = self.get_runtime_summary(db)
        top = self.get_top_rules(db, limit=10)
        explanations = self.get_recent_explanations(limit=20)
        return RuntimeAnalyticsResponse(
            summary=summary,
            top_hot_rules=top.top_hot_rules,
            cold_rules=top.cold_rules,
            recent_explanations=explanations,
        )

    def get_coverage(self, db: Session) -> AnalyticsCoverageResponse:
        summary = self.get_runtime_summary(db)
        metrics = self.store.read_rule_metrics()
        triggered_ids = [str(rule_id) for rule_id, data in metrics.items() if int(data.get("hit_count", 0)) > 0]
        enabled = db.query(Rule).filter(Rule.enabled.is_(True)).all()
        never = [str(rule.id) for rule in enabled if str(rule.id) not in set(triggered_ids)]
        return AnalyticsCoverageResponse(summary=summary, triggered_rule_ids=triggered_ids, never_fired_rule_ids=never)

    @staticmethod
    def _extract_conditions(explanation: str) -> tuple[List[str], List[str]]:
        matched = []
        missing = []
        for chunk in explanation.split("["):
            part = chunk.strip().rstrip("]")
            if part.startswith("✓"):
                matched.append(part[1:].strip())
            elif part.startswith("✗"):
                missing.append(part[1:].strip())
        return matched, missing

    @staticmethod
    def _rule_name_map(db: Session) -> Dict[str, str]:
        return {str(r.id): r.name for r in db.query(Rule).all()}

    @staticmethod
    def _to_rule_metric(data: Dict[str, Any], name_map: Dict[str, str]) -> RuleRuntimeMetric:
        hit_count = int(data.get("hit_count", 0))
        total_ms = float(data.get("total_execution_time_ms", 0.0))
        avg = total_ms / hit_count if hit_count > 0 else 0.0
        last_fired_raw = data.get("last_fired_at")
        last_fired_at = datetime.fromisoformat(last_fired_raw) if last_fired_raw else None
        rule_id = str(data.get("rule_id"))
        return RuleRuntimeMetric(
            rule_id=rule_id,
            rule_name=name_map.get(rule_id),
            hit_count=hit_count,
            total_execution_time_ms=round(total_ms, 2),
            avg_execution_time_ms=round(avg, 2),
            last_fired_at=last_fired_at,
        )


_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
