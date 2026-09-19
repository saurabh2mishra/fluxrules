"""Conflict detection across categorical (string-equality) conditions.

`ConflictDetector` finds candidate pairs through an index before doing the more
expensive pairwise overlap analysis. That index was originally numeric-only, so
a rule constrained purely by string equality (`tier == "premium"`) never entered
it, was never returned as a candidate, and could never be reported as
conflicting - **silently**.

Categorical rules are extremely common, and a conflict detector that quietly
returns "no conflicts" for them is worse than one that does not exist: it
converts an unknown into a false assurance.

These tests pin the fixed behaviour, in both directions. Reporting every
categorical pair as conflicting would be just as wrong as reporting none, so the
disjoint cases matter as much as the overlapping ones.
"""

from __future__ import annotations

from typing import Any

from fluxrules.services.compilation.rule_compiler import RuleCompiler
from fluxrules.services.validation.conflict_detection import ConflictDetector


def _rule(
    rule_id: int,
    name: str,
    condition: dict[str, Any],
    action: str,
    priority: int = 0,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "name": name,
        "condition_dsl": condition,
        "action": action,
        "priority": priority,
    }


def _eq(field: str, value: Any) -> dict[str, Any]:
    return {"type": "condition", "field": field, "op": "==", "value": value}


def _num(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _and(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "group", "op": "AND", "children": list(children)}


def _detect(rules: list[dict[str, Any]]):
    return ConflictDetector().detect(RuleCompiler().compile_rules(rules))


def _pairs(conflicts) -> set[tuple[str, str]]:
    return {
        (min(c.left_rule_id, c.right_rule_id), max(c.left_rule_id, c.right_rule_id))
        for c in conflicts
    }


class TestCategoricalConflicts:
    """The regression: string-only rules must be compared at all."""

    def test_identical_string_equality_with_opposing_actions_conflicts(self):
        conflicts = _detect(
            [
                _rule(1, "vip", _eq("tier", "premium"), "fast_track", priority=100),
                _rule(2, "standard", _eq("tier", "premium"), "normal", priority=1),
            ]
        )

        assert _pairs(conflicts) == {("1", "2")}
        assert conflicts[0].overlapping_fields == ("tier",)

    def test_disjoint_string_values_do_not_conflict(self):
        """gold and silver can never both match - reporting this would be noise."""
        conflicts = _detect(
            [
                _rule(1, "gold_rule", _eq("tier", "gold"), "approve"),
                _rule(2, "silver_rule", _eq("tier", "silver"), "reject"),
            ]
        )

        assert conflicts == []

    def test_identical_conditions_and_identical_actions_are_not_a_conflict(self):
        """Same conditions AND same action is redundancy, not a conflict."""
        conflicts = _detect(
            [
                _rule(1, "a", _eq("tier", "gold"), "approve"),
                _rule(2, "b", _eq("tier", "gold"), "approve"),
            ]
        )

        assert conflicts == []

    def test_only_the_overlapping_pair_is_reported(self):
        conflicts = _detect(
            [
                _rule(1, "vip", _eq("tier", "premium"), "fast_track"),
                _rule(2, "standard", _eq("tier", "premium"), "normal"),
                _rule(3, "basic", _eq("tier", "basic"), "normal"),
            ]
        )

        assert _pairs(conflicts) == {("1", "2")}

    def test_non_string_equality_values_are_handled(self):
        """Equality on a bool is still categorical, not an interval."""
        conflicts = _detect(
            [
                _rule(1, "a", _eq("country", "US"), "approve"),
                _rule(2, "b", _eq("country", "US"), "reject"),
            ]
        )

        assert _pairs(conflicts) == {("1", "2")}


class TestMixedNumericAndCategorical:
    """A contradiction on *any* AND-ed field makes the rules disjoint."""

    def test_shared_category_and_overlapping_range_conflicts(self):
        conflicts = _detect(
            [
                _rule(1, "a", _and(_eq("tier", "gold"), _num("amt", ">", 100)), "x"),
                _rule(2, "b", _and(_eq("tier", "gold"), _num("amt", ">", 50)), "y"),
            ]
        )

        assert _pairs(conflicts) == {("1", "2")}
        assert set(conflicts[0].overlapping_fields) == {"amt", "tier"}

    def test_contradictory_category_defeats_overlapping_range(self):
        """The important one.

        The amount ranges DO intersect, but tier gold and silver cannot both
        hold, so these rules can never fire on the same fact. A numeric-only
        analysis reports a conflict here, which is a false positive.
        """
        conflicts = _detect(
            [
                _rule(1, "a", _and(_eq("tier", "gold"), _num("amt", ">", 100)), "x"),
                _rule(2, "b", _and(_eq("tier", "silver"), _num("amt", ">", 50)), "y"),
            ]
        )

        assert conflicts == []

    def test_shared_category_with_disjoint_ranges_does_not_conflict(self):
        conflicts = _detect(
            [
                _rule(1, "a", _and(_eq("tier", "gold"), _num("amt", ">", 1000)), "x"),
                _rule(2, "b", _and(_eq("tier", "gold"), _num("amt", "<", 500)), "y"),
            ]
        )

        assert conflicts == []


class TestNumericBehaviourUnchanged:
    """Guard the pre-existing numeric path against regression."""

    def test_overlapping_numeric_ranges_conflict(self):
        conflicts = _detect(
            [
                _rule(1, "approve", _num("amount", ">", 1000), "approve"),
                _rule(2, "review", _num("amount", ">", 500), "manual_review"),
            ]
        )

        assert _pairs(conflicts) == {("1", "2")}
        assert conflicts[0].overlapping_fields == ("amount",)

    def test_disjoint_numeric_ranges_do_not_conflict(self):
        conflicts = _detect(
            [
                _rule(1, "high", _num("amount", ">", 1000), "approve"),
                _rule(2, "low", _num("amount", "<", 500), "reject"),
            ]
        )

        assert conflicts == []


class TestDetectCandidate:
    """`detect_candidate` had the same indexing gap and the same fix."""

    def test_categorical_candidate_finds_existing_conflict(self):
        compiled = RuleCompiler().compile_rules(
            [
                _rule(1, "vip", _eq("tier", "premium"), "fast_track"),
                _rule(2, "standard", _eq("tier", "premium"), "normal"),
                _rule(3, "basic", _eq("tier", "basic"), "normal"),
            ]
        )

        conflicts = ConflictDetector().detect_candidate(compiled[0], compiled[1:])

        assert _pairs(conflicts) == {("1", "2")}

    def test_categorical_candidate_with_no_overlap_is_clean(self):
        compiled = RuleCompiler().compile_rules(
            [
                _rule(1, "gold", _eq("tier", "gold"), "approve"),
                _rule(2, "silver", _eq("tier", "silver"), "reject"),
            ]
        )

        conflicts = ConflictDetector().detect_candidate(compiled[0], compiled[1:])

        assert conflicts == []


class TestGrouping:
    """Rules in different groups are independent rulesets."""

    def test_categorical_conflict_does_not_cross_groups(self):
        rules = [
            _rule(1, "a", _eq("tier", "premium"), "approve"),
            _rule(2, "b", _eq("tier", "premium"), "reject"),
        ]
        rules[0]["group"] = "lending"
        rules[1]["group"] = "marketing"

        assert _detect(rules) == []
