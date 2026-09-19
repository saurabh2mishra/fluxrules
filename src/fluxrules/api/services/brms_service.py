from __future__ import annotations

import logging
from typing import Any

from fluxrules.analytics import ExplanationEngine, RuntimeCoverageReport
from fluxrules.api.analytics.metrics import MetricsCollector
from fluxrules.services.compilation.rule_compiler import CompiledRule, RuleCompiler
from fluxrules.services.execution.scheduler import RuleScheduler
from fluxrules.services.validation import (
    CoverageAnalyzer,
    DeadRuleDetector,
    DuplicateDetector,
    GapDetector,
    PriorityCollisionDetector,
)
from fluxrules.services.validation._compiled_cache import (
    get_compiled_rules,
)
from fluxrules.services.validation.conflict_detection import ConflictDetector
from fluxrules.services.validation.redundancy_detection import RedundancyDetector
from fluxrules.services.validation.sat_validation import SATValidator

logger = logging.getLogger(__name__)


class BRMSService:
    def __init__(self) -> None:
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

    def compile(self, rules: list[dict[str, Any]]) -> list[CompiledRule]:
        return self.compiler.compile_rules(rules)

    def validate(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        compiled = get_compiled_rules(rules)
        conflicts = self.conflict_detector.detect(compiled)
        duplicates = self.duplicate_detector.detect(compiled)
        priority_collisions = self.priority_collision_detector.detect(compiled)
        redundant = self.redundancy_detector.detect(compiled)
        dead = self.dead_rule_detector.detect(compiled)
        gaps = self.gap_detector.detect(compiled)

        dead_conflicts = [
            {"type": "brms_dead_rule", "rule_id": d.rule_id, "description": d.reason} for d in dead
        ]
        all_conflicts = [
            c.__dict__ if hasattr(c, "__dict__") and not isinstance(c, dict) else c
            for c in conflicts
        ]
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

    def validate_candidate(
        self,
        candidate_payload: dict[str, Any],
        existing_payloads: list[dict[str, Any]],
        group: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.compiler.compile_rule(candidate_payload)
        # For candidate validation, compile rules directly without caching
        # because existing_payloads are dynamic and change between validations
        existing_compiled = self.compiler.compile_rules(existing_payloads)
        from fluxrules.services.validation._interval_index import IntervalIndex

        index = IntervalIndex()
        for rule in existing_compiled:
            from fluxrules.services.validation.conflict_detection import (
                _branch_numeric_intervals,
                _decompose_or_branches,
            )

            for branch in _decompose_or_branches(rule.source_condition):
                for field, ivs in _branch_numeric_intervals(branch).items():
                    for iv in ivs:
                        index.add(rule.id, field, iv)

        conflicts_raw = self.conflict_detector.detect_candidate(candidate, existing_compiled)

        dead = self.dead_rule_detector.detect([candidate])

        all_for_dup = existing_compiled + [candidate]
        duplicates = self.duplicate_detector.detect(all_for_dup)
        cand_id = candidate.id
        duplicates = [
            d for d in duplicates if d.get("rule1_id") == cand_id or d.get("rule2_id") == cand_id
        ]

        all_for_prio = existing_compiled + [candidate]
        priority_collisions = self.priority_collision_detector.detect(all_for_prio)
        priority_collisions = [p for p in priority_collisions if cand_id in (p.get("rules") or [])]

        dead_conflicts = [
            {"type": "brms_dead_rule", "rule_id": d.rule_id, "description": d.reason} for d in dead
        ]
        all_conflicts = [
            c.__dict__ if hasattr(c, "__dict__") and not isinstance(c, dict) else c
            for c in conflicts_raw
        ]
        all_conflicts.extend(dead_conflicts)

        return {
            "conflicts": all_conflicts,
            "duplicates": duplicates,
            "priority_collisions": priority_collisions,
            "redundancies": [],
            "dead_rules": [d.__dict__ for d in dead],
            "gaps": [],
            "sat": {
                "unsatisfiable_rule_ids": [],
                "subsumed_rules": [],
                "solver": "skipped",
            },
        }
