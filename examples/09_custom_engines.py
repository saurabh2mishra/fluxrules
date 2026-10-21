"""Batch 2 example: build a custom engine from BaseEngine and register it.

``BaseEngine`` handles loading rules, discovering candidates and building the
result. A custom engine only decides which candidates fire, in
``_evaluate_rules``.

This one, ``FirstMatchEngine``, fires only the single highest-priority matching
rule, the way a decision table with "first hit" semantics works. After
``register_engine`` it is selectable by name everywhere ``"PHREAK"`` is: through
``get_engine``, the HTTP API and the CLI ``--engine`` option.
"""

from __future__ import annotations

from typing import Any

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.domain.conditions.evaluator import evaluate_conditions
from fluxrules.engine import BaseEngine, get_engine, register_engine
from fluxrules.engine.phreak import PhreakEngine


class FirstMatchEngine(BaseEngine):
    """Fire only the highest-priority rule whose conditions hold."""

    def _evaluate_rules(
        self, rule_ids: list[int], facts: dict[str, Any]
    ) -> tuple[list[int], list[str], dict[int, str]]:
        rules = [self.rule_repository.get(rule_id) for rule_id in rule_ids]
        by_priority = sorted((r for r in rules if r), key=lambda r: -r.priority)
        for rule in by_priority:
            if evaluate_conditions(rule.conditions, facts):
                reason = f"{rule.name} is the highest-priority match"
                return [rule.id], list(rule.actions), {rule.id: reason}
        return [], [], {}


def main() -> None:
    print("=" * 80)
    print("09_custom_engines.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    register_engine("FIRST_MATCH", FirstMatchEngine, override=True)

    rules = build_shared_rules()
    every_match = PhreakEngine()
    first_match = get_engine("FIRST_MATCH")
    for engine in (every_match, first_match):
        engine.load_rules(rules)

    print("\nPriorities: 1002 block=30, 1001 review=20, 1003 step-up=15\n")
    print(f"{'fact':10} {'PhreakEngine (all matches)':32} {'FirstMatchEngine':20}")
    for fact in SHARED_FACTS:
        all_hits = every_match.evaluate(fact)
        first = first_match.evaluate(fact)
        print(f"{fact['fact_id']:10} {all_hits.fired_rules!s:32} {first.fired_rules!s:20}")
        for reason in first.explanations.values():
            print(f"{'':43}{reason}")


if __name__ == "__main__":
    main()
