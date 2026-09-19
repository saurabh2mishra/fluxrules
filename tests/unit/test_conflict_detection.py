import pytest

import fluxrules.services.validation.conflict_detection as _core_conflict_module
from fluxrules.services.validation._normalization import Interval
from fluxrules.services.validation._normalization import (
    intervals_by_field as _original_intervals_by_field,
)
from fluxrules.services.validation.conflict_detection import (
    ConflictDetector,
    RuleConflict,
)


class DummyCompiledRule:
    def __init__(self, id, name, field_ranges, group="default"):
        self.id = id
        self.name = name
        self.source_condition = {}
        self.constraints = []
        self._field_ranges = field_ranges
        self.group = group


def intervals_by_field(rule):
    """Patch for DummyCompiledRule in tests."""
    if hasattr(rule, "_field_ranges"):
        inclusive_ranges = {}
        for field, intervals in rule._field_ranges.items():
            inclusive_ranges[field] = [
                Interval(i.low, i.high, low_inclusive=True, high_inclusive=True) for i in intervals
            ]
        return inclusive_ranges
    return _original_intervals_by_field(rule)


# Patch in the core module where the function reference lives
_core_conflict_module.intervals_by_field = intervals_by_field


@pytest.mark.parametrize(
    "rules,expected",
    [
        # No overlap
        (
            [
                DummyCompiledRule("1", "Rule1", {"score": [Interval(0, 10, True, True)]}),
                DummyCompiledRule("2", "Rule2", {"score": [Interval(20, 30, True, True)]}),
            ],
            [],
        ),
        # Overlap (adjacent inclusive intervals)
        (
            [
                DummyCompiledRule("1", "Rule1", {"score": [Interval(0, 15, True, True)]}),
                DummyCompiledRule("2", "Rule2", {"score": [Interval(14, 20, True, True)]}),
            ],
            [RuleConflict(left_rule_id="1", right_rule_id="2", overlapping_fields=("score",))],
        ),
        # Multiple fields (guaranteed overlap for both fields)
        (
            [
                DummyCompiledRule(
                    "1",
                    "Rule1",
                    {
                        "score": [Interval(0, 15, True, True)],
                        "age": [Interval(25, 30, True, True)],
                    },
                ),
                DummyCompiledRule(
                    "2",
                    "Rule2",
                    {
                        "score": [Interval(14, 20, True, True)],
                        "age": [Interval(28, 35, True, True)],
                    },
                ),
            ],
            [
                RuleConflict(
                    left_rule_id="1",
                    right_rule_id="2",
                    overlapping_fields=("age", "score"),
                )
            ],
        ),
    ],
)
def test_conflict_detector_overlap(rules, expected):
    detector = ConflictDetector()
    result = detector.detect(rules)
    assert len(result) == len(expected)
    for rc in expected:
        assert any(
            r.left_rule_id == rc.left_rule_id
            and r.right_rule_id == rc.right_rule_id
            and set(r.overlapping_fields) == set(rc.overlapping_fields)
            for r in result
        )


def _brute_force_conflicts(compiled):
    """Reference detector: exhaustive pairwise overlap, no index or memoization.

    Mirrors ``ConflictDetector.detect``'s decision rules (group scoping,
    identical-action skip, authoritative branch analysis when both rules carry a
    source condition, numeric-only fallback otherwise) but compares *every* pair
    directly. The optimized detector must return exactly this set.
    """
    from fluxrules.services.validation.conflict_detection import (
        _branches_overlap,
        _decompose_or_branches,
    )
    from fluxrules.services.validation.conflict_detection import (
        intervals_by_field as _ibf,
    )

    by_group: dict = {}
    for r in compiled:
        g = getattr(r, "group", "default") or "default"
        by_group.setdefault(g, []).append(r)

    out = set()
    for rules in by_group.values():
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                a, b = rules[i], rules[j]
                a_act = getattr(a, "actions", None) or []
                b_act = getattr(b, "actions", None) or []
                if a_act and b_act and a_act == b_act:
                    continue
                fields: set = set()
                has = False
                analysed = bool(a.source_condition and b.source_condition)
                if analysed:
                    for ba in _decompose_or_branches(a.source_condition):
                        for bb in _decompose_or_branches(b.source_condition):
                            res = _branches_overlap(ba, bb)
                            if res is not None:
                                fields |= res
                                has = True
                if not analysed and not has:
                    la, lb = _ibf(a), _ibf(b)
                    for f in set(la) & set(lb):
                        if any(i1.intersects(i2) for i1 in la[f] for i2 in lb[f]):
                            fields.add(f)
                            has = True
                if has and fields:
                    lid, rid = min(a.id, b.id), max(a.id, b.id)
                    out.add((lid, rid, tuple(sorted(fields))))
    return out


def test_optimized_detect_matches_brute_force_reference():
    """Differential parity: the memoized/indexed detector == exhaustive reference.

    Generates a randomized ruleset dense with repeated conditions, OR-branches
    and string equalities (the exact workload the signature memoization targets)
    and asserts the optimized ``detect`` returns the identical conflict set.
    """
    import random

    from fluxrules.services.compilation.rule_compiler import RuleCompiler

    rng = random.Random(20240611)
    ops = (">", ">=", "<", "<=")
    payloads = []
    for i in range(80):
        roll = rng.random()
        if roll < 0.45:
            # Repeated numeric threshold (few distinct values => dense overlap).
            dsl = {
                "type": "condition",
                "field": f"f{i % 3}",
                "op": rng.choice(ops),
                "value": rng.randrange(5),
            }
        elif roll < 0.7:
            # String equality on a small value set.
            dsl = {
                "type": "condition",
                "field": f"c{i % 2}",
                "op": "==",
                "value": rng.choice(["gold", "silver", "bronze"]),
            }
        else:
            # OR-group mixing a range and an equality.
            dsl = {
                "type": "group",
                "op": "OR",
                "children": [
                    {
                        "type": "condition",
                        "field": f"f{i % 3}",
                        "op": rng.choice(ops),
                        "value": rng.randrange(5),
                    },
                    {
                        "type": "condition",
                        "field": f"c{i % 2}",
                        "op": "==",
                        "value": rng.choice(["gold", "silver"]),
                    },
                ],
            }
        payloads.append(
            {
                "id": f"r{i}",
                "name": f"rule_{i}",
                "priority": i % 10,
                "group": f"g{i % 3}",
                "condition_dsl": dsl,
            }
        )

    compiled = RuleCompiler().compile_rules(payloads)

    optimized = {
        (c.left_rule_id, c.right_rule_id, tuple(c.overlapping_fields))
        for c in ConflictDetector().detect(compiled)
    }
    reference = _brute_force_conflicts(compiled)

    assert optimized == reference
    assert optimized  # the workload is dense enough to produce conflicts
