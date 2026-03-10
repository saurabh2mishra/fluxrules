from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.compiler.rule_compiler import CompiledConstraint, CompiledRule
from app.validation._normalization import Interval, intervals_by_field, constraint_to_interval
from app.validation._interval_index import IntervalIndex


@dataclass
class RuleConflict:
    left_rule_id: str
    right_rule_id: str
    overlapping_fields: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Helpers (unchanged from previous iteration)
# ---------------------------------------------------------------------------

def _extract_string_equalities(condition: Dict[str, Any]) -> Dict[str, Set[str]]:
    if not condition:
        return {}
    ctype = condition.get("type")
    if ctype == "condition":
        op = condition.get("op")
        field = condition.get("field")
        value = condition.get("value")
        if op == "==" and isinstance(value, str):
            return {field: {value}}
        return {}
    if ctype == "group":
        group_op = condition.get("op", "AND").upper()
        children = condition.get("children", [])
        if group_op == "AND":
            merged: Dict[str, Set[str]] = {}
            for child in children:
                child_eq = _extract_string_equalities(child)
                for f, vals in child_eq.items():
                    if f in merged:
                        merged[f] = merged[f] & vals
                    else:
                        merged[f] = set(vals)
            return merged
        else:
            merged_or: Dict[str, Set[str]] = {}
            for child in children:
                child_eq = _extract_string_equalities(child)
                for f, vals in child_eq.items():
                    if f in merged_or:
                        merged_or[f] = merged_or[f] | vals
                    else:
                        merged_or[f] = set(vals)
            return merged_or
    return {}


