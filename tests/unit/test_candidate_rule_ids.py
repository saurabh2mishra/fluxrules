"""``fired_rules`` vs ``candidate_rule_ids``: one result type, unambiguous names.

There used to be two ``EvaluationResult`` classes. On the domain one,
``matched_rule_ids`` meant *the rules that fired*; on the engine one it meant
*the rules discovery considered*. Same attribute name, opposite meanings,
depending on which function you happened to call - and both were exported as
``EvaluationResult``.

There is now a single class. ``fired_rules`` is the only field that means "this
matched", ``candidate_rule_ids`` is the discovery prefilter's output, and
``matched_rule_ids`` does not exist at all, so the ambiguity cannot be
reintroduced by accident. These tests pin all three facts.
"""

from __future__ import annotations

import pytest

from fluxrules import PhreakEngine, Rule
from fluxrules.domain.models import EvaluationResult as DomainEvaluationResult
from fluxrules.engine.infrastructure import EvaluationResult

_PARTIAL_MATCH = {
    "type": "and",
    "children": [
        {"type": "condition", "field": "age", "op": ">=", "value": 18},
        {"type": "condition", "field": "country", "op": "==", "value": "US"},
    ],
}


def _engine_with_partial_rule(cls):
    engine = cls()
    engine.load_rules(
        [Rule(name="adult_in_us", condition_dsl=_PARTIAL_MATCH, action="allow")]
    )
    return engine


class TestOneResultType:
    """The engine and domain names must be the same class, not two shapes."""

    def test_engine_and_domain_result_are_the_same_class(self):
        assert EvaluationResult is DomainEvaluationResult

    def test_every_evaluation_path_returns_that_one_type(self):
        from fluxrules import evaluate

        rule = Rule(
            name="adult",
            condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
            action="allow",
        )
        engine = PhreakEngine()
        engine.load_rules([rule])

        from_engine = engine.evaluate({"age": 30})
        from_service = evaluate(rule, {"age": 30})

        assert type(from_engine) is type(from_service) is EvaluationResult
        assert from_engine.fired_rules == from_service.fired_rules


class TestCandidatesAreNotMatches:
    """The two fields genuinely differ, which is why both exist."""

    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_a_rule_that_does_not_match_never_fires(self, cls):
        # ``age`` passes, ``country`` fails, so the rule must not match.
        result = _engine_with_partial_rule(cls).evaluate({"age": 30, "country": "CA"})

        assert result.fired_rules == []
        assert result.actions == []

    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_candidates_are_a_superset_of_fired(self, cls):
        result = _engine_with_partial_rule(cls).evaluate({"age": 30, "country": "CA"})

        assert set(result.fired_rules) <= set(result.candidate_rule_ids)

    def test_the_reference_evaluator_also_keeps_the_invariant(self):
        """`fired ⊆ candidates` must hold on every path, not just engine ones."""
        from fluxrules import evaluate

        rule = Rule(name="adult_in_us", condition_dsl=_PARTIAL_MATCH, action="allow")
        result = evaluate(rule, {"age": 30, "country": "CA"})

        assert result.fired_rules == []
        assert set(result.fired_rules) <= set(result.candidate_rule_ids)


class TestTheAmbiguousNameIsGone:
    """``matched_rule_ids`` meant two different things; it now means nothing."""

    def test_the_attribute_does_not_exist(self):
        result = EvaluationResult(fired_rules=[1])

        assert not hasattr(result, "matched_rule_ids")

    def test_the_constructor_rejects_it(self):
        with pytest.raises(TypeError):
            EvaluationResult(matched_rule_ids=[1])

    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_engine_results_do_not_carry_it(self, cls):
        result = _engine_with_partial_rule(cls).evaluate({"age": 30, "country": "US"})

        assert result.fired_rules != []
        assert not hasattr(result, "matched_rule_ids")
