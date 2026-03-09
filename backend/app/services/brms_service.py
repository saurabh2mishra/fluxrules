from __future__ import annotations

from typing import Any, Dict, List

from app.analytics.coverage_report import RuntimeCoverageReport
from app.analytics.explanation_engine import ExplanationEngine
from app.analytics.metrics import MetricsCollector
from app.compiler.rule_compiler import RuleCompiler
from app.execution.scheduler import RuleScheduler
from app.validation.conflict_detection import ConflictDetector
from app.validation.coverage_analysis import CoverageAnalyzer
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.gap_detection import GapDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.sat_validation import SATValidator
from app.validation.duplicate_detection import DuplicateDetector
from app.validation.priority_collision_detection import PriorityCollisionDetector


class BRMSService:
    """High-level BRMS orchestrator for BRMS-only validation and analytics."""

    def __init__(self):
        self.compiler = RuleCompiler()
        self.coverage_analyzer = CoverageAnalyzer()
        self.conflict_detector = ConflictDetector()
        self.redundancy_detector = RedundancyDetector()
        self.dead_rule_detector = DeadRuleDetector()
        self.gap_detector = GapDetector()
        self.sat_validator = SATValidator()
        self.metrics = MetricsCollector()
        self.runtime_coverage = RuntimeCoverageReport(self.metrics)
        self.explanations = ExplanationEngine()
        self.scheduler = RuleScheduler()
        self.duplicate_detector = DuplicateDetector()
        self.priority_collision_detector = PriorityCollisionDetector()

    def compile(self, rules: List[Dict[str, Any]]):
        return self.compiler.compile_rules(rules)

    def validate(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        compiled = self.compile(rules)
        conflicts = self.conflict_detector.detect(compiled)
        duplicates = self.duplicate_detector.detect(compiled)
        priority_collisions = self.priority_collision_detector.detect(compiled)
        redundant = self.redundancy_detector.detect(compiled)
        dead = self.dead_rule_detector.detect(compiled)
        gaps = self.gap_detector.detect(compiled)

        # Add dead rules as brms_dead_rule conflicts
        dead_conflicts = [
            {
                "type": "brms_dead_rule",
                "rule_id": d.rule_id,
                "description": d.reason
            }
            for d in dead
        ]
        all_conflicts = [c.__dict__ for c in conflicts] if hasattr(conflicts, '__dict__') else conflicts
        all_conflicts.extend(dead_conflicts)

        sat = self.sat_validator.validate(compiled)
        return {
            "conflicts": all_conflicts,
            "duplicates": duplicates,
            "priority_collisions": priority_collisions,
            "redundancies": [r.__dict__ for r in redundant],
            "dead_rules": [d.__dict__ for d in dead],
            "gaps": [g.__dict__ for g in gaps],
            "sat": sat.__dict__,
        }

    # Remove execute method and any RETE/engine logic