def _decompose_or_branches(condition: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not condition:
        return [condition]
    ctype = condition.get("type")
    if ctype == "group" and condition.get("op", "AND").upper() == "OR":
        return condition.get("children", [])
    return [condition]


def _branch_numeric_intervals(branch: Dict[str, Any]) -> Dict[str, List[Interval]]:
    constraints = _flatten_constraints(branch)
    result: Dict[str, List[Interval]] = {}
    for c in constraints:
        interval = constraint_to_interval(c)
        if interval is not None:
            result.setdefault(c.field, []).append(interval)
    from app.validation._normalization import merge_intervals
    return {field: merge_intervals(parts) for field, parts in result.items()}


def _branch_string_equalities(branch: Dict[str, Any]) -> Dict[str, Set[str]]:
    return _extract_string_equalities(branch)


def _flatten_constraints(condition: Dict[str, Any]) -> List[CompiledConstraint]:
    if not condition:
        return []
    ctype = condition.get("type")
    if ctype == "condition":
        field = condition.get("field")
        op = condition.get("op")
        if field is None or op is None:
            return []
        return [CompiledConstraint(field=str(field), operator=str(op), value=condition.get("value"))]
    if ctype == "group":
        out: List[CompiledConstraint] = []
        for child in condition.get("children", []):
            out.extend(_flatten_constraints(child))
        return out
    return []


def _branches_overlap(
    branch_a: Dict[str, Any],
    branch_b: Dict[str, Any],
) -> Optional[Set[str]]:
    str_eq_a = _branch_string_equalities(branch_a)
    str_eq_b = _branch_string_equalities(branch_b)
    common_str_fields = set(str_eq_a.keys()) & set(str_eq_b.keys())
    for field in common_str_fields:
        if not (str_eq_a[field] & str_eq_b[field]):
            return None

    num_a = _branch_numeric_intervals(branch_a)
    num_b = _branch_numeric_intervals(branch_b)
    common_num_fields = set(num_a.keys()) & set(num_b.keys())

    overlapping_fields: Set[str] = set()
    for field in common_num_fields:
        field_overlaps = False
        for iv_a in num_a[field]:
            for iv_b in num_b[field]:
                if iv_a.intersects(iv_b):
                    field_overlaps = True
                    break
            if field_overlaps:
                break
        if not field_overlaps:
            return None
        overlapping_fields.add(field)

    for field in common_str_fields:
        if str_eq_a[field] & str_eq_b[field]:
            overlapping_fields.add(field)

    return overlapping_fields if overlapping_fields else None


# ---------------------------------------------------------------------------
# ConflictDetector — index-accelerated, candidate-only incremental mode
# ---------------------------------------------------------------------------

class ConflictDetector:
    """
    Detect rule overlaps using condition-space analysis.

    Supports two modes:
      1. ``detect(rules)``           — legacy all-vs-all (backward compat)
      2. ``detect_candidate(cand, existing)`` — incremental O(k log n)

    Conflict criteria:
      - Overlapping condition spaces
      - Different actions
      - Same group
    """

    # ---- incremental candidate-only mode (preferred) ----

    def detect_candidate(
        self,
        candidate: CompiledRule,
        existing_rules: List[CompiledRule],
    ) -> List[RuleConflict]:
        """
        Check a single candidate rule against existing rules using an interval
        index.  O(k · log n) where k = number of candidate intervals.
        """
        cand_group = getattr(candidate, 'group', 'default') or 'default'
        cand_actions = getattr(candidate, 'actions', None) or []
        cand_branches = _decompose_or_branches(candidate.source_condition)

        # Build index only from same-group existing rules
        index = IntervalIndex()
        rules_by_id: Dict[str, CompiledRule] = {}
        for rule in existing_rules:
            r_group = getattr(rule, 'group', 'default') or 'default'
            if r_group != cand_group:
                continue
            r_actions = getattr(rule, 'actions', None) or []
            if cand_actions and r_actions and cand_actions == r_actions:
                continue
            rules_by_id[rule.id] = rule
            # Index all branch intervals for this rule
            for branch in _decompose_or_branches(rule.source_condition):
                for field, ivs in _branch_numeric_intervals(branch).items():
                    for iv in ivs:
                        index.add(rule.id, field, iv)

        # Query the index with each candidate branch
        candidate_ids: Set[str] = set()
        for branch in cand_branches:
            branch_nums = _branch_numeric_intervals(branch)
            for field, ivs in branch_nums.items():
                for iv in ivs:
                    hits = index.query_overlapping(field, iv, exclude_rule_id=candidate.id)
                    candidate_ids.update(hits)

        # Precise verification for candidate pairs
        conflicts: List[RuleConflict] = []
        for other_id in candidate_ids:
            other = rules_by_id.get(other_id)
            if other is None:
                continue
            other_branches = _decompose_or_branches(other.source_condition)
            overlap_fields: Set[str] = set()
            has_overlap = False
            for br_a in cand_branches:
                for br_b in other_branches:
                    result = _branches_overlap(br_a, br_b)
                    if result is not None:
                        overlap_fields |= result
                        has_overlap = True
            if has_overlap and overlap_fields:
                conflicts.append(RuleConflict(
                    left_rule_id=candidate.id,
                    right_rule_id=other.id,
                    overlapping_fields=tuple(sorted(overlap_fields)),
                ))
        return conflicts

    # ---- legacy all-vs-all mode (backward compat for tests & full scan) ----

    def detect(self, compiled_rules: List[CompiledRule]) -> List[RuleConflict]:
        rule_actions: Dict[str, List[str]] = {}
        rule_groups: Dict[str, str] = {}
        for rule in compiled_rules:
            rule_actions[rule.id] = getattr(rule, 'actions', None) or []
            rule_groups[rule.id] = getattr(rule, 'group', 'default') or 'default'

        # Build per-group indexes
        group_rules: Dict[str, List[CompiledRule]] = {}
        for rule in compiled_rules:
            g = rule_groups[rule.id]
            group_rules.setdefault(g, []).append(rule)

        all_conflicts: List[RuleConflict] = []

        for group, rules in group_rules.items():
            if len(rules) < 2:
                continue

            # Build interval index for this group using source_condition branches
            index = IntervalIndex()
            rule_branches: Dict[str, List[Dict[str, Any]]] = {}
            indexed_rule_ids: Set[str] = set()  # track which rules contributed intervals
            for rule in rules:
                branches = _decompose_or_branches(rule.source_condition)
                rule_branches[rule.id] = branches
                for branch in branches:
                    for field, ivs in _branch_numeric_intervals(branch).items():
                        for iv in ivs:
                            index.add(rule.id, field, iv)
                            indexed_rule_ids.add(rule.id)

            # Also index rules that have _field_ranges (DummyCompiledRule) but
            # no source_condition intervals — needed for test/legacy compat
            for rule in rules:
                if rule.id not in indexed_rule_ids:
                    direct_fields = intervals_by_field(rule)
                    if direct_fields:
                        for field, ivs in direct_fields.items():
                            for iv in ivs:
                                index.add(rule.id, field, iv)
                        indexed_rule_ids.add(rule.id)

            # For each rule, query the index for candidates
            seen_pairs: Set[Tuple[str, str]] = set()
            rules_by_id = {r.id: r for r in rules}
            for rule in rules:
                candidate_ids: Set[str] = set()

                # Query via source_condition branches
                branches = rule_branches[rule.id]
                for branch in branches:
                    for field, ivs in _branch_numeric_intervals(branch).items():
                        for iv in ivs:
                            hits = index.query_overlapping(field, iv, exclude_rule_id=rule.id)
                            candidate_ids.update(hits)

                # Also query via direct intervals_by_field (DummyCompiledRule)
                if rule.id not in indexed_rule_ids or not candidate_ids:
                    direct_fields = intervals_by_field(rule)
                    for field, ivs in direct_fields.items():
                        for iv in ivs:
                            hits = index.query_overlapping(field, iv, exclude_rule_id=rule.id)
                            candidate_ids.update(hits)

                for other_id in candidate_ids:
                    pair = (min(rule.id, other_id), max(rule.id, other_id))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    left_actions = rule_actions[rule.id]
                    right_actions = rule_actions[other_id]
                    if left_actions and right_actions and left_actions == right_actions:
                        continue

                    other = rules_by_id[other_id]
                    other_branches = rule_branches[other_id]
                    overlap_fields: Set[str] = set()
                    has_overlap = False

                    # Try source_condition branch overlap first
                    if rule.source_condition and other.source_condition:
                        for br_a in branches:
                            for br_b in other_branches:
                                result = _branches_overlap(br_a, br_b)
                                if result is not None:
                                    overlap_fields |= result
                                    has_overlap = True

                    # Fallback: direct intervals_by_field (DummyCompiledRules / legacy)
                    if not has_overlap:
                        left_fields = intervals_by_field(rule)
                        right_fields = intervals_by_field(other)
                        common = set(left_fields.keys()) & set(right_fields.keys())
                        for f in common:
                            for i1 in left_fields[f]:
                                for i2 in right_fields[f]:
                                    if i1.intersects(i2):
                                        overlap_fields.add(f)
                                        has_overlap = True

                    if has_overlap and overlap_fields:
                        all_conflicts.append(RuleConflict(
                            left_rule_id=pair[0],
                            right_rule_id=pair[1],
                            overlapping_fields=tuple(sorted(overlap_fields)),
                        ))

        return all_conflicts
