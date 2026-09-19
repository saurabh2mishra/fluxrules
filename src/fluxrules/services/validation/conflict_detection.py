from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fluxrules.services.compilation.rule_compiler import (
    CompiledConstraint,
    CompiledRule,
)
from fluxrules.services.validation._interval_index import EqualityIndex, IntervalIndex
from fluxrules.services.validation._normalization import (
    Interval,
    constraint_to_interval,
    intervals_by_field,
)


@dataclass
class RuleConflict:
    left_rule_id: str
    right_rule_id: str
    overlapping_fields: tuple[str, ...]


def _extract_string_equalities(condition: dict[str, Any]) -> dict[str, set[str]]:
    if not condition:
        return {}
    ctype = condition.get("type")
    if ctype == "condition":
        op = condition.get("op")
        field = condition.get("field")
        value = condition.get("value")
        if op == "==" and isinstance(value, str) and isinstance(field, str):
            return {field: {value}}
        return {}
    if ctype == "group":
        group_op = condition.get("op", "AND").upper()
        children = condition.get("children", [])
        if group_op == "AND":
            merged: dict[str, set[str]] = {}
            for child in children:
                child_eq = _extract_string_equalities(child)
                for f, vals in child_eq.items():
                    if f in merged:
                        merged[f] = merged[f] & vals
                    else:
                        merged[f] = set(vals)
            return merged
        else:
            merged_or: dict[str, set[str]] = {}
            for child in children:
                child_eq = _extract_string_equalities(child)
                for f, vals in child_eq.items():
                    if f in merged_or:
                        merged_or[f] = merged_or[f] | vals
                    else:
                        merged_or[f] = set(vals)
            return merged_or
    return {}


def _decompose_or_branches(condition: dict[str, Any]) -> list[dict[str, Any]]:
    if not condition:
        return [condition]
    ctype = condition.get("type")
    if ctype == "group" and condition.get("op", "AND").upper() == "OR":
        return condition.get("children", [])
    return [condition]


def _branch_numeric_intervals(branch: dict[str, Any]) -> dict[str, list[Interval]]:
    constraints = _flatten_constraints(branch)
    result: dict[str, list[Interval]] = {}
    for c in constraints:
        interval = constraint_to_interval(c)
        if interval is not None:
            result.setdefault(c.field, []).append(interval)
    from fluxrules.services.validation._normalization import merge_intervals

    return {field: merge_intervals(parts) for field, parts in result.items()}


def _branch_string_equalities(branch: dict[str, Any]) -> dict[str, set[str]]:
    return _extract_string_equalities(branch)


def _flatten_constraints(condition: dict[str, Any]) -> list[CompiledConstraint]:
    if not condition:
        return []
    ctype = condition.get("type")
    if ctype == "condition":
        field = condition.get("field")
        op = condition.get("op")
        if field is None or op is None:
            return []
        return [
            CompiledConstraint(field=str(field), operator=str(op), value=condition.get("value"))
        ]
    if ctype == "group":
        out: list[CompiledConstraint] = []
        for child in condition.get("children", []):
            out.extend(_flatten_constraints(child))
        return out
    return []


# A branch reduced to the only data conflict analysis needs: its per-field
# numeric intervals and per-field string equalities, plus a hashable signature
# of both. Two branches with the same signature always yield the same overlap
# result, so the signature is a safe memoization key (see `detect`).
_BranchSig = tuple[
    tuple[tuple[str, frozenset], ...],
    tuple[tuple[str, frozenset], ...],
]
BranchData = tuple[_BranchSig, dict[str, list[Interval]], dict[str, set[str]]]


def _branch_data(branch: dict[str, Any]) -> BranchData:
    """Precompute a branch's intervals, equalities, and hashable signature once."""
    num = _branch_numeric_intervals(branch)
    str_eq = _branch_string_equalities(branch)
    num_sig = tuple(sorted((field, frozenset(ivs)) for field, ivs in num.items()))
    str_sig = tuple(sorted((field, frozenset(vals)) for field, vals in str_eq.items()))
    return (num_sig, str_sig), num, str_eq


def _overlap_from_data(a: BranchData, b: BranchData) -> set[str] | None:
    """Overlap of two precomputed branches. Equivalent to `_branches_overlap`."""
    _, num_a, str_eq_a = a
    _, num_b, str_eq_b = b
    common_str_fields = set(str_eq_a.keys()) & set(str_eq_b.keys())
    for field in common_str_fields:
        if not (str_eq_a[field] & str_eq_b[field]):
            return None

    common_num_fields = set(num_a.keys()) & set(num_b.keys())

    overlapping_fields: set[str] = set()
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

    return overlapping_fields or None


def _branches_overlap(
    branch_a: dict[str, Any],
    branch_b: dict[str, Any],
) -> set[str] | None:
    return _overlap_from_data(_branch_data(branch_a), _branch_data(branch_b))


