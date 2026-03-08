from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.compiler.rule_compiler import CompiledRule


@dataclass
class DeadRule:
    rule_id: str
    reason: str


class DeadRuleDetector:
    def detect(self, compiled_rules: List[CompiledRule]) -> List[DeadRule]:
        dead: List[DeadRule] = []
        for rule in compiled_rules:
            contradiction = self._find_contradiction(rule)
            if contradiction:
                dead.append(DeadRule(rule_id=rule.id, reason=contradiction))
        return dead

    def _find_contradiction(self, rule: CompiledRule) -> str | None:
        bounds: Dict[str, Tuple[float, bool, float, bool]] = {}
        equals: Dict[str, set] = {}

        for c in rule.constraints:
            field = c.field
            if c.operator == "==":
                equals.setdefault(field, set()).add(c.value)
                continue
            if not isinstance(c.value, (int, float)):
                continue

            low, low_inc, high, high_inc = bounds.get(field, (float("-inf"), False, float("inf"), False))
            val = float(c.value)

            if c.operator == ">":
                if val > low or (val == low and low_inc):
                    low, low_inc = val, False
            elif c.operator == ">=":
                if val > low or (val == low and not low_inc):
                    low, low_inc = val, True
            elif c.operator == "<":
                if val < high or (val == high and high_inc):
                    high, high_inc = val, False
            elif c.operator == "<=":
                if val < high or (val == high and not high_inc):
                    high, high_inc = val, True
            bounds[field] = (low, low_inc, high, high_inc)

        for field, values in equals.items():
            if len(values) > 1:
                return f"conflicting equality constraints on {field}"
            if field in bounds:
                only = next(iter(values))
                low, low_inc, high, high_inc = bounds[field]
                if only < low or only > high:
                    return f"equality outside bounded interval on {field}"
                if only == low and not low_inc:
                    return f"equality violates lower bound on {field}"
                if only == high and not high_inc:
                    return f"equality violates upper bound on {field}"

        for field, (low, low_inc, high, high_inc) in bounds.items():
            if low > high:
                return f"unsatisfiable numeric bounds for {field}"
            if low == high and not (low_inc and high_inc):
                return f"empty numeric interval for {field}"
        return None
