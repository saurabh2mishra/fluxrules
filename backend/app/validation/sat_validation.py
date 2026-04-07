from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from app.compiler.rule_compiler import CompiledConstraint, CompiledRule
from app.validation.dead_rule_detection import DeadRuleDetector
from app.validation.redundancy_detection import RedundancyDetector

try:
    from pysat.formula import CNF, IDPool  # type: ignore
    from pysat.solvers import Solver  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CNF = None
    IDPool = None
    Solver = None


@dataclass
class SATValidationResult:
    unsatisfiable_rule_ids: List[str]
    subsumed_rules: List[str]
    solver: str


class SATValidator:
    """
    SAT validation with PySAT integration.

    Strategy:
    - Use existing dead/redundancy detectors as pre-filters (fast interval heuristics).
    - Confirm UNSAT/subsumption candidates with PySAT when available.
    - Fall back to deterministic heuristic outputs when PySAT is not available.
    """

    def validate(self, compiled_rules: List[CompiledRule]) -> SATValidationResult:
        dead_candidates = DeadRuleDetector().detect(compiled_rules)
        redundant_candidates = RedundancyDetector().detect(compiled_rules)

        if not self._pysat_available():
            safe_dead_ids = {
                d.rule_id
                for d in dead_candidates
                if self._is_conjunctive_rule(next((r for r in compiled_rules if r.id == d.rule_id), None))
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

    def _confirm_unsat_rules(self, solver: "Solver", encoder: "_SATRuleEncoder", dead_candidates) -> set[str]:
        out: set[str] = set()
        for candidate in dead_candidates:
            root = encoder.rule_roots.get(candidate.rule_id)
            if root is None:
                continue
            if not solver.solve(assumptions=[root]):
                out.add(candidate.rule_id)
        return out

    def _confirm_subsumed_rules(self, solver: "Solver", encoder: "_SATRuleEncoder", redundant_candidates) -> set[str]:
        out: set[str] = set()
        for candidate in redundant_candidates:
            parent = encoder.rule_roots.get(candidate.subsuming_rule_id)
            child = encoder.rule_roots.get(candidate.redundant_rule_id)
            if parent is None or child is None:
                continue
            # child ∧ ¬parent UNSAT => parent subsumes child
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

    def _expr_is_conjunctive(self, node: Dict) -> bool:
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
    def __init__(self, rules: List[CompiledRule]):
        assert CNF is not None and IDPool is not None
        self.cnf = CNF()
        self.pool = IDPool()
        self.rule_roots: Dict[str, int] = {}

        self._encode_predicate_semantics(rules)
        self._encode_rules(rules)

    def _encode_rules(self, rules: List[CompiledRule]) -> None:
        for rule in rules:
            condition = rule.source_condition or self._constraints_to_and_group(rule.constraints)
            root_var = self._encode_expr(condition)
            self.rule_roots[rule.id] = root_var

    def _encode_expr(self, condition: Dict) -> int:
        ctype = condition.get("type")
        if ctype == "condition":
            return self._predicate_var(condition)

        if ctype != "group":
            # unknown condition treated as always true gate
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

        # unsupported group op => conservative AND
        for child in children:
            self.cnf.append([-gate, child])
        self.cnf.append([gate] + [-c for c in children])
        return gate

    def _predicate_var(self, condition: Dict) -> int:
        key = self._predicate_key(condition)
        return self.pool.id(key)

    def _predicate_key(self, condition: Dict) -> str:
        return f"pred:{condition.get('field')}:{condition.get('op')}:{repr(condition.get('value'))}"

    def _encode_predicate_semantics(self, rules: List[CompiledRule]) -> None:
        by_field: Dict[str, List[CompiledConstraint]] = {}
        for rule in rules:
            for constraint in rule.constraints:
                by_field.setdefault(constraint.field, []).append(constraint)

        for field, constraints in by_field.items():
            normalized = self._dedupe(constraints)
            for i, a in enumerate(normalized):
                iv_a = _numeric_interval(a)
                if iv_a is None:
                    continue
                va = self.pool.id(f"pred:{field}:{a.operator}:{repr(a.value)}")
                for b in normalized[i + 1 :]:
                    iv_b = _numeric_interval(b)
                    if iv_b is None:
                        continue
                    vb = self.pool.id(f"pred:{field}:{b.operator}:{repr(b.value)}")
                    if _intervals_disjoint(iv_a, iv_b):
                        self.cnf.append([-va, -vb])
                    elif _contains(iv_a, iv_b):
                        self.cnf.append([-vb, va])
                    elif _contains(iv_b, iv_a):
                        self.cnf.append([-va, vb])

    @staticmethod
    def _constraints_to_and_group(constraints: Iterable[CompiledConstraint]) -> Dict:
        return {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": c.field, "op": c.operator, "value": c.value}
                for c in constraints
            ],
        }

    @staticmethod
    def _dedupe(constraints: List[CompiledConstraint]) -> List[CompiledConstraint]:
        seen = set()
        output: List[CompiledConstraint] = []
        for c in constraints:
            k = (c.field, c.operator, repr(c.value))
            if k in seen:
                continue
            seen.add(k)
            output.append(c)
        return output


def _numeric_interval(constraint: CompiledConstraint) -> Optional[Tuple[float, float, bool, bool]]:
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


def _intervals_disjoint(a: Tuple[float, float, bool, bool], b: Tuple[float, float, bool, bool]) -> bool:
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


def _contains(outer: Tuple[float, float, bool, bool], inner: Tuple[float, float, bool, bool]) -> bool:
    o_low, o_high, o_low_inc, o_high_inc = outer
    i_low, i_high, i_low_inc, i_high_inc = inner

    left_ok = o_low < i_low or (o_low == i_low and (o_low_inc or not i_low_inc))
    right_ok = o_high > i_high or (o_high == i_high and (o_high_inc or not i_high_inc))
    return left_ok and right_ok
