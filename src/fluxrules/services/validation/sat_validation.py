from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fluxrules.services.compilation.rule_compiler import (
    CompiledConstraint,
    CompiledRule,
)
from fluxrules.services.validation.dead_rule_detection import DeadRuleDetector
from fluxrules.services.validation.redundancy_detection import RedundancyDetector

try:
    from pysat.formula import CNF, IDPool  # type: ignore
    from pysat.solvers import Solver  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CNF = None
    IDPool = None
    Solver = None


@dataclass
class SATValidationResult:
    unsatisfiable_rule_ids: list[str]
    subsumed_rules: list[str]
    solver: str


class SATValidator:
    """SAT validation with PySAT integration."""

    def validate(self, compiled_rules: list[CompiledRule]) -> SATValidationResult:
        dead_candidates = DeadRuleDetector().detect(compiled_rules)
        redundant_candidates = RedundancyDetector().detect(compiled_rules)

        if not self._pysat_available():
            safe_dead_ids = {
                d.rule_id
                for d in dead_candidates
                if self._is_conjunctive_rule(
                    next((r for r in compiled_rules if r.id == d.rule_id), None)
                )
            }
            return SATValidationResult(
                unsatisfiable_rule_ids=sorted(safe_dead_ids),
                subsumed_rules=sorted({r.redundant_rule_id for r in redundant_candidates}),
                solver="fallback",
            )

        encoder = _SATRuleEncoder(compiled_rules)
        solver = Solver(name="glucose4", bootstrap_with=encoder.cnf.clauses)
        try:
            unsat_ids = self._confirm_unsat_rules(solver, encoder, dead_candidates)
            subsumed = self._confirm_subsumed_rules(solver, encoder, redundant_candidates)
        finally:
            solver.delete()

        return SATValidationResult(
            unsatisfiable_rule_ids=sorted(unsat_ids),
            subsumed_rules=sorted(subsumed),
            solver="pysat",
        )

    def _confirm_unsat_rules(
        self, solver: Solver, encoder: _SATRuleEncoder, dead_candidates
    ) -> set[str]:
        out: set[str] = set()
        for candidate in dead_candidates:
            root = encoder.rule_roots.get(candidate.rule_id)
            if root is None:
                continue
            if not solver.solve(assumptions=[root]):
                out.add(candidate.rule_id)
        return out

    def _confirm_subsumed_rules(
        self, solver: Solver, encoder: _SATRuleEncoder, redundant_candidates
    ) -> set[str]:
        out: set[str] = set()
        for candidate in redundant_candidates:
            parent = encoder.rule_roots.get(candidate.subsuming_rule_id)
            child = encoder.rule_roots.get(candidate.redundant_rule_id)
            if parent is None or child is None:
                continue
            if not solver.solve(assumptions=[child, -parent]):
                out.add(candidate.redundant_rule_id)
        return out

    @staticmethod
    def _pysat_available() -> bool:
        return CNF is not None and IDPool is not None and Solver is not None

    def _is_conjunctive_rule(self, rule: CompiledRule | None) -> bool:
        if rule is None:
            return False
        condition = rule.source_condition
        if not condition:
            return True
        return self._expr_is_conjunctive(condition)

    def _expr_is_conjunctive(self, node: dict) -> bool:
        ntype = node.get("type")
        if ntype == "condition":
            return True
        if ntype != "group":
            return False
        op = str(node.get("op", "AND")).upper()
        if op != "AND":
            return False
        return all(self._expr_is_conjunctive(child) for child in node.get("children", []))


