"""``candidate_rule_ids``: naming the discovery output for what it is.

``EvaluationResult.matched_rule_ids`` claimed a result. It holds a *prefilter*
output: the rules discovery considered for a fact, computed before conditions
are fully evaluated. The two are not the same set, and the gap is observable -
discovery can report a rule as a candidate whose conditions later fail, so any
caller that trusted the name over-reported matches.

The field is now ``candidate_rule_ids``; ``fired_rules`` is what actually
matched. These tests pin the distinction so it cannot quietly regress, and pin
the deprecation shim that carries callers across one release.
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import PhreakEngine, Rule
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
        [
            Rule(
                name="adult_in_us",
                condition_dsl=_PARTIAL_MATCH,
                action="allow",
                persist=False,
            )
        ]
    )
    return engine


class TestCandidatesAreNotMatches:
    """The rename is justified only if the two sets genuinely differ."""

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


class TestDeprecationShim:
    """The old name keeps working, loudly, for one release."""

    def test_attribute_still_reads_and_warns(self):
        result = EvaluationResult(candidate_rule_ids=[1, 2])

        with pytest.warns(DeprecationWarning, match="candidate_rule_ids"):
            assert result.matched_rule_ids == [1, 2]

    def test_constructor_keyword_still_works_and_warns(self):
        with pytest.warns(DeprecationWarning, match="candidate_rule_ids"):
            result = EvaluationResult(matched_rule_ids=[7])

        assert result.candidate_rule_ids == [7]

    def test_assignment_still_works_and_warns(self):
        result = EvaluationResult()

        with pytest.warns(DeprecationWarning, match="candidate_rule_ids"):
            result.matched_rule_ids = [3]

        assert result.candidate_rule_ids == [3]

    def test_passing_both_names_is_an_error(self):
        with pytest.raises(TypeError, match="not both"):
            EvaluationResult(matched_rule_ids=[1], candidate_rule_ids=[2])

    def test_positional_construction_is_unaffected(self):
        """The shim wraps ``__init__``; it must not disturb positional args."""
        result = EvaluationResult([1, 2], [1])

        assert result.candidate_rule_ids == [1, 2]
        assert result.fired_rules == [1]

    def test_the_new_name_is_silent(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            result = EvaluationResult(candidate_rule_ids=[1])
            assert result.candidate_rule_ids == [1]


class TestEngineUsesTheNewName:
    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_evaluate_populates_candidate_rule_ids_without_warning(self, cls):
        engine = cls()
        engine.load_rules(
            [
                Rule(
                    name="adult",
                    condition_dsl={
                        "type": "condition",
                        "field": "age",
                        "op": ">=",
                        "value": 18,
                    },
                    action="allow",
                    persist=False,
                )
            ]
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            result = engine.evaluate({"age": 30})

        assert len(result.fired_rules) == 1
        assert result.actions == ["allow"]
        assert set(result.fired_rules) <= set(result.candidate_rule_ids)
