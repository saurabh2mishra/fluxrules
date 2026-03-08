from __future__ import annotations

from typing import Any, Dict, List

from app.analytics.coverage_report import RuntimeCoverageReport
from app.analytics.explanation_engine import ExplanationEngine
from app.analytics.metrics import MetricsCollector
from app.compiler.rule_compiler import RuleCompiler
from app.execution.scheduler import RuleScheduler
from app.rete.rete_network import ScalableReteNetwork
from app.validation.conflict_detection import ConflictDetector
from app.validation.coverage_analysis import CoverageAnalyzer
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.gap_detection import GapDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.sat_validation import SATValidator


class BRMSService:
    """High-level BRMS orchestrator built on top of existing FluxRules runtime."""

    def __init__(self):
        self.compiler = RuleCompiler()
        self.coverage_analyzer = CoverageAnalyzer()
        self.conflict_detector = ConflictDetector()
        self.redundancy_detector = RedundancyDetector()
        self.dead_rule_detector = DeadRuleDetector()
        self.gap_detector = GapDetector()
        self.sat_validator = SATValidator()
        self.rete = ScalableReteNetwork()
        self.metrics = MetricsCollector()
        self.runtime_coverage = RuntimeCoverageReport(self.metrics)
        self.explanations = ExplanationEngine()
        self.scheduler = RuleScheduler()

    def compile(self, rules: List[Dict[str, Any]]):
        return self.compiler.compile_rules(rules)

    def validate(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        compiled = self.compile(rules)
        conflicts = self.conflict_detector.detect(compiled)
        redundant = self.redundancy_detector.detect(compiled)
        dead = self.dead_rule_detector.detect(compiled)
        gaps = self.gap_detector.detect(compiled)
        sat = self.sat_validator.validate(compiled)
        return {
            "conflicts": [c.__dict__ for c in conflicts],
            "redundancies": [r.__dict__ for r in redundant],
            "dead_rules": [d.__dict__ for d in dead],
            "gaps": [g.__dict__ for g in gaps],
            "sat": sat.__dict__,
        }

    def execute(self, rules: List[Dict[str, Any]], fact: Dict[str, Any]) -> Dict[str, Any]:
        compiled = self.compile(rules)
        self.rete.load_rules(rules)
        result = self.rete.evaluate(fact)

        for item in result.get("matched_rules", []):
            rid = str(item["id"])
            self.metrics.record_hit(rid, result["stats"].get("evaluation_time_ms", 0.0))
            self.scheduler.add_activation(
                rule_id=rid,
                priority=int(item.get("priority", 0)),
                specificity=len(next((r.constraints for r in compiled if r.id == rid), [])),
                matched_facts=[fact],
            )

        ordered = []
        while True:
            nxt = self.scheduler.next_activation()
            if nxt is None:
                break
            ordered.append(nxt.rule_id)

        explanations = {
            rule.id: self.explanations.explain(rule, fact)
            for rule in compiled
            if rule.id in {str(item['id']) for item in result.get("matched_rules", [])}
        }

        result["execution_order"] = ordered or result.get("execution_order", [])
        result["explanations"] = explanations
        result["runtime_coverage"] = self.runtime_coverage.coverage_report(total_rules=len(compiled))
        result["static_coverage"] = self.coverage_analyzer.analyze(compiled).uncovered_ranges
        return result
