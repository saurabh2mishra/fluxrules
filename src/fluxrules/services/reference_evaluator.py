"""Reference evaluator implementing the :class:`EnginePort` protocol.

This is the simple, deterministic, dependency-free reference implementation used
as the default engine for :class:`~fluxrules.services.rule_service.RuleService`
and the API service layer. It is intentionally **not** a selectable single-fact
engine (it does not subclass ``BaseEngine`` and has a different call shape).

For rule evaluation, use:
    - ``fluxrules.engine.phreak.PhreakEngine`` (the FluxRules engine)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fluxrules.domain.models import EngineRule, EvaluationResult, Ruleset
from fluxrules.domain.predicates import evaluate_operator
from fluxrules.engine.interfaces import EnginePort

if TYPE_CHECKING:
    from fluxrules.domain.unified_rule import Rule as CanonicalRule

logger = logging.getLogger(__name__)


def _as_engine_rule(rule: EngineRule | CanonicalRule) -> EngineRule:
    """Return the internal engine ``Rule`` for a rule in a ruleset.

    A rule already in engine form is returned unchanged; the canonical
    :class:`~fluxrules.domain.unified_rule.Rule` is converted through its
    ``to_engine_rule`` adapter so the evaluator only ever works with parsed
    conditions and a tuple of actions.
    """
    if isinstance(rule, EngineRule):
        return rule
    return rule.to_engine_rule()


class ReferenceEvaluator(EnginePort):
    """Reference implementation of the :class:`EnginePort` protocol.

    A minimal, deterministic evaluator that:
    - Takes a domain model ``Ruleset`` (not dict-based DSL).
    - Performs simple linear rule matching.
    - Has NO external dependencies.
    - Is used as the default ``RuleService`` engine and for contracts/education.

    For production rule evaluation, use ``PhreakEngine``.
    """

    def evaluate(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
        # Coerce Pydantic / dataclass-like models to plain dict
        if hasattr(facts, "model_dump"):  # Pydantic v2
            facts = facts.model_dump()
        elif hasattr(facts, "dict"):  # Pydantic v1
            facts = facts.dict()
        elif not isinstance(facts, dict):
            raise TypeError(
                f"facts must be a dict or a Pydantic model, got {type(facts).__name__}. "
                "Convert your object to a dict first, e.g. vars(obj) or obj.__dict__."
            )
        matched: list[EngineRule] = []
        trace: list[dict[str, object]] = []
        engine_rules = [_as_engine_rule(rule) for rule in ruleset.rules]
        for rule in sorted(engine_rules, key=lambda item: (item.priority, item.id), reverse=True):
            outcome = self._evaluate_rule(rule, facts)
            trace.append({"rule_id": rule.id, "matched": outcome})
            if outcome:
                matched.append(rule)

        actions = [action for rule in matched for action in rule.actions]
        return EvaluationResult(
            ruleset_group=ruleset.group,
            matched_rule_ids=[rule.id for rule in matched],
            actions=actions,
            trace=trace,
        )

    def _evaluate_rule(self, rule: EngineRule, facts: dict[str, object]) -> bool:
        # ``condition_dsl`` is the canonical representation of rule logic and
        # is preferred whenever it is present. The ``conditions`` tuple is a
        # flat conjunction: evaluating an OR rule from it would silently
        # answer the wrong question.
        dsl = getattr(rule, "condition_dsl", None)
        if dsl:
            from fluxrules.domain.dsl.evaluator import (
                UnsupportedDSLNodeError,
                evaluate_dsl,
            )

            try:
                return evaluate_dsl(dsl, dict(facts))
            except UnsupportedDSLNodeError:
                logger.warning(
                    "Rule %r uses a DSL node the reference evaluator cannot "
                    "represent; declining to match. Use PhreakEngine "
                    "for this rule.",
                    rule.id,
                )
                return False

        if not rule.conditions:
            # A rule with no conditions used to match *every* fact set by
            # vacuous truth: `all()` of nothing is True. That turned a rule
            # whose conditions were lost in translation into one that fired
            # indiscriminately - a wrong answer indistinguishable from a
            # right one. Declining is the honest reading: there is nothing
            # here to match on.
            logger.warning(
                "Rule %r has no conditions in the flat view; declining to "
                "match. If it was authored with OR/NOT or nested logic, "
                "evaluate it via condition_dsl on PhreakEngine.",
                rule.id,
            )
            return False
        for condition in rule.conditions:
            if condition.fact not in facts:
                return False
            if not evaluate_operator(condition.operator, facts[condition.fact], condition.value):
                return False
        return True