class ConflictDetector:
    """Detect rule overlaps using condition-space analysis."""

    def detect_candidate(
        self,
        candidate: CompiledRule,
        existing_rules: list[CompiledRule],
    ) -> list[RuleConflict]:
        cand_group = getattr(candidate, "group", "default") or "default"
        cand_actions = getattr(candidate, "actions", None) or []
        cand_branches = _decompose_or_branches(candidate.source_condition)

        index = IntervalIndex()
        eq_index = EqualityIndex()
        rules_by_id: dict[str, CompiledRule] = {}
        for rule in existing_rules:
            r_group = getattr(rule, "group", "default") or "default"
            if r_group != cand_group:
                continue
            r_actions = getattr(rule, "actions", None) or []
            if cand_actions and r_actions and cand_actions == r_actions:
                continue
            rules_by_id[rule.id] = rule
            for branch in _decompose_or_branches(rule.source_condition):
                for field, ivs in _branch_numeric_intervals(branch).items():
                    for iv in ivs:
                        index.add(rule.id, field, iv)
                # Purely categorical rules produce no intervals; index their
                # equalities too or they are never offered as candidates.
                for field, values in _branch_string_equalities(branch).items():
                    for value in values:
                        eq_index.add(rule.id, field, value)

        candidate_ids: set[str] = set()
        for branch in cand_branches:
            branch_nums = _branch_numeric_intervals(branch)
            for field, ivs in branch_nums.items():
                for iv in ivs:
                    hits = index.query_overlapping(field, iv, exclude_rule_id=candidate.id)
                    candidate_ids.update(hits)
            for field, values in _branch_string_equalities(branch).items():
                for value in values:
                    candidate_ids.update(
                        eq_index.query_equal(field, value, exclude_rule_id=candidate.id)
                    )

        conflicts: list[RuleConflict] = []
        for other_id in candidate_ids:
            other = rules_by_id.get(other_id)
            if other is None:
                continue
            other_branches = _decompose_or_branches(other.source_condition)
            overlap_fields: set[str] = set()
            has_overlap = False
            for br_a in cand_branches:
                for br_b in other_branches:
                    result = _branches_overlap(br_a, br_b)
                    if result is not None:
                        overlap_fields |= result
                        has_overlap = True
            if has_overlap and overlap_fields:
                conflicts.append(
                    RuleConflict(
                        left_rule_id=candidate.id,
                        right_rule_id=other.id,
                        overlapping_fields=tuple(sorted(overlap_fields)),
                    )
                )
        return conflicts

    def detect(self, compiled_rules: list[CompiledRule]) -> list[RuleConflict]:
        rule_actions: dict[str, list[str]] = {}
        rule_groups: dict[str, str] = {}
        for rule in compiled_rules:
            rule_actions[rule.id] = getattr(rule, "actions", None) or []
            rule_groups[rule.id] = getattr(rule, "group", "default") or "default"

        group_rules: dict[str, list[CompiledRule]] = {}
        for rule in compiled_rules:
            g = rule_groups[rule.id]
            group_rules.setdefault(g, []).append(rule)

        all_conflicts: list[RuleConflict] = []

        for group, rules in group_rules.items():
            if len(rules) < 2:
                continue

            index = IntervalIndex()
            eq_index = EqualityIndex()
            rule_branches: dict[str, list[BranchData]] = {}
            indexed_rule_ids: set[str] = set()
            for rule in rules:
                branches = [
                    _branch_data(branch) for branch in _decompose_or_branches(rule.source_condition)
                ]
                rule_branches[rule.id] = branches
                for _sig, num, str_eq in branches:
                    for field, ivs in num.items():
                        for iv in ivs:
                            index.add(rule.id, field, iv)
                            indexed_rule_ids.add(rule.id)
                    # Rules constrained only by string equality produce no
                    # intervals. Index those separately or they are never
                    # considered as candidates and their conflicts go unreported.
                    for field, values in str_eq.items():
                        for value in values:
                            eq_index.add(rule.id, field, value)
                            indexed_rule_ids.add(rule.id)

            for rule in rules:
                if rule.id not in indexed_rule_ids:
                    direct_fields = intervals_by_field(rule)
                    if direct_fields:
                        for field, ivs in direct_fields.items():
                            for iv in ivs:
                                index.add(rule.id, field, iv)
                        indexed_rule_ids.add(rule.id)

            # Overlap of two branches depends only on their signatures, so the
            # result is memoized across the O(pairs) loop below. On rule sets
            # with many repeated/near-identical conditions this collapses the
            # per-pair interval math (the O(n^2) hot path) to one computation
            # per distinct signature pair. Output is identical either way.
            overlap_memo: dict[frozenset, set[str] | None] = {}

            seen_pairs: set[tuple[str, str]] = set()
            rules_by_id = {r.id: r for r in rules}
            for rule in rules:
                candidate_ids: set[str] = set()

                branches = rule_branches[rule.id]
                for _sig, num, str_eq in branches:
                    for field, ivs in num.items():
                        for iv in ivs:
                            hits = index.query_overlapping(field, iv, exclude_rule_id=rule.id)
                            candidate_ids.update(hits)
                    for field, values in str_eq.items():
                        for value in values:
                            candidate_ids.update(
                                eq_index.query_equal(field, value, exclude_rule_id=rule.id)
                            )

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
                    overlap_fields: set[str] = set()
                    has_overlap = False

                    # When both rules carry a source condition, the branch
                    # analysis is authoritative: it understands string equality
                    # as well as numeric intervals, so a None result means
                    # "proven disjoint", not "unknown".
                    analysed = bool(rule.source_condition and other.source_condition)
                    if analysed:
                        for br_a in branches:
                            for br_b in other_branches:
                                key = frozenset((br_a[0], br_b[0]))
                                if key in overlap_memo:
                                    result = overlap_memo[key]
                                else:
                                    result = _overlap_from_data(br_a, br_b)
                                    overlap_memo[key] = result
                                if result is not None:
                                    overlap_fields |= result
                                    has_overlap = True

                    # Numeric-only fallback for rules with no source condition
                    # to analyse. Running it after a conclusive branch analysis
                    # would resurrect pairs that analysis just ruled out - e.g.
                    # tier=="gold" vs tier=="silver" can never both fire, but
                    # their amount ranges do intersect.
                    if not analysed and not has_overlap:
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
                        all_conflicts.append(
                            RuleConflict(
                                left_rule_id=pair[0],
                                right_rule_id=pair[1],
                                overlapping_fields=tuple(sorted(overlap_fields)),
                            )
                        )

        return all_conflicts
