from __future__ import annotations

from fluxrules.domain.models import EvaluationResult, Rule, Ruleset
from fluxrules.domain.predicates import evaluate_operator


class InterpreterEngine:
    """Deterministic sync engine implementation."""

    def evaluate(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
        matched: list[Rule] = []
        trace: list[dict[str, object]] = []
        for rule in sorted(ruleset.rules, key=lambda item: (item.priority, item.id), reverse=True):
            outcome = self._evaluate_rule(rule, facts)
            trace.append({"rule_id": rule.id, "matched": outcome})
            if outcome:
                matched.append(rule)

        actions = [action for rule in matched for action in rule.actions]
        return EvaluationResult(
            ruleset_id=ruleset.id,
            matched_rule_ids=[rule.id for rule in matched],
            actions=actions,
            trace=trace,
        )

    def _evaluate_rule(self, rule: Rule, facts: dict[str, object]) -> bool:
        for condition in rule.conditions:
            if condition.fact not in facts:
                return False
            if not evaluate_operator(condition.operator, facts[condition.fact], condition.value):
                return False
        return True
