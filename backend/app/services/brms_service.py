from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.analytics.coverage_report import RuntimeCoverageReport
from app.analytics.explanation_engine import ExplanationEngine
from app.analytics.metrics import MetricsCollector
from app.compiler.rule_compiler import CompiledRule, RuleCompiler
from app.execution.scheduler import RuleScheduler
from app.validation.conflict_detection import ConflictDetector
from app.validation.coverage_analysis import CoverageAnalyzer
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.gap_detection import GapDetector
from app.validation.redundancy_detection import RedundancyDetector
from app.validation.sat_validation import SATValidator
from app.validation.duplicate_detection import DuplicateDetector
from app.validation.priority_collision_detection import PriorityCollisionDetector
from app.validation._compiled_cache import (
    get_compiled_rules,
    get_compiled_rules_with_index,
    invalidate as invalidate_compiled_cache,
)

logger = logging.getLogger(__name__)


class BRMSService:
    """High-level BRMS orchestrator for BRMS-only validation and analytics.

    Supports two modes:
      1. ``validate(rules)``  — full all-vs-all validation (backward compat)
      2. ``validate_candidate(candidate, existing_payloads, group)``
         — incremental candidate-only O(k log n)
    """

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

    def compile(self, rules: List[Dict[str, Any]]) -> List[CompiledRule]:
        return self.compiler.compile_rules(rules)

    # ------------------------------------------------------------------
    # Full validation (backward compat — used by detect-all and tests)
    # ------------------------------------------------------------------

    def validate(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        compiled = get_compiled_rules(rules)
        conflicts = self.conflict_detector.detect(compiled)
        duplicates = self.duplicate_detector.detect(compiled)
        priority_collisions = self.priority_collision_detector.detect(compiled)
        redundant = self.redundancy_detector.detect(compiled)
        dead = self.dead_rule_detector.detect(compiled)
        gaps = self.gap_detector.detect(compiled)

        dead_conflicts = [
            {
                "type": "brms_dead_rule",
                "rule_id": d.rule_id,
                "description": d.reason,
            }
            for d in dead
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

    # ------------------------------------------------------------------
    # Incremental candidate-only validation  (O(k log n))
    # ------------------------------------------------------------------

    def validate_candidate(
        self,
        candidate_payload: Dict[str, Any],
        existing_payloads: List[Dict[str, Any]],
        group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate a single candidate rule against the existing ruleset.

        Uses cached compiled rules + pre-built IntervalIndex for the group,
        then runs only the candidate through conflict / dead / duplicate checks.
        This is O(k · log n) instead of O(n²).
        """
        # Compile just the candidate (always fresh)
        candidate = self.compiler.compile_rule(candidate_payload)

        # Get cached compiled existing rules + interval index (group-scoped)
        existing_compiled, index = get_compiled_rules_with_index(
            existing_payloads, group=group
        )

        # 1. Conflict detection — candidate-only via index
        conflicts_raw = self.conflict_detector.detect_candidate(
            candidate, existing_compiled
        )

        # 2. Dead rule detection — only for the candidate
        dead = self.dead_rule_detector.detect([candidate])

        # 3. Duplicate detection — candidate vs existing
        all_for_dup = existing_compiled + [candidate]
        duplicates = self.duplicate_detector.detect(all_for_dup)
        # Only keep duplicates involving the candidate
        cand_id = candidate.id
        duplicates = [
            d for d in duplicates
            if d.get("rule1_id") == cand_id or d.get("rule2_id") == cand_id
        ]

        # 4. Priority collisions — candidate vs existing
        all_for_prio = existing_compiled + [candidate]
        priority_collisions = self.priority_collision_detector.detect(all_for_prio)
        priority_collisions = [
            p for p in priority_collisions
            if cand_id in (p.get("rules") or [])
        ]

        dead_conflicts = [
            {
                "type": "brms_dead_rule",
                "rule_id": d.rule_id,
                "description": d.reason,
            }
            for d in dead
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
            "sat": {"unsatisfiable_rule_ids": [], "subsumed_rules": [], "solver": "skipped"},
        }