class _SATRuleEncoder:
    def __init__(self, rules: list[CompiledRule]):
        assert CNF is not None and IDPool is not None
        self.cnf = CNF()
        self.pool = IDPool()
        self.rule_roots: dict[str, int] = {}

        self._encode_predicate_semantics(rules)
        self._encode_rules(rules)

    def _encode_rules(self, rules: list[CompiledRule]) -> None:
        for rule in rules:
            condition = rule.source_condition or self._constraints_to_and_group(rule.constraints)
            root_var = self._encode_expr(condition)
            self.rule_roots[rule.id] = root_var

    def _encode_expr(self, condition: dict) -> int:
        ctype = condition.get("type")
        if ctype == "condition":
            return self._predicate_var(condition)

        if ctype != "group":
            gate = self.pool.id("const:true")
            self.cnf.append([gate])
            return gate

        op = str(condition.get("op", "AND")).upper()
        children = [self._encode_expr(child) for child in condition.get("children", [])]

        if not children:
            gate = self.pool.id(f"empty:{op}:{id(condition)}")
            self.cnf.append([gate])
            return gate

        if op == "NOT":
            gate = self.pool.id(f"not:{id(condition)}")
            child = children[0]
            self.cnf.append([-gate, -child])
            self.cnf.append([gate, child])
            return gate

        gate = self.pool.id(f"{op}:{id(condition)}")
        if op == "AND":
            for child in children:
                self.cnf.append([-gate, child])
            self.cnf.append([gate] + [-c for c in children])
            return gate

        if op == "OR":
            for child in children:
                self.cnf.append([gate, -child])
            self.cnf.append([-gate] + children)
            return gate

        for child in children:
            self.cnf.append([-gate, child])
        self.cnf.append([gate] + [-c for c in children])
        return gate

    def _predicate_var(self, condition: dict) -> int:
        key = self._predicate_key(condition)
        return self.pool.id(key)

    def _predicate_key(self, condition: dict) -> str:
        return f"pred:{condition.get('field')}:{condition.get('op')}:{condition.get('value')!r}"

    def _encode_predicate_semantics(self, rules: list[CompiledRule]) -> None:
        by_field: dict[str, list[CompiledConstraint]] = {}
        for rule in rules:
            for constraint in rule.constraints:
                by_field.setdefault(constraint.field, []).append(constraint)

        for field, constraints in by_field.items():
            normalized = self._dedupe(constraints)
            for i, a in enumerate(normalized):
                iv_a = _numeric_interval(a)
                if iv_a is None:
                    continue
                va = self.pool.id(f"pred:{field}:{a.operator}:{a.value!r}")
                for b in normalized[i + 1 :]:
                    iv_b = _numeric_interval(b)
                    if iv_b is None:
                        continue
                    vb = self.pool.id(f"pred:{field}:{b.operator}:{b.value!r}")
                    if _intervals_disjoint(iv_a, iv_b):
                        self.cnf.append([-va, -vb])
                    elif _contains(iv_a, iv_b):
                        self.cnf.append([-vb, va])
                    elif _contains(iv_b, iv_a):
                        self.cnf.append([-va, vb])

    @staticmethod
    def _constraints_to_and_group(constraints: Iterable[CompiledConstraint]) -> dict:
        return {
            "type": "group",
            "op": "AND",
            "children": [
                {
                    "type": "condition",
                    "field": c.field,
                    "op": c.operator,
                    "value": c.value,
                }
                for c in constraints
            ],
        }

    @staticmethod
    def _dedupe(constraints: list[CompiledConstraint]) -> list[CompiledConstraint]:
        seen = set()
        output: list[CompiledConstraint] = []
        for c in constraints:
            k = (c.field, c.operator, repr(c.value))
            if k in seen:
                continue
            seen.add(k)
            output.append(c)
        return output


def _numeric_interval(
    constraint: CompiledConstraint,
) -> tuple[float, float, bool, bool] | None:
    if not isinstance(constraint.value, (int, float)):
        return None

    value = float(constraint.value)
    op = constraint.operator
    if op == ">":
        return (value, float("inf"), False, False)
    if op == ">=":
        return (value, float("inf"), True, False)
    if op == "<":
        return (float("-inf"), value, False, False)
    if op == "<=":
        return (float("-inf"), value, False, True)
    if op == "==":
        return (value, value, True, True)
    return None


def _intervals_disjoint(
    a: tuple[float, float, bool, bool], b: tuple[float, float, bool, bool]
) -> bool:
    a_low, a_high, _, a_high_inc = a
    b_low, b_high, b_low_inc, _ = b
    if a_high < b_low:
        return True
    if b_high < a_low:
        return True
    if a_high == b_low and not (a_high_inc and b_low_inc):
        return True

    b_low2, b_high2, _, b_high_inc = b
    a_low2, a_high2, a_low_inc, _ = a
    if b_high2 == a_low2 and not (b_high_inc and a_low_inc):
        return True
    return False


def _contains(
    outer: tuple[float, float, bool, bool], inner: tuple[float, float, bool, bool]
) -> bool:
    o_low, o_high, o_low_inc, o_high_inc = outer
    i_low, i_high, i_low_inc, i_high_inc = inner

    left_ok = o_low < i_low or (o_low == i_low and (o_low_inc or not i_low_inc))
    right_ok = o_high > i_high or (o_high == i_high and (o_high_inc or not i_high_inc))
    return left_ok and right_ok
